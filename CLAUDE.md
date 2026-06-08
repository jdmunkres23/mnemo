# AI Conversation Viewer — 프로젝트 컨텍스트

## 개요

Claude.ai 대화 내보내기 데이터를 파싱해 브라우저에서 열람하고,
대화 내용을 기반으로 AI 채팅(RAG)을 제공하는 오픈소스 로컬 뷰어.

- Claude API 호출 없음 (Groq API만 사용, 사용자 키 입력)
- 완전 로컬 실행, 외부 서버 없음
- Python 표준 라이브러리 + fastembed만 사용
- GitHub 공개 레포 — Anthropic/Claude 브랜드 요소 없음 (저작권 중립 디자인)

---

## CLI

```bash
python -m viewer                         # 현재 폴더 conversations/ 기준 뷰어 실행
python -m viewer --port 9000
python -m viewer --no-browser
python -m viewer --data-dir PATH         # 데이터 디렉토리 직접 지정

python -m parser --input PATH            # Claude.ai 내보내기 JSON → conversations/ 변환
python -m parser --input PATH --output-dir PATH
```

---

## 파일 구조

```
project-root/
├── src/
│   ├── parser.py          Claude.ai 내보내기 JSON → session.json 변환
│   ├── models.py          Pydantic 데이터 스키마 (블록 타입 포함)
│   ├── server.py          HTTP 서버 + API 라우팅
│   ├── indexer.py         fastembed 임베딩 + 벡터 검색
│   ├── knowledge_graph.py 엔티티/관계 추출 + SQLite KG (벡터 엔티티 포함)
│   ├── evaluator.py       RAG Ablation Study 파이프라인
│   └── viewer/
│       ├── index.html
│       ├── style.css
│       ├── app.js
│       └── renderers/     블록 타입별 렌더러 (text, thinking, tool_use 등)
├── notebooks/
│   ├── phase0/            EDA (데이터 구조 탐색)
│   ├── phase1/            파서 + Pydantic 스키마 실습
│   ├── phase2/            서버 + 뷰어 실습
│   ├── phase3/            코어 RAG 실습 (임베딩, KG, 인접 게이팅)
│   ├── phase4/            AI 채팅 실습
│   └── phase5/            RAG 평가 실습
│   (각 phase 폴더: 노트북 파일들 + feedback.md)
├── conversations/                변환된 세션 데이터 (gitignore)
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
        { "type": "thinking", "text": "..." }
      ]
    }
  ]
}
```

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

### 인덱싱 흐름

```
session.json
  → detectTopicBoundaries()
      사용자 메시지만 추출 → Groq → 경계 인덱스 반환
      fallback: 글자 수 기준 균등 분할
  → buildTopics()
      경계로 슬라이싱 → 청크별 Groq 요약 (llama-3.1-8b-instant, 2~3문장)
  → fastembed.embed(summary)
      multilingual-e5-large, ONNX CPU 추론
  → session_index.json 저장
      { summary, embedding, position, turn_start, turn_end }
  → KG 빌드 (백그라운드)
      청크별 엔티티/관계 추출 → knowledge_graph.db
```

### 인접 토픽 게이팅

±1 인접 토픽을 **무조건 추가하지 않는다.**
임베딩은 이미 저장되어 있으므로 추가 비용 없이 실제 유사도 측정.

```python
# indexer.py search() 내부
for neighbor in adjacent_topics:
    neighbor_score = cosine_similarity(query_vec, neighbor["embedding"])
    if neighbor_score > ADJACENT_THRESHOLD:  # 기본값 0.3, 평가로 튜닝
        ctx["score"] = neighbor_score        # 추정치 아닌 실측값
        context_topics.append(ctx)
```

### 벡터 KG

엔티티 검색을 키워드 LIKE → 코사인 유사도로 전환.
"라이브러리 설치 문제" → fastembed 매칭 가능.

```python
# 빌드 시: embed(name + " " + description) → DB 저장
# 검색 시: embed(query) → 엔티티 벡터와 코사인 유사도 → 상위 k개
# 매칭 엔티티의 1홉 관계 자동 포함 (기존 동작 유지)
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

### Dense X 명제 모드 (실험, Phase 5 이후)

```
청크 → Groq로 원자적 명제 추출 → 명제별 fastembed 임베딩
session_index.json에 propositions[] 배열로 추가 저장 (topics[] 병존)
```

명제 추출 프롬프트 원칙:
- 각 사실은 맥락 없이 독립적으로 이해 가능
- 고유명사·경로·에러명은 원문 그대로 포함
- 하나의 사실 = 하나의 문장

### HyDE (hyde 평가 모드)

```
질문 → Groq: 가상의 짧은 답변 생성 → 가상 답변 임베딩 → 토픽 벡터와 비교
```
인덱싱 구조 변경 없음. 검색 시점에만 추가 Groq 호출 1회.

---

## AI 채팅 흐름

### 쿼리 라우팅

```
질문 → classifyQuery() (llama-3.1-8b-instant, 20토큰)
  → simple     세션 없이 바로 답 가능 → groq_simple_model, RAG 생략
  → analytical 분석·추론 필요       → groq_analytical_model, 토픽 요약 사용
  → retrieval  세션 내용 검색 필요  → groq_chat_model, 벡터 + KG 검색
