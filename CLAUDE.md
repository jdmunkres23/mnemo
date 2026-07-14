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
python -m evaluator --session PATH --qa-pairs PATH              # 기존 QA 쌍 재사용
python -m evaluator --session PATH --output PATH                # 결과 저장 경로 지정 (기존 모드 결과 보존)
python -m evaluator --session PATH --max-chars 0                # 청크 크기 제한 없음 — 전체를 하나의 청크로 (짧은 대화용)
python -m evaluator --no-judge                                  # 답변만 생성 (Claude 외부 채점용)
python -m evaluator --load-judgments PATH                       # 기존 판정으로 채점만

python -m src.usage_tracker                          # 오늘(UTC) 모델별 사용량·한도·잔여 토큰 출력
```

---

## 파일 구조

```
project-root/
├── src/
│   ├── parser.py          Claude.ai 내보내기 JSON → session.json 변환
│   ├── models.py          Pydantic 데이터 스키마 (블록 타입 포함)
│   ├── server.py          HTTP 서버 + API 라우팅
│   ├── _groq.py           Groq API 래퍼 (urllib 기반, Cloudflare UA 우회, usage_tracker 연동)
│   ├── usage_tracker.py   Groq 일별 사용량 기록 + 분당 한도 자동 대기
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
│   ├── phase5/            토픽 분할 + 그룹핑 검색 실습 (명제 단위 임베딩 계획했으나 MVP로 완료 기준 충족해 보류)
│   └── phase6/            점진적 개선 실습 (인접 게이팅, KG)
│   (각 phase 폴더: [주제]_theory.md + [번호]_[주제]_notebook.md, AI 무관 영역은 _overview.md)
├── conversations_learning/       변환된 세션 데이터 (gitignore)
├── eval_data/             평가용 합성 대화·QA 쌍·결과 (gitignore)
├── usage/                 Groq 일별 사용량 기록 (gitignore, UTC 날짜별 .jsonl + limits.json)
├── tests/
├── pyproject.toml
├── README.md
└── .env                   Groq API 키 (gitignore)
```

---

## Groq 사용량 관리

`src/usage_tracker.py` — `_groq.py`의 `chat_completion` 성공 시 자동 호출.

- **일별 기록**: `usage/YYYY-MM-DD.jsonl` (UTC 기준). 날짜가 바뀌면 이전 파일 자동 삭제.
- **한도 테이블**: `usage/limits.json` — 당일 UTC 최초 실행 시 Groq 공식 페이지에서 TPD를 파싱해 캐시. 파싱 실패 시 코드 내 기본값 사용.
- **자동 대기**: 분당 남은 토큰이 한도의 25% 미만이면 리셋까지 자동 sleep.
- **사용량 확인**: `python -m src.usage_tracker` → 모델별 사용/한도/잔여 토큰 테이블 출력.

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
  고정 크기(N글자) 청크 분할 + fastembed 벡터 검색 → 관련 청크 → Groq → 답변
  문제: 청크 경계가 주제를 무시해 관련 내용이 잘리거나 분산됨
    ↓
Phase 4 — vector
  토픽 기반 청크 분할 + 요약 임베딩 + fastembed 벡터 검색 → 관련 청크 → Groq → 답변
  평가: baseline 대비 Hit Rate + Correctness + Token Usage 비교
    ↓
Phase 5 — 토픽 분할(split_long_topic) + 그룹핑 검색(search_vector_grouped)
  vector의 토픽 압축 희석 문제(큰 토픽이 요약 하나로 뭉개짐) 근본 수정.
  원래 계획은 명제 단위(Dense X) 임베딩이었으나, MVP 우선 원칙에 따라 기존
  chunk_session()을 재사용한 재분할로 먼저 시도 → 완료 기준을 만족해 propositions는 보류.
  분할 직후 부작용(형제 조각끼리 top_k 경쟁 → single 타입 hit rate 하락) 발견 →
  position 단위로 그룹핑해 대표 점수는 조각 중 최댓값, 전달은 토픽 전체로 재조립.
  평가(3회 반복, 인덱스 고정): baseline 대비 Hit Rate 완전 회복 + Correctness +0.3 이상 → 채택
  알려진 트레이드오프: 토큰 사용량 baseline 대비 최대 +81% (긴 대화)
    ↓
Phase 6 — vector_adjacent → vector_kg (greedy sequential)
  인접 게이팅 추가 → 평가 → 개선되면 채택
  벡터 KG 추가   → 평가 → 개선되면 채택 (분할된 vector, 즉 search_vector() flat 위에서 재평가)
  vector_kg 목표 두 가지: ① 원래 목적인 동의어 매칭 ② vector_grouped는 토큰
  비효율적이라 채택 보류했으므로, KG로 그 정확도를 flat 위에서 토큰 효율적으로
  재현할 수 있는지 검증 (vector_grouped는 비교 기준점으로 유지)
    ↓
Phase 7 — hyde (선택)
  Phase 6 평가 결과에서 개선 여지가 있을 때만 구현
```

