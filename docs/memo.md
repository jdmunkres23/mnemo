# 메모

## 브랜치 전략

- `main`: Phase 0까지 공통 작업
- `solution/main`: 정답 구현체. Phase 1부터 완성된 코드 먼저 작성
- `learning/main`: 포트폴리오 메인 (면접관이 보는 브랜치). 교육용 노트북 + 직접 탐색 결과

---

## Phase 0 EDA 결론

### 파서 설계 핵심 결정

**`text` 필드 vs `content` 블록**
- `text` 필드는 모바일 UI 렌더링용 (artifact 플레이스홀더 문자열 삽입됨)
- **파서는 반드시 `content` 블록 사용**

**블록 타입별 처리**
- `thinking` 블록: 내용은 `text`가 아닌 `thinking` 필드에 있음
- `token_budget` 블록: 파서에서 무시, RAG 제외
- 알 수 없는 타입: `RawBlock(type=, raw={})` 폴백으로 보존 + 경고 로그

**tool_use ↔ tool_result 페어링**
- `tool_use.id` ↔ `tool_result.tool_use_id` 로 매칭
- `tool_result` 1개에 `tool_use_id = None` (데이터 결함, 파서에서 None 체크만 추가)
- 매칭 안 되는 `tool_use`는 `create_file` 타입 — 결과 없는 단방향 동작이므로 정상

### RAG 포함 여부

| 블록 | RAG |
|---|---|
| `text` | ✅ 핵심 컨텍스트 |
| `thinking` | ❌ 제외 |
| `tool_use` (artifacts) | 🔶 title + 앞 500자, 별도 인덱스 |
| `tool_use` (나머지) | ❌ 제외 |
| `tool_result` (knowledge) | 🔶 포함 고려 (웹검색 결과) |
| `tool_result` (나머지) | ❌ 제외 |
| `token_budget` | ❌ 제외 |

### artifact 처리 방향 (미결 → 결정)
- RAG 포함하되 전체가 아닌 **title + content 앞 500자** 별도 인덱스
- 검색은 요약본, 히트 시 원본 전달 (Small-to-Big)
- Phase 5 평가 후 전략 재검토

---

## 학습 노트북 구조

### 계층 구조

```
Phase (노트북 1개)
  └─ 섹션 (개념 단위, 여러 개)
       ├─ 이론 설명
       ├─ 워밍업 — 완성 예제 실행
       ├─ 미니 실습 + 채점
       ├─ 본 실습 + 채점
       └─ 섹션 마무리 — 질문/정리
```

### 노트북 전체 구성

```
[첫 번째 셀]  목차 + 학습 목표 체크리스트
[각 섹션]     이론 → 워밍업 → 미니실습/채점 → 본실습/채점 → 섹션 마무리
[마지막 셀]   스스로 정리해보기 (직접 작성) → 요약 (Claude 작성, 피드백 시점)
```

### 피드백 규칙

- phase당 `feedback.md` 1개 (섹션별 파일 분리 X)
- 흐름: 노트북 섹션 완료 → feedback.md에 코드+질문 작성 → Claude 피드백 추가 → 사용자가 적절한 곳에 피드백/정답/요약 등을 직접 셀에 추가
- 막혔을 때: 섹션 마무리 전에 핀포인트 질문만, 정답 전체 요청 X
- 피드백은 **섹션 마무리 기준**으로 진행 (실습 직후 아님)
- 정답은 **틀리거나 모를 때만** 클로드의 피드백을 채점 다음 셀에 사용자가 추가(사용자 코드 유지)

### 폴더 구조 및 피드백 파일 (Phase 2부터)

Phase 1은 노트북 파일이 크므로 대화에 코드 직접 붙여넣기로 피드백 진행.

```
notebooks/
  phase2/
    phase2_*.ipynb
    feedback.md      ← 섹션별 피드백 전부
  phase3/
    ...
```

`feedback.md` 내부 구조:

```markdown
# Phase N 피드백

## 섹션 1: [제목]

### 내 코드
\```python
# 붙여넣기
\```

### 질문
(없으면 생략)

### 피드백
<!-- Claude 작성 -->

---

## 섹션 2: [제목]
...

## 요약

### 사용자 요약

### Claude 요약
<!-- Claude 작성 -->
```

---

## Phase 2 결론

## 학습 노트북 구조 변경 (Phase 3부터 적용)

