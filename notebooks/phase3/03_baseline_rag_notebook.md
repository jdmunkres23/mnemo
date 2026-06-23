# Phase 3-3 노트북 셀 내용 — Baseline RAG (build_index + search)

셀 타입 표기: **📝 마크다운 셀** / **💻 코드 셀**
각 구분선(`---`) 사이 내용을 해당 타입의 셀에 붙여넣기.

---

📝 **마크다운 셀**

```
# Phase 3-3 — Baseline RAG

**목표:** 고정 크기 청크 + 벡터 검색으로 동작하는 기본 RAG 파이프라인을 구현한다.

**이 노트북을 마치면:**
- [ ] session_index.json을 생성하는 build_index()를 구현할 수 있다
- [ ] 코사인 유사도로 top-k 청크를 검색하는 search()를 구현할 수 있다
- [ ] 검색된 청크를 컨텍스트로 Groq를 호출할 수 있다

**완성 후 연결:**
`src/indexer.py`의 `build_index()`, `search()` 구현
```

---

📝 **마크다운 셀**

```
---
## 섹션 1 — 인덱스 구축 (build_index)

chunk_session() + embed_texts() 를 조합해 session_index.json을 생성한다.

저장 형식:
[{"text": "...", "embedding": [...], "turn_start": 0, "turn_end": 3}, ...]
```

---

💻 **코드 셀** (워밍업)

```python
import json, sys
from pathlib import Path
sys.path.insert(0, "..")

# 이전 노트북에서 구현한 함수들 가져오기
from src.indexer import embed_texts, chunk_session  # 구현 완료 후 실행

# 테스트용 세션
sample_session = {
    "session_id": "test-001",
    "turns": [
        {"role": "user",      "blocks": [{"type": "text", "text": "fastembed 설치 방법은?"}]},
        {"role": "assistant", "blocks": [{"type": "text", "text": "pip install fastembed로 설치합니다."}]},
        {"role": "user",      "blocks": [{"type": "text", "text": "ONNX 런타임도 필요한가요?"}]},
        {"role": "assistant", "blocks": [{"type": "text", "text": "fastembed이 자동으로 포함합니다."}]},
    ]
}

# 청크 분할 확인
chunks = chunk_session(sample_session, chunk_size=80)
print(f"청크 수: {len(chunks)}")
for i, c in enumerate(chunks):
    print(f"  청크 {i}: turn {c['turn_start']}~{c['turn_end']}, {len(c['text'])}자")
```

---

💻 **코드 셀** (미니 실습)

```python
def attach_embeddings(chunks: list[dict], embeddings: list[list[float]]) -> list[dict]:
    """각 청크 딕셔너리에 embedding 필드를 추가해 반환한다.
    
    반환: [{"text": str, "embedding": list[float], "turn_start": int, "turn_end": int}, ...]
    힌트: zip(chunks, embeddings) 로 순서 맞춰 결합
    """
    # TODO
    pass
```

---

💻 **코드 셀** (채점)

```python
sample_chunks = [
    {"text": "청크A", "turn_start": 0, "turn_end": 1},
    {"text": "청크B", "turn_start": 2, "turn_end": 3},
]
sample_embs = [[0.1, 0.2], [0.3, 0.4]]

result = attach_embeddings(sample_chunks, sample_embs)
assert len(result) == 2,                        "청크 수 유지"
assert result[0]["embedding"] == [0.1, 0.2],   "첫 번째 임베딩"
assert result[1]["embedding"] == [0.3, 0.4],   "두 번째 임베딩"
assert result[0]["text"] == "청크A",            "text 필드 유지"
assert result[0]["turn_start"] == 0,            "turn_start 유지"
print("✓ 통과")
```

---

💻 **코드 셀** (본 실습)

