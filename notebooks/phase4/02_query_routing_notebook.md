# Phase 4-2 노트북 셀 내용 — 쿼리 분류 + 라우팅

셀 타입 표기: **📝 마크다운 셀** / **💻 코드 셀**
각 구분선(`---`) 사이 내용을 해당 타입의 셀에 붙여넣기.

---

📝 **마크다운 셀**

```
# Phase 4-2 — 쿼리 분류 + 라우팅

**목표:** 질문 유형(simple/analytical/retrieval)을 분류하고, 유형별로 다른 컨텍스트를 구성한다.

**이 노트북을 마치면:**
- [ ] 숫자/파일명/경로로 retrieval을 강제 판단할 수 있다
- [ ] Groq로 쿼리 유형을 분류할 수 있다
- [ ] 유형별 컨텍스트를 구성하고 Groq 답변까지 연결할 수 있다

**완성 후 연결:**
src/indexer.py의 classify_query() 구현
src/server.py의 POST /api/query-semantic 라우팅 분기 구현
```

---

💻 **코드 셀** (환경 설정)

```python
import sys, re
sys.path.insert(0, "..")

from src._groq import chat_completion, load_env_key
from src.indexer import search_vector

API_KEY = load_env_key()
```

---

📝 **마크다운 셀**

```
---
## 섹션 1 — 강제 규칙 (should_be_retrieval)

LLM 분류 전에 먼저 확인하는 규칙 기반 필터.
숫자/파일명/경로가 질문에 있으면 retrieval로 강제한다.

왜 LLM에 맡기지 않는가?
- LLM이 "CHUNK_SIZE 기본값 2000"을 analytical로 잘못 분류하는 오류가 있다.
- 규칙으로 처리하면 Groq 호출 없이 토큰 비용 0.

**입력:**
  "CHUNK_SIZE 기본값 2000이 설정된 이유는?"  → True  (숫자 포함)
  "session_index.json 구조는?"               → True  (.json 포함)
  "src/indexer.py 어디서 쓰여?"              → True  (/ 경로 포함)
  "이 대화의 주요 주제는?"                    → False (구체적 단서 없음)

**출력:**
  True  → retrieval 강제 (LLM 분류 생략)
  False → LLM 분류 진행
```

---

💻 **코드 셀** (워밍업 — 패턴 확인)

```python
# 각 조건이 어떻게 매칭되는지 확인
examples = [
    "CHUNK_SIZE 기본값 2000이 설정된 이유는?",
    "session_index.json 구조는?",
    "src/indexer.py 어디서 쓰여?",
    "이 대화의 주요 주제는?",
]
for q in examples:
    has_digit = bool(re.search(r'\d', q))
    has_ext   = bool(re.search(r'\.\w{2,4}\b', q))
    has_path  = '/' in q or '\\' in q
    print(f"{q!r}")
    print(f"  숫자:{has_digit}  확장자:{has_ext}  경로:{has_path}  → {has_digit or has_ext or has_path}")
```

---

💻 **코드 셀** (미니 실습 — should_be_retrieval)

```python
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
    # TODO
    pass
```

---

💻 **코드 셀** (채점)

```python
assert should_be_retrieval("CHUNK_SIZE가 2000인 이유는?")  == True,  "숫자 → True"
assert should_be_retrieval("session_index.json 구조는?")   == True,  ".json → True"
assert should_be_retrieval("src/indexer.py 경로는?")       == True,  "경로 → True"
assert should_be_retrieval("top_k=3으로 설정한 이유는?")   == True,  "숫자 → True"

assert should_be_retrieval("이 대화의 주요 주제는?")        == False, "단서 없음 → False"
assert should_be_retrieval("파이썬 문법 알려줘")            == False, "일반 질문 → False"
assert should_be_retrieval("왜 fastembed를 선택했나?")      == False, "고유명사만 → False"
print("✓ 통과")
```

---

📝 **마크다운 셀**

```
**연결:** should_be_retrieval()은 classify_query() 첫 줄에서 호출된다.

---
## 섹션 2 — 쿼리 분류 (classify_query)

세 가지 타입:
- simple:     세션 없이도 알 수 있는 일반 지식
- analytical: 대화 전체 흐름 파악 필요, 구체적 수치/파일명 불필요
- retrieval:  특정 수치, 파일명, 에러명, 결정 사항 필요

원칙: 모호하면 retrieval. 검색 오실행(토큰 낭비)보다 검색 누락(오답)이 더 위험하다.

**입력:**
  question = "chunk_size 기본값이 얼마야?"
  api_key  = "gsk_..."

**출력:**
  "retrieval"    ← LLM이 구체적 사실 질문으로 판단
  "simple"       ← "파이썬 list.sort() 사용법은?"
  "analytical"   ← "이 대화에서 주로 다룬 주제는?"
  Groq 실패 또는 예상 외 값 → "retrieval" 반환 (안전한 폴백)
```

---

💻 **코드 셀** (워밍업 — 분류 프롬프트 실행)

