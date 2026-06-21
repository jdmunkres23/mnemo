# AI Conversation Viewer — 프로젝트 컨텍스트

## 개요

Claude.ai 대화 내보내기 데이터를 파싱해 브라우저에서 열람하고,
대화 내용을 기반으로 AI 채팅(RAG)을 제공하는 오픈소스 로컬 뷰어.

- Groq API 사용 (`.env`에 키 입력, 소스코드에 하드코딩 금지)
- 완전 로컬 실행, 외부 서버 없음
- fastembed + SQLite 외 추가 패키지 없음 (Groq 호출은 내장 urllib 사용)
- GitHub 공개 레포 — Anthropic/Claude 브랜드 요소 없음 (저작권 중립 디자인)

---

## CLI

```bash
python -m viewer                         # 현재 폴더 conversations_learning/ 기준 뷰어 실행
python -m viewer --port 9000
python -m viewer --no-browser
python -m viewer --data-dir PATH         # 데이터 디렉토리 직접 지정

python -m parser --input PATH            # Claude.ai 내보내기 JSON → conversations_learning/ 변환
python -m parser --input PATH --output-dir PATH

python -m evaluator --session PATH --modes baseline,vector
python -m evaluator --session PATH --modes vector,vector_adjacent,vector_kg
python -m evaluator --session PATH --qa-pairs PATH   # 기존 QA 쌍 재사용
python -m evaluator --session PATH --max-chars 0     # 컨텍스트 자르기 없음 (짧은 대화용)
python -m evaluator --no-judge                       # 답변만 생성 (Claude 외부 채점용)
python -m evaluator --load-judgments PATH            # 기존 판정으로 채점만
```

---

## 파일 구조

```
project-root/
├── src/
│   ├── parser.py          Claude.ai 내보내기 JSON → session.json 변환
│   ├── models.py          Pydantic 데이터 스키마 (블록 타입 포함)
│   ├── server.py          HTTP 서버 + API 라우팅
│   ├── _groq.py           Groq API 래퍼 (urllib 기반, Cloudflare UA 우회)
│   ├── indexer.py         fastembed 임베딩 + 벡터 검색
│   ├── knowledge_graph.py 엔티티/관계 추출 + SQLite KG (벡터 엔티티 포함)
│   ├── evaluator.py       RAG 평가 파이프라인
│   └── viewer/
│       ├── index.html
│       ├── style.css
│       ├── app.js
│       ├── chat.js        AI 채팅 패널 로직 (세션별 기록 저장/복원)
│       └── renderers/     블록 타입별 렌더러 (text, thinking, tool_use 등)
├── notebooks/
│   ├── phase0/            EDA (데이터 구조 탐색)
│   ├── phase1/            파서 + Pydantic 스키마 실습
│   ├── phase2/            서버 + 뷰어 실습
│   ├── phase3/            baseline RAG + 평가 실습
│   ├── phase4/            벡터 검색 실습
│   └── phase5/            점진적 개선 실습 (인접 게이팅, KG)
│   (각 phase 폴더: [주제]_theory.md + [번호]_[주제]_notebook.md, AI 무관 영역은 _overview.md)
├── conversations_learning/       변환된 세션 데이터 (gitignore)
├── eval_data/             평가용 합성 대화·QA 쌍·결과 (gitignore)
├── tests/
├── pyproject.toml
├── README.md
└── .env                   Groq API 키 (gitignore)
```

---

## 데이터 구조

### Claude.ai 내보내기 포맷

실제 파일 기준으로 확인 완료 (Phase 0 EDA). 정확한 필드명은 `docs/memo.md` Phase 0 결론 참고.

### 내부 session.json 스키마

```json
{
  "session_id": "string",
  "title": "string",
  "created_at": "ISO8601",
  "updated_at": "ISO8601",
  "turns": [
    {
      "role": "user | assistant",
      "blocks": [
        { "type": "text", "text": "..." },
        { "type": "thinking", "thinking": "..." }
      ]
    }
  ],
  "branches": [
    [ { "role": "user | assistant", "blocks": [...] } ],
    [ { "role": "user | assistant", "blocks": [...] } ]
  ]
}
```

`turns`: 브랜치 분기 전 공통 구간(trunk). 브랜치 없는 대화는 전체 turns.
`branches`: 분기 이후 각 경로의 턴 목록. 브랜치 없으면 `null`.

