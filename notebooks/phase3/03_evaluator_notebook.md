# Phase 3-3 노트북 셀 내용 — RAG 평가 파이프라인

셀 타입 표기: **📝 마크다운 셀** / **💻 코드 셀**  
각 구분선(`---`) 사이 내용을 해당 타입의 셀에 붙여넣기.

---

📝 **마크다운 셀**

```
# Phase 3-3 — RAG 평가 파이프라인 (evaluator.py)

**목표:** RAG가 실제로 얼마나 잘 동작하는지 수치로 측정하는 평가 파이프라인을 구현한다.

**이 노트북을 마치면:**
- [ ] Hit Rate(결정론)를 집합 연산으로 계산할 수 있다
- [ ] key_facts 결정론 채점을 구현할 수 있다
- [ ] LLM-as-judge 프롬프트를 설계하고 점수를 파싱할 수 있다

**완성 후 연결:**  
`src/evaluator.py`의 `compute_hit()`, `keyfact_score()`, `judge_answers()` 구현
```

---

📝 **마크다운 셀**

```
---
## 섹션 1 — Hit Rate (결정론 지표)

### 개념

Hit Rate = 정답이 있는 턴이 컨텍스트에 포함된 비율.

```
source_turns: [2, 5]         # QA 쌍에 명시된 정답 위치
included_turns: {1, 2, 4}   # 컨텍스트에 실제로 포함된 턴들

Hit Rate = |{2, 5} ∩ {1, 2, 4}| / |{2, 5}|
         = |{2}| / 2 = 0.5
```

**왜 결정론인가?** LLM 없이 집합 연산만으로 계산한다. 실행할 때마다 같은 값.
**언제 의미 있는가?** Phase 4에서 벡터 검색이 관련 청크를 선택할 때.
baseline에서는 전체 텍스트를 넣으므로 항상 1.0에 가깝다.
```

---

💻 **코드 셀** (워밍업)

```python
# 집합 연산 복습
source = {2, 5}
included = {1, 2, 4}

intersection = source & included   # 교집합
print(f"교집합: {intersection}")
print(f"hit: {len(intersection)} / {len(source)} = {len(intersection)/len(source):.2f}")
```

---

💻 **코드 셀** (미니 실습)

```python
def compute_hit(source_turns: list[int], included_turns: set[int]) -> float:
    """source_turns 중 included_turns에 있는 비율 (0.0 ~ 1.0).
    
    source_turns가 비어 있으면 1.0 반환 (평가 불가 케이스 중립 처리).
    힌트: set 교집합 연산 활용
    """
    # TODO
    pass
```

---

💻 **코드 셀** (채점)

```python
assert compute_hit([2, 5], {1, 2, 4}) == 0.5,   "절반만 포함"
assert compute_hit([2, 5], {1, 2, 4, 5}) == 1.0, "전부 포함"
assert compute_hit([2, 5], {1, 3, 4}) == 0.0,    "하나도 없음"
assert compute_hit([], {1, 2, 3}) == 1.0,         "source 없으면 1.0"
assert compute_hit([3], {3}) == 1.0,              "단일 턴 매칭"
print("✓ 통과")
```

---

📝 **마크다운 셀**

```
**연결:** `compute_hit()`은 `evaluator.py run_baseline()` 안에서
각 QA 쌍의 `source_turns`와 `included_turns`를 비교할 때 호출된다.

---
## 섹션 2 — key_facts 결정론 채점

### 개념

답변에 핵심 값이 들어있는가를 단순 문자열 포함으로 판단한다.
LLM 판단 없이 빠르고 재현 가능하다.

**정규화 (`_norm`):** 소문자 + 콤마/공백 제거
- "1,024" → "1024"
- "fastembed" → "fastembed"
- "my_function()" → "my_function()" (변경 없음)

단일 질문 → **Correctness** / 멀티홉 질문 → **Completeness**
```

---

💻 **코드 셀** (워밍업)

```python
def _norm(s: str) -> str:
    """매칭용 정규화: 소문자 + 콤마/공백 제거."""
    return s.lower().replace(",", "").replace(" ", "")

# 예시
tests = [
    ("1,024", "1024"),
    ("Hello World", "helloworld"),
    ("0.3", "0.3"),
]
for original, expected in tests:
    result = _norm(original)
    print(f"_norm({original!r}) = {result!r}  {'✓' if result == expected else '✗'}")
```

---

💻 **코드 셀** (미니 실습)

```python
def keyfact_score(answer: str, key_facts: list[str]) -> float | None:
    """답변에 포함된 key_facts 비율 (0.0 ~ 1.0).
    
    key_facts가 비어 있으면 None 반환.
    각 fact가 _norm(answer)에 포함되는지 확인.
    
    힌트:
    - _norm(fact) in _norm(answer)
    - 포함된 수 / 전체 수
    """
    # TODO
    pass
```

---

💻 **코드 셀** (채점)

```python
# 전부 포함
assert keyfact_score("임계값은 0.3입니다", ["0.3"]) == 1.0
# 일부 포함
assert keyfact_score("35명이 참가했습니다", ["35", "20"]) == 0.5
# 하나도 없음
assert keyfact_score("잘 모르겠습니다", ["0.3", "fastembed"]) == 0.0
# key_facts 없으면 None
assert keyfact_score("아무 답변", []) is None
# 대소문자/공백 무관
assert keyfact_score("FastEmbed 설치 완료", ["fastembed"]) == 1.0
# 콤마 있는 숫자
assert keyfact_score("1,024개 토큰", ["1024"]) == 1.0
print("✓ 통과")
```

