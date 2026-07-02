# Phase 4-1 이론 — 토픽 경계 탐지 + 요약 임베딩

## 0. 동기: 고정 크기 청크의 한계

Phase 3 baseline은 turns를 **글자 수 기준**으로 자른다.

```
turn 0: "fastembed 설치 방법은?"
turn 1: "pip install fastembed입니다."
turn 2: "ONNX 런타임은 어디서 필요한가요?"      ← chunk 1 끝 (2000자 초과)
turn 3: "fastembed 내부에 포함되어 있습니다."   ← chunk 2 시작
turn 4: "모델 파일 크기가 얼마나 되나요?"
turn 5: "약 500MB입니다."
```

"ONNX 런타임" 관련 Q&A가 청크 경계에서 잘렸다.
질문은 chunk 1에 있고 답변은 chunk 2에 있어 검색 유사도가 낮아진다.

**핵심 문제:** 고정 크기 분할은 주제(토픽)의 경계를 무시한다.

---

## 1. 직관: 왜 토픽 기반 청크인가

**비유:** 책을 읽을 때 챕터 중간에서 끊으면 이해가 어렵다.
챕터(주제) 단위로 끊어야 각 단위가 완결된 의미를 갖는다.

**근본 문제:**
- RAG에서 검색 단위(청크)는 "하나의 완결된 의미"여야 한다.
- 질문이 "ONNX 런타임" 이야기를 묻는다면, 그 Q&A 전체가 같은 청크에 있어야 검색 유사도가 높아진다.

**대안 비교:**

| 방식 | 원리 | 장점 | 단점 |
|------|------|------|------|
| 고정 크기 | N글자마다 분할 | 단순, 예측 가능 | 주제 경계 무시 |
| 문장 단위 | 마침표/줄바꿈 | 문장 완결성 보장 | 대화 흐름 단절 |
| **토픽 기반** | 사용자가 주제 전환하는 지점 | Q&A 단위 완결성 | Groq 호출 비용 |
| 슬라이딩 윈도우 | N글자, M글자 겹침 | 경계 문제 완화 | 청크 수 증가, 중복 |

**이 프로젝트에서 토픽 기반을 선택한 이유:**
- 사용자 메시지가 주제 전환의 신호다.
- 사용자 메시지만 추출하면 전체 대화보다 토큰이 훨씬 짧다.
- 각 토픽이 독립적인 Q&A 그룹이므로 검색 단위로 자연스럽다.

**논문 배경 (SeCom, ICLR 2025):**
"On Memory Construction and Retrieval for Personalized Conversational Agents"

### SeCom이 보인 실험 결과

세 가지 granularity를 직접 비교:

| 단위 | 문제 | LOCOMO 점수 |
|------|------|------------|
| Turn 단위 | 너무 세밀, 단편적 | 65.58 |
| Session 단위 | 너무 넓음, 무관한 내용 포함 | 63.16 |
| **Segment 단위** | **두 문제 동시 해결** | **71.57** |

논문 자체가 "대화 청킹은 연구가 부족하다"고 명시적으로 지적.

### SeCom의 실제 방법

```
입력: "Turn j:\n[user]: 질문\n[agent]: 답변" (사용자 + AI 전체 발화)

① GPT-4에 zero-shot 지시:
   "같은 주제의 연속된 user-bot 교환은 같은 segment로 묶고,
    주제가 바뀌면 새 segment를 시작하라."

② 출력: JSONL 형식으로 segment 시작/종료 turn 번호
   {"segment": 1, "start": 0, "end": 3}
   {"segment": 2, "start": 4, "end": 8}

③ (선택) Reflection: 오류 케이스 100개 → 루브릭 10항목 학습 → 예시 추출
```

### 이 프로젝트와의 차이

| | SeCom | 이 프로젝트 |
|---|---|---|
| 입력 | 사용자 + AI 전체 발화 | **사용자 메시지만** |
| 이유 | 명시 없음 | 사용자가 주제 전환 주도 |
| 비용 | GPT-4 (비쌈) | llama-3.1-8b-instant (저렴) |
| 출력 | segment 시작/종료 번호 | 경계 turn 인덱스 목록 |

