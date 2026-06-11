# Phase 2-1 노트북 셀 내용

셀 타입 표기: **📝 마크다운 셀** / **💻 코드 셀**  
각 구분선(`---`) 사이 내용을 해당 타입의 셀에 붙여넣기.

---

📝 **마크다운 셀**

```
# Phase 2-1 — HTTP 서버 & API 라우팅

**목표:** Python 표준 라이브러리 `http.server`로 라우팅, JSON API, 정적 파일 서빙을 직접 구현한다.

**이 노트북을 마치면:**
- [ ] HTTP 요청/응답 구조를 이해한다
- [ ] 경로 기반 라우팅을 구현할 수 있다
- [ ] JSON API 엔드포인트를 만들 수 있다
- [ ] path traversal 취약점을 인지하고 방어한다

**완성 후 연결:**
- `src/server.py` 에 구현 내용 옮기기
- `python -m viewer` 로 실행 확인 (노트북 02와 연결)
```

---

📝 **마크다운 셀**

```
---
## 섹션 1 — HTTP 기초 (이론)

### HTTP란?

브라우저가 서버에 **요청(request)** 을 보내면 서버가 **응답(response)** 을 돌려주는 프로토콜.  
모든 웹 통신의 기반이고, REST API도 HTTP 위에서 동작한다.

```
브라우저                서버
  │── GET /api/sessions ──→│
  │←── 200 OK + JSON ──────│
```

### 요청 구조

```
GET /api/sessions HTTP/1.1
Host: localhost:8080
```

- **메서드**: GET, POST, PUT, DELETE 등
- **경로**: `/api/sessions` — 서버가 뭘 해야 할지 결정하는 기준
- **헤더**: 메타 정보 (Content-Type, Authorization 등)

### 응답 구조

```
HTTP/1.1 200 OK
Content-Type: application/json; charset=utf-8
Content-Length: 123

[{"session_id": "abc", ...}]
```

| 상태 코드 | 의미 |
|----------|------|
| `200 OK` | 성공 |
| `301 Moved Permanently` | 영구 리다이렉트 |
| `404 Not Found` | 경로 없음 |
| `500 Internal Server Error` | 서버 오류 |

### 왜 표준 라이브러리 `http.server`를 쓰는가?

이 프로젝트는 외부 의존성을 최소화하는 것이 설계 원칙 중 하나다.  
FastAPI나 Flask는 편리하지만 pip install이 필요하고, 이 뷰어는 단순 로컬 도구라 표준 라이브러리로 충분하다.  
표준 라이브러리 HTTP 서버의 내부를 이해하면, 이후 FastAPI 등을 쓸 때 "왜 이렇게 동작하는지"가 보인다.

### `server.py` 어디에 쓰이나?

```
python -m viewer
  → viewer/__main__.py → src/server.main()
    → HTTPServer(("", 8080), _make_handler(data_dir))
      → do_GET() 가 모든 GET 요청을 처리
```
```

---

💻 **코드 셀** (워밍업 — 완성 코드, 실행만)

```python
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

class HelloHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # 로그 숨김

    def do_GET(self):
        body = b"Hello, World!"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

server = HTTPServer(("", 18081), HelloHandler)
t = threading.Thread(target=server.serve_forever)
t.daemon = True
t.start()

with urllib.request.urlopen("http://localhost:18081/") as resp:
    print("상태 코드:", resp.status)
    print("응답 본문:", resp.read().decode())
    print("Content-Type:", resp.headers.get("Content-Type"))

server.shutdown()
print("서버 종료")
```

---

📝 **마크다운 셀**

```
### 미니 실습 — 경로 분기 추가

위 서버에 두 경로를 추가하세요:
- `/hello` → `"안녕하세요!"` 반환 (200)
- `/status` → `"OK"` 반환 (200)
- 그 외 → `"Not Found"` 반환 (404)

```python
# 힌트: urlparse로 경로 추출
from urllib.parse import urlparse
path = urlparse(self.path).path
if path == "/hello":
    ...
```
```

---

💻 **코드 셀** (미니 실습 TODO)

```python
from urllib.parse import urlparse

class RoutingHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        path = urlparse(self.path).path
        # TODO: /hello, /status, 그 외(404) 분기
        pass
```

---