### 인덱싱 흐름 (Phase 3)

```
session.json
  → 고정 크기(N글자)로 청크 분할
      turns를 순서대로 이어붙이다 N글자 초과 시 새 청크 시작
  → fastembed.embed(chunk_text)
      multilingual-e5-large, ONNX CPU 추론
  → session_index.json 저장
      { text, embedding, turn_start, turn_end }
```

### 인덱싱 흐름 (Phase 4~)

```
session.json
  → detectTopicBoundaries()
      사용자 메시지만 추출 (300자 넘는 메시지는 Groq로 1~2문장 요약 후 사용) → Groq(llama-3.3-70b-versatile)
      → 경계 인덱스 반환
      1단계(전체 대화 거친 분류) → 2단계(구간별 세분화), 각 단계 5회 호출 + 자기일관성 다수결
      (llama-3.1-8b-instant는 동일 프롬프트·temperature=0에도 응답이 재현되지 않아 배제 —
       세션당 1회뿐인 저빈도 호출이라 다수결로 늘어난 호출 수도 비용 부담 낮음)
      사용자 메시지 30개 초과 시: 1단계를 30개 단위 윈도우로 나눠 독립적으로 처리 후,
      윈도우 이음매(서로 다른 호출이라 원래 이어져 있어도 모르는 절단)는 앞뒤 세그먼트의
      임베딩 유사도로 병합 여부 결정 — 임계값은 고정값이 아니라 그 대화 안에서 실제로
      확인된 전환 유사도의 최댓값(대화마다 문체·언어·주제 밀도가 달라 유동적으로 결정)
      fallback: 글자 수 기준 균등 분할
  → buildTopics()
      경계로 Q&A 그룹화 → 청크별 Groq 요약 (llama-3.1-8b-instant, 2~3문장)
  → splitLongTopics() (Phase 5~)
      CHUNK_SIZE(2000자) 넘는 토픽을 chunk_session() 재사용해 여러 조각(entries)으로 재분할
      (새 Groq 호출 종류 추가 없음 — 기존 함수 재사용). 분할된 조각들은 같은 position을 공유.
  → 각 entry별 Groq 요약 + fastembed.embed(summary)
      multilingual-e5-large, ONNX CPU 추론
  → vector_index.json 저장
      { text, summary, embedding, position, turn_start, turn_end }
  → KG 빌드 (백그라운드, Phase 6~)
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

**왜 긴 대화를 윈도우로 나누고 이음매를 유사도로 병합하는가?**
- 대화가 길어질수록 한 번에 판단할 경계 후보가 많아져 Groq 응답이 길어지고, 그만큼 배치 기반 추론의
  비결정성(temperature=0이어도 서버 배치 크기에 따라 결과가 달라짐)에 노출되는 지점이 늘어난다.
- 윈도우로 나누면 판단은 안정되지만, 윈도우 이음매는 서로 다른 호출이라 원래 이어진 내용이어도
  경계로 착각될 수 있다.
- 이 착각을 되돌리는 병합 기준은 고정값이 아니라 **그 대화 안에서 실제로 확인된 전환들의 유사도**로
  잡는다 — 대화마다 문체·언어·주제 밀도가 달라 절대적인 유사도 수준이 다르기 때문에, 세션마다
  유동적으로 정해야 다른 대화에도 일반화된다. 병합 실수(진짜 다른 두 토픽을 하나로 합침)가 병합
  누락(인접한 두 청크로 남는 것, 인접 게이팅으로 어느 정도 보완 가능)보다 되돌리기 어려우므로
  기준은 최댓값(가장 보수적인 값)으로 잡는다.

### 인접 토픽 게이팅 (Phase 6~)

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

### 벡터 KG (Phase 6~)

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

### 토픽 분할 + 그룹핑 검색 (Phase 5)

Phase 4 vector 평가에서 QA 표본을 늘릴수록 baseline보다 낮게 나온 원인 진단 결과,
토픽 경계 탐지가 관대해 토픽 하나에 여러 사실이 뭉치고(예: 6751자/6개 사실짜리
토픽) 이를 2~3문장 요약으로 압축하며 개별 사실이 희석되는 것으로 확인됨. 원래
Phase 6(선택)이었으나, 인접 게이팅·KG(현 Phase 6)보다 먼저 이 근본 원인을
고치기로 순서 변경.

원래 계획은 명제 단위(Dense X) 임베딩(Groq로 원자적 명제 추출)이었으나, MVP 우선
원칙에 따라 더 가벼운 방식을 먼저 시도:

**1. `split_long_topic()`** — 새 Groq 호출 없이 기존 `chunk_session()`을 재사용해
`CHUNK_SIZE`를 넘는 토픽만 여러 조각으로 재분할. 조각별로 독립 요약 + 임베딩.

**2. 부작용 발견** — 조각(entries) 수가 늘면서 `search_vector()`가 조각 단위 flat
리스트에서 top_k를 뽑다 보니, 같은 토픽에서 쪼개진 형제 조각끼리 순위를 경쟁하다
밀려나는 현상 발생 (예: 토픽 8개→조각 16개면 top_k=3 경쟁률이 2배). `single` 타입
질문의 Hit Rate가 baseline 대비 하락.

**3. `search_vector_grouped()`로 해결** — 조각별 유사도는 그대로 계산하되
`position`(원래 토픽) 단위로 그룹핑해 그룹 내 최댓값을 대표 점수로 사용. 선택된
그룹은 형제 조각을 turn 순서로 재조립해 토픽 전체 원문을 LLM에 전달. 검색은 조각
단위로 정밀하게, 전달은 토픽 단위로 완전하게 (Small-to-Big을 조각 단위로 확장).

```python
# indexer.py search_vector_grouped() 핵심 로직
groups = {}
for item in data:
    groups.setdefault(item['position'], []).append(item)