실제 내보내기 데이터에는 5가지 블록 타입이 존재:

| 타입 | 필드 | 설명 |
|------|------|------|
| `text` | `text` | 일반 텍스트 응답 |
| `thinking` | `thinking` | Extended thinking 내용 (`text` 필드 아님 주의) |
| `tool_use` | `name`, `input` | Artifacts, 웹 검색 등 도구 호출 |
| `tool_result` | `name`, `content[]`, `is_error` | 도구 실행 결과 |
| `token_budget` | `remaining` | 메타데이터 (RAG 입력 제외) |

미래에 새 타입 추가 시 `{ "type": "...", "raw": {...} }` 폴백으로 보존.
RAG/AI 채팅 컨텍스트는 `text` 블록만 사용.

---

## RAG 파이프라인

### 검색 모드 발전 과정

MVP에서 시작해 평가 결과를 보고 단계적으로 개선한다.
각 단계에서 효과가 확인된 것만 다음 단계로 이어간다.

```
Phase 3 — baseline
  전체 대화 텍스트 → Groq → 답변
  문제: 긴 대화에서 토큰 초과 + rate limit 빈발
    ↓
Phase 4 — vector
  토픽 분할 + 요약 임베딩 → 관련 청크만 Groq에 전달
  평가: baseline 대비 Hit Rate + Correctness + Token Usage 비교
    ↓
Phase 5 — vector_adjacent → vector_kg (greedy sequential)
  인접 게이팅 추가 → 평가 → 개선되면 채택
  벡터 KG 추가   → 평가 → 개선되면 채택
    ↓
Phase 6 — dense_x / hyde (선택)
  Phase 5 평가 결과에서 개선 여지가 있을 때만 구현
```

### 인덱싱 흐름 (Phase 4~)

```
session.json
  → detectTopicBoundaries()
      사용자 메시지만 추출 → Groq → 경계 인덱스 반환
      fallback: 글자 수 기준 균등 분할
  → buildTopics()
      경계로 Q&A 그룹화 → 청크별 Groq 요약 (llama-3.1-8b-instant, 2~3문장)
  → fastembed.embed(summary)
      multilingual-e5-large, ONNX CPU 추론
  → session_index.json 저장
      { summary, embedding, position, turn_start, turn_end }
  → KG 빌드 (백그라운드, Phase 5~)
      청크별 엔티티/관계 추출 → knowledge_graph.db
```

### 설계 근거

**왜 사용자 메시지로 경계를 탐지하는가?**
- AI와의 대화에서 주제 전환의 주도권은 사용자에게 있다.
- 사용자 메시지는 답변보다 짧아 Groq 토큰 비용이 절감된다.
- Q&A 단위 청크는 너무 세밀해 요청이 과다해지므로, 주제가 바뀌는 경계를 기준으로 여러 Q&A를 하나의 토픽으로 묶는다.

**왜 인접 게이팅을 쓰는가?**
- 대화 속 주제는 갑자기 바뀌더라도 맥락 속에서 나왔으므로 이전 주제와 연관성이 있다.
- 위치가 붙어 있는 토픽은 이유가 있어 붙어 있는 것이므로, 의미적으로 멀어 보여도 인접 토픽을 후보로 검토한다.
- 단, 무조건 추가하지 않고 실제 유사도를 측정해 임계값을 넘을 때만 포함한다.

**왜 벡터 KG를 쓰는가?**
- 같은 개념이 대화마다 다른 단어로 표현될 수 있다. ("fastembed" / "임베딩 라이브러리" / "벡터화 도구")
- 키워드 매칭으로는 이를 연결할 수 없으므로, 엔티티도 임베딩해 의미적으로 유사한 표현을 함께 검색한다.

### 인접 토픽 게이팅 (Phase 5~)

±1 인접 토픽을 **무조건 추가하지 않는다.**
임베딩은 이미 저장되어 있으므로 추가 비용 없이 실제 유사도 측정.

```python
# indexer.py search() 내부
for neighbor in adjacent_topics:
    neighbor_score = cosine_similarity(query_vec, neighbor["embedding"])
    if neighbor_score > ADJACENT_THRESHOLD:  # 기본값 0.3, 평가로 튜닝
        ctx["score"] = neighbor_score
        context_topics.append(ctx)
```

