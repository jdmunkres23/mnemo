# Phase 3-3 이론 — Baseline RAG (고정 크기 청크 + 벡터 검색)

## 0. RAG 등장 배경

**근본 문제: LLM의 지식은 학습 시점에 고정된다.**

학습 이후 새로운 정보(개인 대화, 사내 문서, 최신 뉴스)를 알 방법이 없다.
이를 해결하는 세 가지 방법과 트레이드오프:

| 방법 | 지식 업데이트 | 비용 | 한계 |
|------|------------|------|------|
| 파인튜닝 | 모델 재학습 | 수천만 원~ | 소량 데이터에 부적합, 학습 후 고정 |
| 전체 컨텍스트 주입 | 즉시 | 저비용 | 컨텍스트 창 한계, 토큰 비용 |
| **RAG** | 인덱스 업데이트 | 저비용 | 검색 품질에 의존 |

**RAG 논문 핵심 기여 (Lewis et al., 2020, NeurIPS):**
"모델 파라미터에 모든 지식을 저장하는 대신, 외부 문서를 실시간으로 검색해 답변 생성에 활용한다."
— 검색(Retrieval) + 생성(Generation)을 결합한 것이 이름의 유래.

이 아이디어를 개인 대화 검색에 적용:
- 대화가 추가되면 인덱스만 업데이트, 모델 재학습 불필요
- 전체 대화 대신 관련 청크만 전달 → 컨텍스트 창 효율

---

## 1. Phase 3 RAG 구조

```
[인덱싱 phase — 1회 실행]
session.json
  → chunk_session()      turns를 N글자 단위로 분할
  → embed_texts()        각 청크 임베딩 (fastembed)
  → session_index.json   {text, embedding, turn_start, turn_end}[] 저장

[쿼리 phase — 질문마다 실행]
질문
  → embed_texts([질문])       질문 임베딩
  → cosine_similarity × 전체 청크  각 청크와 유사도 계산
  → top-k 청크 선택
  → [청크 원문] → system 프롬프트 → Groq → 답변
```

## 2. 인덱스 구축 (build_index)

```python
# 저장 경로: {data_dir}/{session_id}/session_index.json
# 저장 형식:
[
  {
    "text":       "[사용자]\n질문\n\n---\n\n[AI]\n답변",
    "embedding":  [0.12, -0.03, ...],   # 1024차원
    "turn_start": 0,
    "turn_end":   3
  },
  ...
]
```

인덱스가 이미 존재하면 재사용한다 (매번 재계산 불필요).

## 3. 벡터 검색 (search)

```python
# 1. 질문 임베딩
query_vec = embed_texts([question])[0]

# 2. 모든 청크와 코사인 유사도 계산
scores = [(cosine_similarity(query_vec, chunk["embedding"]), chunk)
          for chunk in index]

# 3. 유사도 내림차순 정렬 → top_k 선택
top_chunks = sorted(scores, reverse=True)[:top_k]
```

## 4. 컨텍스트 구성 → Groq 호출

```
system:
  "아래는 사용자와 AI가 나눈 대화 내용입니다. 이 내용을 근거로 질문에 답하세요.\n\n"
  + 청크 1 원문
  + "\n\n---\n\n"
  + 청크 2 원문
  + ...

user: 질문
```

전체 대화 대신 **관련 청크만** 전달 → 토큰 절약 + 노이즈 감소.

## 5. AI 채팅 패널과의 연결

Phase 3 AI 채팅은 `/api/query-semantic` 엔드포인트를 통해 위 흐름을 사용한다:
1. chat.js → `POST /api/index-session` (인덱스 없으면 먼저 빌드)
2. chat.js → `POST /api/query-semantic` (쿼리 전송)
3. chat.js → `POST /api/groq-proxy` (검색된 청크를 context로 Groq 호출)

## 6. 한계 (Phase 4에서 개선)

**청크 경계 문제:**
```
질문: "ONNX 런타임은 어디서 필요한가?"
→ 답이 turn 3에 있지만, 청크가 turn 2~3으로 잘리지 않고 turn 1~4로 묶여 있으면 검색 됨
→ 답이 turn 2~3으로 잘리면서 청크 경계에 걸리면 유사도가 낮아짐
```

고정 크기는 주제 경계를 무시한다. Phase 4에서 주제 기반 청크로 개선.

**요약 없이 원문 임베딩:**
긴 청크에서 핵심 정보가 희석될 수 있다. Phase 4에서 Groq 요약을 임베딩.

## 7. 프로젝트 연결

```
indexer.py
  build_index()  → session_index.json 생성
  search()       → top-k 청크 반환

server.py
  POST /api/index-session   → build_index() 호출
  POST /api/query-semantic  → search() 호출

evaluator.py
  run_baseline()  → 각 질문마다 search() → Groq → 답변 → 지표 계산
```