merged = []
for pos, pieces in groups.items():
    pieces.sort(key=lambda p: p['turn_start'])
    merged.append({
        'text': '\n\n'.join(p['text'] for p in pieces),   # 형제 조각 재조립
        'position': pos,
        'turn_start': pieces[0]['turn_start'],
        'turn_end': pieces[-1]['turn_end'],
        'score': max(p['score'] for p in pieces),          # 대표 점수 = 최댓값
    })
```

**평가 결과** (3회 반복, 인덱스 고정해 답변 생성 노이즈만 비교): Hit Rate가 두
세션 모두 baseline 이상으로 완전 회복, Correctness도 baseline 대비 +0.3 이상
(long +0.48, short +0.51) — 채택 기준 통과. 단, 긴 대화에서 토큰 사용량이
baseline 대비 +81% — 그룹핑된 토픽 원문 전체를 전달하기 때문. propositions는
이 MVP로 완료 기준을 만족해 구현 보류.

**구현 상태**: `search_vector()`(flat, 분할만)가 현재 `route_query()`가 쓰는
라이브 경로. `search_vector_grouped()`는 구현·평가 완료했으나 evaluator CLI
모드나 route_query()에는 아직 연결 안 됨 — Phase 6 벡터 KG에서 flat 위에 KG를
얹어 그룹핑 수준 정확도를 토큰 효율적으로 재현하는 것이 목표 중 하나라, 그룹핑은
비교 기준점으로 남겨두고 실제 다음 개발은 flat 위에서 진행.

### HyDE (Phase 7, 선택)

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
질문 → classifyQuery() (기본 llama-3.1-8b-instant, 20토큰, 설정 패널에서 모델 변경 가능)
  → simple      세션 불필요 → Groq 직접 호출, RAG 생략
  → analytical  전체 흐름 파악 필요, 구체적 사실 불필요 → 토픽 요약만 전달
  → retrieval   구체적 사실(수치·파일명·에러명 등) 필요 → 벡터 검색 + KG → Groq
```

