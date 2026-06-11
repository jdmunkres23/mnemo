# Phase 2 피드백

---

## 섹션 1: HTTP 기초 (01_http_server.ipynb)

### 내 코드

```python
# 미니 실습
from urllib.parse import urlparse

class RoutingHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        path = urlparse(self.path).path
        # TODO: /hello, /status, 그 외(404) 분기
        if path == '/hello':
            body = "안녕하세요!".encode("utf-8") # 한글과 같은 멀티바이트 문자는 b".." 형태로 못씀 뒤에 encode()를 붙여야 함.
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=uft-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == '/status':
            body = b"OK"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            body = b'Not Found'
            self.send_response(404)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
```

```python
# 본 실습 
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
        if path == '/':
            self._send(200, "AI Conversation Viewer")
        elif path == '/health':
            self._send(200, 'status=ok')
        elif '/echo?msg=' in path:
            params = parse_qs(parsed.query)
            msg = params.get("msg", [""])[0]
            self._send(200, msg.encode())
        else:
            self._send(404, 'Not Found')
```

### 질문

1. FastAPI는 다른 건가? 자세한 설명이 필요함.
2. 응답 구조는 항상 똑같이 해야 하나?
3. do_GET() 안에 있는 self.send_header() 안에 들어가는 "Content-Type" 이런 거는 지정된 인자값들 인건가?
4. 아래의 코드 부분이 실제로 서버를 여는 건가? 그리고 지금 내 컴퓨터를 서버로 사용해서 응답을 주고 받은 건가?
    ```python
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


### 피드백

**미니 실습 ✓ 통과** (타이포 1개 주의)

- `charset=uft-8` → `utf-8` 타이포. 채점기는 통과하지만 실제 브라우저에서 한글이 깨질 수 있음.
- 로직 자체는 완전히 정확함.

---

**본 실습 ✗ 버그 2개**

버그 1 — `_send()`에 `bytes` 대신 `str`을 전달함.

```python
# ✗ 현재 코드
self._send(200, "AI Conversation Viewer")  # str
self._send(200, 'status=ok')               # str
self._send(404, 'Not Found')               # str

# ✓ 수정
self._send(200, b"AI Conversation Viewer")
self._send(200, b'status=ok')
self._send(404, b'Not Found')
```

`_send()` 마지막 줄 `self.wfile.write(body)`는 bytes만 받음.
str을 넣으면 `TypeError`가 발생해서 서버가 500 오류를 냄.

버그 2 — echo 경로 판단 실수.

```python
# ✗ 현재 코드
elif '/echo?msg=' in path:   # 항상 False

# ✓ 수정
elif path == '/echo':
```

`urlparse(self.path).path`는 경로 부분만 추출함.
`/echo?msg=hello` 요청에서 `path`는 `/echo`이고 쿼리스트링은 이미 잘려 있음.
그래서 조건이 항상 False가 되어 `/echo` 요청이 전부 404로 떨어짐.

---

## 섹션 2: JSON API + 팩토리 패턴 (01_http_server.ipynb)

### 내 코드

```python
# 미니 실습
def make_greeter(name: str):
    # TODO: name을 클래스 변수로 바인딩한 핸들러 클래스를 반환하세요.
    # do_GET()은 f"안녕, {self._name}!" 을 200으로 응답해야 합니다.
    class HelloHandler(BaseHTTPRequestHandler):
        _name = name
        def do_GET(self):
            body = f'안녕, {self._name}!'.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', "text/plain; charter=utf-8")
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    return HelloHandler
```

```python
# 본 실습
class MiniHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _json(self, obj):
        # TODO: json 직렬화 후 200 응답
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, code: int, message: str):
        # TODO: 상태 코드 + 텍스트 응답
        body = message.encode()
        self.send_response(code)
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


    def do_GET(self):
        path = urlparse(self.path).path
        # TODO: /api/hello → _json, 그 외 → _error(404, ...)
        if path=='/api/hello':
            return self._json({"msg": "안녕"})
        else:
            return self._error(404, "Not Found")
