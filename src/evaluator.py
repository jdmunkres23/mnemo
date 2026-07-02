# evaluator.py
# 역할: RAG 평가 파이프라인. Hit Rate/Correctness 계산, LLM-as-judge 채점.
# 연결: CLI로 실행 (python -m evaluator)
# 참고 노트북: notebooks/phase3/03_baseline_rag_notebook.md (섹션 1~3)
#              notebooks/phase3/04_evaluator_notebook.md (섹션 1~3)

from __future__ import annotations

import argparse
import json
import sys
import re
from collections import defaultdict
from pathlib import Path

from src._groq import chat_completion, load_env_key

_FAST_MODEL = "llama-3.1-8b-instant"       # 분류, QA 생성, judge 등 단순 작업
_ANSWER_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"  # RAG 답변 생성


# ── Hit Rate 계산 ─────────────────────────────────────────────────────────────

def compute_hit(source_turns: list[int], included_turns: set[int]) -> float:
    """source_turns 중 included_turns에 있는 비율 (0.0~1.0). (노트북 04 섹션 1 참고)

    source_turns 가 비어 있으면 1.0 반환.
    """
    if not source_turns:
        return 1.0
    
    intersection = set(source_turns) & included_turns
    return len(intersection) / len(source_turns)


# ── key_facts 결정론 채점 ─────────────────────────────────────────────────────

def _norm(s: str) -> str:
    """매칭용 정규화: 소문자 + 콤마/공백 제거."""
    return s.lower().replace(",", "").replace(" ", "")


def keyfact_score(answer: str, key_facts: list[str]) -> float | None:
    """답변에 포함된 key_facts 비율 (0.0~1.0). (노트북 04 섹션 2 참고)

    key_facts 가 없으면 None.
    단일/paraphrase 질문 → Correctness, multihop 질문 → Completeness 역할.
    """
    # _norm() 으로 정규화 후 포함 여부 확인
    if not key_facts:
        return None
    
    count = 0
    for fact in key_facts:
        if _norm(fact) in _norm(answer):
            count += 1
    return count / len(key_facts)


# ── QA 쌍 자동 생성 ───────────────────────────────────────────────────────────

def generate_qa_pairs(context: str, api_key: str, n: int = 5) -> list[dict]:
    """대화 내용을 바탕으로 RAG 평가용 QA 쌍 자동 생성.

    Returns: [{"question": str, "expected": str}, ...]
    조건: 이 대화를 모르면 답할 수 없는 질문만 생성.

    구현 순서:
    1. context[:6000] 를 포함한 프롬프트 구성
    2. _FAST_MODEL 으로 호출 (temperature=0.3, max_tokens=1024)
    3. 응답에서 JSON 배열 파싱 (content.find("[") ... content.rfind("]"))
    4. 예외 발생 시 [] 반환
    """
    try:
        prompt = f"""다음은 AI와의 대화 내용입니다.

{context[:6000]}

위 대화를 모르면 답할 수 없는 질문 {n}개를 JSON 배열로 생성하세요.
일반 지식(Python 문법, 알고리즘 등)은 제외하고, 이 대화에만 있는 구체적인 정보(파일명, 설정값, 결정 사항 등)를 물어보세요.

출력 형식 (JSON 배열만, 설명 없이):
[
  {{"question": "질문", "expected": "정답 (간결하게)"}},
  ...
]"""

        content, _, _ = chat_completion(
            [{"role": "user", "content": prompt}],
            _FAST_MODEL, api_key, temperature=0.3, max_tokens=1024,
        )
        start = content.find("[")
        end = content.rfind("]") + 1
        return json.loads(content[start:end])
    except Exception:
        return []


# ── 평가 모드: baseline ───────────────────────────────────────────────────────

