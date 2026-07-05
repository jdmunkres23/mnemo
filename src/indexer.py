# indexer.py
# 역할: 세션 텍스트를 고정 크기 청크로 분할, fastembed로 임베딩, 코사인 유사도 검색.
# 연결: server.py의 POST /api/index-session, POST /api/query-semantic
# 참고 노트북: notebooks/phase3/02_embedding.ipynb (섹션 1~3)
#              notebooks/phase3/03_baseline_rag.ipynb (섹션 1~2)

from __future__ import annotations
import json
import math
from pathlib import Path

EMBEDDING_MODEL = "intfloat/multilingual-e5-large"
CHUNK_SIZE = 2000  # 기본 청크 크기 (글자 수)

_model = None  # 지연 초기화 (첫 embed 호출 시)


_CACHE_DIR = Path.home() / ".cache" / "fastembed"

def _get_model():
    """fastembed TextEmbedding 인스턴스 반환 (싱글턴)."""
    global _model
    if _model is None:
        from fastembed import TextEmbedding
        _model = TextEmbedding(EMBEDDING_MODEL, cache_dir=str(_CACHE_DIR))
    return _model


def embed_texts(texts: list[str]) -> list[list[float]]:
    """텍스트 목록을 벡터 목록으로 변환한다. (노트북 02 섹션 1 참고)

    반환: [[float, ...], ...] — 각 텍스트의 1024차원 벡터
    """
    # list(model.embed(texts)) → numpy array 리스트 → 각 원소를 list()로 변환
    return list(_get_model().embed(texts))


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """두 벡터의 코사인 유사도를 반환한다. (노트북 02 섹션 2 참고)

    반환: -1.0 ~ 1.0 (norm이 0이면 0.0)
    """
    # dot(a, b) / (norm(a) * norm(b))
    dot = sum(ai * bi for ai, bi in zip(a,b))
    norm_a = math.sqrt(sum(ai**2 for ai in a))
    norm_b = math.sqrt(sum(bi**2 for bi in b))
    if norm_a != 0 and norm_b != 0:
        return dot / (norm_a * norm_b)
    else:
        return 0.0

def format_turn(turn: dict) -> str | None:
    """turn 하나에서 text 블록을 추출해 "[사용자]\n텍스트" 형식으로 반환한다.
    
    text 블록이 없으면 None 반환.
    여러 text 블록은 줄바꿈으로 합친다.
    
    힌트:
    - role_label = "사용자" if turn["role"] == "user" else "AI"
    - b["type"] == "text" 인 블록만 필터링
    - f"[{role_label}]\n{text}"
    """
    role_label = "사용자" if turn['role'] == 'user' else "AI"
    text = "\n".join(b['text'] for b in turn['blocks'] if b ['type'] == 'text')
    if text:
        return f'[{role_label}]\n{text}'
    else:
        return None

def chunk_session(session: dict, chunk_size: int = CHUNK_SIZE) -> list[dict]:
    """session.json의 turns를 고정 크기 청크로 분할한다. (노트북 02 섹션 3 참고)

    반환: [{"text": str, "turn_start": int, "turn_end": int}, ...]
    분할: turns를 [사용자]/[AI] 포맷으로 이어붙이다 chunk_size 초과 시 새 청크.
    text 블록만 포함 (thinking, tool_use 등 제외).
    chunk_size=0 이면 전체를 단일 청크로.
    """
    _SEP = "\n\n---\n\n"
    # 1. turns 순회 → text 블록만 추출 → "[사용자]\n텍스트" 또는 "[AI]\n텍스트"
    # 2. parts 누적, chunk_size 초과 시 현재 parts 저장 후 새 청크 시작
    # 3. 청크가 비어있으면 크기 초과해도 일단 추가 (빈 청크 방지)
    # 4. 루프 끝에 마지막 청크 저장
    chunks = []
    parts = []
    turn_start = 0
    current_len = 0

    for i, turn in enumerate(session['turns']):
        text = format_turn(turn)
        if text is None:
            continue
        added_len = len(text) + (len(_SEP) if parts else 0)
        if parts and chunk_size!= 0 and current_len + added_len > chunk_size:
            chunks.append({
                'text': _SEP.join(parts),
                'turn_start': turn_start,
                'turn_end': i
            })
            current_len = 0
            turn_start = i
            parts = []
        parts.append(text)
        current_len += added_len

    if parts:
        chunks.append({
            'text': _SEP.join(parts),
            'turn_start': turn_start,
            'turn_end': len(session['turns']) - 1
        })

    return chunks

