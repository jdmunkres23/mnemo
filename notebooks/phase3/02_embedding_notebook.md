# Phase 3-2 노트북 셀 내용 — fastembed 임베딩 + 코사인 유사도 + 고정 크기 청크

셀 타입 표기: **📝 마크다운 셀** / **💻 코드 셀**
각 구분선(`---`) 사이 내용을 해당 타입의 셀에 붙여넣기.

---

📝 **마크다운 셀**

```
# Phase 3-2 — fastembed 임베딩 + 코사인 유사도 + 고정 크기 청크

**목표:** 세션 텍스트를 벡터로 변환하고 코사인 유사도로 검색하는 기반을 구현한다.

**이 노트북을 마치면:**
- [ ] fastembed로 텍스트를 벡터로 변환할 수 있다
- [ ] 코사인 유사도를 직접 구현할 수 있다
- [ ] session.json turns를 고정 크기 청크로 분할할 수 있다

**완성 후 연결:**
`src/indexer.py`의 `embed_texts()`, `cosine_similarity()`, `chunk_session()` 구현
```

---

📝 **마크다운 셀**

```
---
## 섹션 1 — fastembed 기초

fastembed: ONNX 기반, GPU 불필요, 첫 실행 시 모델 다운로드 (~500MB).
`model.embed()` 는 generator를 반환 → `list()` 변환 필요.
```

---

💻 **코드 셀** (워밍업)

```python
from fastembed import TextEmbedding

model = TextEmbedding("intfloat/multilingual-e5-large")

texts = ["fastembed 설치 완료", "코사인 유사도를 구현하자"]
vecs = list(model.embed(texts))

print(f"벡터 수:    {len(vecs)}")
print(f"벡터 차원:  {len(vecs[0])}")
print(f"첫 5개 값:  {list(vecs[0])[:5]}")
# 출력: 벡터 수: 2, 벡터 차원: 1024
```

---

💻 **코드 셀** (미니 실습)

```python
def embed_texts(texts: list[str]) -> list[list[float]]:
    """텍스트 목록을 벡터 목록으로 변환한다.
    
    반환: [[float, ...], ...] — 각 텍스트의 1024차원 벡터
    힌트: list(model.embed(texts)), 각 원소를 list()로 변환
    """
    # TODO
    pass
```

---

💻 **코드 셀** (채점)

```python
vecs = embed_texts(["hello", "world"])
assert len(vecs) == 2,              "텍스트 수만큼 벡터"
assert len(vecs[0]) == 1024,        "multilingual-e5-large = 1024차원"
assert isinstance(vecs[0][0], float), "float 타입"
print("✓ 통과")
```

---

📝 **마크다운 셀**

```
---
## 섹션 1 본 실습 — find_most_similar_by_dot

multilingual-e5-large는 내부적으로 L2 정규화를 거치므로
dot product ≈ cosine similarity (벡터 norm ≈ 1.0).
embed_texts()를 활용해 쿼리와 가장 유사한 텍스트를 찾는다.
```

---

💻 **코드 셀** (본 실습)

```python
def find_most_similar_by_dot(query: str, corpus: list[str]) -> tuple[int, float]:
    """쿼리와 가장 유사한 텍스트의 인덱스와 dot product 유사도를 반환한다.
    
    반환: (가장 유사한 인덱스, 유사도 점수)
    힌트:
    - embed_texts([query])[0]  → query_vec
    - embed_texts(corpus)      → corpus_vecs
    - sum(a * b for a, b in zip(v1, v2)) → dot product
    - max(enumerate(scores), key=lambda x: x[1]) → (index, score)
    """
    # TODO
    pass
```

---

💻 **코드 셀** (채점)

```python
texts = ["fastembed 설치 방법", "코사인 유사도 구현", "오늘 점심 메뉴"]
idx, score = find_most_similar_by_dot("pip install 방법", texts)

assert idx == 0,           f"'fastembed 설치 방법'이 가장 유사, 실제: {idx}"
assert 0.5 < score <= 1.0, f"유사도 범위 초과: {score:.3f}"

idx2, _ = find_most_similar_by_dot("벡터 유사도 측정", texts)
assert idx2 == 1, f"'코사인 유사도 구현'이 더 유사, 실제: {idx2}"
print(f"'pip install 방법' → [{idx}] {texts[idx]} ({score:.3f})")
print("✓ 통과")
```

---

📝 **마크다운 셀**

```
**연결:** `embed_texts()`는 `indexer.py build_index()`에서 청크마다 임베딩 생성 시 호출된다.
dot product 유사도는 섹션 2의 `cosine_similarity()`로 형식화된다.

---
## 섹션 2 — 코사인 유사도

cosine_similarity(a, b) = dot(a, b) / (norm(a) × norm(b))

방향이 같으면 1.0, 직교하면 0.0, 반대 방향이면 -1.0.
```