### 벡터 KG (Phase 5~)

엔티티 검색을 키워드 LIKE → 코사인 유사도로 전환.
"라이브러리 설치 문제" → fastembed 매칭 가능.

```python
# 빌드 시: embed(name + " " + description) → DB 저장
# 검색 시: embed(query) → 엔티티 벡터와 코사인 유사도 → 상위 k개
# 매칭 엔티티의 1홉 관계 자동 포함
# 유사도 < 0.3 → 키워드 LIKE 폴백
```

**knowledge_graph.db 스키마:**
```sql
entities           — name, type, description, embedding (JSON float 배열)
entity_occurrences — entity_name, topic_idx, turn_start, turn_end
relations          — source_name, relation, target_name, topic_idx
```

엔티티 타입: `concept | error | tool | path | config | term`
관계 타입: `uses | requires | defines | resolves | leads_to | relates_to`

### Dense X 명제 모드 (Phase 6, 선택)

```
청크 → Groq로 원자적 명제 추출 → 명제별 fastembed 임베딩
session_index.json에 propositions[] 배열로 추가 저장 (topics[] 병존)
```

명제 추출 프롬프트 원칙:
- 각 사실은 맥락 없이 독립적으로 이해 가능
- 고유명사·경로·에러명은 원문 그대로 포함
- 하나의 사실 = 하나의 문장

### HyDE (Phase 6, 선택)

```
질문 → Groq: 가상의 짧은 답변 생성 → 가상 답변 임베딩 → 토픽 벡터와 비교
```
인덱싱 구조 변경 없음. 검색 시점에만 추가 Groq 호출 1회.

---

## AI 채팅 흐름

### 쿼리 라우팅 (Phase 4~)

세 타입은 "세션 데이터를 얼마나 필요로 하는가" 기준으로 나뉜다.

| 타입 | 컨텍스트 구성 | 대표 예시 |
|------|-------------|----------|
| `simple` | 세션 데이터 없음 | "파이썬 문법 알려줘" |
| `analytical` | 토픽 요약만 (벡터 검색 생략) | "이 방식의 문제점이 뭘까?" |
| `retrieval` | 전체 RAG + KG 파이프라인 | "어떤 파일 수정했어?" |

```
질문 → classifyQuery() (llama-3.1-8b-instant, 20토큰)
  → simple      세션 불필요 → Groq 직접 호출, RAG 생략
  → analytical  전체 흐름 파악 필요, 구체적 사실 불필요 → 토픽 요약만 전달
  → retrieval   구체적 사실(수치·파일명·에러명 등) 필요 → 벡터 검색 + KG → Groq
```

분류 경계: 구체적 수치·파일명·에러명이 언급되면 무조건 `retrieval`. 모호하면 `retrieval`로 폴백.

### retrieval 경로

```
벡터 검색: 질문 임베딩 → 코사인 유사도 top_k=3
           + 인접 게이팅 (유사도 > 0.3인 ±1 토픽만 추가, Phase 5~)
KG 검색:  엔티티 벡터 유사도 → 매칭 엔티티의 1홉 관계 자동 포함 (Phase 5~)

system 프롬프트:
  [주요 내용]   원본 대화 텍스트 (Small-to-Big)
  [인접 맥락]   게이팅 통과한 인접 토픽 원본 (있을 때만)
  [관련 개념]   KG 엔티티 + 관계 (있을 때만)
```

### 증분 업데이트

새 대화 추가 후 AI 채팅 시 마지막 토픽부터 재처리.
`session_index.json`에 `indexed_turn_count`, `last_topic_turn_start` 저장.

---

## RAG 평가

### 신뢰 있는 QA 생성 원칙

평가의 핵심 이슈: **AI가 이미 알고 있는 것을 테스트하면 RAG를 평가하는 게 아니다.**

RAG가 실제로 필요한 질문이어야 평가가 의미 있다:
- 대화 속 개인 파일 경로, 특정 설정값, 고유한 결정 사항
- 대화 없이는 AI가 알 수 없는 프로젝트 고유 맥락
- 일반 지식 질문(Python 문법, 알고리즘 등)은 RAG 없이도 답할 수 있으므로 제외

