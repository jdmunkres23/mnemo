# RAG 답변 채점 가이드 (A안: 다축 평가)

`evaluator.py`를 `--no-judge`로 돌려 답변만 뽑은 뒤(`results-*.json`),
아래 두 경로로 채점합니다. 8B 자동 심판은 쓰지 않습니다(노이즈 큼).

## 평가 축 4개

| 축 | 무엇을 보나 | 어떻게 | 언제 |
|---|---|---|---|
| **Hit Rate** | 정답 청크를 검색했나 | 결정론 (`source_turns` ∩ 검색청크) | 이미 evaluator에 있음 |
| **Correctness** | 답이 정답 사실을 맞혔나 | key_facts(결정론) + 클로드 | 지금 |
| **Completeness** | (멀티홉) 필요한 사실을 다 담았나 | key_facts 비율 + 클로드 | 지금 |
| **Faithfulness** | 답이 컨텍스트에 근거하나(환각 아님) | 클로드 (컨텍스트 필요) | 검색 모드 구현 후 |

> Correctness/Completeness는 `expected`/`key_facts`만 있으면 채점돼서 지금 바로 됩니다.
> Faithfulness는 항목별 컨텍스트가 필요해서, vector/kg 모드를 만들 때 추가합니다(맨 아래 Phase 2).

## 두 채점 경로 (하이브리드)

- **결정론(key_facts)** — 값 질문(포트·퍼센트·건수 등)에 빠르고 재현되고 무료. Correctness/Completeness를 자동 산출.
- **클로드(Sonnet 4.6)** — 패러프레이즈·설명형·멀티홉의 뉘앙스, 그리고 Faithfulness 판단.
- **권장 흐름**: 결정론으로 전체를 1차 채점 → 결정론과 어긋나거나 `key_facts`가 약한 설명형 항목만 클로드로 확인·보정.

> 채점 모델은 **Sonnet 4.6**이면 충분합니다(채점은 깊은 추론이 아니라 대조 작업). Opus는 멀티홉 부분점수가 애매한 소수 항목 재확인용으로만. 핵심은 **비교하는 모든 모드를 같은 채점자·같은 루브릭으로 고정**하는 것. VS Code 클로드 익스텐션이면 모델 드롭다운을 Sonnet 4.6으로 두고 채점 내내 바꾸지 마세요.

---

## A) 결정론 스코어러 — evaluator.py에 추가

```python
def _norm(s: str) -> str:
    return s.lower().replace(",", "").replace(" ", "")

def keyfact_score(answer: str, key_facts: list[str]) -> float | None:
    """답변에 포함된 key_facts 비율(0~1). 없으면 None."""
    if not key_facts:
        return None
    a = _norm(answer)
    return sum(1 for k in key_facts if _norm(k) in a) / len(key_facts)
```

`run_baseline`의 결과 dict에 두 줄만 추가:

```python
            results.append({
                "question": question,
                "expected": qa.get("expected", ""),
                "answer": content,
                "usage": usage,
                "hit": hit,
                "type": qa.get("type", "single"),
                "source_turns": qa.get("source_turns", []),
                "key_facts": qa.get("key_facts", []),                       # 추가
                "keyfact_score": keyfact_score(content, qa.get("key_facts", [])),  # 추가
            })
```

- 단일·값 질문에서는 `keyfact_score`가 곧 Correctness입니다(0~1 → ×10).
- 멀티홉에서는 `keyfact_score`가 곧 Completeness입니다(필요 사실 중 몇 개나 담았나).
- `--no-judge`로 돌려도 이 값은 LLM 호출 없이 채워지므로 Groq 한도와 무관합니다.

---

## B) 클로드 채점 프롬프트 (새 대화에 붙여넣기)

> **새 빈 대화**에서 쓰세요. 프로젝트 지식·CLAUDE.md가 딸려 들어가면 채점 기준이 오염됩니다.
> 모드마다·실행마다 **이 텍스트 그대로** 쓰세요(루브릭이 바뀌면 모드 비교가 깨짐).
> 결과 파일은 하나씩(short/long, baseline/vector 따로) 붙여넣으세요.

