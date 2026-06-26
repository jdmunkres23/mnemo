# Phase 3-1 이론 — Groq API 래퍼 (`_groq.py`)

## 1. 왜 urllib인가?

이 프로젝트의 원칙: **외부 의존성 최소화**.
`requests` 패키지가 더 간결하지만, Python 표준 라이브러리 `urllib.request`로 충분하다.

| | `urllib.request` | `requests` |
|---|---|---|
| 설치 | 불필요 (표준 라이브러리) | `pip install requests` |
| JSON 전송 | `json.dumps().encode()` + 헤더 수동 설정 | `requests.post(json=...)` |
| 응답 헤더 | `resp.headers.get(key)` | `resp.headers[key]` |
| 역할 | 충분 | 더 편리하지만 의존성 추가 |

---

## 2. HTTP 메서드 — GET vs POST

HTTP 요청에는 종류가 있다. 이 프로젝트에서 쓰는 두 가지:

| | GET | POST |
|---|---|---|
| 용도 | 데이터를 달라고 요청 | 데이터를 보내면서 요청 |
| body | 없음 | 있음 (`data=payload`) |
| 예시 | 모델 목록 조회 | 채팅 메시지 전송 |

`urllib.request.Request`는 `data`가 있으면 자동으로 POST, 없으면 자동으로 GET:

```python
# POST — data 있음
urllib.request.Request(url, data=payload, headers=...)

# GET — data 없음, method 생략 가능
urllib.request.Request(url, headers=...)
```

---

## 3. REST API 외부 호출 패턴

외부 API는 항상 같은 패턴:

```
1. URL 결정
2. 인증 헤더 추가 (Authorization: Bearer ...)
3. payload를 JSON으로 직렬화
4. 요청 전송
5. 응답 JSON 파싱
6. 오류 코드 처리 (4xx, 5xx)
```

urllib로 표현하면:

```python
import urllib.request, json

payload = json.dumps({"model": "...", "messages": [...]}).encode("utf-8")

req = urllib.request.Request(
    url,
    data=payload,
    headers={
        "Authorization": "Bearer gsk_...",
        "Content-Type": "application/json",
    },
    method="POST",
)

with urllib.request.urlopen(req, timeout=60) as resp:
    body = json.loads(resp.read().decode("utf-8"))
```

---

## 3. Cloudflare User-Agent 차단 (error 1010)

Groq API는 Cloudflare CDN 뒤에 있다.
기본 Python User-Agent (`Python-urllib/3.x`)를 Cloudflare가 봇으로 판단해 **HTTP 1010** 오류를 반환한다.

* 추가 설명 : UA = User-Agent

HTTP 요청 시 "나는 어떤 클라이언트다"라고 서버에 알려주는 헤더입니다.

브라우저가 보내는 예시:


Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36
Python이 기본으로 보내는 예시:


Python-urllib/3.11
Cloudflare 입장에서 Python-urllib/3.11은 봇 시그니처이므로 차단하고, 브라우저 UA는 통과시킵니다. 그래서 _groq.py에서 브라우저 UA로 위장하는 겁니다.



**해결:** 브라우저 User-Agent로 위장

```python
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
```

모든 요청 헤더에 `"User-Agent": _UA` 필수.

---

## 4. Authorization Bearer 토큰

REST API 인증의 표준 방식. HTTP 헤더에 토큰을 담아 전달한다.

```
Authorization: Bearer gsk_xxxxxxxxxxxxxxxxxxxxxxxx
```

- `Bearer`: 토큰 타입 (소지자 토큰)
- Groq의 경우 API 대시보드에서 `gsk_...` 형식의 키 발급
- 키는 **`.env` 파일에만** 저장, 소스코드·JS·로그에 절대 노출 금지

```python
# .env 파일 예시
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

---

## 5. Rate Limit 헤더

Groq 무료 플랜은 분당 요청/토큰 수가 제한된다.
API 응답 헤더에서 현재 남은 한도를 읽을 수 있다.

| 헤더 | 의미 |
|---|---|
| `x-ratelimit-remaining-requests` | 남은 요청 수 |
| `x-ratelimit-remaining-tokens` | 남은 토큰 수 |
| `x-ratelimit-reset-requests` | 요청 한도 초기화까지 남은 시간 |
| `x-ratelimit-reset-tokens` | 토큰 한도 초기화까지 남은 시간 |

이 값들을 읽어 UI의 rate limit 배지에 표시한다 (`chat.js`).

```python
with urllib.request.urlopen(req) as resp:
    rate_limit = {
        "remaining_requests": resp.headers.get("x-ratelimit-remaining-requests", ""),
        "remaining_tokens":   resp.headers.get("x-ratelimit-remaining-tokens", ""),
        "reset_requests":     resp.headers.get("x-ratelimit-reset-requests", ""),
        "reset_tokens":       resp.headers.get("x-ratelimit-reset-tokens", ""),
    }
