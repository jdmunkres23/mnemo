# Phase 3-2 이론 — fastembed 임베딩 + 고정 크기 청크 분할

## 0. 임베딩이 의미를 포착하는 이유

**분포 가설 (Distributional Hypothesis):**
같은 맥락에서 함께 등장하는 단어들은 비슷한 의미를 가진다.

언어 모델은 이 원리로 학습된다:
```
입력: "fastembed를 ___ 하면 벡터가 나온다"
예측: "임베딩" (주변 단어로 빈칸 예측)
→ 이 과정을 수십억 문장에서 반복 → 의미가 벡터에 인코딩됨
```

결과: **비슷한 의미 → 벡터 공간에서 비슷한 방향**

```
"fastembed 설치 방법"  → [0.12, -0.03, 0.45, ...]
"fastembed 어떻게 써"  → [0.11, -0.04, 0.43, ...]  ← 방향이 비슷
"오늘 날씨는 맑음"     → [0.78,  0.91, -0.22, ...] ← 방향이 다름
```

**multilingual-e5-large 배경:**
- 논문: "Text Embeddings by Weakly-Supervised Contrastive Pre-training" (Wang et al., 2022, Microsoft)
- 학습 방식: 관련 있는 텍스트 쌍은 가깝게, 관련 없는 쌍은 멀게 — 대조 학습(Contrastive Learning)
- `multilingual`: 100개 이상 언어 동시 지원 → 한국어 질문 ↔ 한국어 대화 비교 가능
- `large`: 1024차원. small(384차원) 대비 정확도 높음, 속도 느림

---

## 1. 왜 벡터 검색인가

전체 대화를 컨텍스트로 주면 토큰이 낭비되고, 관련 없는 내용이 답변 품질을 낮춘다.
필요한 부분만 꺼내 전달하는 것이 RAG의 핵심이다.

벡터 검색 흐름:
```
텍스트 → [임베딩 모델] → 1024차원 벡터
쿼리 벡터와 저장된 벡터들의 코사인 유사도 계산 → 유사도 높은 순 top-k 반환
```

## 2. fastembed

```bash
# pyproject.toml에 이미 포함됨
pip install fastembed
```

- ONNX 모델 → GPU 없이 CPU 동작
- `intfloat/multilingual-e5-large`: 1024차원, 한국어 포함 다국어 지원
- 첫 실행 시 모델 다운로드 (~500MB), 이후 캐시 사용

```python
from fastembed import TextEmbedding

model = TextEmbedding("intfloat/multilingual-e5-large")
vecs = list(model.embed(["텍스트 예시"]))  # generator → list 변환 필요
# len(vecs[0]) == 1024
```

**왜 generator인가?** 대용량 텍스트를 메모리에 다 올리지 않고 스트리밍으로 처리.
노트북에서는 `list()`로 변환해 사용한다.

## 3. 코사인 유사도

```
cosine_similarity(a, b) = dot(a, b) / (norm(a) × norm(b))
```

- 값 범위: -1 ~ 1 (텍스트 임베딩에서는 보통 0 ~ 1)
- 방향이 같으면 1.0 / 직교하면 0.0 / 반대 방향이면 -1.0
- 벡터 크기가 아니라 **방향**만 비교 → 짧은 텍스트와 긴 텍스트를 공정하게 비교

**왜 유클리드 거리가 아닌가?**

유클리드 거리는 벡터의 크기(길이)에 영향 받는다:
```
"안녕" (짧은 텍스트)                      → 작은 벡터
"안녕하세요. 오늘 fastembed를 설치했는데..." → 큰 벡터
→ 같은 주제여도 길이 차이만으로 거리가 멀어짐
```

코사인 유사도는 L2 정규화(벡터 크기를 1로 맞춤) 후 방향만 비교하므로 길이 무관.
짧은 질문 ↔ 긴 답변도 공정하게 비교할 수 있다.

```python
# multilingual-e5-large는 내부적으로 L2 정규화를 거치므로
# norm(a) ≈ norm(b) ≈ 1.0 → dot product ≈ cosine similarity
```

## 4. 고정 크기 청크 분할 (Phase 3 baseline)

turns를 순서대로 이어붙이다 chunk_size(글자 수) 초과 시 새 청크 시작.

```
[chunk_size = 100]

turn 0 user: "fastembed 설치 방법은?"        [20자]  누계: 20
turn 1 asst: "pip install fastembed"         [20자]  누계: 40
turn 2 user: "ONNX 런타임도 필요한가요?"      [14자]  누계: 54
turn 3 asst: "fastembed이 자동으로 포함합니다" [22자]  누계: 76 → 100 초과 → 청크 1 저장
turn 4 user: "multilingual-e5-large 크기는?"  [21자]  새 청크 시작
turn 5 asst: "약 500MB입니다."                [8자]
→ 청크 2: turn 4~5
```

**저장 형식 (session_index.json):**
```json
[
  {
    "text": "[사용자]\n...\n\n---\n\n[AI]\n...",
    "embedding": [0.12, -0.03, ...],
    "turn_start": 0,
    "turn_end": 3
  },
  {
    "text": "[사용자]\n...\n\n---\n\n[AI]\n...",
    "embedding": [...],
    "turn_start": 4,
    "turn_end": 5
  }
]
```

`turn_start`, `turn_end`: 평가(Hit Rate) 계산 시 정답 turn이 검색 결과에 포함됐는지 확인.

## 5. Phase 3 vs Phase 4 임베딩 전략

|  | Phase 3 (baseline) | Phase 4 (vector) |
|---|---|---|
| 청크 기준 | 글자 수 | 토픽(주제) |
| 임베딩 대상 | 청크 원문 | Groq가 생성한 요약 |
| 한계 | 청크 경계가 주제를 무시 | — |

Phase 3에서 문제를 직접 체감한 뒤 Phase 4에서 개선한다.

## 6. 프로젝트 연결

```
indexer.py
  embed_texts()       → fastembed 임베딩
  cosine_similarity() → 유사도 계산
  chunk_session()     → 고정 크기 청크 분할
  build_index()       → chunk + embed → session_index.json 저장 (노트북 03 구현)
  search()            → 쿼리 임베딩 → top-k 검색 (노트북 03 구현)

server.py
  POST /api/index-session  → build_index() 호출
  POST /api/query-semantic → search() 호출
```