```python
def _raw_classify(question: str) -> str:
    """강제 규칙 없이 Groq만으로 분류하는 원형 — 패턴 확인용."""
    prompt = f"""다음 질문을 아래 세 가지 중 하나로 분류하세요.

- simple: 이 대화 세션 없이도 LLM이 알고 있는 일반 지식
- analytical: 대화 전체 흐름 파악 필요, 구체적 수치/파일명 불필요
- retrieval: 특정 수치, 파일명, 에러명, 결정 사항 등 구체적 사실 필요

중요: 모호하면 retrieval로 답하세요.
단어 하나만 출력하세요: simple 또는 analytical 또는 retrieval

질문: {question}
분류:"""

    content, _, _ = chat_completion(
        [{"role": "user", "content": prompt}],
        "llama-3.1-8b-instant", API_KEY, max_tokens=20, temperature=0.0
    )
    token = content.strip().lower().split()[0] if content.strip() else "retrieval"
    print(f"  [{token}] ← {content!r}")
    return token

questions = [
    "파이썬 list.sort()와 sorted()의 차이는?",
    "이 대화에서 주로 어떤 주제를 다뤘나?",
    "CHUNK_SIZE 기본값이 얼마야?",
    "session_index.json에 저장되는 필드는?",
]
for q in questions:
    print(f"\n[Q] {q}")
    _raw_classify(q)
```

---

💻 **코드 셀** (본 실습 — classify_query)

```python
def classify_query(question: str, api_key: str) -> str:
    """질문을 simple / analytical / retrieval 로 분류한다.

    입력:
      question: 분류할 질문 문자열
      api_key:  Groq API 키
    출력:
      "simple" | "analytical" | "retrieval"
      Groq 실패 또는 예상치 못한 값 → "retrieval"

    구현 순서:
    1. should_be_retrieval(question) → True이면 바로 "retrieval" 반환
    2. 분류 프롬프트 구성 (_raw_classify 참고)
    3. llama-3.1-8b-instant 호출 (max_tokens=20, temperature=0.0)
    4. content.strip().lower().split()[0] 로 파싱
    5. {"simple","analytical","retrieval"} 외의 값 → "retrieval"
    6. 예외 발생 시 → "retrieval"
    """
    # TODO
    pass
```

---

💻 **코드 셀** (채점)

```python
r1 = classify_query("파이썬 dict.get()이 KeyError를 안 내는 이유는?", API_KEY)
assert r1 in {"simple", "analytical", "retrieval"}, f"유효한 값이어야 함: {r1}"
print(f"'파이썬 dict.get()...' → {r1}")

r2 = classify_query("chunk_size 기본값 2000의 근거는?", API_KEY)
assert r2 == "retrieval", f"숫자 포함 → retrieval 강제, 실제: {r2}"
print(f"'chunk_size 기본값 2000...' → {r2}  ✓ 강제")

r3 = classify_query("session_index.json의 필드 구조는?", API_KEY)
assert r3 == "retrieval", f"파일명 포함 → retrieval 강제, 실제: {r3}"
print(f"'session_index.json...' → {r3}  ✓ 강제")

r_err = classify_query("어떤 질문이든", "INVALID_KEY_XYZ")
assert r_err == "retrieval", f"예외 시 retrieval 폴백, 실제: {r_err}"
print(f"예외 폴백 → {r_err}  ✓")
print("✓ 통과")
```

---

📝 **마크다운 셀**

```
**연결:** classify_query()의 반환값이 route_query()에서 컨텍스트 구성 분기를 결정한다.

---
## 섹션 3 — 라우팅 (route_query)

분류 결과에 따라 system 프롬프트에 담는 내용이 다르다.

| 타입       | system 포함 내용          | 검색 여부 |
|------------|--------------------------|---------|
| simple     | 짧은 지시문만             | X       |
| analytical | 토픽 요약 목록            | X       |
| retrieval  | 검색된 원문               | O       |

**입력:**
  question   = "ONNX 런타임이 자동 포함되나요?"
  topics     = [{"position": 0, "summary": "..."}, ...]
  index_path = Path("conversations_learning/abc/vector_index.json")
  api_key    = "gsk_..."
  top_k      = 3

**출력:**
  {
    "query_type":     "retrieval",
    "system":         "아래는 관련 대화 내용입니다...\n\n[사용자]\nONNX...",
    "search_results": [{"text": ..., "score": 0.87, ...}]
  }

  query_type = "simple"이면:
  {
    "query_type":     "simple",
    "system":         "당신은 도움이 되는 AI 어시스턴트입니다.",
    "search_results": []
  }
```

---

💻 **코드 셀** (워밍업 — analytical 컨텍스트 구성)