---

📝 **마크다운 셀**

```
**연결:** `keyfact_score()`는 `evaluator.py run_baseline()`에서
각 QA 답변의 `key_facts` 포함 여부를 확인할 때 호출된다.

---
## 섹션 3 — LLM-as-judge

### 개념

key_facts로 잡지 못하는 서술형 답변 품질을 LLM이 0~10점으로 채점한다.

**프롬프트 설계 원칙:**
1. 기준 명시: 채점 기준을 명확히 설명
2. 참조 제공: 기대 답변을 함께 제공
3. 출력 제한: "숫자만 출력"으로 파싱 용이하게
4. 낮은 토큰: max_tokens=10 (숫자 하나면 충분)
```

---

💻 **코드 셀** (워밍업)

```python
# LLM judge 프롬프트 예시
example_prompt = """다음 질문에 대한 답변을 평가하세요.

질문: 이 대화에서 설정한 top_k 값은?
기대 답변: 3
실제 답변: top_k는 5로 설정했습니다.

평가 기준:
- 기대 답변의 핵심 정보가 포함됐는지 (0~10점)
- 사실과 다른 내용이 있으면 감점

숫자만 출력하세요 (예: 7)"""

print(example_prompt)
print()
# 실제 답변이 틀렸으므로 → 0~2점 예상
```

---

💻 **코드 셀** (본 실습)

```python
def build_judge_prompt(question: str, expected: str, answer: str) -> str:
    """LLM-as-judge 프롬프트를 생성한다.
    
    포함 요소:
    - 질문, 기대 답변, 실제 답변
    - 채점 기준 (핵심 정보 포함 여부, 사실 오류 감점)
    - "숫자만 출력" 지시
    """
    # TODO
    pass
```

---

💻 **코드 셀** (채점)

```python
p = build_judge_prompt("임계값은?", "0.3", "임계값은 0.3입니다.")
assert "임계값은?" in p or "임계값" in p, "질문 포함"
assert "0.3" in p, "기대 답변 포함"
assert "임계값은 0.3입니다" in p, "실제 답변 포함"
assert "숫자" in p, "'숫자만 출력' 지시 포함"
print("✓ 통과")
print("\n생성된 프롬프트:")
print(p)
```

---

💻 **코드 셀** (본 실습)

```python
import re

def parse_judge_score(content: str) -> float:
    """LLM 출력에서 0~10 점수를 파싱한다.
    
    파싱 실패 시 0.0 반환.
    0~10 범위를 벗어나면 클리핑.
    
    힌트:
    - content.strip().split()[0].rstrip(".")
    - float() + try/except
    - max(0.0, min(10.0, score))
    """
    # TODO
    pass
```

---

💻 **코드 셀** (채점)

```python
assert parse_judge_score("7") == 7.0,       "정수"
assert parse_judge_score("7.5") == 7.5,     "소수"
assert parse_judge_score("7.") == 7.0,      "마침표 포함"
assert parse_judge_score("7 점") == 7.0,    "숫자 뒤 텍스트"
assert parse_judge_score("abc") == 0.0,     "파싱 실패 → 0"
assert parse_judge_score("15") == 10.0,     "10 초과 → 클리핑"
assert parse_judge_score("-3") == 0.0,      "0 미만 → 클리핑"
print("✓ 통과")
```

---

💻 **코드 셀** (본 실습)

```python
# API 키 준비 (노트북 01에서 가져오기)
import sys
sys.path.insert(0, "..")
from src._groq import chat_completion, load_env_key  # _groq.py 구현 완료 후 실행

def judge_single(question: str, expected: str, answer: str, api_key: str) -> float:
    """답변 하나를 0~10점으로 채점한다.
    
    힌트:
    - build_judge_prompt()로 프롬프트 생성
    - chat_completion([{"role": "user", "content": prompt}],
                      "llama-3.1-8b-instant", api_key, max_tokens=10, temperature=0.0)
    - parse_judge_score()로 점수 파싱
    - 예외 발생 시 0.0 반환
    """
    # TODO
    pass
```

---

📝 **마크다운 셀**

```
### 실제 채점 실험

`_groq.py` 구현 완료 후 실행.
```

---

💻 **코드 셀** (본 실습)

```python
# _groq.py 구현 후 실행
API_KEY = load_env_key()

test_cases = [
    {
        "question": "설치 명령어는?",
        "expected": "pip install fastembed",
        "answer":   "pip install fastembed 명령어로 설치합니다.",
    },
    {
        "question": "설치 명령어는?",
        "expected": "pip install fastembed",
        "answer":   "conda install 명령어를 쓰세요.",
    },
]

for tc in test_cases:
    score = judge_single(tc["question"], tc["expected"], tc["answer"], API_KEY)
    print(f"Q: {tc['question']}")
    print(f"A: {tc['answer']}")
    print(f"Score: {score}/10\n")
```

---

📝 **마크다운 셀**

```
**연결:** `build_judge_prompt()`, `parse_judge_score()`, `judge_single()`은
`evaluator.py judge_answers()` 내부에서 각 결과 항목마다 호출된다.

---
## 스스로 정리해보기

노트북 완료 후 직접 작성:
- Hit Rate가 1.0이어도 Correctness가 낮을 수 있는 이유는?
- LLM-as-judge의 가장 큰 신뢰성 문제는 무엇이고, 이 프로젝트에서 어떻게 완화하는가?
- baseline에서 전체 텍스트를 넣어도 답변이 틀리는 이유는 무엇일까?
```