```

---

## 6. 429 재시도 패턴

한도 초과 시 Groq는 `HTTP 429 Too Many Requests`를 반환하며, 오류 메시지에 대기 시간이 포함된다.

```json
{"error": {"message": "Rate limit exceeded: please try again in 12.5s"}}
```

정규식으로 대기 시간 추출 → `time.sleep()` → 재시도:

```python
import re, time

m = re.search(r"try again in ([\d.]+)s", error_message)
wait = float(m.group(1)) + 2.0 if m else 60.0   # 파싱 실패 시 60초 보수적 대기
time.sleep(wait)
```

최대 재시도 횟수를 두어 무한 루프를 방지한다 (solution: 최대 4회).

---

## 7. resp와 exc 객체 구조

`urlopen()`을 쓸 때 실제로 어떤 데이터가 오가는지 구체적으로 정리한다.

### 성공 시 — `resp` (HTTPResponse)

```python
with urllib.request.urlopen(req, timeout=60) as resp:
    ...
```

**`resp.headers`** — 응답 헤더. `dict`처럼 `.get(키, 기본값)`으로 접근.

```
x-ratelimit-remaining-requests: 28
x-ratelimit-remaining-tokens: 5000
x-ratelimit-reset-requests: 2s
x-ratelimit-reset-tokens: 500ms
content-type: application/json
```

**`resp.read()`** — 응답 body. bytes 타입.

```python
b'{"id":"chatcmpl-xxx","object":"chat.completion","choices":[{"message":{"role":"assistant","content":"안녕하세요!"}}],"usage":{"prompt_tokens":10,"completion_tokens":5,"total_tokens":15}}'
```

`json.loads(resp.read().decode("utf-8"))` 후 dict가 되면:

```python
{
    "choices": [
        {"message": {"role": "assistant", "content": "안녕하세요!"}}
    ],
    "usage": {
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "total_tokens": 15
    }
}
```

→ 답변 꺼내기: `body["choices"][0]["message"]["content"]`  
→ 사용량 꺼내기: `body["usage"]`

---

### 실패 시 — `exc` (HTTPError)

```python
except urllib.error.HTTPError as exc:
    ...
```

**`exc.code`** — HTTP 상태 코드 (숫자).

```
429   # rate limit 초과 → 대기 후 재시도
401   # 인증 실패 → API 키 확인
500   # 서버 오류 → raise
```

**`exc.read()`** — 오류 body. `resp.read()`와 똑같이 bytes 타입.

```python
b'{"error":{"message":"Rate limit exceeded: please try again in 12.5s","type":"rate_limit_exceeded"}}'
```

`json.loads(exc.read().decode("utf-8"))` 후:

```python
{
    "error": {
        "message": "Rate limit exceeded: please try again in 12.5s",
        "type": "rate_limit_exceeded"
    }
}
```

→ 메시지 꺼내기: `body["error"]["message"]`

---

### 요약

| | 헤더 | body |
|---|---|---|
| 성공 (`resp`) | `resp.headers.get("키", "")` | `resp.read()` |
| 실패 (`exc`) | `exc.code` (숫자) | `exc.read()` |

`resp`와 `exc` 모두 `.read()`로 body를 읽는 구조는 동일하다.
API마다 달라지는 건 body 안의 JSON 구조뿐이다.

---

## 8. 프로젝트 내 연결

```
_groq.py
  ├── load_env_key()      .env에서 GROQ_API_KEY 읽기
  │     → server.py, evaluator.py 에서 호출
  │
  ├── chat_completion()   Groq chat completions 호출
  │     → server.py  /api/groq-proxy  (브라우저 → 서버 → Groq)
  │     → evaluator.py  직접 호출 (CLI 평가)
  │
  └── list_models()       가용 모델 목록 조회
        → server.py  /api/groq-models  (chat.js 드롭다운용)
```

**왜 서버가 Groq 프록시를 하는가?**
브라우저(JS)가 직접 Groq를 호출하면 API 키가 JS 코드에 노출된다.
서버를 거치면 키는 서버의 `.env`에만 존재하고, 브라우저는 키를 볼 수 없다.

```
브라우저                서버                  Groq
  │─── POST /api/groq-proxy ──→│
  │       (키 없음)             │─── POST api.groq.com ──→│
  │                            │←── 응답 ────────────────│
  │←─── 응답 ──────────────────│
```
