# RAG 평가용 합성 대화 데이터 생성 요청

## 배경

이 프로젝트는 AI 대화 내보내기 파일을 열람하고, 대화 내용을 기반으로 RAG(검색 증강 생성) 채팅을 제공하는 로컬 뷰어입니다.

RAG 시스템을 평가하려면 테스트용 대화 데이터가 필요합니다.
실제 개인 대화는 사용할 수 없으므로, **가상의 합성 대화**를 생성해야 합니다.

---

## 핵심 요구사항

### 대화 내용 조건

**반드시 포함해야 하는 것:**
- 구체적이고 고유한 값: 포트 번호, 파일 경로, 에러 메시지, 설정값, 라이브러리 버전, 변수명 등
- AI 응답에 등장한 구체적 값도 포함 (사용자가 명시적으로 확인하지 않아도 됨)
- 여러 주제가 자연스럽게 섞인 실제 대화 느낌 (주제가 깔끔하게 구분되지 않아도 됨)
- 사용자가 새 주제로 넘어가면서 이전 주제의 구체적 정보가 자연스럽게 묻히는 흐름도 자연스러움

**반드시 피해야 하는 것:**
- 일반 지식으로 답할 수 있는 내용 (Python 문법, 알고리즘 개념 등)
- 실제 존재하는 사람 이름, 실제 회사 내부 정보

**핵심 원칙:** 이 대화를 읽지 않은 AI는 QA의 답을 절대 알 수 없어야 합니다.

---

## 생성할 데이터 두 가지

### 1. 짧은 대화 (short)

- **턴 수:** 10~12턴 (user + assistant 각각 1회 = 1턴)
- **주제:** 2~3개가 자연스럽게 섞임
- **목적:** LLM 기본 성능 측정 (baseline이 전체 텍스트를 처리할 수 있는 길이)

### 2. 긴 대화 (long)

- **턴 수:** 30턴 이상
- **주제 특성 (중요):**
  - 주제가 깊어짐: 한 주제에서 막히면 파고들며 여러 턴에 걸쳐 발전
  - 주제가 이어짐: 앞에서 나온 내용이 나중에 다시 언급되거나 전제로 깔림
  - 주제가 얽힘: 서로 다른 주제가 연결되거나 영향을 주고받음
- **목적:** RAG 검색 효과 측정 (baseline은 잘라서 일부를 못 보지만, 벡터 검색은 관련 청크를 찾아냄)

---

## 출력 형식

### session.json

```json
{
  "session_id": "eval-short-001",
  "title": "대화 제목",
  "created_at": "2025-03-10T09:00:00Z",
  "updated_at": "2025-03-10T11:00:00Z",
  "turns": [
    {
      "role": "user",
      "blocks": [{ "type": "text", "text": "사용자 메시지" }]
    },
    {
      "role": "assistant",
      "blocks": [{ "type": "text", "text": "AI 응답" }]
    }
  ]
}
```

- `role`: `"user"` 또는 `"assistant"`만 사용
- `blocks`: 항상 `[{ "type": "text", "text": "..." }]` 형태
- `session_id`: 짧은 대화는 `"eval-short-001"`, 긴 대화는 `"eval-long-001"`

### qa_pairs.json

```json
[
  {
    "question": "질문 (이 대화를 모르면 답할 수 없는 것)",
    "expected": "정답 (대화에서 직접 확인 가능한 구체적 값)"
  }
]
```

- 짧은 대화: QA 8개
- 긴 대화: QA 15개
- 질문은 대화 전반에 걸쳐 고르게 분포할 것 (앞부분, 중간, 뒷부분 모두 포함)
- expected는 짧고 명확하게 (한두 문장)

---

## 좋은 QA 예시

```json
{
  "question": "데이터베이스 연결 포트를 몇 번으로 설정했나요?",
  "expected": "5433번 포트로 설정했습니다."
}
```

```json
{
  "question": "캐시 디렉토리 경로는 어디로 결정했나요?",
  "expected": "/var/app/cache/responses 로 설정했습니다."
}
```

## 나쁜 QA 예시 (사용 금지)

```json
{
  "question": "Python의 list comprehension이란 무엇인가요?",
  "expected": "..."
}
```
→ 이 대화 없이도 AI가 알 수 있는 일반 지식이므로 RAG 평가에 부적합

---

## 요청

