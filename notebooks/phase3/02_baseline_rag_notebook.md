# Phase 3-2 노트북 셀 내용 — Baseline RAG

셀 타입 표기: **📝 마크다운 셀** / **💻 코드 셀**  
각 구분선(`---`) 사이 내용을 해당 타입의 셀에 붙여넣기.

---

📝 **마크다운 셀**

```
# Phase 3-2 — Baseline RAG

**목표:** session.json에서 텍스트를 추출해 Groq에 컨텍스트로 전달하는 baseline RAG를 구현한다.

**이 노트북을 마치면:**
- [ ] session.json에서 text 블록만 추출할 수 있다
- [ ] max_chars 기준으로 앞 60% + 뒤 40% 자르기를 구현할 수 있다
- [ ] system + multi-turn messages 배열을 구성할 수 있다

**완성 후 연결:**  
`src/evaluator.py`의 `extract_text_context()`, `run_baseline()` 구현
```

---

📝 **마크다운 셀**

```
---
## 섹션 1 — session.json에서 텍스트 추출

### session.json 구조 복습

```json
{
  "turns": [
    {"role": "user",      "blocks": [{"type": "text", "text": "..."}]},
    {"role": "assistant", "blocks": [{"type": "text",    "text": "..."},
                                     {"type": "thinking", "thinking": "..."}]}
  ]
}
```

RAG 컨텍스트에는 **text 블록만** 사용한다.
`thinking`, `tool_use`, `tool_result`는 노이즈이거나 RAG에 불필요한 정보.
```

---

💻 **코드 셀** (워밍업)

```python
import json
from pathlib import Path

# 테스트용 미니 세션 (실제 session.json과 같은 구조)
sample_session = {
    "session_id": "test-001",
    "title": "테스트 대화",
    "turns": [
        {"role": "user", "blocks": [
            {"type": "text", "text": "fastembed 설치 방법을 알려줘"}
        ]},
        {"role": "assistant", "blocks": [
            {"type": "thinking", "thinking": "사용자가 fastembed 설치를 원한다..."},
            {"type": "text", "text": "pip install fastembed 명령어로 설치할 수 있습니다."}
        ]},
        {"role": "user", "blocks": [
            {"type": "text", "text": "ONNX 런타임도 필요한가요?"}
        ]},
        {"role": "assistant", "blocks": [
            {"type": "text", "text": "fastembed이 자동으로 포함합니다."},
            {"type": "token_budget", "remaining": 5000}
        ]},
    ]
}

# text 블록만 추출하는 기본 패턴
for idx, turn in enumerate(sample_session["turns"]):
    role = "사용자" if turn["role"] == "user" else "AI"
    texts = [b["text"] for b in turn["blocks"] if b["type"] == "text"]
    print(f"[{idx}] {role}: {texts}")
```

---

📝 **마크다운 셀**

```
### 미니 실습: 턴을 포맷 문자열로 변환

각 턴을 `"[사용자]\n텍스트"` 또는 `"[AI]\n텍스트"` 형식으로 만든다.
```

---

💻 **코드 셀** (미니 실습)

```python
def format_turn(idx: int, turn: dict) -> tuple[int, str] | None:
    """턴 하나를 (인덱스, 포맷 문자열)로 변환한다.
    
    text 블록이 없으면 None 반환.
    포맷: "[사용자]\n텍스트" 또는 "[AI]\n텍스트"
    힌트: role == "user" → "사용자", 나머지 → "AI"
    """
    # TODO
    pass
```

---

💻 **코드 셀** (채점)

