# Phase 3-2 개요 — AI 채팅 패널 (`chat.js`)

> JS 프론트엔드 영역. 노트북/실습 없음. 구조와 흐름만 파악한다.

---

## 전체 구조

```
chat.js
  ├── 상태 관리          aiState, _serverHasKey, _cachedChats
  ├── 초기화             initAIChat(sessionId), _initAIChatPanel()
  ├── 모델 관리          _fetchModels(), _buildModelDropdown()
  ├── 메시지 전송        sendAIMessage()  →  POST /api/groq-proxy
  ├── 채팅 기록 저장     _saveChat()      →  POST /api/chat-save
  ├── 채팅 기록 복원     _loadChatHistory()  →  GET /api/chat-list
  └── Rate Limit 배지    _updateRateLimitBadge()
```

---

## 상태 (`aiState`)

```javascript
let aiState = {
  sessionId: null,     // 현재 열린 대화 세션 ID
  chatId:    null,     // 저장된 채팅 기록 ID (uuid)
  messages:  [],       // multi-turn 이력 { role, content }
  sessionTitle: '',
  loading:   false,
};
```

`messages`가 Groq에 전달되는 실제 대화 이력이다.
`chatId`는 서버에 저장된 기록을 식별하는 키.

---

## 초기화 흐름

세션이 열릴 때마다 `app.js`가 `initAIChat(sessionId)` 호출 → 상태 초기화 + 기존 기록 복원.

```
initAIChat(id)
  ├── aiState 초기화 (messages 비움)
  ├── _renderAIMessages()  UI 갱신
  └── _loadChatHistory(id)
        ├── GET /api/chat-list?session_id=id
        └── 가장 최근 기록 자동 로드 → aiState.messages 복원
```

패널이 처음 열릴 때 (1회):
```
_initAIChatPanel()
  ├── _checkServerKey()   GET /api/groq-key-status → .env 키 여부 확인
  └── _fetchModels()      GET /api/groq-models → 드롭다운 구성
```

---

## 모델 선택

Groq에서 동적으로 모델 목록을 가져와 드롭다운 구성.
API 호출 실패 시 하드코딩된 `FALLBACK_MODELS` 사용.

```javascript
const FALLBACK_MODELS = [
  { id: 'llama-3.1-8b-instant',    context_window: 131072 },
  { id: 'llama-3.3-70b-versatile', context_window: 131072 },
  { id: 'mixtral-8x7b-32768',      context_window: 32768  },
];
```

선택한 모델은 `localStorage`에 저장 → 새로고침 후에도 유지.

---

## 메시지 전송 흐름

```
사용자 입력
  → sendAIMessage()
      1. messages에 user 메시지 추가
      2. _renderAIMessages()  (로딩 스피너 표시)
      3. POST /api/groq-proxy  { messages, model, api_key, session_context }
      4. 응답에서 content, rate_limit 추출
      5. messages에 assistant 메시지 추가
      6. _updateRateLimitBadge(rate_limit)
      7. _saveChat()  → POST /api/chat-save
```

`session_context`는 서버에서 session.json을 읽어 system 프롬프트에 포함한다.
(`server.py _api_groq_proxy()` 내부에서 처리)

---

## Rate Limit 배지

응답 헤더에서 읽은 `rate_limit` 값을 화면에 표시한다.

```javascript
function _updateRateLimitBadge(rl) {
  // remaining_requests, remaining_tokens → 배지 텍스트 갱신
  // 값이 낮으면 경고 색상으로 전환
}
```

배지는 입력 툴바 옆에 항상 노출. 한도가 낮아지면 전송 전 확인 유도.

---

## 채팅 기록 저장/복원

```
저장:  _saveChat()
  POST /api/chat-save  { id, session_id, messages, updated_at }
  → data_dir/chats/{id}.json

목록:  _loadChatHistory(sessionId)
  GET /api/chat-list?session_id=...
  → 해당 세션의 기록 목록 (최신순)
  → 가장 최근 기록 자동 로드

불러오기:  _loadChat(chatId)
  GET /api/chat-load?id=...
  → messages 배열 복원

삭제:  _deleteChat(chatId)
  DELETE /api/chat-delete?id=...
```

기록은 대화 뷰어 우측의 "이전 대화" 목록에서 확인·선택 가능.

---

## server.py 연동 (`_api_groq_proxy`)

`/api/groq-proxy`는 단순 중계가 아니라 서버에서 컨텍스트를 **조립**한다.

```python
def _api_groq_proxy(self, body):
    session_id = body.get("session_id")
    messages   = body.get("messages", [])   # chat.js의 multi-turn 이력
    model      = body.get("model", "llama-3.1-8b-instant")
    api_key    = body.get("api_key") or load_env_key()

    # 세션 컨텍스트를 system 메시지로 앞에 삽입
    if session_id:
        session = ...  # session.json 로드
        context, _ = extract_text_context(session, max_chars=8000)
        system = {"role": "system", "content": "대화 기록:\n\n" + context}
        messages = [system] + messages

    content, usage, rate_limit = chat_completion(messages, model, api_key)
    self._json({"content": content, "usage": usage, "rate_limit": rate_limit})
```

Phase 4+에서는 이 system 프롬프트 구성 부분이 벡터 검색 + KG 결과로 교체된다.