💻 **코드 셀** (미니 채점)

```python
import urllib.error

server2 = HTTPServer(("", 18082), RoutingHandler)
t2 = threading.Thread(target=server2.serve_forever)
t2.daemon = True
t2.start()

all_pass = True
try:
    with urllib.request.urlopen("http://localhost:18082/hello") as r:
        body = r.read().decode()
        assert r.status == 200, f"/hello status 오류: {r.status}"
        assert "안녕" in body, f"/hello 본문 오류: {body!r}"
        print("✓ /hello 통과:", body)
except Exception as e:
    print(f"✗ /hello 실패: {e}")
    all_pass = False

try:
    with urllib.request.urlopen("http://localhost:18082/status") as r:
        assert r.status == 200
        print("✓ /status 통과")
except Exception as e:
    print(f"✗ /status 실패: {e}")
    all_pass = False

try:
    urllib.request.urlopen("http://localhost:18082/unknown")
    print("✗ /unknown 404가 아님")
    all_pass = False
except urllib.error.HTTPError as e:
    assert e.code == 404, f"404여야 함, 실제: {e.code}"
    print("✓ /unknown 404 통과")
except Exception as e:
    print(f"✗ /unknown 실패: {e}")
    all_pass = False

server2.shutdown()
if all_pass:
    print("\n✓✓✓ 섹션 1 미니 실습 전체 통과!")
```

---

📝 **마크다운 셀**

```
### 본 실습 — 쿼리 스트링 + 다중 Content-Type 응답

`EchoHandler` 를 구현하세요. 아래 4개 엔드포인트를 모두 처리해야 합니다.

| 경로 | 동작 |
|------|------|
| `/` | `"AI Conversation Viewer"` 텍스트 반환 (200) |
| `/health` | `status=ok` 텍스트 반환 (200) |
| `/echo` | 쿼리 스트링 `msg` 값 그대로 반환 — `?msg=hello` → `hello` |
| 그 외 | `"Not Found"` (404) |

```python
# 힌트: 쿼리 스트링 파싱
from urllib.parse import urlparse, parse_qs

parsed = urlparse("/echo?msg=hello")
params = parse_qs(parsed.query)     # → {"msg": ["hello"]}
msg = params.get("msg", [""])[0]    # → "hello"
```
```

---

💻 **코드 셀** (본 실습 TODO)

```python
from urllib.parse import urlparse, parse_qs

class EchoHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send(self, code: int, body: bytes, content_type: str = "text/plain; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        # TODO: /, /health, /echo?msg=..., 그 외 404
        pass
```

---

💻 **코드 셀** (본 채점)

```python
server_echo = HTTPServer(("", 18085), EchoHandler)
t_echo = threading.Thread(target=server_echo.serve_forever)
t_echo.daemon = True
t_echo.start()

all_pass = True

try:
    with urllib.request.urlopen("http://localhost:18085/") as r:
        assert r.status == 200
        body = r.read().decode()
        assert "Viewer" in body or "viewer" in body, f"/ 본문 오류: {body!r}"
        print("✓ / 통과:", body)
except Exception as e:
    print(f"✗ / 실패: {e}")
    all_pass = False

try:
    with urllib.request.urlopen("http://localhost:18085/health") as r:
        assert r.status == 200
        body = r.read().decode()
        assert "ok" in body.lower(), f"/health 본문 오류: {body!r}"
        print("✓ /health 통과:", body)
except Exception as e:
    print(f"✗ /health 실패: {e}")
    all_pass = False

try:
    with urllib.request.urlopen("http://localhost:18085/echo?msg=안녕하세요") as r:
        assert r.status == 200
        body = r.read().decode()
        assert "안녕하세요" in body, f"/echo 본문 오류: {body!r}"
        print("✓ /echo?msg=안녕하세요 통과:", body)
except Exception as e:
    print(f"✗ /echo 실패: {e}")
    all_pass = False

try:
    urllib.request.urlopen("http://localhost:18085/unknown")
    print("✗ /unknown 404가 아님")
    all_pass = False
except urllib.error.HTTPError as e:
    assert e.code == 404
    print("✓ /unknown 404 통과")
except Exception as e:
    print(f"✗ /unknown 실패: {e}")
    all_pass = False

server_echo.shutdown()
if all_pass:
    print("\n✓✓✓ 섹션 1 본 실습 전체 통과!")
```

