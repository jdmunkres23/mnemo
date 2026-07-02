# Phase 4-1 노트북 셀 내용 — 토픽 경계 탐지 + 요약 임베딩

셀 타입 표기: **📝 마크다운 셀** / **💻 코드 셀**
각 구분선(`---`) 사이 내용을 해당 타입의 셀에 붙여넣기.

---

📝 **마크다운 셀**

```
# Phase 4-1 — 토픽 경계 탐지 + 요약 임베딩

**목표:** 고정 크기 청크 대신 주제(토픽) 단위로 분할하고, 요약으로 임베딩해 검색 정확도를 높인다.

**이 노트북을 마치면:**
- [ ] 사용자 메시지로 토픽 경계를 탐지할 수 있다
- [ ] 경계 기준으로 turns를 토픽으로 그룹화할 수 있다
- [ ] 토픽을 요약하고 임베딩해 vector_index.json에 저장할 수 있다
- [ ] 벡터 인덱스에서 top-k 토픽을 검색할 수 있다

**완성 후 연결:**
src/indexer.py의 detect_topic_boundaries(), build_topics(),
summarize_topic(), build_vector_index(), search_vector() 구현
```

---

💻 **코드 셀** (환경 설정)

```python
import sys, json, re
sys.path.insert(0, "..")

from src._groq import chat_completion, load_env_key
from src.indexer import embed_texts, cosine_similarity, format_turn

API_KEY = load_env_key()

sample_session = {
    "session_id": "test",
    "turns": [
        {"role": "user",      "blocks": [{"type": "text", "text": "fastembed 설치 방법은?"}]},
        {"role": "assistant", "blocks": [{"type": "text", "text": "pip install fastembed로 설치합니다. ONNX 런타임은 내장되어 있습니다."}]},
        {"role": "user",      "blocks": [{"type": "text", "text": "ONNX 런타임이 자동으로 포함되나요?"}]},
        {"role": "assistant", "blocks": [{"type": "text", "text": "네, fastembed 내부에 포함되어 있어 별도 설치 불필요합니다."}]},
        {"role": "user",      "blocks": [{"type": "text", "text": "RAG 평가는 어떻게 하나요?"}]},
        {"role": "assistant", "blocks": [{"type": "text", "text": "Hit Rate와 Correctness로 평가합니다."}]},
        {"role": "user",      "blocks": [{"type": "text", "text": "Hit Rate 계산 방법은?"}]},
        {"role": "assistant", "blocks": [{"type": "text", "text": "source_turns와 검색된 turn 범위의 교집합 비율입니다."}]},
    ]
}
print(f"총 turn 수: {len(sample_session['turns'])}")
```

---

📝 **마크다운 셀**

```
---
## 섹션 1 — 균등 분할 (_uniform_boundaries)

detect_topic_boundaries()가 실패했을 때 쓰는 fallback.
사용자 turn 인덱스를 n_topics 개로 균등하게 나눈다.

**입력:**
  session["turns"] = [user, assistant, user, assistant, user, assistant]  (총 6턴)
  사용자 turn 인덱스 = [0, 2, 4]
  n_topics = 3

**출력:**
  [2, 4]   ← step=1이면 user_idxs[1]=2, user_idxs[2]=4
```

---

💻 **코드 셀** (미니 실습 — _uniform_boundaries)

```python
def _uniform_boundaries(session: dict, n_topics: int = 5) -> list[int]:
    """사용자 turn을 n_topics개로 균등 분할하는 경계 인덱스를 반환한다.

    입력:
      session: {"turns": [...]}
      n_topics: 목표 그룹 수
    출력:
      [int, ...]  — 경계 turn 인덱스 목록 (첫 0 제외)
      예: 사용자 turn [0,2,4,6,8,10], n_topics=3 → step=2 → [4, 8]

    힌트:
    - user_idxs = [i for i, t in enumerate(turns) if t["role"] == "user"]
    - step = max(1, len(user_idxs) // n_topics)
    - [user_idxs[step*k] for k in range(1, n_topics) if step*k < len(user_idxs)]
    """
    # TODO
    pass
```

