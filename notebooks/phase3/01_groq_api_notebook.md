# Phase 3-1 노트북 셀 내용 — Groq API 래퍼

셀 타입 표기: **📝 마크다운 셀** / **💻 코드 셀**  
각 구분선(`---`) 사이 내용을 해당 타입의 셀에 붙여넣기.

---

📝 **마크다운 셀**

```
# Phase 3-1 — Groq API 래퍼 (_groq.py)

**목표:** Python 표준 라이브러리 `urllib`로 외부 HTTPS API를 직접 호출한다.

**이 노트북을 마치면:**
- [ ] urllib.request.Request로 POST 요청을 구성할 수 있다
- [ ] Authorization Bearer 헤더를 올바르게 추가할 수 있다
- [ ] 응답 헤더에서 rate limit 정보를 파싱할 수 있다
- [ ] 429 응답에서 대기 시간을 파싱해 재시도할 수 있다

**완성 후 연결:**  
노트북에서 구현한 패턴을 `src/_groq.py`에 옮기기
```

---

📝 **마크다운 셀**

```
---
## 섹션 1 — urllib로 HTTP 요청 구성

### urllib.request.Request

Python 표준 라이브러리로 HTTP 요청 객체를 만드는 방법.

```python
import urllib.request

req = urllib.request.Request(
    url,
    data=b"...",             # bytes (POST body)
    headers={"Key": "Val"},  # HTTP 헤더
    method="POST",
)
```

### JSON payload 만들기

```python
import json
payload = {"model": "llama-3.1-8b-instant", "messages": [...]}
data = json.dumps(payload).encode("utf-8")   # str → bytes
```

### 응답 읽기

```python
with urllib.request.urlopen(req, timeout=60) as resp:
    body_str = resp.read().decode("utf-8")   # bytes → str
    body = json.loads(body_str)              # str → dict
```
```

---

💻 **코드 셀** (워밍업 — 완성된 예제 실행)

```python
import json
import urllib.request
import os

# .env에서 키 읽기 (직접 넣어도 됨 — 노트북에서만, 소스코드에는 금지)
def _read_env_key():
    from pathlib import Path
    env = Path("../.env")
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("GROQ_API_KEY=") and not line.startswith("#"):
                return line[len("GROQ_API_KEY="):].strip().strip('"').strip("'")
    return os.environ.get("GROQ_API_KEY", "")

API_KEY = _read_env_key()
print("키 로드:", "OK" if API_KEY else "MISSING")
```

---

💻 **코드 셀** (워밍업 — 완성된 Groq 호출 예제)

```python
# 완성된 예제 — 직접 실행해보고 패턴을 익힌다
_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

payload = json.dumps({
    "model": "llama-3.1-8b-instant",
    "messages": [{"role": "user", "content": "한 줄로 자기소개해줘"}],
    "max_tokens": 50,
}).encode("utf-8")

req = urllib.request.Request(
    _CHAT_URL,
    data=payload,
    headers={
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "User-Agent": _UA,
    },
    method="POST",
)

with urllib.request.urlopen(req, timeout=60) as resp:
    body = json.loads(resp.read().decode("utf-8"))

print(body["choices"][0]["message"]["content"])
```

---

📝 **마크다운 셀**

```
### 미니 실습: build_headers() 구현

API 호출에 필요한 헤더 dict를 반환하는 함수를 만든다.
```

---

💻 **코드 셀** (미니 실습)

```python
def build_headers(api_key: str) -> dict:
    """Authorization + Content-Type + User-Agent 헤더 dict를 반환한다."""
    # TODO: 위 워밍업 예제의 headers dict를 그대로 반환
    pass
```

---

💻 **코드 셀** (채점)

```python
h = build_headers("test_key_123")
assert isinstance(h, dict), "dict를 반환해야 합니다"
assert "Authorization" in h, "Authorization 헤더 누락"
assert h["Authorization"] == "Bearer test_key_123", "Bearer 토큰 형식 확인"
assert "Content-Type" in h, "Content-Type 헤더 누락"
assert "User-Agent" in h, "User-Agent 헤더 누락"
print("✓ 통과")
```

---

📝 **마크다운 셀**

```
### 본 실습: make_request() 구현

URL, payload dict, api_key를 받아 urllib.request.Request 객체를 반환한다.
```

---

💻 **코드 셀** (본 실습)

```python
def make_request(url: str, payload: dict, api_key: str) -> urllib.request.Request:
    """POST 요청 객체를 만들어 반환한다.
    
    힌트:
    - payload를 json.dumps().encode("utf-8") 로 직렬화
    - build_headers(api_key) 활용
    - method="POST"
    """
    # TODO
    pass
```

---

💻 **코드 셀** (채점)

```python
req = make_request("https://example.com/api", {"key": "val"}, "my_key")
assert isinstance(req, urllib.request.Request), "Request 객체여야 합니다"
assert req.get_method() == "POST", "method는 POST여야 합니다"
assert req.full_url == "https://example.com/api", "URL 확인"
assert req.get_header("Authorization") == "Bearer my_key", "Authorization 확인"
assert req.data == json.dumps({"key": "val"}).encode("utf-8"), "payload 직렬화 확인"
print("✓ 통과")
```