사용자 메시지만 추출하는 방식은 이 프로젝트의 독자적 설계.
토큰 비용이 절반 이하로 줄고, "사용자가 주제 전환의 주도권을 갖는다"는 대화 구조 특성을 명시적으로 활용.

---

## 2. Small-to-Big 검색

**직관:** 도서관에서 책 요약(색인 카드)으로 찾고, 실제 책 내용을 읽어준다.

```
[색인 카드(요약)] "fastembed 설치 및 ONNX 런타임 포함 여부 설명"
       ↓  코사인 유사도 검색
[질문] "ONNX 런타임 필요한가요?"
       ↓  매칭됨
[원문 전달] "fastembed 설치 방법은?\npip install fastembed...\nONNX 런타임은?\nfastembed 내부에..."
```

- **Small**: 요약(짧음)으로 임베딩 → 검색 정확도 향상
- **Big**: 원문(긴 원본)을 LLM에 전달 → 풍부한 컨텍스트

**근본 문제:** 긴 원문을 임베딩하면 핵심 키워드가 희석된다.
"fastembed 설치 방법, ONNX 런타임, 모델 크기 500MB, 초기화 시간..." 을 통째로 임베딩하면
각 주제 어느 쪽으로도 유사도가 평범해진다.

**대안 비교:**

| 방식 | 임베딩 대상 | 전달 대상 |
|------|-----------|---------|
| 원문 임베딩 | 원문 전체 | 원문 |
| **Small-to-Big** | 요약(핵심만) | 원문 전체 |
| 명제 임베딩 (Phase 6) | 원자적 사실 하나 | 해당 문장 |

**논문 배경:**
이 개념의 학술적 근거는 Dense X Retrieval (Chen et al., 2023)이 명제(proposition) 단위로 임베딩하면서 정립했다.
Phase 6에서 명제 단위 임베딩을 구현할 때 자세히 다룬다.
Phase 4에서는 "요약으로 임베딩, 원문을 LLM에 전달"하는 핵심 아이디어만 가져온다.

---

## 3. Adaptive RAG 논문 배경

**논문:** "Adaptive-RAG: Learning to Adapt Retrieval-Augmented Large Language Models through Question Complexity" (Jeong et al., 2024)

**핵심 기여:**
질문 복잡도에 따라 검색 전략을 달리한다.
단순 질문은 검색 없이, 복잡한 질문은 다단계 검색.

이 프로젝트에서는 Adaptive RAG 아이디어를 쿼리 라우팅에 적용:
- **쿼리 라우팅** (02_query_routing) — "이 질문에 검색이 필요한가"를 AI가 분류

토픽 기반 분할은 Adaptive RAG가 아닌 **SeCom** (Section 1 참고)의 근거를 따른다.

---

## 4. detectTopicBoundaries() 흐름

```
[입력] session.json

① 사용자 turn만 추출 (user role)
   → [0] "fastembed 설치 방법은?"
   → [2] "ONNX 런타임도 필요한가요?"
   → [4] "multilingual-e5-large 크기는?"

② Groq 호출 (llama-3.1-8b-instant, 저렴)
   프롬프트:
     "아래는 사용자 메시지 목록입니다 (인덱스: 메시지).
      주제가 크게 바뀌는 경계 직전의 인덱스를 JSON 배열로 반환하세요.
      예: [2, 6, 10]
      
      0: fastembed 설치 방법은?
      2: ONNX 런타임도 필요한가요?
      4: multilingual-e5-large 크기는?"

③ 응답 파싱
   "[4]"  → [4]   (4번 turn부터 새 토픽 시작)

④ fallback: Groq 실패 시 균등 분할
   총 사용자 턴 수 // 5 간격으로 경계 설정
```

**실제 Groq 응답 예시:**