def run_baseline(
    qa_pairs: list[dict],
    session: dict,
    session_dir: Path,
    api_key: str,
    top_k: int = 3,
) -> list[dict]:
    """baseline: 고정 크기 청크 벡터 검색 → top-k 청크 → Groq. (노트북 03 섹션 1~2, 노트북 04 참고)

    Returns: result 목록
    각 result 키: question, expected, answer, usage, hit, type, source_turns,
                  key_facts, keyfact_score

    구현 순서:
    1. build_index(session, session_dir) 로 인덱스 구축 (이미 있으면 재사용)
    2. 각 QA 쌍에 대해:
       a. search(qa["question"], index_path, top_k) → top-k 청크
       b. included_turns: 검색된 청크의 turn_start~turn_end 범위 합집합
       c. compute_hit(qa["source_turns"], included_turns) 로 hit 계산
       d. top-k 청크를 system 프롬프트로 조립
          "아래는 ... 대화 내용입니다. 이 내용을 근거로 답하세요.\n\n" + 청크 텍스트
       e. chat_completion([system, user_question], _ANSWER_MODEL, api_key, max_tokens=512, temperature=0.0)
       f. keyfact_score(answer, qa["key_facts"]) 로 결정론 점수
       g. 결과 dict 구성
    3. 예외 발생 시 오류 메시지를 answer로, keyfact_score를 0.0(key_facts 있을 때)으로 저장
    """
    from src.indexer import build_index, search
    index_path = build_index(session, session_dir)
    
    results = []
    for qa in qa_pairs:
        try:
            chunks = search(qa["question"], index_path, top_k)
            
            included_turns = set()
            for chunk in chunks:
                for t in range(chunk['turn_start'], chunk['turn_end'] + 1):
                    included_turns.add(t)
            
            hit = compute_hit(qa.get('source_turns', []), included_turns)

            chunk_text = "\n\n".join(c['text'] for c in chunks)
            system_content = f'아래는 대화 내용입니다. 이 내용을 근거로 답하세요.\n\n{chunk_text}'

            messages = [
                {'role': 'system', 'content': system_content},
                {'role': 'user', "content": qa['question']},
            ]
            answer, usage, _ = chat_completion(
                messages, _ANSWER_MODEL, api_key, max_tokens=512, temperature=0.0
            )
            kf_score = keyfact_score(answer, qa.get("key_facts", []))

            results.append({
                "question": qa['question'],
                "expected":     qa.get("expected", ""),
                "answer":       answer,
                "usage":        usage,
                "hit":          hit,
                "type":         qa.get("type", "single"),
                "source_turns": qa.get("source_turns", []),
                "key_facts":    qa.get("key_facts", []),
                "keyfact_score": kf_score,
            })

        except Exception as e:
            results.append({
                "question":     qa["question"],
                "expected":     qa.get("expected", ""),
                "answer":       str(e),
                "usage":        {},
                "hit":          0.0,
                "type":         qa.get("type", "single"),
                "source_turns": qa.get("source_turns", []),
                "key_facts":    qa.get("key_facts", []),
                "keyfact_score": 0.0 if qa.get("key_facts") else None,
            })
    return results





# ── 평가 모드: vector ────────────────────────────────────────────────────────