---

💻 **코드 셀** (채점)

```python
turns = []
for i in range(6):
    turns.append({"role": "user",      "blocks": [{"type": "text", "text": f"질문 {i}"}]})
    turns.append({"role": "assistant", "blocks": [{"type": "text", "text": f"답변 {i}"}]})
test_session = {"turns": turns}  # 사용자 turn: 0, 2, 4, 6, 8, 10

result = _uniform_boundaries(test_session, n_topics=3)
print(f"균등 분할 경계: {result}")

assert isinstance(result, list), "리스트 반환"
assert len(result) == 2, f"3그룹 → 경계 2개, 실제: {result}"
assert all(isinstance(x, int) for x in result), "정수"
assert all(0 < x < len(test_session["turns"]) for x in result), "유효 범위"
print("✓ 통과")
```

---

📝 **마크다운 셀**

```
**연결:** _uniform_boundaries()는 detect_topic_boundaries() 예외 처리 블록에서 호출된다.

---
## 섹션 2 — 토픽 경계 탐지 (detect_topic_boundaries)

사용자 메시지만 Groq에 보내 경계 인덱스를 받는다.

**입력:**
  session = {"turns": [8개 turn...]}
  api_key = "gsk_..."

**출력:**
  [4]      ← turn 4부터 새 토픽 (turns 0~3 / 4~끝 두 그룹)
  [4, 9]   ← 세 그룹
  []       ← 경계 없음
  Groq 실패 → _uniform_boundaries(session) 결과

**주의:** 반환 인덱스는 session["turns"] 기준 (사용자 turn만이 아님).
```

---

💻 **코드 셀** (워밍업 — Groq 경계 탐지 실행)

```python
# 사용자 메시지 추출 + 프롬프트 구성
user_msgs = []
for i, turn in enumerate(sample_session["turns"]):
    if turn["role"] == "user":
        text = " ".join(b["text"] for b in turn["blocks"] if b["type"] == "text")
        user_msgs.append((i, text))

prompt_input = "\n".join(f"{i}: {text}" for i, text in user_msgs)

prompt = f"""아래는 대화에서 사용자가 보낸 메시지 목록입니다 (형식: turn인덱스: 메시지).
주제가 크게 바뀌는 경계 직전의 turn 인덱스를 JSON 배열로 반환하세요.
경계가 없으면 [] 를 반환하세요.
숫자 배열만 출력, 설명 없이.

{prompt_input}

경계 인덱스:"""

content, usage, _ = chat_completion(
    [{"role": "user", "content": prompt}],
    "llama-3.1-8b-instant", API_KEY, max_tokens=50, temperature=0.0
)
print(f"입력:\n{prompt_input}")
print(f"\nGroq 응답: {content!r}")
print(f"파싱: {[int(n) for n in re.findall(r'\\d+', content)]}")
```

---

💻 **코드 셀** (본 실습 — detect_topic_boundaries)

```python
def detect_topic_boundaries(session: dict, api_key: str) -> list[int]:
    """사용자 메시지에서 토픽 경계 인덱스를 탐지한다.

    입력:
      session: {"turns": [{"role": "user"|"assistant", "blocks": [...]}, ...]}
      api_key: Groq API 키
    출력:
      [int, ...]  — 경계 turn 인덱스 (1 이상 len-1 이하)
      Groq 실패 → _uniform_boundaries(session)

    구현 순서:
    1. [(i, text)] 사용자 turn 추출
    2. 사용자 turn 1개 이하 → [] 반환
    3. 프롬프트 구성 + llama-3.1-8b-instant 호출 (max_tokens=50, temperature=0.0)
    4. re.findall(r'\\d+', content) → 정수 변환
    5. 유효 범위 필터 (1 이상 len(turns)-1 이하)
    6. 예외 → _uniform_boundaries(session) 반환
    """
    # TODO
    pass
```