QA 쌍 생성 방법:
- Claude.ai(Opus)로 생성. 프롬프트 템플릿: `eval_data/eval_data_prompt.md`
- 개인 대화 사용 금지 → 합성 대화 사용 (`eval_data/eval-*.session.json`)

QA 쌍 스키마 (`eval_data/eval-*.qa_pairs.json`):
```json
{
  "question": "이 대화를 모르면 답할 수 없는 질문",
  "expected": "정답 (간결하게)",
  "source_turns": [3, 5],      // 정답 근거가 있는 turns 배열 인덱스 (0-based)
  "key_facts": ["35", "20"],   // 정답에 반드시 포함돼야 할 핵심 값
  "type": "single"             // single | paraphrase | multihop
}
```

- `paraphrase`: 원문 단어 대신 동의어로 질문 (벡터 검색 이점 측정용)
- `multihop`: 2개 이상 turns 합쳐야 답 가능 (`source_turns` 복수, 인접 게이팅·KG 측정용)
- 짧은 대화: paraphrase 1~2개 / 긴 대화: multihop 4개+, paraphrase 3개+

### 평가 모드

| 모드 | 도입 Phase | 검색 방식 |
|------|-----------|----------|
| `baseline` | Phase 3 | 전체 텍스트를 컨텍스트로 사용 |
| `vector` | Phase 4 | 코사인 유사도 top_k |
| `vector_adjacent` | Phase 5 | vector + 인접 게이팅 |
| `vector_kg` | Phase 5 | vector_adjacent + 벡터 KG |
| `hyde` | Phase 6 | HyDE 쿼리 확장 + vector |
| `dense_x` | Phase 6 | 명제 단위 벡터 검색 |

### 평가 지표

| 지표 | 측정 방식 | 도입 시점 |
|------|----------|----------|
| Hit Rate | `source_turns ∩ 검색청크` 비율, 결정론 | Phase 3~ |
| Correctness | `key_facts` 포함 비율 + Claude judge | Phase 3~ |
| Completeness | 멀티홉에서 필요 사실 비율 (key_facts) + Claude judge | Phase 3~ |
| Token Usage | 요청당 평균 토큰 수 | Phase 3~ |
| Faithfulness | 답변이 컨텍스트에 근거하는가, Claude judge | Phase 4~ |

채점 흐름: `--no-judge`로 답변 생성 → `eval_data/eval_scoring_prompt.md` 프롬프트로 Claude(Sonnet 4.6) 채점.
모드 비교 시 **동일 채점자·동일 루브릭** 유지 필수.

### Greedy Sequential 채택 기준

```
이전 모드 대비 Correctness +0.3 이상 → 채택
이전 모드 대비 Correctness +0.3 미만 → 버림
```

multihop Completeness 개선도 함께 확인. 임계값은 QA 수와 분산을 보고 조정 가능.

### 평가 뷰어 패널

```
⚖ 평가 버튼 → 평가 패널
  QA 쌍 입력 또는 자동 생성
  모드 선택 (체크박스)
  [평가 실행]
  ─────────────────────────────
  모드              평균    개선
  baseline          6.2      —
  vector            7.4    +1.2  ✓ 채택
  vector_adjacent   7.9    +0.5  ✓ 채택
  vector_kg         8.1    +0.2  △ 미미
  hyde              7.6    -0.3  ✗ 버림
  ─────────────────────────────
  개별 QA 클릭 → 모드별 답변 나란히 비교
```

---

## 서버 API

```
GET  /viewer/*                      → 정적 파일
GET  /conversations/*               → 변환된 세션 파일
GET  /api/sessions                  → 세션 목록 (session_id, title, updated_at, turn_count, has_branches)
GET  /api/session/<id>              → session.json 반환
GET  /api/index-status?session_id=  → 인덱싱 상태 + topics 배열
GET  /api/kg-status?session_id=     → KG 상태 + 엔티티 수
GET  /api/groq-key-status           → 서버 .env 키 존재 여부 (키 값 미노출)
GET  /api/groq-models?api_key=      → Groq 가용 모델 목록 동적 조회
GET  /api/chat-list?session_id=     → 대화 기록 목록
GET  /api/chat-load?id=             → 대화 기록 전체
POST /api/groq-proxy                → Groq API 프록시 (rate limit 헤더 포함, .env 키 폴백)
POST /api/index-session             → 임베딩 저장 (incremental 지원)
POST /api/query-semantic            → 벡터 검색
POST /api/build-kg                  → KG 빌드
POST /api/kg-query                  → KG 엔티티/관계 검색
POST /api/chat-save                 → 대화 기록 저장
DELETE /api/chat-delete?id=         → 대화 기록 삭제
```