def attach_embeddings(chunks: list[dict], embeddings: list[list[float]]) -> list[dict]:
    """각 청크 딕셔너리에 embedding 필드를 추가해 반환한다.
    
    반환: [{"text": str, "embedding": list[float], "turn_start": int, "turn_end": int}, ...]
    힌트: zip(chunks, embeddings) 로 순서 맞춰 결합
    """
    return [{**c, "embedding": emb} for c, emb in zip(chunks, embeddings)]

def build_index(session: dict, session_dir: Path, chunk_size: int = CHUNK_SIZE) -> Path:
    """세션을 청크로 분할 후 임베딩해 session_index.json으로 저장한다. (노트북 03 섹션 1 참고)

    저장 경로: session_dir / "session_index.json"
    저장 형식: [{"text": str, "embedding": list[float], "turn_start": int, "turn_end": int}, ...]
    반환: session_index.json 경로
    인덱스가 이미 존재하면 재계산 없이 경로만 반환.
    """
    # 1. index_path = session_dir / "session_index.json"
    # 2. index_path.exists() → 바로 반환
    # 3. session_dir.mkdir(parents=True, exist_ok=True)
    # 4. chunk_session(session, chunk_size) → chunks
    # 5. embed_texts([c["text"] for c in chunks]) → embeddings
    # 6. 각 chunk에 embedding 추가 → json 저장
    index_path = session_dir / "session_index.json"
    if index_path.exists():
        return index_path
    
    session_dir.mkdir(parents=True, exist_ok=True)
    chunk = chunk_session(session, chunk_size=chunk_size)
    embed = [e.tolist() for e in embed_texts([c['text'] for c in chunk])]
    data = attach_embeddings(chunk, embed)
    index_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding='utf-8'
    )
    return index_path



def rank_chunks(query_vec: list[float], index_data: list[dict]) -> list[dict]:
    """각 청크에 score를 추가하고 코사인 유사도 내림차순으로 정렬해 반환한다.
    
    반환: [{"text": str, "score": float, "turn_start": int, "turn_end": int}, ...]
    힌트:
    - cosine_similarity(query_vec, c["embedding"]) for c in index_data
    - {**c, "score": score} 로 기존 필드 유지하며 score 추가
    - sorted(..., key=lambda x: x["score"], reverse=True)
    """
    score = [cosine_similarity(query_vec, c['embedding']) for c in index_data]
    return sorted([{**c, "score": score} for score, c in zip(score, index_data)], key=lambda x: x['score'], reverse=True)

def search(query: str, index_path: Path, top_k: int = 3) -> list[dict]:
    """코사인 유사도로 상위 top_k 청크를 검색한다. (노트북 03 섹션 2 참고)

    반환: [{"text": str, "score": float, "turn_start": int, "turn_end": int}, ...]
          유사도 내림차순 정렬.
    인덱스 파일이 없으면 [] 반환.
    """
    # 1. index_path 없으면 [] 반환
    # 2. 인덱스 로드
    # 3. embed_texts([query])[0] → query_vec
    # 4. 각 청크와 cosine_similarity 계산 → score 추가
    # 5. score 내림차순 정렬 → [:top_k] 반환
    if not index_path.exists():
        return []
    data = json.loads(index_path.read_text(encoding='utf-8'))
    query_embed = embed_texts([query])[0]
    return rank_chunks(query_embed, data)[:top_k]


# ── Phase 4: 토픽 기반 벡터 인덱스 ───────────────────────────────────────────

VECTOR_INDEX_FILENAME = "vector_index.json"

_FAST_MODEL = "llama-3.1-8b-instant"
_BOUNDARY_MODEL = "llama-3.3-70b-versatile"
_BOUNDARY_N_RUNS = 5
_BOUNDARY_THRESHOLD = 0.5
_SUMMARY_MODEL = _FAST_MODEL           # 긴 메시지 요약용 (검증되면 이 줄만 교체)
_LONG_MESSAGE_THRESHOLD = 300          # 이 길이(자) 넘는 사용자 메시지만 요약
_MAX_MESSAGES_PER_WINDOW = 30          # 이 개수 넘으면 윈도우로 나눠 1단계 처리

from src._groq import chat_completion, load_env_key
from src.indexer import embed_texts, cosine_similarity, format_turn