위 조건에 맞게 두 쌍을 생성해주세요:

1. `eval-short-001` session.json + qa_pairs.json
2. `eval-long-001` session.json + qa_pairs.json

각각 session.json과 qa_pairs.json을 코드 블록으로 출력해주세요.

---

## [추가] RAGAS 평가용 개선 규칙 (v2)

> 아래 3가지는 RAGAS의 **검색 측 지표**(context_precision / context_recall / Hit Rate)와
> **모드 변별력**(baseline vs vector vs adjacent vs kg)을 확보하기 위한 필수 보강 규칙이다.
> 이 규칙을 지키지 않으면 키워드 검색만으로도 정답이 잡혀 모드 간 점수 차이가 사라진다.

### 1. `source_turns` (골드 청크 레이블) — 스키마 추가

`qa_pairs.json`의 각 항목에 `source_turns` 필드를 추가한다.

```json
{
  "question": "...",
  "expected": "...",
  "source_turns": [16, 17],
  "type": "single"
}
```

- **정의:** 정답의 근거가 실제로 들어있는 메시지의 인덱스 목록.
- **인덱스 기준:** `session.json`의 `turns` 배열에 대한 **0-based 인덱스**
  (turns[0] = 첫 user 메시지, turns[1] = 첫 assistant 메시지 …).
- **용도:** RAGAS의 NonLLM context precision/recall, CLAUDE.md의 Hit Rate를 LLM 없이 결정론적으로 계산.
- **주의:** 이 값은 런타임 리트리버가 잡는 게 아니라 **데이터 작성자가 고정해두는 정답 레이블**이다
  (정답을 채점 대상이 만들면 순환논리가 됨).

### 2. paraphrase (동의어 질문) — 내용 규칙

질문 일부는 대화 원문에 등장한 표현을 **그대로 쓰지 말고 동의어/우회 표현**으로 작성한다.
(예: 원문 "fastembed" → 질문 "임베딩 라이브러리"; 원문 "TTL" → 질문 "만료 시간")

- 목적: 키워드(LIKE) 검색만으로 못 맞히게 해서 벡터·KG의 동의어 매칭 이점을 점수로 드러냄.
- 비율 권장: 짧은 대화 QA의 약 1/4, 긴 대화 QA의 약 1/4 이상.
- `type` 필드에 `"paraphrase"`로 표시.

### 3. 멀티홉 질문 — 내용 규칙 (긴 대화 필수)

긴 대화에는 **2개 이상의 턴/토픽을 합쳐야만 답이 나오는** 질문을 최소 4개 포함한다.

- 목적: 인접 게이팅과 KG 관계(leads_to, resolves)가 실제로 쓰이는지, baseline이 잘려서
  못 맞히는 걸 vector가 맞히는지를 측정.
- `source_turns`에 서로 떨어진 인덱스가 2개 이상 들어간다 (예: `[9, 13, 16, 17]`).
- `type` 필드에 `"multihop"`으로 표시.

### `type` 필드 값

- `"single"`: 단일 사실 조회
- `"paraphrase"`: 동의어/우회 표현 질문
- `"multihop"`: 다중 턴 결합 질문

### RAGAS 적재 매핑 메모

| qa_pairs.json | RAGAS SingleTurnSample | 채움 시점 |
|---|---|---|
| `question` | `user_input` | 데이터셋 |
| `expected` | `reference` | 데이터셋 |
| `source_turns` | `reference_contexts` / Hit Rate 골드 | 데이터셋 |
| (RAG 실행 결과) | `retrieved_contexts` | 평가 시 RAG 실행 |
| (RAG 실행 결과) | `response` | 평가 시 RAG 실행 |

> 참고: RAGAS 0.2/0.3 기준 필드명은 `user_input` / `retrieved_contexts` / `response` / `reference`.
> 한국어+영문 기술용어 혼용이므로 answer_similarity·answer_relevancy용 임베딩은 multilingual 계열을 쓸 것.

### 수량/분포 (v2 기준)

- 짧은 대화: QA 8개 (paraphrase 1~2개 포함)
- 긴 대화: QA 15개 (multihop 4개 이상, paraphrase 3개 이상)
- 질문은 앞·중간·뒷부분에 고르게 분포 (source_turns 인덱스가 한쪽에 몰리지 않게)

### 이용 모델
Claude - Opus 4.8