분류 경계: 구체적 수치·파일명·에러명이 언급되면 무조건 `retrieval`. 모호하면 `retrieval`로 폴백.
이 폴백 때문에 세션과 무관한 일반 질문도 retrieval로 새는 경우가 실사용에서 확인됨(예: "1+1은 뭐야"는 숫자 포함으로 강제 retrieval, "LLM이 뭐야"는 분류 모델이 모호하다고 판단해 retrieval) — 근본 수정 전까지는 설정 패널/AI 채팅 툴바의 라우팅 모드를 `simple`/`analytical`/`retrieval` 중 하나로 수동 고정해 우회 가능 (`route_query()`의 `forced_type`).

### retrieval 경로

```
벡터 검색: 질문 임베딩 → 코사인 유사도 top_k=3 (search_vector(), flat — 분할된 조각 단위)
           + 인접 게이팅 (유사도 > 0.3인 ±1 토픽만 추가, Phase 6~)
KG 검색:  엔티티 벡터 유사도 → 매칭 엔티티의 1홉 관계 자동 포함 (Phase 6~)

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

| 모드 | 도입 Phase | 검색 방식 | 구현 상태 |
|------|-----------|----------|----------|
| `baseline` | Phase 3 | 고정 크기 청크 + 벡터 검색 | 구현됨 (`run_baseline`) |
| `vector` | Phase 4~5 | 토픽 기반 청크(긴 토픽은 `split_long_topic()`으로 재분할) + 조각 단위 flat 벡터 검색 | 구현됨 (`run_vector`), route_query() 라이브 경로 |
| `vector_grouped` | Phase 5 | vector + `search_vector_grouped()` (position 단위 그룹핑, 채택된 비교 기준점) | 함수 구현·평가 완료, evaluator CLI 모드 미연결 |
| `vector_adjacent` | Phase 6 | vector + 인접 게이팅 | 미구현 |
| `vector_kg` | Phase 6 | vector_adjacent + 벡터 KG (vector_grouped 수준 정확도를 토큰 효율적으로 재현이 목표) | 미구현 |
| `hyde` | Phase 7 | HyDE 쿼리 확장 + vector | 미구현 |

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
GET  /api/usage-status              → Groq 사용량 조회 (모델별 사용·한도·남은 토큰·리셋까지 남은 시간)
POST /api/groq-proxy                → Groq API 프록시 (rate limit 헤더 포함, .env 키 폴백)
POST /api/index-session             → 임베딩 저장 (incremental 지원)
POST /api/query-semantic            → 쿼리 라우팅 + 벡터 검색 (routing_model, forced_type로 라우팅 모델/수동 고정 지정 가능)
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
┌─────────────┬─────────────────────────┬────────────────┬──────────┐
│   사이드바   │      대화 뷰어           │   AI 채팅 패널  │  설정 패널 │
│  세션 목록   │  (메시지 버블 렌더링)     │  + 평가 패널   │ (선택 열림)│
│             │                         │                │          │
└─────────────┴─────────────────────────┴────────────────┴──────────┘
```

### 주요 UI 요소

- **사이드바:** 세션 목록 (제목 + 날짜 + 메시지 수) + 검색 필터
- **대화 뷰어:** 역할별 버블, thinking 블록 기본 접힘, 라이트/다크 모드. 각 turn에 `data-turn-index` 부여 — AI 채팅 출처 칩 클릭 시 해당 turn으로 스크롤+하이라이트
- **AI 채팅 패널:** 메시지 목록 + 입력 툴바 + 답변마다 출처 표시(retrieval이면 턴 범위 칩, simple/analytical이면 안내 텍스트)
  - 툴바: 답변 모델 선택 + 쿼리 라우팅 모드 선택(자동/simple/analytical/retrieval 고정, 설정 패널과 값 동기화) + 전송 버튼 + Rate Limit 뱃지