---

📝 **마크다운 셀**

```
**연결:** `make_request()`는 `_groq.py`의 `chat_completion()` 안에서
`urllib.request.Request(...)` 을 직접 만드는 부분에 해당한다.

---
## 섹션 2 — Rate Limit 헤더 파싱

응답 헤더에서 rate limit 정보를 추출해 dict로 반환한다.
이 값은 `server.py`가 응답 body에 포함시켜 `chat.js`의 배지에 표시된다.
```

---

💻 **코드 셀** (워밍업)

```python
# urllib의 HTTPResponse 헤더는 dict처럼 접근 가능
# 없는 키는 None 대신 기본값 반환
class MockHeaders:
    def __init__(self, d): self._d = d
    def get(self, key, default=""): return self._d.get(key, default)

mock = MockHeaders({
    "x-ratelimit-remaining-requests": "28",
    "x-ratelimit-remaining-tokens":   "5000",
    "x-ratelimit-reset-requests":     "2s",
    "x-ratelimit-reset-tokens":       "500ms",
})
print(mock.get("x-ratelimit-remaining-requests"))  # "28"
print(mock.get("x-ratelimit-limit-requests", ""))  # "" (없는 키)
```

---

💻 **코드 셀** (미니 실습)

```python
def parse_rate_limit(headers) -> dict:
    """응답 헤더에서 rate limit 정보를 추출해 dict로 반환한다.
    
    반환 키:
        remaining_requests, remaining_tokens,
        reset_requests, reset_tokens
    힌트: headers.get("x-ratelimit-remaining-requests", "")
    """
    # TODO
    pass
```

---

💻 **코드 셀** (채점)

```python
rl = parse_rate_limit(mock)
assert isinstance(rl, dict), "dict를 반환해야 합니다"
assert set(rl.keys()) == {"remaining_requests", "remaining_tokens",
                           "reset_requests", "reset_tokens"}, "키 이름 확인"
assert rl["remaining_requests"] == "28", "remaining_requests 값 확인"
assert rl["reset_tokens"] == "500ms", "reset_tokens 값 확인"

# 없는 헤더는 빈 문자열
empty = MockHeaders({})
rl2 = parse_rate_limit(empty)
assert rl2["remaining_requests"] == "", "없는 헤더는 빈 문자열"
print("✓ 통과")
```

---

📝 **마크다운 셀**

```
**연결:** `parse_rate_limit()`은 `_groq.py`의 `chat_completion()` 내부,
`urlopen()` 컨텍스트 매니저 안에서 `resp.headers`를 인자로 호출된다.

---
## 섹션 3 — 429 재시도 패턴

한도 초과 시 Groq는 오류 메시지에 대기 시간을 알려준다.
```json
{"error": {"message": "Rate limit exceeded: please try again in 12.5s"}}
```
정규식으로 숫자를 추출해 `time.sleep()` 후 재시도한다.
```

---

💻 **코드 셀** (워밍업)

```python
import re

# 정규식으로 숫자 추출
messages = [
    "Rate limit exceeded: please try again in 12.5s",
    "Please try again in 60s",
    "Unknown error occurred",   # 숫자 없음
]

for msg in messages:
    m = re.search(r"try again in ([\d.]+)s", msg)
    if m:
        print(f"대기 시간: {float(m.group(1))}초")
    else:
        print("대기 시간 파싱 실패 → 기본값 사용")
```

---

💻 **코드 셀** (본 실습)

```python
def extract_wait_seconds(error_msg: str, default: float = 60.0) -> float:
    """오류 메시지에서 대기 시간(초)을 추출한다.
    
    파싱 실패 시 default 반환.
    힌트: re.search(r"try again in ([\d.]+)s", error_msg)
    """
    # TODO
    pass
```

---

💻 **코드 셀** (채점)

```python
assert abs(extract_wait_seconds("please try again in 12.5s") - 12.5) < 1e-6, "12.5초"
assert abs(extract_wait_seconds("try again in 60s") - 60.0) < 1e-6, "60초"
assert abs(extract_wait_seconds("unknown error") - 60.0) < 1e-6, "파싱 실패 → 기본값"
assert abs(extract_wait_seconds("unknown error", default=30.0) - 30.0) < 1e-6, "기본값 변경"
print("✓ 통과")
```

---

📝 **마크다운 셀**

```
**연결:** `extract_wait_seconds()`는 `_groq.py chat_completion()`의 429 처리 블록에서 쓰인다.

```python
# _groq.py 내부 (골격 파일 구현 시 참고)
if exc.code == 429 and attempt < 3:
    wait = extract_wait_seconds(error_msg) + 2.0   # 여유 시간 추가
    time.sleep(wait)
    continue
```

---
## 스스로 정리해보기

노트북 완료 후 직접 작성:
- urllib로 외부 API를 호출할 때 꼭 필요한 헤더 3가지는?
- Cloudflare가 Python을 차단하는 이유와 우회 방법은?
- 429 오류가 발생했을 때 바로 raise하지 않고 재시도하는 이유는?
```