```
당신은 RAG 시스템이 생성한 답변을 채점하는 평가자입니다.
각 항목에서 시스템의 `answer`를 `expected`(정답)와 비교해 두 축으로 0~10점을 매기세요.

[채점 원칙]
- `expected`가 유일한 정답 기준입니다. 외부/세상 지식으로 expected를 교정하거나 의심하지 마세요.
  이 값들은 특정 대화에 종속되며 일부는 가상입니다. answer가 expected와 다르면 그럴듯해도 오답입니다.
- 표현이 아니라 의미로 채점하세요. 동의어·패러프레이즈·같은 뜻의 다른 단위는 정답 인정.
  단, 숫자·식별자(포트, 퍼센트, 건수, 설정값)는 정확히 일치해야 합니다. 다른 숫자는 오답.
- 요구 안 한 추가 정보에 가점 금지, 핵심 사실이 있으면 답이 길어도 감점 금지.
- answer가 비었거나 "모른다/찾을 수 없다/회피"거나 "오류:"로 시작하면 두 축 모두 0점.

[두 축의 정의]
- correctness(정답성): answer가 진술한 사실이 expected와 맞는가. expected와 모순되는 사실이 있으면 강하게 감점.
- completeness(완전성): expected가 요구하는 사실을 빠짐없이 담았는가.
  expected에 사실이 N개면, 맞게 담은 비율로 점수(예: 3개 중 2개 → 약 7). 단일 사실 질문이면 correctness와 같게.
  (즉 correctness="말한 게 맞나", completeness="다 말했나". 멀티홉에서 둘이 갈립니다.)

[참고용 key_facts]
각 항목에는 정답에 들어가야 할 핵심 문자열 목록 `key_facts`가 있습니다. 채점에 참고하되,
answer가 key_facts와 글자는 달라도 같은 의미를 정확히 전달하면 정답으로 인정하세요(당신의 판단이 우선).

[출력]
1) 항목마다 한 줄:
   #<번호> [<type>] correctness=<0-10> completeness=<0-10> hit=<hit> — <15자 이내 사유>
2) [요약]:
   - 평균 correctness, 평균 completeness
   - type별(single/paraphrase/multihop) 평균 correctness·completeness
   - correctness 0점 항목 수
   - hit=0 항목들의 평균 correctness vs hit>0 항목들의 평균 correctness
     (hit=0인데 correctness가 높으면 정답이 골드 턴이 아닌 곳에서 샌 것이니 지적해 주세요.)
3) 저장용 JSON: [{"question":"...","correctness":N,"completeness":N,"hit":H,"type":"...","reason":"..."}, ...]
4) 여러 모드("baseline","vector"...)가 있으면 전부 채점하고 끝에 모드 비교표(모드→평균 correctness·completeness, 0점 수).

채점할 데이터입니다(`answer`가 채점 대상, `expected`가 기준, `key_facts`는 참고):

<여기에 results-*.json 내용 붙여넣기>
```

---

## 점수 읽는 법

| hit | correctness | 해석 |
|-----|-----|------|
| 높음 | 높음 | 정상 — 정답 청크 검색 + 답 맞음 |
| 높음 | 낮음 | 청크는 찾았는데 모델이 못 읽어냄(생성 문제) |
| **낮음** | **낮음** | **검색 실패 → 오답. baseline 절단이 가운데를 놓친 케이스. 검색 모드가 채울 여지** |
| 낮음 | 높음 | 정답이 골드 턴 밖에서 샘(요약 누출 등) → 데이터 점검 신호 |

- **긴 대화 baseline**: 앞/뒤 질문은 hit·correctness 둘 다 높고, 가운데(잘린 구간) 질문은 둘 다 낮아야 정상. 이 "낮음/낮음" 폭 = 검색 모드가 개선할 상한선.
- **짧은 대화 baseline**: 안 잘리므로(`--max-chars 0`) 거의 전부 hit 1.0 + 높은 correctness. 대조군.
- **completeness**: 멀티홉에서 baseline이 "일부만 답하는지"를 잡습니다. vector/kg가 멀티홉 completeness를 올리는지가 검색 모드의 핵심 가치.
- 모드 비교: 같은 질문 세트에서 평균 correctness가 baseline → vector → +adjacent → +kg로 오르는지, 특히 multihop completeness가 오르는지 보세요.

---

## Phase 2 — Faithfulness (vector/kg 모드 구현 후)

검색이 틀렸는데 그럴듯하게 지어내면 correctness는 우연히 맞아도 위험합니다. 이를 잡는 축.

1. evaluator가 항목별로 **그 답이 본 컨텍스트**를 저장하게 합니다(한 줄):
   ```python
   "context_used": context,   # baseline: 잘린 대화 / 검색 모드: 검색된 청크들
   ```
2. 채점 프롬프트에 축 하나 추가:
   ```
   - faithfulness(충실성): answer의 내용이 그 항목의 `context_used`에 실제로 근거하는가.
     컨텍스트에 없는 사실을 지어냈으면(설령 expected와 맞아도) 낮게 주세요.
   ```
3. 주의: baseline은 `context_used`가 커서(잘린 대화 전체) 토큰이 많이 듭니다. 클로드 채점은
   Groq 한도와 무관하니 괜찮지만, 컨텍스트가 동일한 baseline은 "대화 본문을 한 번만" 주고
   질문/답만 반복하는 식으로 줄여도 됩니다. 검색 모드는 청크가 작아 부담이 적습니다.