def run_vector(
    qa_pairs: list[dict],
    session: dict,
    session_dir: Path,
    api_key: str,
    top_k: int = 3,
) -> list[dict]:
    """vector: 토픽 기반 청크 + 요약 임베딩 벡터 검색 → top-k 원문 → Groq. (노트북 04-1 참고)

    입력:
      qa_pairs: [{"question": str, "expected": str, "source_turns": [int], "key_facts": [...], "type": str}, ...]
      session: session.json dict
      session_dir: vector_index.json이 저장될 디렉토리
      api_key: Groq API 키

    반환: run_baseline()과 동일 구조
      [{"question", "expected", "answer", "usage", "hit", "type", "source_turns",
        "key_facts", "keyfact_score"}, ...]

    run_baseline()과의 차이:
    - build_index() → build_vector_index() (토픽 기반 인덱스)
    - search()      → search_vector()     (요약 임베딩 검색, 원문 전달)

    구현 순서:
    1. build_vector_index(session, session_dir, api_key) → index_path
    2. 각 QA 쌍에 대해:
       a. search_vector(qa["question"], index_path, top_k) → top-k 토픽
       b. included_turns: 검색된 토픽의 turn_start~turn_end 범위 합집합
       c. compute_hit(qa["source_turns"], included_turns) 로 hit 계산
       d. 토픽 원문(result["text"])을 system 프롬프트로 조립
       e. chat_completion([system, user_question], _ANSWER_MODEL, api_key, max_tokens=512, temperature=0.0)
       f. keyfact_score(answer, qa["key_facts"])
       g. 결과 dict 구성
    3. 예외 발생 시 run_baseline()과 동일한 오류 처리
    """
    from src.indexer import build_vector_index, search_vector
    index_path = build_vector_index(session, session_dir, api_key)
    
    results = []
    for qa in qa_pairs:
        try:
            chunks = search_vector(qa["question"], index_path, top_k)
            
            included_turns = set()
            for chunk in chunks:
                for t in range(chunk['turn_start'], chunk['turn_end'] + 1):
                    included_turns.add(t)
            
            hit = compute_hit(qa.get('source_turns', []), included_turns)

            chunk_text = "\n\n".join(c['text'] for c in chunks)
            system_content = f'아래는 대화 내용입니다. 이 내용을 근거로 답하세요.\n\n{chunk_text}'

            messages = [
                {'role': 'system', 'content': system_content},
                {'role': 'user', "content": qa['question']},
            ]
            answer, usage, _ = chat_completion(
                messages, _ANSWER_MODEL, api_key, max_tokens=512, temperature=0.0
            )
            kf_score = keyfact_score(answer, qa.get("key_facts", []))

            results.append({
                "question": qa['question'],
                "expected":     qa.get("expected", ""),
                "answer":       answer,
                "usage":        usage,
                "hit":          hit,
                "type":         qa.get("type", "single"),
                "source_turns": qa.get("source_turns", []),
                "key_facts":    qa.get("key_facts", []),
                "keyfact_score": kf_score,
            })

        except Exception as e:
            results.append({
                "question":     qa["question"],
                "expected":     qa.get("expected", ""),
                "answer":       str(e),
                "usage":        {},
                "hit":          0.0,
                "type":         qa.get("type", "single"),
                "source_turns": qa.get("source_turns", []),
                "key_facts":    qa.get("key_facts", []),
                "keyfact_score": 0.0 if qa.get("key_facts") else None,
            })
    return results


# ── LLM-as-judge ─────────────────────────────────────────────────────────────

def build_judge_prompt(question: str, expected: str, answer: str) -> str:
    """LLM-as-judge 프롬프트를 생성한다.
    
    포함 요소:
    - 질문, 기대 답변, 실제 답변
    - 채점 기준 (핵심 정보 포함 여부, 사실 오류 감점)
    - "숫자만 출력" 지시
    """
    prompt = f"""다음 질문에 대한 답변을 평가하세요.

    질문: {question}
    기대 답변: {expected}
    실제 답변: {answer}

    평가 기준:
    - 기대 답변의 핵심 정보가 포함됐는지 (0~10점)
    - 사실과 다른 내용이 있으면 감점
    숫자만 출력하세요 (예: 7)
    """
    return prompt

def parse_judge_score(content: str) -> float:
    """LLM 출력에서 0~10 점수를 파싱한다.
    
    파싱 실패 시 0.0 반환.
    0~10 범위를 벗어나면 클리핑.
    
    힌트:
    - content.strip().split()[0].rstrip(".")
    - float() + try/except
    - max(0.0, min(10.0, score))
    """
    cleaned = content.strip().split()[0].rstrip(".")
    try:
        score = float(cleaned)
    except ValueError:
        return 0.0
    return max(0.0, min(10.0, score))


def judge_answers(results: list[dict], api_key: str) -> list[dict]:
    """각 답변을 0~10점으로 채점. (노트북 04 섹션 3 참고)

    Returns: results + score 필드 추가된 목록
    프롬프트: 질문 + 기대 답변 + 실제 답변 → "숫자만 출력" 지시
    모델: _FAST_MODEL (max_tokens=10, temperature=0.0)
    예외 발생 시 score=0.0
    """
    for r in results:
        try:
            prompt = build_judge_prompt(r["question"], r["expected"], r["answer"])
            content, _, _ = chat_completion(
                [{'role': 'user', 'content': prompt}],
                _FAST_MODEL, api_key, max_tokens=10, temperature=0.0
            )

            r['score'] = parse_judge_score(content)

        except Exception:
            r['score'] = 0.0

    return results