### 변경 이유

Phase 2까지 방식으로는 이론이 노트북 셀 안에 묻혀서 깊이 있는 개념 설명이 어려웠고, feedback.md 파일 관리가 번거로웠음.

### 계층 구조 변경

```
Phase
  ├─ [주제]_theory.md     이론 전체 (논문 연결, 설계 이유, 트레이드오프)
  └─ [번호]_[주제]_notebook.md   노트북 셀 내용 (핵심 요약 + 실습)
       └─ 섹션 (개념 단위, 여러 개)
            ├─ 이론 요약 (핵심 + 연결만)
            ├─ 워밍업 — 완성 예제 실행
            ├─ 미니 실습 + 채점
            ├─ 본 실습 + 채점
            └─ 섹션 마무리 — 질문/정리
```

### 피드백 방식 변경

- `feedback.md` 사용 안 함
- 실습 완료 후 **Claude 세션에 직접 코드+질문 붙여넣기** → 힌트/피드백 요청
- 세션 끝난 후 요약/정리/질문은 내가 직접 노트북 셀에 작성
- 막혔을 때: 핀포인트 질문만, 정답 전체 요청 X

### AI와 무관한 영역 처리 (추가)

JavaScript 프론트엔드(Phase 2 app.js, Phase 7 UI) 등 AI 직군과 무관한 파트:
- 노트북/실습 없음
- **overview md 파일 1개**로 대체: 파일 구조, 무엇이 추가됐는지, 왜 그렇게 생겼는지, 전체 흐름

---

## 이론 설명 길이 실험

노트북 이론 셀의 적정 분량을 phase별로 달리 시도하며 효과를 기록한다.

### 기준 정의

| 수준 | 분량 기준 | 내용 |
|------|---------|------|
| 짧음 | 5~10줄 | 핵심 개념 1~2문장 + 코드 예시 1개 |
| 중간 | 15~25줄 | 개념 설명 + 왜 이렇게 설계했는지 + 코드 예시 2개 |
| 깊음 | 30~50줄 | 배경 + 설계 이유 + 트레이드오프 + 논문 연결 + 코드 예시 |

### Phase별 계획 및 기록

| Phase | 계획 수준 | 실제 결과 | 메모 |
|-------|---------|---------|------|
| Phase 0 | — | 짧음 | EDA라 이론 셀 없음 |
| Phase 1 | 짧음 | 짧음 | Pydantic 기초, 코드 위주. 개념 배경 설명이 부족했다는 느낌 |
| Phase 2 | 중간 | 시도 예정 | HTTP 서버 + 라우팅 — 왜 이 구조인지 설명 추가해볼 것 |
| Phase 3 | 깊음 | 시도 예정 | RAG 핵심부. 논문 연결 + 설계 근거까지 |
| Phase 4 | 중간~깊음 | 미정 | Phase 3 결과 보고 결정 |
| Phase 5 | 깊음 | 미정 | LLM-as-judge 방법론 — 논문 기반 설명 필수 |

### 평가 기준 (피드백 후 기록)

- 면접관이 노트북만 봤을 때 개념 이해 여부가 보이는가?
- 실습과 이론의 연결이 자연스러운가?
- 너무 길어서 읽기 싫어지는 시점이 어디인가?



## Phase 3

### 평가 설계 결정

**모델 분리**
- 답변 생성: `llama-3.3-70b-versatile` (`_ANSWER_MODEL`)
- 분류·judge 등 단순 작업: `llama-3.1-8b-instant` (`_FAST_MODEL`)

**평가 지표**
- `Hit Rate`: `source_turns ∩ included_turns` 비율, 결정론, LLM 없음
- `key_facts`: 정답 핵심 값 포함 비율 (결정론)
- `Answer Score`: LLM-as-judge (0~10점, temperature=0.0으로 일관성 확보)

**Baseline 구현 방식**
- solution과 달리 **벡터 검색 기반** baseline 채택 (CLAUDE.md 스펙 기준)
- 고정 크기 청크(2000자) 분할 + fastembed 임베딩 + 코사인 유사도 top-k=3 검색
- solution baseline(전체 텍스트 직접 전달)과 비교 기준점이 다름

### Baseline 점수 (Phase 4 비교 기준)

**짧은 대화 (8개, 벡터 검색)**