---

💻 **코드 셀** (워밍업)

```python
import math

a = [1.0, 0.0, 0.0]
b = [0.0, 1.0, 0.0]  # a와 직교
c = [1.0, 0.0, 0.0]  # a와 동일

def manual_cosine(x, y):
    dot   = sum(xi * yi for xi, yi in zip(x, y))
    norm_x = math.sqrt(sum(xi**2 for xi in x))
    norm_y = math.sqrt(sum(yi**2 for yi in y))
    return dot / (norm_x * norm_y)

print(f"a vs b (직교): {manual_cosine(a, b):.3f}")  # 0.0
print(f"a vs c (동일): {manual_cosine(a, c):.3f}")  # 1.0
```

---

💻 **코드 셀** (미니 실습)

```python
def cosine_similarity(a: list[float], b: list[float]) -> float:
    """두 벡터의 코사인 유사도를 반환한다.
    
    반환: -1.0 ~ 1.0
    힌트: dot(a, b) / (norm(a) * norm(b)), norm이 0이면 0.0 반환
    """
    # TODO
    pass
```

---

💻 **코드 셀** (채점)

```python
assert abs(cosine_similarity([1,0,0], [1,0,0]) - 1.0) < 1e-6, "동일 벡터 → 1.0"
assert abs(cosine_similarity([1,0,0], [0,1,0]) - 0.0) < 1e-6, "직교 → 0.0"
assert abs(cosine_similarity([1,0,0], [-1,0,0]) + 1.0) < 1e-6, "반대 → -1.0"
assert cosine_similarity([0,0,0], [1,0,0]) == 0.0, "영 벡터 → 0.0"

# 실제 임베딩으로 의미 유사도 확인
vecs = embed_texts(["RAG 구현", "검색 증강 생성", "날씨 정보"])
print(f"'RAG 구현' vs '검색 증강 생성': {cosine_similarity(vecs[0], vecs[1]):.3f}")  # 높음
print(f"'RAG 구현' vs '날씨 정보':      {cosine_similarity(vecs[0], vecs[2]):.3f}")  # 낮음
print("✓ 통과")
```

---

📝 **마크다운 셀**

```
---
## 섹션 2 본 실습 — find_most_similar

embed_texts()와 cosine_similarity()를 조합해 쿼리와 가장 유사한 텍스트를 찾는다.
indexer.py search()의 핵심 로직을 단순화한 버전이다.
```

---

💻 **코드 셀** (본 실습)

```python
def find_most_similar(query: str, corpus: list[str]) -> tuple[int, float]:
    """쿼리와 가장 유사한 텍스트의 인덱스와 코사인 유사도를 반환한다.
    
    반환: (가장 유사한 인덱스, 유사도 점수)
    힌트:
    - embed_texts([query])[0]  → query_vec
    - embed_texts(corpus)      → corpus_vecs
    - cosine_similarity(query_vec, v) for v in corpus_vecs
    - max(enumerate(scores), key=lambda x: x[1])
    """
    # TODO
    pass
```

---

💻 **코드 셀** (채점)

```python
corpus = ["벡터 유사도 검색", "기계 번역 모델", "점심 뭐 먹지"]
idx, score = find_most_similar("코사인 유사도로 검색", corpus)

assert idx == 0,           f"'벡터 유사도 검색'이 가장 유사, 실제: {idx}"
assert 0.5 < score <= 1.0, f"유사도 범위 초과: {score:.3f}"

idx2, _ = find_most_similar("기계 번역", corpus)
assert idx2 == 1, f"'기계 번역 모델'이 더 유사, 실제: {idx2}"
print(f"'코사인 유사도로 검색' → [{idx}] {corpus[idx]} ({score:.3f})")
print("✓ 통과")
```

---

📝 **마크다운 셀**

```
**연결:** `find_most_similar()`의 구조가 `indexer.py search()`의 핵심.
search()는 여기서 한 발 더 나아가 top_k개를 반환하고 인덱스 파일에서 데이터를 로드한다.

---
## 섹션 3 — 고정 크기 청크 분할

turns를 순서대로 이어붙이다 chunk_size(글자 수) 초과 시 새 청크 시작.
반환 형식: [{"text": str, "turn_start": int, "turn_end": int}, ...]
```

---

💻 **코드 셀** (워밍업)