Groq 프록시 필수: Cloudflare가 Python UA를 봇으로 차단 (error 1010).
Python이 rate limit 헤더를 읽어 응답 body에 `rate_limit` 필드로 포함.

---

## UI 설계 원칙

### 저작권 중립 디자인

- Anthropic/Claude 로고, 색상(주황·보라), 아이콘 사용 금지
- 대화 뷰어 구조(버블·역할 구분)는 일반적 UI 패턴으로 저작권 없음
- 독자적인 색상 팔레트와 폰트 사용

### 레이아웃

```
┌─────────────┬─────────────────────────┬────────────────┐
│   사이드바   │      대화 뷰어           │   AI 채팅 패널  │
│  세션 목록   │  (메시지 버블 렌더링)     │  + 평가 패널   │
│             │                         │                │
└─────────────┴─────────────────────────┴────────────────┘
```

### 주요 UI 요소

- **사이드바:** 세션 목록 (제목 + 날짜 + 메시지 수) + 검색 필터
- **대화 뷰어:** 역할별 버블, thinking 블록 기본 접힘, 라이트/다크 모드
- **AI 채팅 패널:** 메시지 목록 + 입력 툴바
  - 툴바: 모델 선택 + 전송 버튼 + Rate Limit 뱃지
- **청크 패널:** 토픽 목록 + 클릭 시 해당 위치 스크롤
- **KG 패널:** 그래프 탭(vis-network) + 목록 탭
- **설정 패널:** Groq API 키 + 모델 설정
- **평가 패널:** QA 입력 + 모드 선택 + 결과 비교

---

## 구현 우선순위

```
Phase 0  EDA
         데이터 구조 탐색, 블록 타입 분포 확인

Phase 1  파서 + Pydantic 스키마
         models.py + parser.py

Phase 2  서버 + 기본 뷰어
         세션 목록 + 대화 렌더링 + 블록 타입 필터

Phase 3  MVP RAG 채팅
         전체 대화 텍스트 → Groq → 답변
         세션별 채팅 기록 저장/복원, 모델 목록 동적 조회
         대화 이력 유지 (multi-turn), rate limit 배지
         baseline 평가 파이프라인 (src/evaluator.py)

Phase 4  벡터 검색 + 평가
         토픽 분할 + 요약 임베딩 + 코사인 유사도 검색
         평가: baseline vs vector (Hit Rate + Correctness + Completeness + Token Usage)
         개선 확인 후 다음 단계 진행

Phase 5  점진적 개선 + 평가 (greedy sequential)
         인접 게이팅 추가 → 평가 → 채택 여부 결정
         벡터 KG 추가   → 평가 → 채택 여부 결정

Phase 6  실험적 기법 (Phase 5 결과 기반으로 필요한 것만)
         Dense X (명제 단위 임베딩)
         HyDE (가상 문서 쿼리 확장)

Phase 7  UI 완성
         청크 패널 + KG 패널 + 평가 패널 + 설정 패널
```

---

## 핵심 설계 원칙

1. **외부 의존성 최소화** — fastembed + groq + SQLite 외 추가 패키지 없음
2. **MVP 우선** — 동작하는 최소 버전부터 시작, 문제를 직접 체감한 뒤 개선
3. **평가 주도** — 개선할 때마다 바로 평가, 수치로 확인된 것만 채택
4. **Small-to-Big** — 요약으로 검색, 원문을 LLM에 전달
5. **역할 분리** — 의미 검색은 벡터, 관계 탐색은 KG
6. **인접 게이팅** — 무조건 추가 아닌 유사도 임계값 통과 시만 추가

---

## 제약 조건

- 절대 경로 하드코딩 금지
- `conversations_learning/`, `data/`, `.env` gitignore (대화 내용, API 키)
- API 키는 `.env`에만 저장, 소스코드에 하드코딩 금지
- Anthropic/Claude 관련 상표·디자인 요소 금지