---

💻 **코드 셀** (채점)

```python
boundaries = detect_topic_boundaries(sample_session, API_KEY)
print(f"탐지된 경계: {boundaries}")

assert isinstance(boundaries, list)
assert all(isinstance(b, int) for b in boundaries)
assert all(0 < b < len(sample_session["turns"]) for b in boundaries), "유효 범위"
assert len(boundaries) >= 1, f"경계 없음 — 프롬프트/파싱 확인, 결과: {boundaries}"
print("✓ 통과")
```

---

📝 **마크다운 셀**

```
**연결:** detect_topic_boundaries()의 결과가 build_topics()의 두 번째 인자가 된다.

---
## 섹션 3 — turn 텍스트 변환 (format_turns_as_text)

turn 목록을 "[사용자]/[AI]" 형식의 하나의 문자열로 만든다.
build_topics()에서 내부적으로 쓰인다.

**입력:**
  turns = [
    {"role": "user",      "blocks": [{"type": "text", "text": "질문"}]},
    {"role": "assistant", "blocks": [{"type": "text", "text": "답변"}]},
    {"role": "user",      "blocks": [{"type": "thinking", "thinking": "..."}]},  # text 없음 → 건너뜀
  ]

**출력:**
  "[사용자]\n질문\n\n---\n\n[AI]\n답변"
  text 블록이 하나도 없으면 → None
```

---

💻 **코드 셀** (미니 실습 — format_turns_as_text)

```python
def format_turns_as_text(turns: list[dict]) -> str | None:
    """turn 목록을 "[사용자]/[AI]" 형식 텍스트로 변환한다.

    입력:
      turns: [{"role": ..., "blocks": [...]}, ...]
    출력:
      "[사용자]\n질문\n\n---\n\n[AI]\n답변"  또는 None (text 블록 없는 경우)

    힌트:
    - format_turn(turn)을 각 turn에 적용 (None이면 건너뜀)
    - "\n\n---\n\n".join(parts)
    """
    # TODO
    pass
```

---

💻 **코드 셀** (채점)

```python
test_turns = [
    {"role": "user",      "blocks": [{"type": "text", "text": "질문"}]},
    {"role": "assistant", "blocks": [{"type": "text", "text": "답변"}]},
    {"role": "user",      "blocks": [{"type": "thinking", "thinking": "..."}]},
]
result = format_turns_as_text(test_turns)
print(repr(result))

assert result is not None
assert "[사용자]\n질문" in result
assert "[AI]\n답변"    in result
assert "---" in result

only_thinking = [{"role": "user", "blocks": [{"type": "thinking", "thinking": "..."}]}]
assert format_turns_as_text(only_thinking) is None, "text 없으면 None"
print("✓ 통과")
```

---

📝 **마크다운 셀**

```
**연결:** format_turns_as_text()의 출력이 build_topics()의 "text" 필드가 된다.

---
## 섹션 4 — 토픽 그룹화 (build_topics)

경계 인덱스로 turns를 슬라이싱해 토픽 목록을 만든다.

**입력:**
  session = {"turns": [8개 turn...]}
  boundaries = [4]

**출력:**
  [
    {"text": "[사용자]\nfastembed...", "turn_start": 0, "turn_end": 3, "position": 0},
    {"text": "[사용자]\nRAG 평가...",  "turn_start": 4, "turn_end": 7, "position": 1},
  ]

position 필드: Phase 5 인접 게이팅에서 ±1 토픽을 찾을 때 사용.
```

---

💻 **코드 셀** (워밍업 — 경계로 turns 슬라이싱 패턴)

