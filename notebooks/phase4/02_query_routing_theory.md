# Phase 4-2 이론 — 쿼리 분류 + 라우팅

## 0. 동기: 모든 질문에 RAG가 필요한가?

Phase 3까지는 모든 질문에 동일하게 RAG 파이프라인을 실행했다.

```
"파이썬에서 리스트를 정렬하는 방법은?" → 벡터 검색 → Groq
```

이 질문은 세션 데이터와 무관하다. LLM이 이미 알고 있는 일반 지식이다.
벡터 검색을 실행하면:
- 불필요한 Groq 호출 (토큰 낭비)
- 관련 없는 청크가 컨텍스트에 포함되어 답변 품질 저하 가능

**핵심 문제:** 질문 유형에 따라 필요한 컨텍스트가 다르다.

---

## 1. 세 가지 쿼리 타입

"세션 데이터를 얼마나 필요로 하는가" 기준으로 나눈다.

| 타입 | 컨텍스트 | 대표 예시 |
|------|---------|---------|
| `simple` | 세션 불필요 | "파이썬 문법 알려줘", "코사인 유사도란?" |
| `analytical` | 토픽 요약만 | "이 대화에서 주로 어떤 주제를 다뤘나?", "이 방식의 문제점이 뭐야?" |
| `retrieval` | 전체 RAG | "어떤 파일을 수정했어?", "chunk_size 기본값이 뭐야?" |

### 분류 기준 (CLAUDE.md 원칙)

**retrieval로 강제:** 구체적 수치, 파일명, 에러명이 언급되면 무조건 retrieval.
**모호하면 retrieval로 폴백:** 틀린 방향보다 느린 방향이 낫다.

```
"이 대화의 RAG는 어떻게 동작해?"
→ 전체 흐름 파악 필요, 구체적 수치/파일명 없음
→ analytical

"session_index.json에 저장된 필드 목록은?"
→ 구체적 파일명 포함
→ retrieval

"파이썬 dict.get()이 KeyError를 안 내는 이유는?"
→ 세션 무관 일반 지식
→ simple
```

---

## 2. 직관: 왜 라우팅이 좋은가

**비유:** 도서관 사서에게 "파이썬 문법 책 찾아줘"라고 하면,
사서는 사내 전용 문서 보관함을 뒤지지 않는다.
일반 서가로 바로 안내한다.

**근본 문제:**
- 벡터 검색은 질문과 텍스트가 의미적으로 가까운 청크를 찾는다.
- 세션 무관 질문에서 검색된 청크는 우연히 유사도가 높은 텍스트다.
- 이 텍스트가 컨텍스트에 포함되면 LLM이 엉뚱한 방향으로 답변할 수 있다.

**대안 비교:**

| 방식 | 처리 | 단점 |
|------|------|------|
| 항상 RAG | 모든 질문에 검색 실행 | 불필요한 토큰 비용, 노이즈 컨텍스트 |
| **라우팅** | 질문 유형별 다른 경로 | 분류 오류 가능 (simple → retrieval 폴백으로 최소화) |
| 사용자 선택 | UI에서 모드 직접 선택 | UX 저하, 사용자 부담 |

---

## 3. Adaptive RAG 논문 배경

**논문:** "Adaptive-RAG: Learning to Adapt Retrieval-Augmented Large Language Models through Question Complexity" (Jeong et al., 2024)

**핵심 기여:**
작은 분류 모델이 질문 복잡도를 A(단순)/B(단일 검색)/C(다단계 검색)로 분류.
각 경로에서 적합한 검색 전략을 실행.

이 프로젝트에서의 적용:
- Groq (llama-3.1-8b-instant)로 simple/analytical/retrieval 분류 (max_tokens=20)
- 분류 결과에 따라 다른 파이프라인 실행

---

## 4. classifyQuery() 흐름

```
[입력] 질문 텍스트

① Groq 호출 (llama-3.1-8b-instant, max_tokens=20)
   프롬프트:
     "다음 질문을 분류하세요.
      - simple: 이 대화 세션 없이도 답할 수 있는 일반 지식
      - analytical: 대화 전체 흐름 파악 필요, 구체적 사실 불필요
      - retrieval: 특정 수치/파일명/에러명/결정 사항 등 구체적 사실 필요
      
      중요: 모호하면 retrieval로 답하세요.
      
      질문: chunk_size 기본값이 뭐야?
      분류:"

② 응답 파싱
   "retrieval" → "retrieval"
   예상치 못한 값 → "retrieval" (폴백)

③ 라우팅
   simple      → Groq 직접 호출 (RAG 생략)
   analytical  → 토픽 요약 목록만 system에 포함
   retrieval   → 전체 RAG + (Phase 5~) KG
```

**실제 응답 예시:**

```python
# 요청
classify_query("파이썬 list.sort() 사용법은?", session_topics, api_key)
# 응답: "simple"

classify_query("이 대화에서 주로 무엇을 구현했나?", session_topics, api_key)
# 응답: "analytical"

classify_query("CHUNK_SIZE 기본값이 얼마야?", session_topics, api_key)
# 응답: "retrieval"
```

max_tokens=20이면 분류 결과 단어 하나만 반환하므로 비용이 거의 없다.

---

## 5. 라우팅별 컨텍스트 구성

### simple 경로

```
system: "당신은 도움이 되는 AI 어시스턴트입니다."
user:   질문
```

세션 데이터 없음. Groq 직접 호출.

### analytical 경로

```
system:
  "아래는 이 대화 세션의 주요 주제 요약입니다.\n\n"
  + "1. fastembed 설치 및 ONNX 런타임 포함 여부\n"
  + "2. 코사인 유사도 구현 방법\n"
  + "3. chunk_size 기본값 설정 과정\n"
  + ...
  + "\n이 요약을 바탕으로 답변하세요."
user:   질문
```

벡터 검색 없음. 토픽 요약 목록만 전달.
전체 대화 흐름은 파악할 수 있지만 구체적 수치를 물으면 정확도 낮음.

### retrieval 경로 (Phase 4 기준)

```
system:
  "[주요 내용]\n"
  + 검색된 토픽 원문
  + "\n이 내용을 근거로 답변하세요."
user:   질문
```

Phase 5부터 인접 게이팅, KG 검색 결과 추가.

---

## 6. 분류 경계 원칙

**왜 모호하면 retrieval인가?**
- simple 오분류: 세션 데이터 없이 잘못된 답변
- retrieval 오분류: 불필요한 검색 실행 (토큰 낭비는 있지만 오답 위험 없음)

틀린 방향보다 느린 방향이 낫다.

**analytical 판단 기준:**
- 세션이 있어야 답할 수 있지만 (→ simple 제외)
- 수치/파일명 없이 흐름 파악만으로 충분 (→ retrieval로 가지 않아도 됨)
- "어떤 순서로 구현했나?", "이 방법의 장단점은?"

---

## 7. 프로젝트 연결

```
server.py
  classify_query()        → simple/analytical/retrieval 반환
  POST /api/query-semantic → classify_query() 결과에 따라 경로 분기

chat.js
  response.query_type     → 채팅 패널에 분류 결과 표시 가능
```

참고 논문:
- Adaptive-RAG (Jeong et al., 2024)