```

### retrieval 경로

```
벡터 검색: 질문 임베딩 → 코사인 유사도 top_k=3
           + 인접 게이팅 (유사도 > 0.3인 ±1 토픽만 추가)
KG 검색:  엔티티 벡터 유사도 → 매칭 엔티티의 1홉 관계 자동 포함

system 프롬프트:
  [주요 내용]   원본 대화 텍스트 (Small-to-Big)
  [인접 맥락]   게이팅 통과한 인접 토픽 원본 (있을 때만)
  [관련 개념]   KG 엔티티 + 관계 (있을 때만)
```

### 증분 업데이트

새 대화 추가 후 AI 채팅 시 마지막 토픽부터 재처리.
`session_index.json`에 `indexed_turn_count`, `last_topic_turn_start` 저장.

---

## RAG 평가 파이프라인

### 평가 모드

| 모드 | 검색 방식 |
|------|----------|
| `baseline` | 전체 토픽 요약을 컨텍스트로 사용 |
| `vector` | 코사인 유사도 top_k |
| `vector_adjacent` | vector + 인접 게이팅 |
| `vector_kg` | vector_adjacent + 벡터 KG |
| `hyde` | HyDE 쿼리 확장 + vector |
| `dense_x` | 명제 단위 벡터 검색 (Phase 5 이후) |

### 평가 지표

| 지표 | 측정 내용 |
|------|----------|
| Answer Score | LLM-as-judge 0~10점 |
| Hit Rate | 올바른 청크가 검색됐는가 (정답 레이블 있을 때) |

### CLI

```bash
python -m evaluator --session PATH --modes baseline,vector,vector_adjacent,vector_kg,hyde
python -m evaluator --session PATH --qa-pairs PATH   # 기존 QA 쌍 재사용
python -m evaluator --no-judge                       # 판정 없이 답변만 생성
python -m evaluator --load-judgments PATH            # 기존 판정으로 채점만
```

### 평가 뷰어 패널

```
⚖ 평가 버튼 → 평가 패널
  QA 쌍 입력 또는 자동 생성
  모드 선택 (체크박스)
  [평가 실행]
  ─────────────────────────────
  모드              평균    개선
  baseline          6.2      —
  vector            7.4    +1.2
  vector_adjacent   7.9    +0.5
  vector_kg         8.1    +0.2
  hyde              7.6    -0.3
  ─────────────────────────────
  개별 QA 클릭 → 모드별 답변 나란히 비교
```

---

## 서버 API

```
GET  /viewer/*                      → 정적 파일 (패키지 번들)
GET  /conversations/*                      → 변환된 세션 파일
GET  /api/sessions                  → conversations/ 세션 목록
GET  /api/session/<id>              → session.json 반환
GET  /api/index-status?session_id=  → 인덱싱 상태 + topics 배열
GET  /api/kg-status?session_id=     → KG 상태 + 엔티티 수
GET  /api/chat-list?session_id=     → 대화 기록 목록
GET  /api/chat-load?id=             → 대화 기록 전체
POST /api/groq-proxy                → Groq API 프록시 (rate limit 헤더 포함)
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
- **AI 채팅 패널:** 대화 기록 바 + 메시지 목록 + 입력 툴바
  - 툴바: 쿼리 라우팅 토글 + 모델 선택 + 전송 버튼 + Rate Limit 뱃지
- **청크 패널:** 토픽 목록 + 클릭 시 해당 위치 스크롤
- **KG 패널:** 그래프 탭(vis-network) + 목록 탭
- **설정 패널:** 모델 설정 + Rate Limit 현황
- **평가 패널:** QA 입력 + 모드 선택 + 결과 비교

---

## 구현 우선순위

```
Phase 0  EDA (데이터 구조 탐색, 블록 타입 분포, 노트북)
Phase 1  파서 + Pydantic 스키마 (models.py)
Phase 2  서버 + 기본 뷰어 (세션 목록 + 대화 렌더링 + 블록 타입 필터)
Phase 3  코어 RAG (토픽 분할 + 임베딩 + 인접 게이팅 + 벡터 KG)
Phase 4  AI 채팅 (쿼리 라우팅 + retrieval 파이프라인 + 대화 저장)
Phase 5  RAG 평가 파이프라인 (모드 비교 + LLM-as-judge + 결과 시각화)
Phase 6  Dense X + HyDE (평가 결과 기반으로 필요한 것만 구현)
Phase 7  UI 완성 (청크 패널 + KG 패널 + 평가 패널 + 설정 패널)
```

---

## 핵심 설계 원칙

1. **외부 의존성 최소화** — fastembed + SQLite 외 추가 패키지 없음
2. **평가 먼저** — Phase 5 평가 결과를 보고 Phase 6 구현 여부 결정
3. **Small-to-Big 유지** — 요약으로 검색, 원문을 LLM에 전달
4. **역할 분리** — 의미 검색은 벡터, 관계 탐색은 KG
5. **인접 게이팅** — 무조건 추가 아닌 유사도 임계값 통과 시만 추가

---

## 제약 조건

- 절대 경로 하드코딩 금지
- `conversations/`, `.env` gitignore (대화 내용, API 키)
- API 키는 `.env` 또는 설정 파일에만 저장
- Anthropic/Claude 관련 상표·디자인 요소 금지