```python
def build_index(session: dict, session_dir: Path, chunk_size: int = 2000) -> Path:
    """세션을 청크로 분할 후 임베딩해 session_index.json으로 저장한다.
    
    저장 경로: session_dir / "session_index.json"
    저장 형식: [{"text": str, "embedding": list[float],
                 "turn_start": int, "turn_end": int}, ...]
    반환: session_index.json 경로
    
    인덱스가 이미 존재하면 재계산 없이 기존 파일 경로 반환.
    
    힌트:
    - session_dir.mkdir(parents=True, exist_ok=True)
    - chunk_session() → embed_texts() → 각 청크에 embedding 추가
    - json.dumps(..., ensure_ascii=False, indent=2)
    """
    index_path = session_dir / "session_index.json"
    # TODO
    pass
```

---

💻 **코드 셀** (채점)

```python
import tempfile

with tempfile.TemporaryDirectory() as tmpdir:
    session_dir = Path(tmpdir) / "test-001"
    
    idx_path = build_index(sample_session, session_dir, chunk_size=80)
    
    assert idx_path.exists(), "session_index.json 생성됨"
    data = json.loads(idx_path.read_text(encoding="utf-8"))
    
    assert isinstance(data, list) and len(data) >= 1, "청크 목록"
    assert "text" in data[0], "text 필드"
    assert "embedding" in data[0], "embedding 필드"
    assert len(data[0]["embedding"]) == 1024, "1024차원"
    assert "turn_start" in data[0] and "turn_end" in data[0], "turn 범위"
    
    # 이미 있으면 재계산하지 않음
    idx_path2 = build_index(sample_session, session_dir, chunk_size=80)
    assert idx_path == idx_path2, "같은 경로 반환"
    
    print(f"청크 수: {len(data)}, 첫 청크 turn: {data[0]['turn_start']}~{data[0]['turn_end']}")
    print("✓ 통과")
```

---

📝 **마크다운 셀**

```
**연결:** `build_index()`는 server.py `POST /api/index-session` 에서 호출된다.
인덱스 파일은 `conversations_learning/{session_id}/session_index.json`에 저장된다.

---
## 섹션 2 — 벡터 검색 (search)

질문 임베딩 → 모든 청크와 코사인 유사도 → top_k 선택 → 유사도 내림차순 반환.
```

---

💻 **코드 셀** (워밍업)

```python
# 이미 저장된 인덱스 로드 후 수동 검색
with tempfile.TemporaryDirectory() as tmpdir:
    session_dir = Path(tmpdir) / "test-001"
    idx_path = build_index(sample_session, session_dir, chunk_size=80)
    data = json.loads(idx_path.read_text(encoding="utf-8"))

query = "ONNX 런타임 필요 여부"
query_vec = embed_texts([query])[0]

# 각 청크와 유사도 계산
from src.indexer import cosine_similarity
scores = [(cosine_similarity(query_vec, c["embedding"]), i) for i, c in enumerate(data)]
scores.sort(reverse=True)

print("유사도 순위:")
for score, idx in scores:
    print(f"  청크 {idx} (turn {data[idx]['turn_start']}~{data[idx]['turn_end']}): {score:.3f}")
```

---

💻 **코드 셀** (미니 실습)

```python
def rank_chunks(query_vec: list[float], index_data: list[dict]) -> list[dict]:
    """각 청크에 score를 추가하고 코사인 유사도 내림차순으로 정렬해 반환한다.
    
    반환: [{"text": str, "score": float, "turn_start": int, "turn_end": int}, ...]
    힌트:
    - cosine_similarity(query_vec, c["embedding"]) for c in index_data
    - {**c, "score": score} 로 기존 필드 유지하며 score 추가
    - sorted(..., key=lambda x: x["score"], reverse=True)
    """
    from src.indexer import cosine_similarity
    # TODO
    pass
```

---

💻 **코드 셀** (채점)

```python
sample_index = [
    {"text": "ONNX 런타임 포함됨", "embedding": [1.0, 0.0], "turn_start": 2, "turn_end": 3},
    {"text": "pip install",        "embedding": [0.0, 1.0], "turn_start": 0, "turn_end": 1},
]
q_vec = [0.9, 0.1]  # 첫 번째 청크와 더 유사

ranked = rank_chunks(q_vec, sample_index)
assert len(ranked) == 2,                    "청크 수 유지"
assert ranked[0]["turn_start"] == 2,        "유사도 높은 청크가 1위"
assert ranked[0]["score"] > ranked[1]["score"], "내림차순 정렬"
assert "text" in ranked[0],                 "text 필드 유지"
print(f"1위: turn {ranked[0]['turn_start']}~{ranked[0]['turn_end']}, score={ranked[0]['score']:.3f}")
print("✓ 통과")
```