```python
# boundaries = [4] → turns 0~3, 4~끝 두 그룹
sample_boundaries = [4]
turns = sample_session["turns"]

starts = [0] + sample_boundaries           # [0, 4]
ends   = sample_boundaries + [len(turns)]  # [4, 8]

for start, end in zip(starts, ends):
    group = turns[start:end]
    print(f"turn {start}~{end-1}: {len(group)}개")
    for t in group:
        role = "사용자" if t["role"] == "user" else "AI"
        text = " ".join(b["text"] for b in t["blocks"] if b["type"] == "text")
        print(f"  [{role}] {text}")
```

---

💻 **코드 셀** (본 실습 — build_topics)

```python
def build_topics(session: dict, boundaries: list[int]) -> list[dict]:
    """경계 인덱스로 turns를 토픽 그룹으로 묶는다.

    입력:
      session: {"turns": [...]}
      boundaries: [4] 또는 [4, 9] 등
    출력:
      [{"text": str, "turn_start": int, "turn_end": int, "position": int}, ...]
      text가 None인 토픽은 건너뜀.

    구현 순서:
    1. starts = [0] + boundaries, ends = boundaries + [len(turns)]
    2. zip(starts, ends) 로 슬라이싱
    3. format_turns_as_text(group) → text, None이면 건너뜀
    4. position은 건너뛰지 않은 순서 (0부터)
    """
    # TODO
    pass
```

---

💻 **코드 셀** (채점)

```python
boundaries = detect_topic_boundaries(sample_session, API_KEY)
topics = build_topics(sample_session, boundaries)

print(f"토픽 수: {len(topics)}")
for t in topics:
    print(f"  position {t['position']}: turn {t['turn_start']}~{t['turn_end']}")

assert len(topics) >= 1
assert topics[0]["position"] == 0
assert topics[0]["turn_start"] == 0
assert topics[-1]["turn_end"] == len(sample_session["turns"]) - 1, "마지막 turn 포함"
assert [t["position"] for t in topics] == list(range(len(topics))), "position 연속"
print("✓ 통과")
```

---

📝 **마크다운 셀**

```
**연결:** build_topics()의 각 topic["text"]가 summarize_topic()의 입력이 된다.

---
## 섹션 5 — 토픽 요약 (summarize_topic)

토픽 원문을 Groq로 2~3문장 요약한다.
요약이 임베딩 대상(Small), 원문이 LLM 전달 대상(Big).

왜 원문 그대로 임베딩하지 않는가?
긴 원문은 여러 키워드가 섞여 유사도가 평범해진다.
요약은 핵심만 남아 쿼리와의 유사도가 선명해진다.

**입력:**
  topic_text = "[사용자]\nfastembed 설치 방법은?\n\n---\n\n[AI]\npip install fastembed..."

**출력:**
  "fastembed는 pip install fastembed로 설치하며 ONNX 런타임이 내장되어 있다."
  Groq 실패 시 → topic_text[:200]
```

---

💻 **코드 셀** (워밍업 — Groq 요약 실행)

```python
test_text = topics[0]["text"]
summary_prompt = f"""다음 대화를 핵심 정보만 포함해 2~3문장으로 요약하세요.
고유명사, 경로, 설정값, 에러명은 원문 그대로 포함하세요.

{test_text[:1500]}

요약:"""

content, usage, _ = chat_completion(
    [{"role": "user", "content": summary_prompt}],
    "llama-3.1-8b-instant", API_KEY, max_tokens=150, temperature=0.0
)
print(f"원문 ({len(test_text)}자):")
print(test_text[:100].replace("\n", " "), "...")
print(f"\n요약 ({len(content)}자):")
print(content)
```

---

💻 **코드 셀** (본 실습 — summarize_topic)

```python
def summarize_topic(topic_text: str, api_key: str) -> str:
    """토픽 텍스트를 Groq로 2~3문장 요약한다.

    입력:
      topic_text: "[사용자]\n...\n\n---\n\n[AI]\n..."
      api_key: Groq API 키
    출력:
      "핵심 2~3문장."  (고유명사, 경로, 설정값 원문 보존)
      예외 → topic_text[:200]

    모델: llama-3.1-8b-instant, max_tokens=150, temperature=0.0
    """
    # TODO
    pass
```

