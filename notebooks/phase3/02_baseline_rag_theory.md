# Phase 3-2 이론 — Baseline RAG

## 1. RAG란?

**Retrieval-Augmented Generation** — 모델의 학습 지식만 쓰지 않고,
외부 데이터를 **검색(Retrieve)** 해 컨텍스트로 추가한 뒤 **생성(Generate)** 하는 방법.

```
일반 LLM 호출:
  [질문] → LLM → [답변]  (모델이 아는 것만)

RAG:
  [질문] → 검색 → [관련 문서] → LLM → [답변]  (문서 기반 답변)
```

이 프로젝트에서 "외부 데이터"는 사용자가 업로드한 **대화 세션(session.json)**.
LLM이 학습 당시 본 적 없는 나의 개인 대화 내용이므로, 반드시 컨텍스트로 제공해야 한다.

---

## 2. Baseline: 전체 텍스트를 컨텍스트로

가장 단순한 RAG. 검색 없이 **대화 전체**를 system 프롬프트에 넣는다.

```
session.json  →  텍스트 추출  →  system 프롬프트  →  Groq  →  답변
                 (text 블록만)
```

**장점:**
- 구현 단순
- 모든 정보가 컨텍스트에 있어 이론상 완전한 답변 가능

**단점:**
- 긴 대화는 **토큰 한계**를 초과 (Groq 모델: 8k~32k 토큰)
- 토큰이 많으면 **rate limit** 빈발
- 비용 (토큰 = 비용)

→ Phase 4에서 벡터 검색으로 관련 청크만 전달해 해결한다.

---

## 3. 텍스트 추출: text 블록만

session.json의 blocks에는 5가지 타입이 있다:
`text`, `thinking`, `tool_use`, `tool_result`, `token_budget`

RAG 컨텍스트에는 **`text` 블록만** 사용한다.

이유:
- `thinking`: 추론 과정, 최종 답변 아님
- `tool_use` / `tool_result`: 도구 입출력 raw 데이터, 맥락 이해에 노이즈
- `token_budget`: 메타데이터

```python
# 예시
for turn in session["turns"]:
    role = "사용자" if turn["role"] == "user" else "AI"
    texts = [b["text"] for b in turn["blocks"] if b["type"] == "text"]
```

---

## 4. 컨텍스트 자르기 전략

전체 텍스트가 `max_chars`를 초과할 때, **앞 60% + 뒤 40%** 전략으로 자른다.

```
전체 텍스트: [====앞=====][====중간====][====뒤====]
                 60%                        40%
              ↑ 유지                        ↑ 유지
                          ↑ 중략 처리
```

**왜 균등하게 자르지 않는가?**
- 대화 초반: 주제 설정, 배경 정보 → 중요
- 대화 후반: 최종 결론, 최근 맥락 → 중요
- 중간: 상대적으로 덜 중요

**왜 앞을 더 많이 남기는가?**
- 초반 맥락이 없으면 뒤의 내용을 이해하기 어렵다
- 60/40은 휴리스틱 — 평가 후 조정 가능

---

## 5. Multi-turn 대화 이력

한 번 질문-답변하고 끝나는 게 아니라, **연속적인 대화**를 유지한다.

```
messages = [
  {"role": "system", "content": "...대화 컨텍스트..."},
  {"role": "user",   "content": "첫 번째 질문"},
  {"role": "assistant", "content": "첫 번째 답변"},
  {"role": "user",   "content": "두 번째 질문"},   ← 현재 질문
]
```

이전 대화 이력이 있어야 "그거 다시 설명해줘" 같은 질문이 가능하다.
이력이 길어지면 마찬가지로 토큰 한계에 걸리므로, **최근 N개만 유지**한다.

---

## 6. 세션별 채팅 기록 저장/복원

브라우저를 새로고침해도 이전 AI 채팅 이력이 유지되어야 한다.

```
저장 (POST /api/chat-save):
  {id, session_id, messages, updated_at} → data_dir/chats/{id}.json

복원 (GET /api/chat-load?id=...):
  chats/{id}.json → messages 복원

목록 (GET /api/chat-list?session_id=...):
  해당 세션의 채팅 기록 목록 반환
```

`chats/` 디렉토리는 `data_dir` 아래에 생성된다 (gitignore 대상).

---

## 7. 프로젝트 내 연결

```
02_baseline_rag 노트북
  ├── extract_text_context()    → evaluator.py 에서 재사용
  ├── system 프롬프트 구성 패턴  → evaluator.py run_baseline()
  └── multi-turn messages 관리  → chat.js (JS에서 직접 구현)

server.py (Phase 3에서 추가된 엔드포인트):
  POST /api/groq-proxy    → _groq.chat_completion() 호출
  GET  /api/groq-key-status  → .env 키 존재 여부
  GET  /api/groq-models      → _groq.list_models()
  POST /api/chat-save        → chats/ 디렉토리에 JSON 저장
  GET  /api/chat-list        → 세션별 기록 목록
  GET  /api/chat-load        → 기록 전체 반환
  DELETE /api/chat-delete    → 기록 삭제
```