def _uniform_boundaries(session: dict, n_topics: int = 5) -> list[int]:
    """균등 분할 fallback: 사용자 turns를 n_topics 그룹으로 나누는 경계 인덱스 반환.

    입력:
      session: {"turns": [...], ...}
      n_topics: 목표 그룹 수 (기본값 5)

    반환:
      [int, ...] — 경계 turn 인덱스 목록
      예: 사용자 turn이 [0, 2, 4, 6, 8, 10], n_topics=3 → [4, 8]
    """
    turn = session['turns']
    user_idxs = [i for i, t in enumerate(turn) if t['role'] == 'user']
    step = max(1, len(user_idxs) // n_topics)
    boundaries = [user_idxs[step * k] for k in range(1, n_topics) if step * k < len(user_idxs)]
    return boundaries

def _optimal_1d_partition(values: list[int], k: int) -> list[list[int]]:
    """정렬된 1차원 값을 SSE(그룹 내 편차 제곱합) 최소가 되도록 k개의 연속 구간으로 나눈다.

    1차원에서는 최적 분할이 항상 정렬 순서상 연속 구간이므로, 동적계획법으로 O(n^2*k)에
    정확한 최적해를 구한다 (절단점 조합 전수조사는 n·k가 커지면 조합이 폭발함).
    """
    values = sorted(values)
    n = len(values)
    if k <= 1:
        return [values]
    if n <= k:
        return [[v] for v in values]  # 값 개수가 그룹 수 이하 -> 값마다 자기 그룹

    prefix = [0.0] * (n + 1)
    prefix_sq = [0.0] * (n + 1)
    for i, v in enumerate(values):
        prefix[i + 1] = prefix[i] + v
        prefix_sq[i + 1] = prefix_sq[i] + v * v

    def cost(i, j):
        if j <= i:
            return 0.0
        s = prefix[j] - prefix[i]
        sq = prefix_sq[j] - prefix_sq[i]
        cnt = j - i
        return sq - (s * s) / cnt

    INF = float("inf")
    dp = [[INF] * (n + 1) for _ in range(k + 1)]
    dp[0][0] = 0.0
    split_point = [[0] * (n + 1) for _ in range(k + 1)]

    for g in range(1, k + 1):
        for j in range(g, n + 1):
            best_cost, best_i = INF, g - 1
            for i in range(g - 1, j):
                c = dp[g - 1][i] + cost(i, j)
                if c < best_cost:
                    best_cost, best_i = c, i
            dp[g][j] = best_cost
            split_point[g][j] = best_i

    bounds = [n]
    g, j = k, n
    while g > 0:
        i = split_point[g][j]
        bounds.append(i)
        j = i
        g -= 1
    bounds.reverse()

    return [values[bounds[t]:bounds[t + 1]] for t in range(k)]


def _determine_boundaries(per_run_boundaries: list[list[int]], valid_idxs: list[int],
                           threshold: float = _BOUNDARY_THRESHOLD) -> list[int]:
    """run별로 낸 경계 개수의 최빈값을 진짜 경계 개수(k)로 채택하고, 그 최빈값 비율이
    threshold 이상일 때만 신뢰한다. 전체 값을 _optimal_1d_partition으로 k개 그룹으로 나누고,
    각 그룹의 중앙값을 가장 가까운 유효 인덱스로 스냅해 확정 경계로 반환한다.

    (배치 크기에 따라 reduction 연산 순서가 달라져 temperature=0에도 완전히 결정적이지
    않은 Groq 추론 특성 때문에, 단일 호출 대신 여러 번 호출해 다수결로 안정성을 확보한다.)
    """
    import statistics
    from collections import Counter

    n_runs = len(per_run_boundaries)
    counts_per_run = [len(set(b)) for b in per_run_boundaries]
    mode_k, mode_freq = Counter(counts_per_run).most_common(1)[0]

    if mode_k == 0 or mode_freq / n_runs < threshold:
        return []

    pooled = [v for boundaries in per_run_boundaries for v in set(boundaries)]
    groups = _optimal_1d_partition(pooled, mode_k)

    confirmed = []
    for g in groups:
        if not g:
            continue
        med = statistics.median(g)
        rep = min(valid_idxs, key=lambda x: (abs(x - med), x))
        confirmed.append(rep)

    return sorted(set(confirmed))


def _vote_boundaries(prompt: str, turns_len: int, user_idxs_set: set[int], api_key: str,
                      exclude: set[int] = frozenset()) -> list[int]:
    """같은 프롬프트를 _BOUNDARY_N_RUNS번 호출하고 _determine_boundaries()로 확정 경계를 반환한다.
    exclude: 후보에서 제외할 인덱스 (예: 세그먼트 자기 자신의 시작 turn)."""
    import re

    valid_idxs = sorted(user_idxs_set - set(exclude))
    per_run_boundaries = []
    for _ in range(_BOUNDARY_N_RUNS):
        content, usage, _ = chat_completion(
            [{'role': 'user', 'content': prompt}],
            _BOUNDARY_MODEL, api_key, max_tokens=300, temperature=0.0
        )
        nums = re.findall(r'\d+', content)
        boundaries = [int(n) for n in nums]
        boundaries = [b for b in boundaries if 1 <= b <= turns_len - 1 and b in user_idxs_set and b not in exclude]
        per_run_boundaries.append(boundaries)

    return _determine_boundaries(per_run_boundaries, valid_idxs)


def _summarize_if_long(text: str, api_key: str) -> str:
    """길이가 _LONG_MESSAGE_THRESHOLD를 넘는 사용자 메시지를 1~2문장으로 요약한다.
    브레인스토밍처럼 긴 메시지 하나가 다른 메시지 대비 과도하게 큰 신호가 되는 걸 막기 위함.
    짧으면 그대로 반환. Groq 호출 실패 시 text[:200] fallback."""
    if len(text) <= _LONG_MESSAGE_THRESHOLD:
        return text

    summary_prompt = f"""다음 메시지를 핵심 내용만 남겨 1~2문장으로 요약하세요.
고유명사, 경로, 설정값, 에러명은 원문 그대로 포함하세요.

{text[:4000]}

요약:"""
    try:
        content, usage, _ = chat_completion(
            [{'role': 'user', 'content': summary_prompt}],
            _SUMMARY_MODEL, api_key, max_tokens=150, temperature=0.0
        )
        return content
    except Exception:
        return text[:200]


def _coarse_prompt(prompt_input: str) -> str:
    """1단계(거친 분류)용 프롬프트를 만든다. 전체 대화든 윈도우 하나든 동일하게 쓴다."""
    return f"""아래는 대화에서 사용자가 보낸 메시지 목록입니다 (형식: turn인덱스: 메시지).
주제가 크게 바뀌는 경계 직전의 turn 인덱스를 JSON 배열로 반환하세요.
경계가 없으면 [] 를 반환하세요.
숫자 배열만 출력, 설명 없이.

{prompt_input}

경계 인덱스:"""


def _windowed_coarse_boundaries(user_msgs: list[tuple[int, str]], turns: list[dict], api_key: str) -> list[int]:
    """사용자 메시지가 _MAX_MESSAGES_PER_WINDOW개를 넘는 대화의 1단계 처리.

    _MAX_MESSAGES_PER_WINDOW개씩 윈도우로 나눠 각 윈도우 안에서 독립적으로 거친 분류를 하고,
    윈도우 이음매(서로 다른 호출이라 원래 이어져 있어도 모르는 인위적 절단)마다
    앞뒤 세그먼트의 임베딩 유사도를 확인해 병합 여부를 정한다.

    임계값은 고정값이 아니라 "이 대화 안에서 실제로 확인된 전환(각 윈도우 내부 세그먼트 간
    유사도)"의 최댓값을 그 대화 자신의 기준으로 삼는다 — 대화마다 문체·언어·주제 밀도가 달라
    절대적인 유사도 수준이 다를 수 있어서, 세션마다 유동적으로 정해야 다른 대화에 일반화된다.
    이음매 유사도가 이 기준보다 높으면(=이 대화 기준으로 "진짜 전환"치고는 덜 떨어짐) 병합.
    """
    windows = [user_msgs[i:i + _MAX_MESSAGES_PER_WINDOW]
               for i in range(0, len(user_msgs), _MAX_MESSAGES_PER_WINDOW)]

    window_ranges = []
    for i in range(len(windows)):
        start = windows[i][0][0]
        end = windows[i + 1][0][0] if i + 1 < len(windows) else len(turns)
        window_ranges.append((start, end))

    per_window_internal = []
    for w in windows:
        w_idxs = set(i for i, _ in w)
        prompt_input = "\n".join(f"{i}: {text}" for i, text in w)
        internal = _vote_boundaries(_coarse_prompt(prompt_input), len(turns), w_idxs, api_key)
        per_window_internal.append(internal)

    # 이 대화 안에서 실제로 확인된 전환들의 유사도 분포(윈도우 내부 인접 세그먼트끼리)
    reference_sims = []
    for (w_start, w_end), internal in zip(window_ranges, per_window_internal):
        bounds = [w_start] + internal + [w_end]
        seg_texts = [format_turns_as_text(turns[bounds[i]:bounds[i + 1]]) for i in range(len(bounds) - 1)]
        seg_texts = [t for t in seg_texts if t]
        if len(seg_texts) >= 2:
            embs = embed_texts(seg_texts)
            for i in range(len(embs) - 1):
                reference_sims.append(cosine_similarity(embs[i], embs[i + 1]))

    merge_threshold = max(reference_sims) if reference_sims else None

    boundaries = []
    for internal in per_window_internal:
        boundaries.extend(internal)

    for i in range(len(windows) - 1):
        seam = window_ranges[i + 1][0]
        prev_start = per_window_internal[i][-1] if per_window_internal[i] else window_ranges[i][0]
        next_end = per_window_internal[i + 1][0] if per_window_internal[i + 1] else window_ranges[i + 1][1]

        text_before = format_turns_as_text(turns[prev_start:seam])
        text_after = format_turns_as_text(turns[seam:next_end])

        should_merge = False
        if text_before and text_after and merge_threshold is not None:
            embs = embed_texts([text_before, text_after])
            seam_sim = cosine_similarity(embs[0], embs[1])
            should_merge = seam_sim > merge_threshold

        if not should_merge:
            boundaries.append(seam)

    return sorted(set(boundaries))


def detect_topic_boundaries(session: dict, api_key: str) -> list[int]:
    """사용자 메시지에서 토픽 경계 인덱스를 탐지한다. (노트북 04-1 섹션 1, 안정성 조사 참고)

    입력:
      session: {"turns": [{"role": "user"|"assistant", "blocks": [...]}, ...], ...}
      api_key: Groq API 키

    반환:
      [int, ...] — 경계가 되는 turn 인덱스 목록 (0-based, session["turns"] 기준)
      예: [4, 9]  → turns 0~3 / 4~8 / 9~끝 세 그룹

    계층적 분류(1단계: 전체 대화 거친 분류 → 2단계: 구간별 세분화) + 자기일관성 다수결로 탐지한다.
    각 단계는 _BOUNDARY_N_RUNS번 호출해 _determine_boundaries()로 확정한다.
    llama-3.1-8b-instant는 이 판단에서 응답이 재현되지 않아(10회 중 0회 일치) 배제하고
    llama-3.3-70b-versatile로 교체함 — 세션당 1회만 호출되는 저빈도 작업이라 호출 수가
    늘어도 비용 부담이 낮다.

    사용자 메시지가 길면(_LONG_MESSAGE_THRESHOLD 초과) 요약해서 프롬프트에 넣고,
    메시지 개수가 많으면(_MAX_MESSAGES_PER_WINDOW 초과) 1단계를 윈도우로 나눠 처리한다
    (_windowed_coarse_boundaries 참고).
    Groq 호출 실패 시 _uniform_boundaries(session) fallback.
    """
    try:
        turns = session['turns']
        user_msgs = []
        for i, turn in enumerate(turns):
            if turn['role'] == 'user':
                text = " ".join(b['text'] for b in turn['blocks'] if b['type'] == 'text')
                text = _summarize_if_long(text, api_key)
                user_msgs.append((i, text))

        if len(user_msgs) <= 1:
            return []

        user_idxs_set = set(i for i, _ in user_msgs)

        # 1단계: 거친 분류
        if len(user_msgs) <= _MAX_MESSAGES_PER_WINDOW:
            prompt_input = "\n".join(f"{i}: {text}" for i, text in user_msgs)
            coarse_boundaries = _vote_boundaries(_coarse_prompt(prompt_input), len(turns), user_idxs_set, api_key)
        else:
            coarse_boundaries = _windowed_coarse_boundaries(user_msgs, turns, api_key)

        # 2단계: 세그먼트별 세분화
        starts = [0] + coarse_boundaries
        ends = coarse_boundaries + [len(turns)]
        final_boundaries = list(coarse_boundaries)

        for seg_start, seg_end in zip(starts, ends):
            seg_user_msgs = [(i, t) for i, t in user_msgs if seg_start <= i < seg_end]
            if len(seg_user_msgs) <= 2:
                continue

            seg_prompt_input = "\n".join(f"{i}: {text}" for i, text in seg_user_msgs)
            split_prompt = f"""아래는 어떤 대화의 한 구간입니다. 이 구간은 이미 하나의 큰 주제로 묶여 있습니다.
사용자가 보낸 메시지 목록입니다 (형식: turn인덱스: 메시지).

이 구간 안에서 다시 주제가 크게 바뀌는 지점이 있다면, 그 경계 직전의 turn 인덱스를 JSON 배열로 반환하세요.
이 구간을 더 나눌 필요가 없다면(하나의 흐름으로 자연스럽게 이어진다면) [] 를 반환하세요.
숫자 배열만 출력, 설명 없이.

{seg_prompt_input}

경계 인덱스:"""

            seg_user_idxs = set(i for i, _ in seg_user_msgs)
            sub_boundaries = _vote_boundaries(
                split_prompt, len(turns), seg_user_idxs, api_key, exclude={seg_start}
            )
            final_boundaries.extend(sub_boundaries)

        return sorted(set(final_boundaries))
    except Exception:
        return _uniform_boundaries(session)

def format_turns_as_text(turns: list[dict]) -> str | None:
    """turn 목록을 "[사용자]/[AI]" 형식 텍스트로 변환한다.
    
    입력:
      turns: [{"role": "user"|"assistant", "blocks": [...]}, ...]
    
    출력:
      "[사용자]\n질문\n\n---\n\n[AI]\n답변"  또는
      None (text 블록이 하나도 없는 경우)
    
    힌트:
    - format_turn(turn) 활용 (이미 src/indexer.py에 구현됨)
    - None 결과는 필터링
    - "\n\n---\n\n".join(parts)
    """
    
    parts = []
    for turn in turns:
        result = format_turn(turn)
        if result is not None:
            parts.append(result)
    if not parts:
        return None
    
    return "\n\n---\n\n".join(parts)

def build_topics(session: dict, boundaries: list[int]) -> list[dict]:
    """경계 인덱스로 turns를 토픽 그룹으로 묶는다. (노트북 04-1 섹션 2 참고)

    입력:
      session: {"turns": [...], ...}
      boundaries: [4, 9]  ← detect_topic_boundaries() 결과

    반환:
      [
        {"text": "[사용자]\n...\n\n---\n\n[AI]\n...", "turn_start": 0, "turn_end": 3, "position": 0},
        {"text": "...", "turn_start": 4, "turn_end": 8, "position": 1},
        ...
      ]
      text가 None인 토픽(text 블록 없는 turns만 있는 경우)은 건너뜀.
    """
    # 1. starts = [0] + boundaries, ends = boundaries + [len(turns)]
    # 2. zip(starts, ends) 로 슬라이싱
    # 3. format_turn() 으로 각 turn 포맷 → "\n\n---\n\n".join()
    # 4. text None이면 건너뜀
    # 5. position은 건너뛰지 않은 토픽 순서 (0부터)
    turns = session['turns']
    starts = [0] + boundaries
    ends = boundaries + [len(turns)]

    topics = []
    position = 0
    for s, e in zip(starts, ends):
        group = turns[s:e]
        text = format_turns_as_text(group)
        if text is None:
            continue
        topics.append({
            "text": text,
            "turn_start": s,
            "turn_end": e-1,
            "position": position
        })
        position += 1

    return topics


def summarize_topic(topic_text: str, api_key: str) -> str:
    """토픽 텍스트를 Groq로 2~3문장 요약한다. (노트북 04-1 섹션 2 참고)

    입력:
      topic_text: "[사용자]\nfastembed 설치 방법은?\n\n---\n\n[AI]\npip install fastembed..."
      api_key: Groq API 키

    반환:
      "fastembed는 pip install fastembed로 설치하며 ONNX 런타임이 내장되어 있다."
      Groq 호출 실패 시 topic_text[:200] fallback.

    모델: llama-3.1-8b-instant, max_tokens=250, temperature=0.0
    원칙: 고유명사, 경로, 설정값은 원문 그대로 포함.
    """
    # 1. 요약 프롬프트 구성 (topic_text[:4000] 사용)
    # 2. chat_completion 호출
    # 3. 응답 content 반환
    # 4. 예외 → topic_text[:200]
    summary_prompt = f"""다음 대화를 핵심 정보만 포함해 2~3문장으로 요약하세요.
    고유명사, 경로, 설정값, 에러명은 원문 그대로 포함하세요.

    {topic_text[:4000]}

    요약:"""
    try:

      content, usage, _ = chat_completion(
        [{'role': 'user', 'content': summary_prompt}],
        'llama-3.1-8b-instant', api_key, max_tokens=250, temperature=0.0
      )
      return content

    except Exception:
        return topic_text[:200]


def build_vector_index(session: dict, session_dir: Path, api_key: str) -> Path:
    """토픽 기반 인덱스를 빌드해 vector_index.json으로 저장한다. (노트북 04-1 섹션 3 참고)

    입력:
      session: {"session_id": str, "turns": [...], ...}
      session_dir: 인덱스를 저장할 디렉토리 (없으면 생성)
      api_key: Groq API 키

    저장 경로: session_dir / "vector_index.json"
    저장 형식:
      [
        {
          "text":       "[사용자]\n...",   # 원문 (LLM에 전달)
          "summary":    "핵심 2~3문장",   # 임베딩 대상
          "embedding":  [0.12, ...],      # 1024차원
          "position":   0,
          "turn_start": 0,
          "turn_end":   3
        },
        ...
      ]
    이미 존재하면 재계산 없이 경로만 반환.
    """
    # 1. index_path = session_dir / VECTOR_INDEX_FILENAME
    # 2. exists() → 바로 반환
    # 3. mkdir(parents=True, exist_ok=True)
    # 4. detect_topic_boundaries() → boundaries
    # 5. build_topics() → topics
    # 6. 각 topic: summarize_topic() → summary
    # 7. embed_texts([요약 목록]) → embeddings (list로 변환)
    # 8. 각 topic에 summary, embedding 추가
    # 9. json 저장
    index_path = session_dir / "vector_index.json"

    if index_path.exists():
        return index_path
    
    session_dir.mkdir(parents=True, exist_ok=True)
    boundaries = detect_topic_boundaries(session, api_key)
    topics = build_topics(session, boundaries)
    summaries = [summarize_topic(t['text'], api_key) for t in topics]
    embeddings = embed_texts(summaries)
    for i, topic in enumerate(topics):
        topic['summary'] = summaries[i]
        topic['embedding'] = list(embeddings[i])
    index_path.write_text(json.dumps(topics, ensure_ascii=False), encoding='utf-8')
    return index_path


def search_vector(query: str, index_path: Path, top_k: int = 3) -> list[dict]:
    """벡터 인덱스에서 코사인 유사도로 상위 top_k 토픽을 검색한다. (노트북 04-1 섹션 3 참고)

    입력:
      query: "ONNX 런타임 자동 설치 여부"
      index_path: session_dir / "vector_index.json"
      top_k: 반환할 최대 개수

    반환:
      [
        {
          "text":       "[사용자]\n...",   # 원문
          "summary":    "핵심 2~3문장",
          "score":      0.87,             # 코사인 유사도
          "position":   0,
          "turn_start": 0,
          "turn_end":   3
        },
        ...
      ]
      유사도 내림차순 정렬. 인덱스 파일 없으면 [] 반환.
    """
    # search() 와 동일 패턴, embedding 필드는 공유
    if not index_path.exists():
        return []
    data = json.loads(index_path.read_text(encoding='utf-8'))
    query_vec = list(embed_texts([query])[0])
    for item in data:
        item['score'] = cosine_similarity(query_vec, item['embedding'])
    return sorted(data, key=lambda x: x['score'], reverse=True)[:top_k]


# ── Phase 4: 쿼리 분류 ────────────────────────────────────────────────────────

import re
_RETRIEVAL_PATTERN = re.compile(r'\d|\.\w{2,4}\b|[/\\]')

def should_be_retrieval(question: str) -> bool:
    """구체적 수치/파일명/경로 포함 여부로 retrieval 강제 여부를 반환한다.

    입력:
      question: 분류할 질문 문자열
    출력:
      True  → retrieval 강제 (LLM 분류 생략)
      False → LLM 분류 진행

    True 조건 (하나라도 해당 시):
    - 숫자 포함:      re.search(r'\\d', question)
    - 파일 확장자:    re.search(r'\\.\\w{2,4}\\b', question)  (.py .json .js .md 등)
    - 경로 포함:      '/' in question or '\\\\' in question
    """
    return bool(_RETRIEVAL_PATTERN.search(question))

def classify_query(question: str, api_key: str, model: str = 'llama-3.1-8b-instant') -> str:
    """질문을 simple / analytical / retrieval 로 분류한다. (노트북 04-2 섹션 1 참고)

    입력:
      question: "chunk_size 기본값이 얼마야?"
      api_key: Groq API 키
      model: 분류에 쓸 모델 (설정 패널에서 선택 가능, 기본 llama-3.1-8b-instant)

    반환:
      "simple"     — 세션 없이 LLM이 알 수 있는 일반 지식
      "analytical" — 대화 흐름 파악 필요, 구체적 수치/파일명 불필요
      "retrieval"  — 특정 수치, 파일명, 에러명, 결정 사항 필요

    원칙: 숫자/파일명/.py/.json 포함 시 retrieval 강제.
          Groq 호출 실패 시 "retrieval" 반환 (안전한 폴백).
    """
    # 1. 숫자/경로/파일 확장자 패턴 → retrieval 강제
    # 2. 분류 프롬프트 구성
    # 3. llama-3.1-8b-instant 호출 (max_tokens=20, temperature=0.0)
    # 4. 응답 파싱: {"simple","analytical","retrieval"} 검증
    # 5. 예외 → "retrieval"
    if should_be_retrieval(question):
        return "retrieval"
    
    prompt = f"""다음 질문을 아래 세 가지 중 하나로 분류하세요.
    
    - simple: 이 대화 세션 없이도 LLM이 알고 있는 일반 지식
    - analytical: 대화 전체 흐름 파악 필요, 구체적 수치/파일명 불필요
    - retrieval: 특정 수치, 파일명, 에러명, 결정 사항 등 구체적 사실 필요

    중요: 모호하면 retrieval로 답하세요.
    단어 하나만 출력하세요: simple 또는 analytical 또는 retrieval

    질문: {question}
    분류:"""

    try:
        content, usage, _ = chat_completion(
            [{'role': 'user', 'content': prompt}],
            model, api_key, max_tokens=20, temperature=0.0
        )
        answer = content.strip().lower().split()[0]

    except Exception:
        return 'retrieval'
    return answer if answer in {'simple', 'analytical', 'retrieval'} else 'retrieval'


def build_analytical_context(topics: list[dict]) -> str:
    """토픽 요약 목록으로 analytical 경로의 system 프롬프트를 만든다.

    입력:
      topics: [{"position": int, "summary": str, ...}, ...]
    출력:
      "아래는 이 대화 세션의 주요 주제 요약입니다.\n1. ...\n2. ...\n이 요약을 바탕으로 답변하세요."

    힌트:
    - lines = ["아래는 이 대화 세션의 주요 주제 요약입니다.\n"]
    - 각 topic의 position+1 번호와 summary 추가
    - lines.append("\n이 요약을 바탕으로 답변하세요.")
    - "\n".join(lines)
    """
    lines = ['아래는 이 대화 세션의 주요 주제 요약입니다.\n']
    for t in topics:
        lines.append(f"{t['position'] + 1}. {t['summary']}")
    lines.append('\n이 요약을 바탕으로 답변하세요.')
    return '\n'.join(lines)


def build_retrieval_context(search_results: list[dict]) -> str:
    """검색된 토픽 원문으로 retrieval 경로의 system 프롬프트를 만든다.

    입력:
      search_results: [{"text": str, "summary": str, "score": float, ...}, ...]
    출력:
      "아래는 관련 대화 내용입니다. 이 내용을 근거로 답변하세요.\n\n---\n\n[사용자]\n..."

    힌트:
    - parts = ["아래는 관련 대화 내용입니다. 이 내용을 근거로 답변하세요.\n"]
    - 각 result의 "text" 추가
    - "\n\n---\n\n".join(parts)
    """
    parts = ['아래는 관련 대화 내용입니다. 이 내용을 근거로 답변하세요. \n']
    for r in search_results:
        parts.append(r['text'])
    return '\n\n---\n\n'.join(parts)


def route_query(
    question: str,
    topics: list[dict],
    index_path: Path,
    api_key: str,
    top_k: int = 3,
    routing_model: str = 'llama-3.1-8b-instant',
    forced_type: str | None = None,
) -> dict:
    """질문을 분류하고 유형별 컨텍스트를 구성한다.

    입력:
      question:      분류할 질문
      topics:        [{"position": int, "summary": str, ...}, ...]
      index_path:    vector_index.json 경로
      api_key:       Groq API 키
      top_k:         retrieval 경로에서 가져올 토픽 수
      routing_model: classify_query에 쓸 모델 (설정 패널에서 선택 가능)
      forced_type:   "simple"|"analytical"|"retrieval" 중 하나면 분류 생략하고 그대로 사용
                      (설정 패널에서 라우팅을 수동 고정한 경우)
    출력:
      {
        "query_type":     "simple" | "analytical" | "retrieval",
        "system":         str,
        "search_results": list[dict]   ← retrieval일 때만 채워짐, 나머지 []
      }

    구현 순서:
    1. forced_type이 유효한 값이면 그대로 query_type으로 사용, 아니면 classify_query(question, api_key, routing_model) → query_type
    2. "simple"     → system = "당신은 도움이 되는 AI 어시스턴트입니다.", search_results = []
    3. "analytical" → system = build_analytical_context(topics),       search_results = []
    4. "retrieval"  → search_results = search_vector(question, index_path, top_k)
                       system = build_retrieval_context(search_results)
    5. return {"query_type": query_type, "system": system, "search_results": search_results}
    """
    if forced_type in ('simple', 'analytical', 'retrieval'):
        query_type = forced_type
    else:
        query_type = classify_query(question, api_key, routing_model)

    if query_type == 'simple':
        system = '당신은 도움이 되는 AI 어시스턴트입니다.'
        search_results = []

    elif query_type == 'analytical':
        system = build_analytical_context(topics)
        search_results = []
    else:
        search_results = search_vector(question, index_path, top_k)
        system = build_retrieval_context(search_results)
    
    return {
        'query_type' : query_type,
        'system' : system,
        'search_results': search_results,
    }