---

💻 **코드 셀** (채점)

```python
summary = summarize_topic(topics[0]["text"], API_KEY)
print(f"요약: {summary}")

assert isinstance(summary, str)
assert 10 < len(summary) < 500, f"길이 범위 초과: {len(summary)}"

# fallback 확인
fallback = summarize_topic(topics[0]["text"], "INVALID_KEY_XYZ")
assert isinstance(fallback, str)
assert len(fallback) <= 200, "fallback은 200자 이하"
print("✓ 통과")
```

---

📝 **마크다운 셀**

```
**연결:** summarize_topic()의 출력이 embed_texts()에 들어간다.
summaries 리스트를 먼저 만든 뒤 embed_texts(summaries) 한 번에 호출하면
API 호출 횟수를 줄일 수 있다.

---
## 섹션 6 — 벡터 인덱스 저장 (build_vector_index)

토픽 원문 + 요약 + 임베딩을 vector_index.json에 저장한다.

저장 형식:
  [
    {
      "text":       "[사용자]\n...",   ← LLM에 전달할 원문
      "summary":    "핵심 2~3문장",   ← 임베딩 대상
      "embedding":  [0.12, ...],      ← 1024차원
      "position":   0,
      "turn_start": 0,
      "turn_end":   3
    }, ...
  ]
```

---

💻 **코드 셀** (워밍업 — 요약 임베딩 vs 원문 임베딩 유사도 비교)

```python
# Small-to-Big 효과 확인
query    = "ONNX 런타임 자동 설치 여부"
original = topics[0]["text"]
summary  = summarize_topic(original, API_KEY)

vecs = embed_texts([query, original, summary])
q, o, s = list(vecs[0]), list(vecs[1]), list(vecs[2])

print(f"원문 ({len(original):4d}자) 유사도: {cosine_similarity(q, o):.4f}")
print(f"요약 ({len(summary):4d}자) 유사도: {cosine_similarity(q, s):.4f}")
# 요약 유사도가 더 높아야 Small-to-Big 효과 확인
```

---

💻 **코드 셀** (본 실습 — build_vector_index)

```python
from pathlib import Path

def build_vector_index(session: dict, session_dir: Path, api_key: str) -> Path:
    """토픽 기반 인덱스를 빌드해 vector_index.json으로 저장한다.

    입력:
      session: {"session_id": str, "turns": [...]}
      session_dir: 저장 디렉토리
      api_key: Groq API 키
    출력:
      Path("session_dir/vector_index.json")
      이미 존재하면 재계산 없이 경로만 반환.

    구현 순서:
    1. index_path = session_dir / "vector_index.json"
    2. exists() → 바로 반환
    3. session_dir.mkdir(parents=True, exist_ok=True)
    4. detect_topic_boundaries(session, api_key) → boundaries
    5. build_topics(session, boundaries) → topics
    6. [summarize_topic(t["text"], api_key) for t in topics] → summaries
    7. embed_texts(summaries) → embeddings (list(vec)로 변환)
    8. 각 topic에 summary, embedding 추가 → json 저장
    """
    import json
    # TODO
    pass
```

---

💻 **코드 셀** (채점)

```python
import tempfile, json
from pathlib import Path

with tempfile.TemporaryDirectory() as tmp:
    session_dir = Path(tmp) / "test"
    index_path = build_vector_index(sample_session, session_dir, API_KEY)

    assert index_path.exists()
    assert index_path.name == "vector_index.json"

    data = json.loads(index_path.read_text(encoding="utf-8"))
    assert len(data) >= 1

    f = data[0]
    for field in ("text", "summary", "embedding", "position", "turn_start", "turn_end"):
        assert field in f, f"필드 누락: {field}"
    assert len(f["embedding"]) == 1024, "1024차원"
    assert f["position"] == 0

    # 이미 존재하면 재계산 없이 반환
    path2 = build_vector_index(sample_session, session_dir, API_KEY)
    assert path2 == index_path
    print(f"토픽 수: {len(data)}")
    print("✓ 통과")
```