```python
t0 = sample_session["turns"][0]  # user, text 있음
t1 = sample_session["turns"][1]  # assistant, text + thinking
t3_no_text = {"role": "assistant", "blocks": [{"type": "token_budget", "remaining": 1}]}

r0 = format_turn(0, t0)
assert r0 is not None and r0[0] == 0, "인덱스 반환 확인"
assert "[사용자]" in r0[1], "[사용자] 포함 확인"
assert "fastembed" in r0[1], "텍스트 포함 확인"

r1 = format_turn(1, t1)
assert "[AI]" in r1[1], "[AI] 포함 확인"
assert "thinking" not in r1[1].lower(), "thinking 내용 제외 확인"
assert "pip install" in r1[1], "text 블록 내용 포함 확인"

assert format_turn(0, t3_no_text) is None, "text 없으면 None"
print("✓ 통과")
```

---

📝 **마크다운 셀**

```
### 본 실습: extract_text_context() 구현

세션 전체 텍스트를 추출하고, max_chars 초과 시 잘라낸다.

**자르기 전략: 앞 60% + 뒤 40%**
```
전체: [0][1][2][3][4][5][6][7][8][9]
head(60%): [0][1][2][3][4]
tail(40%): [7][8][9]
결과: [0][1][2][3][4] + "...[중략: N자 생략]..." + [7][8][9]
```
```

---

💻 **코드 셀** (본 실습)

```python
def extract_text_context(session: dict, max_chars: int = 0) -> tuple[str, set]:
    """session.json에서 text 블록만 추출해 하나의 문자열로 합친다.
    
    max_chars > 0 이면 앞 60% + 뒤 40% 전략으로 자른다.
    Returns: (context_str, included_turn_indices)
    
    구분자: "\n\n---\n\n"
    잘릴 경우 중간에 삽입: "\n\n...[중략: N자 생략]...\n\n"
    
    힌트:
    - format_turn()으로 각 턴을 변환 (None 제외)
    - 전체 텍스트 길이 ≤ max_chars 이면 그대로 반환
    - head_budget = int(max_chars * 0.6)
    - head_parts: 앞에서부터 budget을 채우는 턴들
    - tail_parts: 뒤에서부터 budget을 채우는 턴들 (head와 겹치지 않게)
    """
    _SEP = "\n\n---\n\n"
    # TODO
    pass
```

---

💻 **코드 셀** (채점)

```python
# 자르기 없는 경우
ctx, included = extract_text_context(sample_session, max_chars=0)
assert "fastembed" in ctx, "텍스트 포함 확인"
assert len(included) == 4, f"4개 턴 모두 포함, 실제: {len(included)}"
assert "thinking" not in ctx.lower(), "thinking 제외 확인"
assert "---" in ctx, "구분자 포함 확인"

# 자르기 적용 (최소 글자 수 지정)
ctx2, included2 = extract_text_context(sample_session, max_chars=50)
assert "중략" in ctx2, "중략 표시 확인"
assert len(included2) < 4, "일부 턴만 포함"

print(f"전체: {len(ctx)}자, 포함 턴: {included}")
print(f"자른 후: {len(ctx2)}자, 포함 턴: {included2}")
print("✓ 통과")
```

---

📝 **마크다운 셀**

```
**연결:** `extract_text_context()`는 `evaluator.py`와 `server.py _api_groq_proxy()`에서 그대로 재사용된다.

---
## 섹션 2 — RAG 호출 (system 프롬프트 구성)

세션 컨텍스트를 system 메시지에 담아 Groq에 전달하는 패턴.
```

---

💻 **코드 셀** (워밍업)

```python
# system + user messages 구조
context, _ = extract_text_context(sample_session)

system_content = (
    "아래는 사용자와 AI가 나눈 대화 기록입니다. "
    "이 대화 내용만을 근거로 질문에 답하세요.\n\n"
    + context
)

messages = [
    {"role": "system",  "content": system_content},
    {"role": "user",    "content": "fastembed 설치는 어떻게 해?"},
]

print(f"system 길이: {len(system_content)}자")
print(f"messages 구조: {[m['role'] for m in messages]}")
```

---

💻 **코드 셀** (본 실습)