---

💻 **코드 셀** (본 실습)

```python
def search(query: str, index_path: Path, top_k: int = 3) -> list[dict]:
    """코사인 유사도로 상위 top_k 청크를 검색한다.
    
    반환: [{"text": str, "score": float, "turn_start": int, "turn_end": int}, ...]
          유사도 내림차순 정렬
    
    인덱스 파일이 없으면 [] 반환.
    
    힌트:
    - json.loads(index_path.read_text()) 로 인덱스 로드
    - embed_texts([query])[0] 로 쿼리 임베딩
    - 각 청크와 cosine_similarity 계산
    - sorted(..., key=lambda x: x["score"], reverse=True)[:top_k]
    """
    # TODO
    pass
```

---

💻 **코드 셀** (채점)

```python
with tempfile.TemporaryDirectory() as tmpdir:
    session_dir = Path(tmpdir) / "test-001"
    idx_path = build_index(sample_session, session_dir, chunk_size=80)
    
    results = search("ONNX 런타임 설치 필요 여부", idx_path, top_k=2)
    
    assert isinstance(results, list), "리스트 반환"
    assert len(results) <= 2, "top_k 이하"
    assert "text" in results[0] and "score" in results[0], "필드 확인"
    assert results[0]["score"] >= results[-1]["score"], "유사도 내림차순"
    
    # 존재하지 않는 인덱스
    empty = search("질문", Path("/없는/경로/index.json"), top_k=3)
    assert empty == [], "파일 없으면 빈 리스트"
    
    print(f"1위: turn {results[0]['turn_start']}~{results[0]['turn_end']}, score={results[0]['score']:.3f}")
    print("✓ 통과")
```

---

📝 **마크다운 셀**

```
**연결:** `search()`는 server.py `POST /api/query-semantic`에서 호출된다.
evaluator.py `run_baseline()`도 각 질문마다 search()를 호출해 top-k를 얻는다.

---
## 섹션 3 — RAG 호출 (multi-turn + trim)

검색된 청크를 system 프롬프트에 넣고 Groq를 호출한다.
대화 이력이 쌓이면 오래된 것부터 제거한다.
```

---

💻 **코드 셀** (워밍업)

```python
# 검색 결과 → system 프롬프트 구성 패턴
with tempfile.TemporaryDirectory() as tmpdir:
    session_dir = Path(tmpdir) / "test-001"
    idx_path = build_index(sample_session, session_dir)

results = search("설치 방법", idx_path, top_k=2)

context = "\n\n---\n\n".join(r["text"] for r in results)
system_content = (
    "아래는 사용자와 AI가 나눈 대화 내용입니다. "
    "이 내용을 근거로 질문에 답하세요.\n\n"
    + context
)

messages = [
    {"role": "system",  "content": system_content},
    {"role": "user",    "content": "fastembed는 어떻게 설치하나요?"},
]

print(f"system 길이: {len(system_content)}자")
print(f"messages 구조: {[m['role'] for m in messages]}")
```

---

💻 **코드 셀** (미니 실습)

```python
def build_rag_messages(results: list[dict], question: str, history: list[dict]) -> list[dict]:
    """검색 결과와 질문으로 Groq 호출용 messages 배열을 만든다.
    
    구조: [system(top-k 청크 컨텍스트), ...history, user(question)]
    
    힌트:
    - "\n\n---\n\n".join(r["text"] for r in results) 로 컨텍스트 구성
    - system: "아래는 ... 대화 내용입니다. 이 내용을 근거로 답하세요.\n\n" + context
    - history는 기존 user/assistant 쌍
    - 마지막에 user 메시지 추가
    """
    # TODO
    pass
```

---

💻 **코드 셀** (채점)

