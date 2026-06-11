# Phase 2 뷰어 구조 개요

> 이 문서는 구현 연습용이 아닙니다.
> Phase 2에서 무엇이 추가됐고, 왜 그런 구조인지, 전체 흐름이 어떻게 되는지 이해하기 위한 읽기용 문서입니다.

---

## Phase 2에서 추가된 것

Phase 1까지는 JSON을 파싱하는 Python 코드만 있었습니다.
Phase 2에서 "브라우저에서 대화를 열람할 수 있는 로컬 웹 앱"이 추가됩니다.

```
Phase 1 완료 상태          Phase 2 완료 상태
─────────────────          ─────────────────────────────
src/
  models.py                src/
  parser.py                  models.py
                             parser.py
                             server.py         ← 추가 (HTTP 서버)
                             viewer/
                               index.html      ← 추가 (HTML 뼈대)
                               style.css       ← 추가 (스타일)
                               app.js          ← 추가 (JS 로직)
                               renderers/      ← 추가 (블록 렌더러)
                                 text.js
                                 thinking.js
                                 tool.js
viewer/
  __main__.py               ← 추가 (python -m viewer 진입점)
parser/
  __main__.py               ← 추가 (python -m parser 진입점)
```

---

## 왜 이런 구조인가

### server.py가 하는 일

브라우저와 Python 사이에서 중간 다리 역할을 합니다.

```
브라우저                     server.py                  파일시스템
  │                              │                           │
  │── GET /viewer/ ─────────────→│                           │
  │                              │── index.html 읽기 ───────→│
  │←── HTML 반환 ────────────────│                           │
  │                              │                           │
  │── GET /api/sessions ────────→│                           │
  │                              │── *.json 목록 읽기 ──────→│
  │←── JSON 반환 ────────────────│                           │
  │                              │                           │
  │── GET /api/session/abc ─────→│                           │
  │                              │── abc.json 읽기 ─────────→│
  │←── JSON 반환 ────────────────│                           │
```

`server.py` 혼자서 세 가지를 합니다:
1. 정적 파일 서빙 (`index.html`, `style.css`, `app.js`)
2. 세션 목록 API (`/api/sessions`)
3. 세션 상세 API (`/api/session/{id}`)

### renderers/ 폴더가 따로 있는 이유

블록 타입이 5가지(`text`, `thinking`, `tool_use`, `tool_result`, `token_budget`)이고, 타입별 렌더링 로직이 복잡합니다. 하나의 파일에 다 넣으면 너무 길어져서 타입별로 분리했습니다.

```
app.js                    renderers/
  renderBlock(block)        text.js     → renderMarkdown(), escHtml(), toggleBlock()
    → type === 'text'       thinking.js → renderThinkingBlock()
    → type === 'thinking'   tool.js     → segmentBlocks(), renderToolGroup()
    → type === 'tool_*'
```

### `_make_handler(data_dir)` 패턴

`HTTPServer`는 핸들러 **클래스**를 받습니다 (인스턴스가 아님).
`data_dir` 같은 설정값을 전달하려면 클래스를 함수로 감싸서 반환해야 합니다.

```python
# server.py 구조
def _make_handler(data_dir):
    class Handler(BaseHTTPRequestHandler):
        _data_dir = data_dir   # 이 값이 캡처됨
        ...
    return Handler

HTTPServer(("", 8080), _make_handler(data_dir))
```

FastAPI에서 `Depends(get_db)` 같은 의존성 주입이 이 패턴의 발전형입니다.

---

## 전체 실행 흐름

`python -m viewer` 를 입력했을 때 무슨 일이 일어나는가:

```
1. python -m viewer
      ↓
2. viewer/__main__.py
      from src.server import main
      main()
      ↓
3. src/server.py — main()
      data_dir = conversations_learning/
      HTTPServer(("", 8080), _make_handler(data_dir))
      webbrowser.open("http://localhost:8080/viewer/")
      server.serve_forever()   ← 요청 대기 시작
```

브라우저에서 페이지가 열리면:

```
4. 브라우저 → GET /viewer/
      server: src/viewer/index.html 파일 읽어서 반환

5. 브라우저가 index.html 파싱
      → <link rel="stylesheet" href="style.css"> 발견
      → GET /viewer/style.css 요청
      → <script src="renderers/text.js"> 발견
      → GET /viewer/renderers/text.js 요청
      → ... (JS 파일 3개 더 로드)
      → <script src="app.js"> 발견
      → GET /viewer/app.js 요청

6. app.js 로드 완료 → loadData() 자동 실행
      fetch('/api/sessions')
        ↓
      server: conversations_learning/*.json 목록 읽기
              각 파일에서 session_id, title, updated_at, turn_count 추출
              JSON 배열로 반환
        ↓
      SESSIONS 전역 변수에 저장
      renderSidebar() → 사이드바 HTML 생성
      loadConv(첫 번째 세션 id) 호출

7. 사이드바 클릭 → loadConv(id)
      fetch('/api/session/abc-123')
        ↓
      server: conversations_learning/abc-123.json 읽기
              파일 내용 그대로 반환
        ↓
      session.turns 순회
        role === 'user'    → 텍스트 버블
        role === 'assistant' → renderBlocks(turn.blocks)
          → segmentBlocks()로 tool 쌍 묶기
          → 블록 타입별 HTML 생성
      chatInner에 삽입 → 화면에 표시
```

---

## app.js 함수 역할 요약

| 함수 | 언제 호출 | 하는 일 |
|------|----------|--------|
| `loadData()` | 페이지 로드 시 자동 | `/api/sessions` fetch → SESSIONS 채우기 → 사이드바/첫 대화 로드 |
| `renderSidebar()` | loadData 완료 후 | SESSIONS를 월별 그룹화 → 사이드바 HTML 생성 |
| `loadConv(id)` | 사이드바 클릭 시 | `/api/session/{id}` fetch → turns 순회 → 화면에 표시 |
| `renderBlocks(blocks)` | loadConv 내부 | 블록 배열 → segmentBlocks → 각 블록 HTML 조합 |
| `renderBlock(block)` | renderBlocks 내부 | 블록 type에 따라 다른 HTML 반환 |

---

## Phase 3에서 이 구조가 어떻게 확장되는가

Phase 2에서 만든 뷰어는 "읽기 전용"입니다. 대화를 보여주기만 합니다.

Phase 3부터 오른쪽 패널(AI 채팅)이 붙습니다:

```
Phase 2 완료                    Phase 3+ 추가
──────────────────              ──────────────────────────
┌─────┬──────────┐              ┌─────┬──────────┬────────┐
│사이드│  대화    │              │사이드│  대화    │AI 채팅 │
│ 바  │  뷰어    │     →        │ 바  │  뷰어    │ 패널   │
│     │          │              │     │          │        │
└─────┴──────────┘              └─────┴──────────┴────────┘

server.py에 추가되는 API:
  POST /api/index-session   → fastembed 임베딩 저장
  POST /api/query-semantic  → 코사인 유사도 검색
  POST /api/build-kg        → 지식 그래프 빌드
  POST /api/groq-proxy      → Groq API 프록시
```

Phase 2 뷰어는 이 확장을 받아들이는 기반 구조입니다.