```python
def build_rag_messages(session: dict, question: str, history: list[dict],
                       max_chars: int = 8000) -> list[dict]:
    """RAG 호출용 messages 배열을 만든다.
    
    구조: [system(컨텍스트), ...history, user(question)]
    
    힌트:
    - extract_text_context(session, max_chars) 로 컨텍스트 추출
    - system 메시지: "아래는 ... 대화 기록입니다. 이 대화 내용만을 근거로 답하세요.\n\n" + context
    - history는 기존 대화 이력 (role: user/assistant)
    - 마지막에 user 메시지 추가
    """
    # TODO
    pass
```

---

💻 **코드 셀** (채점)

```python
msgs = build_rag_messages(sample_session, "설치 명령어는?", [])
assert msgs[0]["role"] == "system", "첫 번째가 system"
assert "대화 기록" in msgs[0]["content"], "system에 컨텍스트 설명 포함"
assert "fastembed" in msgs[0]["content"] or "pip" in msgs[0]["content"], "컨텍스트 포함"
assert msgs[-1]["role"] == "user", "마지막이 user"
assert msgs[-1]["content"] == "설치 명령어는?", "질문 포함"

# 이력이 있는 경우
history = [
    {"role": "user", "content": "이전 질문"},
    {"role": "assistant", "content": "이전 답변"},
]
msgs2 = build_rag_messages(sample_session, "다음 질문", history)
roles = [m["role"] for m in msgs2]
assert roles == ["system", "user", "assistant", "user"], f"순서 확인: {roles}"
print("✓ 통과")
```

---

📝 **마크다운 셀**

```
---
## 섹션 3 — Multi-turn 이력 관리

대화가 계속되면 messages 배열이 길어진다.
토큰 한계를 넘지 않도록 최근 N개만 유지한다.

**규칙:** system 메시지는 항상 유지. user/assistant 쌍 단위로 잘라낸다.
```

---

💻 **코드 셀** (본 실습)

```python
def trim_history(messages: list[dict], max_turns: int = 10) -> list[dict]:
    """messages에서 최근 max_turns 쌍(user+assistant)만 유지한다.
    
    system 메시지는 항상 첫 번째에 유지.
    user/assistant 교대 쌍을 기준으로 오래된 것부터 제거.
    
    힌트:
    - messages[0]["role"] == "system" 인지 먼저 확인
    - system 이후의 메시지를 pair 단위(2개씩)로 끊어서 최신 max_turns 쌍만 유지
    """
    # TODO
    pass
```

---

💻 **코드 셀** (채점)

```python
# system + 6쌍 = 13개 메시지
msgs = [{"role": "system", "content": "ctx"}]
for i in range(6):
    msgs.append({"role": "user",      "content": f"q{i}"})
    msgs.append({"role": "assistant", "content": f"a{i}"})

trimmed = trim_history(msgs, max_turns=3)
assert trimmed[0]["role"] == "system", "system 유지"
# system 1개 + 최근 3쌍 6개 = 7개
assert len(trimmed) == 7, f"system + 3쌍 = 7개, 실제: {len(trimmed)}"
assert trimmed[1]["content"] == "q3", f"q3부터 시작해야 함, 실제: {trimmed[1]['content']}"

# system 없는 경우
msgs_no_sys = [{"role": "user", "content": f"q{i}"} for i in range(6)]
trimmed2 = trim_history(msgs_no_sys, max_turns=2)
assert len(trimmed2) == 2, "system 없으면 단순 슬라이싱"
print("✓ 통과")
```

---

📝 **마크다운 셀**

```
**연결:**
- `build_rag_messages()`의 패턴 → `server.py _api_groq_proxy()` 내부
- `trim_history()` → `chat.js`에서 JS로 동일한 로직 구현

---
## 스스로 정리해보기

노트북 완료 후 직접 작성:
- RAG에서 text 블록만 쓰는 이유는?
- 앞 60% + 뒤 40% 전략의 trade-off는?
- system 메시지를 매 요청마다 넣는 비용을 어떻게 줄일 수 있을까? (Phase 4 힌트)
```