- **청크 패널:** 토픽 목록 + 클릭 시 해당 위치 스크롤
- **KG 패널:** 그래프 탭(vis-network) + 목록 탭
- **설정 패널:** AI 채팅 패널과 별도로 오른쪽에 열리는 독립 패널 (동시에 열어둘 수 있음). Groq API 키 + 답변 모델/쿼리 라우팅 모델 각각 선택 + 라우팅 모드 고정 + 오늘 Groq 사용량(모델별 막대그래프 + 리셋까지 남은 시간)
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

Phase 3  기본 RAG 체험
         고정 크기(N글자) 청크 분할 + fastembed 벡터 검색 → 관련 청크 → Groq 답변
         세션별 채팅 기록 저장/복원, 모델 목록 동적 조회
         대화 이력 유지 (multi-turn), rate limit 배지
         baseline 평가 파이프라인 (src/evaluator.py)

Phase 4  벡터 검색 + 평가
         토픽 분할 + 요약 임베딩 + 코사인 유사도 검색
         평가: baseline vs vector (Hit Rate + Correctness + Completeness + Token Usage)
         개선 확인 후 다음 단계 진행

Phase 4.5  토픽 경계 탐지 안정성 개선 (실사용 중 발견)
         llama-3.1-8b-instant 응답이 동일 프롬프트·temperature=0에도 재현 안 됨을 발견
         → 모델 비교(8b/70b/scout) 후 70b로 교체, 계층적 분류(거친 분류→세분화) +
           자기일관성 다수결로 안정화
         긴 사용자 메시지 요약 + 긴 대화(30개 초과) 윈도우 분할·이음매 유사도 병합 추가

Phase 5  토픽 분할 + 그룹핑 검색 — vector 저하 원인 수정
         평가에서 vector가 QA 표본을 늘릴수록 baseline보다 낮게 나옴을 확인 →
         원인: 토픽 경계 탐지가 관대해 토픽 하나에 여러 사실이 뭉치고(예: 6751자/
         6개 사실), 이를 2~3문장 요약으로 압축하며 개별 사실이 희석됨
         → 원래 계획(명제 단위 임베딩) 대신 MVP로 먼저 시도: split_long_topic()으로
         큰 토픽만 chunk_session() 재사용해 재분할 (새 Groq 호출 없음)
         → 부작용: 조각 수 증가로 top_k 경쟁이 빡빡해져 single 타입 Hit Rate 하락
         → search_vector_grouped() 추가: position 단위로 그룹핑해 대표 점수는
         조각 중 최댓값, 전달은 형제 조각을 재조립한 토픽 전체 (Small-to-Big 확장)
         평가(3회 반복): baseline 대비 Hit Rate 완전 회복 + Correctness +0.3 이상
         → 완료 기준 충족, 명제 단위 임베딩은 보류. 단 토큰 사용량 +81%(긴 대화) 트레이드오프
         (원래 Phase 6이었으나 인접 게이팅·KG보다 먼저 진행 — 핵심 설계 원칙 7 참고)

Phase 6  점진적 개선 + 평가 (greedy sequential)
         인접 게이팅 추가 → 평가 → 채택 여부 결정
         벡터 KG 추가   → 평가 → 채택 여부 결정
         (분할된 vector, 즉 search_vector() flat 위에서 재평가)
         vector_kg 목표 두 가지: ① 원래 목적인 동의어 매칭 ② vector_grouped는
         정확하지만 토큰 비효율적이라 채택 보류했으므로, KG로 그 정확도를 flat
         위에서 토큰 효율적으로 재현할 수 있는지 검증 (vector_grouped는 비교
         기준점/정확도 상한선으로 유지)

Phase 7  실험적 기법 (Phase 6 결과 기반으로 필요한 것만)
         HyDE (가상 문서 쿼리 확장)

Phase 8  UI 완성
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
7. **근본 원인 우선** — 회피(인접 게이팅)나 부분 보완(KG의 동의어 매칭)보다, 진단된
   근본 원인(토픽 압축 희석)을 먼저 고치고 그 위에서 나머지를 평가한다

---

## 제약 조건

- 절대 경로 하드코딩 금지
- `conversations_learning/`, `data/`, `.env` gitignore (대화 내용, API 키)
- API 키는 `.env`에만 저장, 소스코드에 하드코딩 금지
- Anthropic/Claude 관련 상표·디자인 요소 금지