```python
msgs = build_rag_messages(results, "설치 방법은?", [])
assert msgs[0]["role"] == "system", "첫 번째가 system"
assert "대화 내용" in msgs[0]["content"], "system에 설명 포함"
assert msgs[-1]["role"] == "user", "마지막이 user"
assert msgs[-1]["content"] == "설치 방법은?", "질문 포함"

# 이력 있는 경우
history = [{"role": "user", "content": "이전 질문"},
           {"role": "assistant", "content": "이전 답변"}]
msgs2 = build_rag_messages(results, "다음 질문", history)
roles = [m["role"] for m in msgs2]
assert roles == ["system", "user", "assistant", "user"], f"순서 확인: {roles}"
print("✓ 통과")
```

---

💻 **코드 셀** (미니 실습)

```python
def trim_history(messages: list[dict], max_turns: int = 10) -> list[dict]:
    """messages에서 최근 max_turns 쌍(user+assistant)만 유지한다.
    
    system 메시지는 항상 첫 번째에 유지.
    user/assistant 교대 쌍 기준으로 오래된 것부터 제거.
    
    힌트:
    - messages[0]["role"] == "system" 확인
    - system 이후 메시지를 pair 단위(2개씩)로 끊어 최신 max_turns 쌍만 유지
    """
    # TODO
    pass
```

---

💻 **코드 셀** (채점)

```python
# system + 6쌍 = 13개
msgs = [{"role": "system", "content": "ctx"}]
for i in range(6):
    msgs.append({"role": "user",      "content": f"q{i}"})
    msgs.append({"role": "assistant", "content": f"a{i}"})

trimmed = trim_history(msgs, max_turns=3)
assert trimmed[0]["role"] == "system", "system 유지"
assert len(trimmed) == 7, f"system + 3쌍 = 7, 실제: {len(trimmed)}"
assert trimmed[1]["content"] == "q3", f"q3부터 시작, 실제: {trimmed[1]['content']}"

# system 없는 경우
msgs_no = [{"role": "user", "content": f"q{i}"} for i in range(6)]
trimmed2 = trim_history(msgs_no, max_turns=2)
assert len(trimmed2) == 2, "system 없으면 단순 슬라이싱"
print("✓ 통과")
```

---

📝 **마크다운 셀**

```
### 실제 RAG 실험

`_groq.py` 구현 완료 후 실행.
실제 세션 데이터로 질문해보고 검색된 청크와 답변을 함께 확인한다.
```

---

💻 **코드 셀** (본 실습)

```python
# _groq.py 구현 완료 후 실행
from src._groq import chat_completion, load_env_key

def run_rag_query(question: str, index_path: Path, api_key: str, top_k: int = 3) -> str:
    """벡터 검색 → Groq 호출 → 답변 반환.
    
    힌트:
    - search(question, index_path, top_k)
    - build_rag_messages(results, question, [])
    - chat_completion(messages, "llama-3.3-70b-versatile", api_key, max_tokens=512, temperature=0.0)
    """
    # TODO
    pass

# 실험: 실제 session.json에서 테스트
# session_path = Path("../../conversations_learning/{session_id}.json")
# session = json.loads(session_path.read_text(encoding="utf-8"))
# session_dir = session_path.parent / session["session_id"]
# idx_path = build_index(session, session_dir)
# 
# API_KEY = load_env_key()
# answer = run_rag_query("이 대화에서 사용한 모델 이름은?", idx_path, API_KEY)
# print(answer)
```

---

📝 **마크다운 셀**

```
**연결:**
- `build_rag_messages()`, `trim_history()` → `chat.js`에서 JS로 동일 로직 구현
- `run_rag_query()` 패턴 → `evaluator.py run_baseline()` 내부에서 사용

---
## 스스로 정리해보기

노트북 완료 후 직접 작성:
- 고정 크기 청크 RAG에서 Hit Rate가 낮게 나오는 전형적인 케이스는?
- top_k를 늘리면 답변 품질이 항상 좋아지는가? 언제 나빠지는가?
- 인덱스를 매번 재계산하지 않는 이유는?
```