```python
import sys
sys.path.insert(0, "..")

# 테스트용 세션
sample_session = {
    "turns": [
        {"role": "user",      "blocks": [{"type": "text", "text": "fastembed 설치 방법은?"}]},
        {"role": "assistant", "blocks": [{"type": "text", "text": "pip install fastembed로 설치합니다."}]},
        {"role": "user",      "blocks": [{"type": "text", "text": "ONNX 런타임도 필요한가요?"}]},
        {"role": "assistant", "blocks": [{"type": "text", "text": "fastembed이 자동으로 포함합니다."}]},
        {"role": "user",      "blocks": [{"type": "text", "text": "multilingual-e5-large 크기는?"}]},
        {"role": "assistant", "blocks": [{"type": "text", "text": "약 500MB입니다."}]},
    ]
}

# turn별 text 추출 패턴 확인
for i, turn in enumerate(sample_session["turns"]):
    role = "사용자" if turn["role"] == "user" else "AI"
    text = " ".join(b["text"] for b in turn["blocks"] if b["type"] == "text")
    print(f"turn {i} [{role}] {len(text)}자")
```

---

💻 **코드 셀** (미니 실습)

```python
def format_turn(turn: dict) -> str | None:
    """turn 하나에서 text 블록을 추출해 "[사용자]\n텍스트" 형식으로 반환한다.
    
    text 블록이 없으면 None 반환.
    여러 text 블록은 줄바꿈으로 합친다.
    
    힌트:
    - role_label = "사용자" if turn["role"] == "user" else "AI"
    - b["type"] == "text" 인 블록만 필터링
    - f"[{role_label}]\n{text}"
    """
    # TODO
    pass
```

---

💻 **코드 셀** (채점)

```python
user_turn = {"role": "user",      "blocks": [{"type": "text", "text": "fastembed 설치 방법은?"}]}
asst_turn = {"role": "assistant", "blocks": [{"type": "text", "text": "pip install fastembed"}]}
no_text   = {"role": "user",      "blocks": [{"type": "thinking", "thinking": "생각 중..."}]}

u = format_turn(user_turn)
a = format_turn(asst_turn)
n = format_turn(no_text)

assert u == "[사용자]\nfastembed 설치 방법은?", f"사용자 포맷 오류: {u!r}"
assert a == "[AI]\npip install fastembed",      f"AI 포맷 오류: {a!r}"
assert n is None,                               "text 블록 없으면 None"
print("✓ 통과")
```

---

💻 **코드 셀** (본 실습)

```python
def chunk_session(session: dict, chunk_size: int = 2000) -> list[dict]:
    """session.json의 turns를 고정 크기 청크로 분할한다.
    
    반환: [{"text": str, "turn_start": int, "turn_end": int}, ...]
    
    분할 방법:
    - turn을 [사용자]/[AI] 포맷으로 이어붙이다 chunk_size 초과 시 현재까지 저장, 새 청크 시작
    - text 블록만 포함 (thinking, tool_use 등 제외)
    - turn 간 구분자: "\n\n---\n\n"
    - chunk_size=0이면 전체를 단일 청크로
    - 청크가 비어있으면 크기 초과해도 일단 추가 (빈 청크 방지)
    
    힌트:
    - 현재 청크 parts 리스트에 turn 추가 전에 길이 확인
    - "\n\n---\n\n".join(parts) 로 text 생성
    - 마지막 청크 저장 잊지 말기
    """
    _SEP = "\n\n---\n\n"
    # TODO
    pass
```

---

💻 **코드 셀** (채점)

```python
chunks = chunk_session(sample_session, chunk_size=100)
print(f"청크 수: {len(chunks)}")
for i, c in enumerate(chunks):
    print(f"  청크 {i}: turn {c['turn_start']}~{c['turn_end']}, {len(c['text'])}자")

assert len(chunks) >= 2, "100글자 제한에서 최소 2개 청크"
assert chunks[0]["turn_start"] == 0, "첫 청크는 turn 0부터"
assert chunks[-1]["turn_end"] == len(sample_session["turns"]) - 1, "마지막 turn 포함"

# 모든 turn이 누락 없이 포함되는지
covered = set()
for c in chunks:
    covered.update(range(c["turn_start"], c["turn_end"] + 1))
assert covered == set(range(len(sample_session["turns"]))), "모든 turn 포함"

# 크기 제한 없음
chunks_full = chunk_session(sample_session, chunk_size=0)
assert len(chunks_full) == 1, "제한 없으면 단일 청크"
print("✓ 통과")
```

---

📝 **마크다운 셀**

```
**연결:** `chunk_session()`은 `indexer.py build_index()`의 첫 번째 단계.
분할된 청크를 `embed_texts()`로 임베딩한 뒤 session_index.json에 저장.

다음 노트북(03_baseline_rag)에서 build_index()와 search()를 구현한다.

---
## 스스로 정리해보기

노트북 완료 후 직접 작성:
- fastembed가 generator를 반환하는 이유는? list()로 변환하지 않으면 어떻게 되는가?
- 코사인 유사도가 L2 정규화된 벡터에서는 dot product와 같은 이유는?
- chunk_size를 너무 작게 하면 어떤 문제가 생기는가? 너무 크면?
```