---

📝 **마크다운 셀**

```
**연결:** build_vector_index()로 저장된 파일을 search_vector()가 로드해 검색한다.

---
## 섹션 7 — 벡터 검색 (search_vector)

vector_index.json을 로드해 쿼리와 코사인 유사도가 높은 토픽을 반환한다.
Phase 3 search()와 동일한 패턴 — 필드명만 다름.

**입력:**
  query = "ONNX 런타임 자동 설치 여부"
  index_path = Path(".../vector_index.json")
  top_k = 2

**출력:**
  [
    {"text": "...", "summary": "...", "score": 0.87, "position": 0, "turn_start": 0, "turn_end": 3},
    {"text": "...", "summary": "...", "score": 0.71, "position": 1, "turn_start": 4, "turn_end": 7},
  ]
  유사도 내림차순. index_path 없으면 [] 반환.
```

---

💻 **코드 셀** (본 실습 — search_vector)

```python
def search_vector(query: str, index_path: Path, top_k: int = 3) -> list[dict]:
    """벡터 인덱스에서 코사인 유사도로 상위 top_k 토픽을 검색한다.

    입력:
      query: 검색 질문
      index_path: vector_index.json 경로
      top_k: 반환할 최대 개수
    출력:
      [{"text", "summary", "score", "position", "turn_start", "turn_end"}, ...]
      유사도 내림차순. index_path 없으면 [] 반환.

    힌트: Phase 3 search()와 동일 패턴
    - embed_texts([query])[0] → query_vec
    - cosine_similarity(query_vec, item["embedding"])
    - sorted(..., reverse=True)[:top_k]
    """
    import json
    # TODO
    pass
```

---

💻 **코드 셀** (채점)

```python
import tempfile
from pathlib import Path

with tempfile.TemporaryDirectory() as tmp:
    session_dir = Path(tmp) / "test"
    index_path = build_vector_index(sample_session, session_dir, API_KEY)

    results = search_vector("ONNX 런타임", index_path, top_k=2)

    print(f"검색 결과 {len(results)}개:")
    for r in results:
        print(f"  score {r['score']:.4f}  turn {r['turn_start']}~{r['turn_end']}")
        print(f"  요약: {r['summary'][:60]}...")

    assert 1 <= len(results) <= 2
    for f in ("text", "summary", "score", "position", "turn_start", "turn_end"):
        assert f in results[0], f"필드 누락: {f}"
    assert results == sorted(results, key=lambda x: x["score"], reverse=True), "내림차순"
    assert search_vector("쿼리", Path(tmp) / "없음.json", top_k=3) == [], "없는 파일 → []"
    print("✓ 통과")
```

---

📝 **마크다운 셀**

```
**연결:** search_vector()는 evaluator.py run_vector()에서 Phase 3 search()와 같은 위치에 쓰인다.
반환 형식이 유사해 evaluator 구조를 그대로 유지할 수 있다.

다음 노트북(02_query_routing)에서 이 검색 결과를 어떤 질문에 사용할지 분류한다.

---
## 스스로 정리해보기

노트북 완료 후 직접 작성:
- 사용자 메시지만 경계 탐지에 사용하는 이유는? SeCom과 어떻게 다른가?
- Small-to-Big에서 요약 대신 원문 앞 200자를 쓰면 어떤 문제가 생기는가?
- build_vector_index()에서 summarize_topic()을 하나씩 호출하지 않고
  summaries 리스트를 먼저 만든 뒤 embed_texts()를 한 번만 호출하는 이유는?
```