입력 대화가 "fastembed 설치 → 코사인 유사도 구현 → 평가 방법 → 실제 사용 팁" 주제라면:

```
응답: [4, 9, 14]
```

숫자 하나씩 반환하므로 `max_tokens=50` 정도면 충분.

**사용자 메시지만 쓰는 이유 (CLAUDE.md):**
- AI 답변보다 사용자 메시지가 주제 전환 신호
- 답변은 길어 토큰 비용이 크다
- 경계 탐지용이므로 핵심 질문만 있으면 된다

---

## 5. buildTopics() + summarize_topic()

### buildTopics()

경계 인덱스를 기준으로 turns를 그룹화한다.

```python
# boundaries = [4, 9]  → 0~3, 4~8, 9~끝 세 그룹

topics = [
    {
        "text":       "[사용자]\nfastembed 설치 방법은?\n\n---\n\n[AI]\npip install fastembed...",
        "turn_start": 0,
        "turn_end":   3,
        "position":   0,
    },
    {
        "text":       "[사용자]\n코사인 유사도는?\n\n---\n\n[AI]\ndot product / (norm_a * norm_b)...",
        "turn_start": 4,
        "turn_end":   8,
        "position":   1,
    },
    ...
]
```

`position` 필드: Phase 5 인접 게이팅에서 ±1 토픽을 찾을 때 사용.

### summarize_topic()

각 토픽을 Groq로 2~3문장 요약.

```
프롬프트:
  "다음 대화를 핵심 정보만 포함해 2~3문장으로 요약하세요.
   고유명사, 경로, 설정값은 원문 그대로 포함하세요.
   
   [사용자]
   fastembed 설치 방법은?
   
   [AI]
   pip install fastembed 로 설치합니다. ONNX 런타임은 내부에 포함되어 있어
   별도 설치 불필요합니다."

응답:
  "fastembed는 pip install fastembed로 설치하며, ONNX 런타임이 내장되어 있다."
```

요약에는 고유명사가 그대로 남아 검색 유사도가 높아진다.

**실패 시 fallback:** `topic_text[:200]` (앞부분 잘라 사용)

---

## 6. 새 인덱스 구조 (vector_index.json)

Phase 3 `session_index.json` 과 별도로 저장.

```json
[
  {
    "text":       "[사용자]\nfastembed 설치 방법은?\n...",
    "summary":    "fastembed는 pip install fastembed로 설치하며 ONNX 런타임이 내장되어 있다.",
    "embedding":  [0.12, -0.03, ...],
    "position":   0,
    "turn_start": 0,
    "turn_end":   3
  },
  ...
]
```

| 필드 | 용도 |
|------|------|
| `text` | LLM에 전달할 원문 (Small-to-Big의 Big) |
| `summary` | 임베딩된 요약 (Small-to-Big의 Small) |
| `embedding` | `summary` 임베딩 — 검색에 사용 |
| `position` | 토픽 순서 — Phase 5 인접 게이팅 |
| `turn_start/end` | Hit Rate 계산에 사용 |

---

## 7. 프로젝트 연결

```
indexer.py
  detect_topic_boundaries()  → 경계 인덱스 반환
  build_topics()             → 토픽 그룹화
  summarize_topic()          → Groq 요약
  build_vector_index()       → vector_index.json 생성
  search_vector()            → 코사인 유사도 top_k 검색

server.py
  POST /api/index-session    → build_vector_index() 호출 (mode=vector 시)
  POST /api/query-semantic   → search_vector() 호출 (mode=vector 시)

evaluator.py
  run_vector()               → search_vector() 기반 RAG → 답변 생성 → 지표 계산
```

참고 논문:
- SeCom (ICLR 2025) — 대화 토픽 세그멘테이션 근거
- Adaptive-RAG (Jeong et al., 2024) — 쿼리 라우팅 근거 (02_query_routing에서 상세)
- Dense X Retrieval (Chen et al., 2023) — Small-to-Big 학술 근거 (Phase 6에서 상세)