| 지표 | 점수 |
|------|------|
| Hit Rate | 1.00 |
| key_facts | 0.94 |
| Answer Score | 7.1 / 10 |

**긴 대화 (15개, 벡터 검색)**

| 지표 | 점수 |
|------|------|
| Hit Rate | 0.91 |
| key_facts | 0.77 |
| Answer Score | 5.1 / 10 |

→ 긴 대화에서 Hit Rate는 높지만 key_facts·Answer Score가 낮음 → 고정 청크 경계가 주제를 무시해 답변 품질 저하
→ Phase 4 토픽 기반 청크로 개선 후 위 수치와 비교

### 아쉬운 점
- notebook.md에 인풋이 뭐고 아웃풋이 뭔지 자세한 설명이 없어서 힘들었음.

---

## Phase 4

### 구현 결정

**답변 모델 변경**
- `llama-3.3-70b-versatile` → `meta-llama/llama-4-scout-17b-16e-instruct`
- 이유: 70b TPD 100K로는 long 세션 15개 QA 1회 실행(~97,500 토큰)도 빠듯함
- scout는 TPD 500K → 하루 여러 번 실험 가능

**쿼리 라우팅 평가는 Phase 4에서 제외**
- 라우팅 분류 자체의 정확도 평가는 별도 QA 설계 필요 → 나중에

**Groq 사용량 추적 추가 (`src/usage_tracker.py`)**
- `_groq.py` 호출 성공 시 자동으로 `usage/YYYY-MM-DD.jsonl` 기록
- `python -m src.usage_tracker` 로 모델별 당일 사용량·잔여 토큰 확인
- 분당 토큰 25% 미만 시 자동 sleep

### 버그 수정 (indexer.py)

`detect_topic_boundaries` 내 오타 2개 + `search_vector` 오타 1개:

| 위치 | 버그 | 수정 |
|------|------|------|
| detect_topic_boundaries | `session['turn']` | `session['turns']` |
| detect_topic_boundaries | `" ".json(...)` | `" ".join(...)` |
| search_vector | `embed_texts(query)` | `embed_texts([query])` |

두 함수 모두 오타로 인해 항상 예외 발생 → `_uniform_boundaries(n_topics=5)` fallback으로만 동작 중이었음.
수정 후 Groq가 실제로 토픽 경계를 탐지하게 됨.

### 평가 결과 (llama-4-scout, --no-judge)

**짧은 대화 (8개)**

| 모드 | Hit Rate | key_facts | avg tokens |
|------|----------|-----------|------------|
| baseline | 1.00 | 9.4 | 2,752 |
| vector | 1.00 | 9.4 | 3,674 |

→ 점수는 동일, 토큰은 vector가 더 많음 (short는 차이가 미미)

**긴 대화 (15개)**

| 모드 | Hit Rate | key_facts | avg tokens |
|------|----------|-----------|------------|
| baseline | 0.98 | 9.3 | 2,368 |
| vector | 1.00 | 8.8 | 10,391 |

→ 검색(Hit Rate)은 vector가 더 좋음 (multihop 0.93 → 1.00)
→ 답변(key_facts)은 vector가 더 낮음 — 토픽 원문 top_k=3이 10K 토큰 → LLM이 중간 정보를 놓치는 "lost in the middle" 현상

### 결론 및 다음 단계

- **vector 검색 채택** — Hit Rate가 baseline보다 높으므로 검색 방식은 vector로 확정
- **남은 과제** — LLM에 넘기는 컨텍스트 크기를 줄여 답변 품질 복구
  - 후보: top_k 축소, 토픽 원문 길이 제한
  - 목표: vector keyfact가 baseline(9.3) 이상이 되면 Phase 4 완료

### Phase 5 진행 조건

현재 데이터셋(eval-long-001, 15개 QA)으로는 Phase 5가 필요한 시나리오가 나타나지 않음.
Hit Rate가 이미 1.00이므로 인접 게이팅·KG를 추가해도 검색이 더 좋아질 여지가 없음.

Phase 5는 아래 조건이 갖춰진 뒤 진행:
1. 더 복잡한 평가 데이터셋 구축 — 토픽 20개 이상의 긴 대화, 3홉 이상 multihop 질문
2. 새 데이터셋에서 vector만으로 못 잡는 케이스가 실제로 나올 때 인접 게이팅·KG 추가
3. Phase 5 구현 후 새 데이터셋 기준으로 비교 평가