---

📝 **마크다운 셀**

```
### 섹션 1 마무리

**질문/정리:** 이 섹션에서 궁금한 점이나 정리한 내용을 여기에 작성하세요.

---
```

---

📝 **마크다운 셀**

```
## 섹션 2 — JSON API + 팩토리 패턴 (이론)

### JSON API란?

브라우저(JavaScript)와 서버(Python)가 데이터를 주고받는 표준 방식.  
Content-Type을 `application/json`으로 설정하면 브라우저가 JSON으로 파싱한다.

```python
import json

# Python 객체 → JSON 문자열 → bytes
data = json.dumps([{"id": 1}, {"id": 2}], ensure_ascii=False).encode("utf-8")
# ensure_ascii=False: 한국어 등 비ASCII 문자를 이스케이프하지 않음
```

### 왜 `_make_handler` 팩토리 패턴인가?

`HTTPServer`는 핸들러 클래스를 인자로 받는다 (인스턴스가 아님).  
그런데 `data_dir` 같은 설정값을 핸들러에 전달하려면 클래스 정의 시점에 값을 바인딩해야 한다.

```python
# 문제: HTTPServer는 클래스를 받는다
HTTPServer(("", 8080), Handler)  # Handler 인스턴스 X, 클래스 자체

# 해결: 팩토리 함수로 클로저 캡처
def _make_handler(data_dir):
    class Handler(BaseHTTPRequestHandler):
        _data_dir = data_dir   # 클래스 변수로 바인딩
        ...
    return Handler

HTTPServer(("", 8080), _make_handler(data_dir))  # 클래스 반환
```

이 패턴은 파라미터가 있는 핸들러/미들웨어를 만들 때 Django, Flask, FastAPI에서도 동일하게 쓰인다.

### `server.py` 어디에 쓰이나?

```
Handler._api_sessions()  →  GET /api/sessions  →  app.js loadData()
Handler._api_session(id) →  GET /api/session/{id}  →  app.js loadConv(id)
Handler._json(obj)       →  공통 JSON 응답 헬퍼
```
```

---

💻 **코드 셀** (워밍업 — 완성 코드, 실행만)

```python
import json

# json.dumps: Python 객체 → JSON 문자열
data = [{"session_id": "abc-123", "title": "테스트 대화", "turn_count": 5}]
json_str = json.dumps(data, ensure_ascii=False)
json_bytes = json_str.encode("utf-8")
print("JSON 문자열:", json_str)
print("바이트 길이:", len(json_bytes))  # Content-Length 에 이 값을 씀

# json.loads: JSON 문자열 → Python 객체
parsed = json.loads(json_str)
print("파싱 결과 타입:", type(parsed))
print("첫 항목:", parsed[0]["title"])
```

---

📝 **마크다운 셀**

```
### 미니 실습 — `_make_handler` 팩토리 이해

아래 코드를 완성하세요.  
`make_greeter(name)` 은 `do_GET()` 이 `"안녕, {name}!"` 을 반환하는 핸들러 클래스를 돌려주는 팩토리 함수입니다.

```python
# 힌트: 클로저로 name을 클래스 변수에 바인딩
def make_greeter(name: str):
    class Handler(BaseHTTPRequestHandler):
        _name = ???
        ...
    return Handler
```
```

---

💻 **코드 셀** (미니 실습 TODO)

```python
def make_greeter(name: str):
    # TODO: name을 클래스 변수로 바인딩한 핸들러 클래스를 반환하세요.
    # do_GET()은 f"안녕, {self._name}!" 을 200으로 응답해야 합니다.
    pass
```

---

💻 **코드 셀** (미니 채점)

```python
import urllib.error

for test_name in ["Alice", "홍길동"]:
    srv = HTTPServer(("", 18082 + ord(test_name[0]) % 10), make_greeter(test_name))
    import threading
    t = threading.Thread(target=srv.serve_forever)
    t.daemon = True
    t.start()
    port = srv.server_address[1]
    try:
        with urllib.request.urlopen(f"http://localhost:{port}/") as r:
            body = r.read().decode()
            assert r.status == 200, f"상태 오류: {r.status}"
            assert test_name in body, f"'{test_name}' 가 응답에 없음: {body!r}"
            print(f"✓ make_greeter('{test_name}') 통과: {body}")
    except AssertionError as e:
        print(f"✗ 실패: {e}")
    except Exception as e:
        print(f"✗ 예외: {e}")
    finally:
        srv.shutdown()

print("\n✓✓✓ 섹션 2 미니 실습 통과!")
```