# ── 결과 출력 ─────────────────────────────────────────────────────────────────

def print_results(mode: str, judged: list[dict], no_judge: bool, truncated: bool = False):
    """평가 결과를 터미널에 출력한다."""
    # 출력 항목:
    # - 모드, QA 수, truncated 여부
    # - 평균 토큰, 평균 Hit Rate
    # - 평균 key_facts 점수 (있을 때) + hit=0 / hit>0 분리 (정답 누출 탐지)
    # - 평균 Answer Score (no_judge=False 일 때)
    # - 타입별 상세 (single/paraphrase/multihop 혼재 시)
    # - 개별 QA 결과 (질문 45자, 답변 80자, score/keyfact/hit/tokens)
    print()
    print("=" * 60)
    print(f"  모드: {mode}" + (" (truncated)" if truncated else ""))
    print(f"  QA 수: {len(judged)}")

    total_tokens = sum(r.get("usage", {}).get("total_tokens", 0) for r in judged)
    avg_tokens = total_tokens / len(judged) if judged else 0
    print(f"  평균 토큰: {avg_tokens:.0f}")

    hits = [r.get("hit", 1.0) for r in judged]
    avg_hit = sum(hits) / len(hits) if hits else 0.0
    print(f"  평균 Hit Rate: {avg_hit:.2f}")

    kf_all = [r["keyfact_score"] for r in judged if r.get("keyfact_score") is not None]
    if kf_all:
        print(f"  평균 key_facts 점수: {sum(kf_all) / len(kf_all) * 10:.1f} / 10  ({len(kf_all)}개 항목)")
        kf_zero = [r["keyfact_score"] for r in judged
                   if r.get("keyfact_score") is not None and r.get("hit", 0) == 0]
        kf_nonzero = [r["keyfact_score"] for r in judged
                      if r.get("keyfact_score") is not None and r.get("hit", 0) > 0]
        if kf_zero:
            print(f"    └ hit=0 항목 평균: {sum(kf_zero) / len(kf_zero) * 10:.1f}"
                  f"  (낮아야 정상 · 높으면 정답 누출 의심)")
        if kf_nonzero:
            print(f"    └ hit>0 항목 평균: {sum(kf_nonzero) / len(kf_nonzero) * 10:.1f}")

    if not no_judge:
        avg_score = sum(r.get("score", 0) for r in judged) / len(judged) if judged else 0
        print(f"  평균 Answer Score(LLM): {avg_score:.2f} / 10")

    by_type: dict[str, list] = defaultdict(list)
    for r in judged:
        by_type[r.get("type", "single")].append(r)

    if any(k != "single" for k in by_type):
        print("\n  타입별:")
        for qtype in ["single", "paraphrase", "multihop"]:
            items = by_type.get(qtype)
            if not items:
                continue
            avg_hit_t = sum(r.get("hit", 1.0) for r in items) / len(items)
            line = f"    {qtype:12s} ({len(items)}개)  hit {avg_hit_t:.2f}"
            kf_t = [r["keyfact_score"] for r in items if r.get("keyfact_score") is not None]
            if kf_t:
                line += f"  keyfact {sum(kf_t) / len(kf_t) * 10:.1f}"
            if not no_judge:
                avg_score_t = sum(r.get("score", 0) for r in items) / len(items)
                line += f"  score {avg_score_t:.1f}"
            print(line)

    print("-" * 60)
    for r in judged:
        tokens = r.get("usage", {}).get("total_tokens", "?")
        print(f"[{r.get('type', '?'):10s}] Q: {r['question'][:45]}")
        print(f"  A: {r['answer'][:80].replace(chr(10), ' ')}")
        kf = r.get("keyfact_score")
        kf_str = f"keyfact {kf * 10:.0f}" if kf is not None else "keyfact -"
        hit_str = f"hit {r.get('hit', 0.0):.1f}"
        if not no_judge:
            print(f"  score {r.get('score', '?'):.1f}  {kf_str}  {hit_str}  tokens {tokens}")
        else:
            print(f"  {kf_str}  {hit_str}  tokens {tokens}")
        print()
    print("=" * 60)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="RAG 평가 파이프라인")
    ap.add_argument("--session", required=False, default=None, type=Path, metavar="PATH",
                    help="session.json 파일 경로 (--load-judgments 단독 사용 시 생략 가능)")
    ap.add_argument("--modes", default="baseline", metavar="MODES",
                    help="평가 모드 (쉼표 구분, 현재: baseline)")
    ap.add_argument("--qa-pairs", type=Path, default=None, metavar="PATH",
                    help="QA 쌍 JSON 파일 (없으면 자동 생성)")
    ap.add_argument("--max-chars", type=int, default=0, metavar="N",
                    help="청크 크기 글자 수 (0=전체를 하나의 청크로, 기본값: CHUNK_SIZE=2000)")
    ap.add_argument("--no-judge", action="store_true",
                    help="LLM 판정 없이 답변만 생성")
    ap.add_argument("--load-judgments", type=Path, default=None, metavar="PATH",
                    help="기존 판정 JSON으로 채점만 재실행")
    ap.add_argument("--output", type=Path, default=None, metavar="PATH",
                    help="결과 JSON 저장 경로")
    args = ap.parse_args()

    # TODO: 구현
    # 1. session.json 로드 + api_key 확인
    # 2. qa_pairs 로드 또는 generate_qa_pairs():
    #    from src.indexer import chunk_session
    #    chunks = chunk_session(session)
    #    context = "\n\n---\n\n".join(c["text"] for c in chunks)[:6000]
    #    qa_pairs = generate_qa_pairs(context, api_key)
    # 3. session_dir = session.json 경로의 부모 / session_id
    # 4. modes 루프:
    #    - "baseline" → run_baseline()
    #    - 그 외 → "아직 구현되지 않은 모드" 출력
    # 5. no_judge=False 이면 judge_answers()
    # 6. print_results()
    # 7. output 지정 시 JSON 저장

    modes = args.modes.split(",")
    all_results = {}
    if args.output and args.output.exists():
        all_results = json.loads(args.output.read_text(encoding="utf-8"))

    # --load-judgments 단독: 기존 결과 파일을 바로 출력
    if args.load_judgments:
        saved = json.loads(args.load_judgments.read_text(encoding="utf-8"))
        for mode in modes:
            judged = saved.get(mode, [])
            if not judged:
                print(f"  [{mode}] 결과 없음", file=sys.stderr)
                continue
            print_results(mode, judged, args.no_judge)
            all_results[mode] = judged
        if args.output:
            args.output.write_text(json.dumps(all_results, ensure_ascii=False, indent=2), encoding="utf-8")
        return

    # 1. session.json 로드 + api_key 확인
    if not args.session:
        print("오류: --session 또는 --load-judgments 중 하나가 필요합니다.", file=sys.stderr)
        raise SystemExit(1)
    session = json.loads(args.session.read_text(encoding="utf-8"))
    api_key = load_env_key()

    # 2. QA 쌍 로드 또는 자동 생성
    if args.qa_pairs:
        qa_pairs = json.loads(args.qa_pairs.read_text(encoding="utf-8"))
    else:
        from src.indexer import chunk_session
        chunks = chunk_session(session)
        context = "\n\n---\n\n".join(c["text"] for c in chunks)[:6000]
        qa_pairs = generate_qa_pairs(context, api_key)

    # 3. session_dir
    session_id = session["session_id"]
    session_dir = args.session.parent / session_id

    # 4. modes 루프
    for mode in modes:
        if mode == "baseline":
            results = run_baseline(qa_pairs, session, session_dir, api_key)
        elif mode == "vector":
            results = run_vector(qa_pairs, session, session_dir, api_key)
        else:
            print(f"아직 구현되지 않은 모드: {mode}")
            continue

        # 5. judge
        if not args.no_judge:
            judged = judge_answers(results, api_key)
        else:
            judged = results

        # 6. 결과 출력
        print_results(mode, judged, args.no_judge)
        all_results[mode] = judged

    # 7. output 저장
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(all_results, ensure_ascii=False, indent=2), encoding="utf-8")



if __name__ == "__main__":
    main()