```python
# analytical: 토픽 요약 목록만 system에 포함
sample_topics = [
    {"position": 0, "summary": "fastembed 설치 방법과 ONNX 런타임 내장 여부 설명."},
    {"position": 1, "summary": "RAG 평가 지표(Hit Rate, Correctness)와 계산 방법 설명."},
]

def build_analytical_context(topics: list[dict]) -> str:
    lines = ["아래는 이 대화 세션의 주요 주제 요약입니다.\n"]
    for t in topics:
        lines.append(f"{t['position'] + 1}. {t['summary']}")
    lines.append("\n이 요약을 바탕으로 답변하세요.")
    return "\n".join(lines)

print(build_analytical_context(sample_topics))
```

---

💻 **코드 셀** (워밍업 — retrieval 컨텍스트 구성)

```python
# retrieval: 검색된 토픽 원문을 system에 포함
sample_results = [
    {
        "text":       "[사용자]\nONNX 런타임은?\n\n---\n\n[AI]\nfastembed 내장.",
        "summary":    "ONNX 런타임 내장 여부 설명.",
        "score":      0.87,
        "turn_start": 2, "turn_end": 3,
    }
]

def build_retrieval_context(search_results: list[dict]) -> str:
    parts = ["아래는 관련 대화 내용입니다. 이 내용을 근거로 답변하세요.\n"]
    for r in search_results:
        parts.append(r["text"])
    return "\n\n---\n\n".join(parts)

print(build_retrieval_context(sample_results))
```

---

💻 **코드 셀** (본 실습 — route_query)

```python
from pathlib import Path

def route_query(
    question: str,
    topics: list[dict],
    index_path: Path,
    api_key: str,
    top_k: int = 3,
) -> dict:
    """질문을 분류하고 유형별 컨텍스트를 구성한다.

    입력:
      question:   분류할 질문
      topics:     [{"position": int, "summary": str, ...}, ...]
      index_path: vector_index.json 경로
      api_key:    Groq API 키
      top_k:      retrieval 경로에서 가져올 토픽 수
    출력:
      {
        "query_type":     "simple" | "analytical" | "retrieval",
        "system":         str,
        "search_results": list[dict]   ← retrieval일 때만 채워짐, 나머지 []
      }

    구현 순서:
    1. classify_query(question, api_key) → query_type
    2. "simple"     → system = "당신은 도움이 되는 AI 어시스턴트입니다.", results = []
    3. "analytical" → system = build_analytical_context(topics), results = []
    4. "retrieval"  → search_vector(question, index_path, top_k) → results
                       system = build_retrieval_context(results)
    """
    # TODO
    pass
```

---

💻 **코드 셀** (채점)

```python
from pathlib import Path

sample_topics_for_routing = [
    {"position": 0, "summary": "fastembed 설치 방법 설명."},
    {"position": 1, "summary": "RAG 평가 방법 설명."},
]

result = route_query(
    "파이썬 list.sort() 사용법은?",
    sample_topics_for_routing,
    Path("없는파일.json"),
    API_KEY,
)
assert result["query_type"] in {"simple", "analytical", "retrieval"}
assert isinstance(result["system"], str) and len(result["system"]) > 0
assert isinstance(result["search_results"], list)
print(f"[{result['query_type']}] system 앞 60자: {result['system'][:60]}")

result_ret = route_query(
    "CHUNK_SIZE 기본값 2000의 근거는?",
    sample_topics_for_routing,
    Path("없는파일.json"),
    API_KEY,
)
assert result_ret["query_type"] == "retrieval", f"retrieval 강제, 실제: {result_ret['query_type']}"
print(f"[{result_ret['query_type']}] search_results: {result_ret['search_results']}")
print("✓ 통과")
```

---

💻 **코드 셀** (통합 실행 — Groq 답변까지)

```python
# 분류 → 컨텍스트 → Groq 답변 전체 흐름
question = "이 대화에서 주로 어떤 주제를 다뤘나?"

routed = route_query(question, sample_topics_for_routing, Path("없는파일.json"), API_KEY)
print(f"분류: {routed['query_type']}")
print(f"system:\n{routed['system'][:200]}")

messages = [
    {"role": "system", "content": routed["system"]},
    {"role": "user",   "content": question},
]
answer, usage, _ = chat_completion(messages, "llama-3.3-70b-versatile", API_KEY, max_tokens=200)
print(f"\n답변: {answer[:150]}")
print(f"토큰 사용: {usage}")
```

---

📝 **마크다운 셀**

```
**연결:** route_query()의 반환값이 server.py에서 Groq 호출로 이어진다.

  routed = route_query(question, topics, index_path, api_key)
  messages = [
      {"role": "system", "content": routed["system"]},
      {"role": "user",   "content": question},
  ]
  answer, usage, _ = chat_completion(messages, model, api_key, max_tokens=512)

Phase 5에서 retrieval 경로에 인접 게이팅과 KG 검색 결과가 추가된다.

---
## 스스로 정리해보기

노트북 완료 후 직접 작성:
- should_be_retrieval()이 LLM 분류보다 먼저 실행되는 이유는?
- analytical과 retrieval의 system 프롬프트 토큰 수를 비교하면 어떤가?
- 분류 오류가 가장 위험한 방향은? (simple→retrieval vs retrieval→simple)
```