---

📝 **마크다운 셀**

```
### 본 실습 — `_json()`, `_error()`, `do_GET()` 기본 라우팅

아래 `MiniHandler` 클래스에 세 메서드를 구현하세요.

**`_json(self, obj)`**
- `json.dumps(obj, ensure_ascii=False).encode("utf-8")`
- `send_response(200)` → Content-Type + Content-Length → `end_headers()` → `wfile.write(data)`

**`_error(self, code, message)`**
- `message.encode()` → `send_response(code)` → Content-Type text/plain + Content-Length → write

**`do_GET(self)`**
- `/api/hello` → `_json({"msg": "안녕"})` 반환
- 그 외 → `_error(404, "Not Found")`
```

---

💻 **코드 셀** (본 실습 TODO)

```python
class MiniHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _json(self, obj):
        # TODO: json 직렬화 후 200 응답
        pass

    def _error(self, code: int, message: str):
        # TODO: 상태 코드 + 텍스트 응답
        pass

    def do_GET(self):
        path = urlparse(self.path).path
        # TODO: /api/hello → _json, 그 외 → _error(404, ...)
        pass
```

---

💻 **코드 셀** (본 채점)

```python
server3 = HTTPServer(("", 18083), MiniHandler)
t3 = threading.Thread(target=server3.serve_forever)
t3.daemon = True
t3.start()

all_pass = True

try:
    with urllib.request.urlopen("http://localhost:18083/api/hello") as r:
        assert r.status == 200
        ct = r.headers.get("Content-Type", "")
        assert "application/json" in ct, f"Content-Type 오류: {ct!r}"
        body = json.loads(r.read().decode())
        assert "msg" in body, f"'msg' 키 없음: {body}"
        print("✓ /api/hello 통과:", body)
except Exception as e:
    print(f"✗ /api/hello 실패: {e}")
    all_pass = False

try:
    urllib.request.urlopen("http://localhost:18083/unknown")
    print("✗ /unknown 404가 아님")
    all_pass = False
except urllib.error.HTTPError as e:
    assert e.code == 404
    print("✓ /unknown 404 통과")
except Exception as e:
    print(f"✗ /unknown 실패: {e}")
    all_pass = False

server3.shutdown()
if all_pass:
    print("\n✓✓✓ 섹션 2 본 실습 통과!")
```

---

📝 **마크다운 셀**

```
### 섹션 2 마무리

**질문/정리:** 이 섹션에서 궁금한 점이나 정리한 내용을 여기에 작성하세요.

---
```

---

📝 **마크다운 셀**

```
## 섹션 3 — 정적 파일 서빙 + 보안 (이론)

### 정적 파일 서빙

브라우저가 `/viewer/style.css` 를 요청하면 서버는 파일을 읽어 그대로 전달한다.  
이때 `Content-Type` 헤더가 중요하다 — `.css` 는 `text/css`, `.js` 는 `application/javascript`.

```python
import mimetypes

mime, _ = mimetypes.guess_type("style.css")   # → "text/css"
mime, _ = mimetypes.guess_type("app.js")      # → "application/javascript"
mime, _ = mimetypes.guess_type("unknown.xyz") # → None → 폴백 필요
```

`Content-Length` 는 바이트 수를 정확히 전달해야 한다.  
브라우저는 이 값으로 응답 본문의 끝을 판단한다.

### Path Traversal 취약점

`_api_session()` 은 session_id 를 URL 에서 받아 파일 경로를 구성한다.  
악의적인 사용자가 `session_id = "../../etc/passwd"` 를 넘기면 어떻게 될까?

```python
# 위험한 코드
file_path = data_dir / f"{session_id}.json"
# → data_dir/../../etc/passwd.json  (상위 디렉토리 탈출)
```

방어법: session_id 에 `/`, `\\`, `..` 이 포함되면 즉시 404 반환.

```python
if not session_id or "/" in session_id or "\\" in session_id or ".." in session_id:
    self._not_found()
    return