```

### 질문

#### 정리

##### HTTP 서버

브라우저가 어떤 웹사이트에 들어가면 서버에 요청을 보내고 서버는 응답을 보내준다. 

##### Handler
핸들러는 요청이 들어왔을 때 어떻게 처리할지 담당하는 처리기이다. 

HTTP 서버는 음식점 건물이라면 핸들러는 직원이다.

손님(요청)이 오면 직원(핸들러 인스턴스)가 하나씩 배치된다.

##### 클래스와 인스턴스

클래스는 설계도이고 인스턴스는 설계도로 만든 실물이다. 붕어빵틀과 붕어빵의 관계이다.


##### HTTP와 클래스

HTTPServer(("", 8000), Handler)

위의 코드로 서버를 열 수 있다. 이때 HTTPServer는 클래스를 받는데, 요청이 올 때마다 새로운 인스턴스가 필요하기 때문이다. HTTPServer가 요청이 올 때마다 Handler()를 직접 호출해서 만든다. 미리 만들어 놓고 대기할 수 없다.

##### 팩토리 패턴

핸들러가 브라우저의 요청을 처리하기 위해서 핸들러 외부에 있는 값을 가져와야 하는 경우에 핸들러를 생성하는 함수에 팩토리 패턴을 이용할 수 있다. 


아쉬운 점
1. Content-Type 인자값 종류들에 대한 설명이 없어서 클로드 도움을 받음.
2. 내 수준 대비 설명이 적었다고 느꼈음. 클로드한테 물어보면서 이해했음.

### 피드백

**미니 실습 ✓ 통과** (타이포 1개 주의)

- `charter=utf-8` → `charset=utf-8` 타이포. 채점기는 통과하지만 잘못된 헤더.
- 팩토리 패턴 이해는 정확함. `_name = name`으로 클로저 캡처, `self._name`으로 접근하는 구조가 옳음.

---

**본 실습 ✓ 완전 정확**

`_json()`, `_error()`, `do_GET()` 모두 올바름. 특히:
- `_error`에서 `message.encode()`로 bytes 변환한 것 정확.
- `do_GET`에서 `return self._json(...)` 패턴도 무방함 (`_json()`은 None을 반환하지만 명시적으로 분기가 끝난다는 표현으로 나쁘지 않음).

---

## 섹션 3: 정적 파일 서빙 + 보안 (01_http_server.ipynb)

### 내 코드

```python
# 미니 실습
def is_safe_session_id(session_id: str) -> bool:
    # TODO: 위 조건에 따라 True/False 반환
    if not session_id or '/' in session_id or '\\' in session_id or '..' in session_id:
        return False
    else:
        return True
```

```python
# 본 실습
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
                # 노트북 테스트용 단순 정적 파일 경로
                rel = path[len("/static/"):]
                self._serve_file(self._data_dir / rel)
            else:
                self._not_found()

        def _serve_file(self, file_path: Path):
            # TODO: 파일 읽기 → MIME 타입 추론 → 200 응답
            try:
                body = file_path.read_bytes()
            except FileNotFoundError:
                self._not_found()
            except Exception:
                self._error(500, 'error')
            
            mime, _ = mimetypes.guess_type(str(file_path))
            if mime == None:
                mime = "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", f"{mime}; charset=utf-8")
            self.send_header("Content-Length", str(body))
            self.end_headers()
            self.wfile.write(body)

            

        def _api_sessions(self):
            # TODO: *.json 파일 목록 → 메타데이터 리스트 → _json()
            sessions = []
            for file_path in self._data_dir.glob("*.json"):
                text = file_path.read_text(encoding='utf-8')
                data = json.loads(text)
                turns = data.get("turns", [])
                if not turns:
                    continue
                sessions.append({
                    "session_id": data['session_id'],
                    "title": data["title"],
                    "updated_at": data["updated_at"],
                    "turn_count": len(turns),
                    })
            sessions.sort(key=lambda s: s['updated_at'], reverse=True)
            self._json(sessions)



        def _api_session(self, session_id: str):
            # TODO: 보안 검증 → 파일 읽기 → 200 응답
            if not session_id or '/' in session_id or '\\' in session_id or '..' in session_id:
                self._not_found()
            else:
                file_path = self._data_dir/f"{session_id}.json"
                if file_path.exists(): # Path 객체는 항상 true라서 exists() 필요함.
                    text = file_path.read_text(encoding='utf-8')
                    body = text.encode('utf-8')
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)


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


### 질문

(없으면 생략)
아쉬원 점
1. 함수에 대한 자세한 설명이 없어서 힘듦.
2. 피드백은 따로 

### 피드백

**미니 실습 ✓ 완전 정확**

4가지 조건(`not session_id`, `/`, `\\`, `..`)을 정확히 검사함. 간결하고 옳음.

---

**본 실습 △ _api_sessions·_api_session은 정확, _serve_file에 버그 2개**

`_api_sessions` ✓ — `turns` 없으면 건너뛰기, `turn_count`, `updated_at` 기준 내림차순 정렬까지 완벽.

`_api_session` ✓ — 보안 검증과 파일 읽기 정확. 사소한 누락: `file_path.exists()`가 False일 때 아무 응답도 안 보냄. `else: self._not_found()` 추가 필요하지만 채점기는 통과.

`_serve_file` ✗ 버그 2개:

버그 1 — 예외 처리 후 `return` 없음.

```python
# ✗ 현재 코드
try:
    body = file_path.read_bytes()
except FileNotFoundError:
    self._not_found()
    # return 없음 → 아래 코드 계속 실행
except Exception:
    self._error(500, 'error')
    # return 없음

mime, _ = mimetypes.guess_type(...)  # FileNotFoundError 후에도 여기 도달
self.wfile.write(body)               # body 미정의 → NameError

# ✓ 수정
except FileNotFoundError:
    self._not_found()
    return
except Exception:
    self._error(500, 'error')
    return
```

404를 보낸 뒤에도 계속 실행되어 서버가 터짐. Python 예외 처리에서 자주 나오는 실수.

버그 2 — `Content-Length`에 bytes 객체 자체를 씀.

```python
# ✗ 현재 코드
self.send_header("Content-Length", str(body))
# → Content-Length: b'body { margin: 0; }'  (잘못된 값)

# ✓ 수정
self.send_header("Content-Length", str(len(body)))
# → Content-Length: 19  (바이트 수)
```

`len(body)`는 정수(바이트 수), `str(body)`는 bytes 객체의 문자열 표현임.
같아 보이지만 완전히 다른 것.

---