```

### `server.py` 어디에 쓰이나?

```
Handler._serve_file()   → GET /viewer/*.css, *.js → 브라우저로 전달
Handler._api_session()  → GET /api/session/{id} → session.json 반환
```
```

---

💻 **코드 셀** (워밍업 — 완성 코드, 실행만)

```python
import mimetypes

for filename in ["index.html", "style.css", "app.js", "session.json", "logo.png", "unknown.xyz"]:
    mime, enc = mimetypes.guess_type(filename)
    fallback = mime or "application/octet-stream"
    print(f"{filename:20s} → {fallback}")
```

---

📝 **마크다운 셀**

```
### 미니 실습 — Path Traversal 검증 함수

아래 조건을 만족하는 `is_safe_session_id(session_id)` 함수를 작성하세요.
- 빈 문자열 → `False`
- `/` 포함 → `False`
- `\\` 포함 → `False`
- `..` 포함 → `False`
- 정상 ID (`"abc-123"`, `"세션-01"`) → `True`
```

---

💻 **코드 셀** (미니 실습 TODO)

```python
def is_safe_session_id(session_id: str) -> bool:
    # TODO: 위 조건에 따라 True/False 반환
    pass
```

---

💻 **코드 셀** (미니 채점)

```python
cases = [
    ("abc-123",          True),
    ("세션-01",           True),
    ("",                 False),
    ("../../etc/passwd", False),
    ("foo/bar",          False),
    ("foo\\bar",         False),
    ("a..b",             False),
]

all_pass = True
for sid, expected in cases:
    result = is_safe_session_id(sid)
    ok = result == expected
    mark = "✓" if ok else "✗"
    print(f"{mark} is_safe_session_id({sid!r:25s}) → {result} (기대: {expected})")
    if not ok:
        all_pass = False

if all_pass:
    print("\n✓✓✓ 섹션 3 미니 실습 통과!")
```

---

📝 **마크다운 셀**

```
### 본 실습 — `_serve_file()`, `_api_sessions()`, `_api_session()`

아래 세 메서드를 구현하세요.

**`_serve_file(self, file_path)`**
1. `file_path.read_bytes()` — `FileNotFoundError` 시 `_not_found()`, 그 외 오류 시 `_error(500, ...)`
2. `mimetypes.guess_type(str(file_path))` → None이면 `"application/octet-stream"`
3. 200 응답: Content-Type + Content-Length + 본문

**`_api_sessions(self)`**
1. `self._data_dir.glob("*.json")` 로 파일 목록 순회
2. 각 파일을 파싱해 `{ session_id, title, updated_at, turn_count }` 딕셔너리 생성
3. `turns` 가 없으면 건너뜀
4. `updated_at` 기준 내림차순 정렬 후 `_json()` 호출

**`_api_session(self, session_id)`**
1. 보안 검증: 빈 문자열 또는 `/`, `\\`, `..` 포함 시 `_not_found()`
2. `self._data_dir / f"{session_id}.json"` 존재 확인
3. 파일 읽어 200 응답 (이미 JSON이므로 `_json()` 말고 직접 bytes 전송)
```

---

💻 **코드 셀** (본 실습 TODO)

```python
import json
import mimetypes
import tempfile
from pathlib import Path

def _make_full_handler(data_dir: Path):
    class FullHandler(BaseHTTPRequestHandler):
        _data_dir = data_dir

        def log_message(self, fmt, *args):
            pass

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/api/sessions":
                self._api_sessions()
            elif path.startswith("/api/session/"):
                self._api_session(path[len("/api/session/"):])
            elif path.startswith("/static/"):
                rel = path[len("/static/"):]
                self._serve_file(self._data_dir / rel)
            else:
                self._not_found()

        def _serve_file(self, file_path: Path):
            # TODO: 파일 읽기 → MIME 타입 추론 → 200 응답
            pass

        def _api_sessions(self):
            # TODO: *.json 파일 목록 → 메타데이터 리스트 → _json()
            pass

        def _api_session(self, session_id: str):
            # TODO: 보안 검증 → 파일 읽기 → 200 응답
            pass

        def _json(self, obj):
            data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _not_found(self):
            self._error(404, "Not Found")

        def _error(self, code: int, message: str):
            body = message.encode()
            self.send_response(code)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return FullHandler
```

---

💻 **코드 셀** (본 채점)

```python
import tempfile

tmpdir = Path(tempfile.mkdtemp())

sess = {
    "session_id": "test-001",
    "title": "테스트 세션",
    "created_at": "2025-12-01T00:00:00Z",
    "updated_at": "2025-12-02T00:00:00Z",
    "turns": [{"role": "user", "blocks": [{"type": "text", "text": "안녕"}]}]
}
(tmpdir / "test-001.json").write_text(json.dumps(sess, ensure_ascii=False), encoding="utf-8")
(tmpdir / "app.css").write_bytes(b"body { margin: 0; }")

handler_cls = _make_full_handler(tmpdir)
server4 = HTTPServer(("", 18084), handler_cls)
t4 = threading.Thread(target=server4.serve_forever)
t4.daemon = True
t4.start()

all_pass = True

try:
    with urllib.request.urlopen("http://localhost:18084/api/sessions") as r:
        sessions = json.loads(r.read().decode())
        assert isinstance(sessions, list)
        assert len(sessions) == 1
        assert sessions[0]["session_id"] == "test-001"
        assert sessions[0]["turn_count"] == 1
        print("✓ /api/sessions 통과:", sessions[0]["title"])
except Exception as e:
    print(f"✗ /api/sessions 실패: {e}")
    all_pass = False

try:
    with urllib.request.urlopen("http://localhost:18084/api/session/test-001") as r:
        data = json.loads(r.read().decode())
        assert data["session_id"] == "test-001"
        print("✓ /api/session/test-001 통과")
except Exception as e:
    print(f"✗ /api/session 실패: {e}")
    all_pass = False

try:
    urllib.request.urlopen("http://localhost:18084/api/session/../../etc/passwd")
    print("✗ Path Traversal 방어 실패")
    all_pass = False
except urllib.error.HTTPError as e:
    assert e.code == 404
    print("✓ Path Traversal 방어 통과 (404)")
except Exception as e:
    print(f"✗ Path Traversal 예외 오류: {e}")
    all_pass = False

try:
    with urllib.request.urlopen("http://localhost:18084/static/app.css") as r:
        ct = r.headers.get("Content-Type", "")
        assert r.status == 200
        assert "text/css" in ct, f"Content-Type 오류: {ct!r}"
        print("✓ 정적 파일 서빙 통과 (Content-Type:", ct, ")")
except Exception as e:
    print(f"✗ 정적 파일 실패: {e}")
    all_pass = False

server4.shutdown()
if all_pass:
    print("\n✓✓✓ 섹션 3 전체 통과!")
```

---

📝 **마크다운 셀**

```
### 섹션 3 마무리

**질문/정리:** 이 섹션에서 궁금한 점이나 정리한 내용을 여기에 작성하세요.

---
```

---

📝 **마크다운 셀**

```
## 연결 — 다음 단계

### 구현한 것 → `src/server.py` 로 옮기기

| 이 노트북 | `src/server.py` |
|----------|-----------------||
| `_json()`, `_error()` | `Handler._json()`, `Handler._error()` |
| `do_GET()` 라우팅 | `Handler.do_GET()` (viewer/ 경로 추가) |
| `_serve_file()` | `Handler._serve_file()` |
| `_api_sessions()` | `Handler._api_sessions()` |
| `_api_session()` + 보안 | `Handler._api_session()` |

### Phase 2-2 연결

```
python -m viewer
  → server.py가 /api/sessions, /api/session/<id> 응답
  → app.js의 loadData(), loadConv() 가 이를 fetch
  → renderSidebar(), renderBlocks() 로 화면에 표시
```

### AI 취업 연결

```
FastAPI  — 라우팅은 @app.get("/api/sessions") 데코레이터로, 내부는 동일 패턴
Django   — urls.py + views.py 가 do_GET() 라우팅 역할을 분리한 것
Flask    — @app.route() 데코레이터
```
```

---

📝 **마크다운 셀**

```
---
## 스스로 정리해보기

> 이 노트북에서 배운 내용을 자신의 말로 정리해보세요.

### 내 정리

<!-- 여기에 작성 -->

### Claude 요약

<!-- Claude 작성 -->
```
