# Phase 3-3 이론 — RAG 평가 파이프라인 (`evaluator.py`)

## 1. 왜 평가가 필요한가?

"더 좋아졌다"는 느낌은 믿기 어렵다. 수치로 확인해야 한다.

이 프로젝트의 설계 원칙: **평가 주도 개선**
- Phase 4에서 벡터 검색을 도입할 때, baseline 대비 실제로 더 좋아졌는지 수치로 확인
- Phase 5에서 인접 게이팅, KG를 추가할 때도 동일
- 수치 개선 없으면 채택 안 함 (greedy sequential)

---

## 2. RAG 평가의 핵심 이슈

**AI가 이미 알고 있는 것을 테스트하면 RAG를 평가하는 게 아니다.**

나쁜 질문 예시:
- "Python에서 리스트를 정렬하는 방법은?" → LLM이 학습 데이터에서 이미 알고 있음

좋은 질문 예시:
- "이 대화에서 결정한 임계값이 뭔가요?" → 대화 없이는 알 수 없음
- "내가 사용하는 설정 파일 경로가 뭐죠?" → 개인 대화 고유 정보

→ **개인 파일 경로, 특정 설정값, 고유한 결정 사항**만 평가 대상.

---

## 3. Hit Rate (결정론 지표)

검색이 **정답이 있는 턴을 찾았는가?**

```
source_turns: [3, 5]         # 정답이 있는 턴 인덱스 (QA 쌍에 명시)
included_turns: {1, 3, 7}    # 실제로 컨텍스트에 포함된 턴

Hit Rate = |{3, 5} ∩ {1, 3, 7}| / |{3, 5}|
         = |{3}| / 2
         = 0.5
```

- **결정론** — LLM 없이 집합 연산만으로 계산. 빠르고 재현 가능.
- baseline에서는 전체 텍스트가 컨텍스트이므로 Hit Rate가 항상 1.0에 가깝다.
- Phase 4 벡터 검색에서 이 지표가 의미 있어진다.

---

## 4. Correctness / key_facts

답변에 **핵심 값이 포함됐는가?**

```json
{
  "question": "설정한 임계값은?",
  "expected": "0.3",
  "key_facts": ["0.3"]
}
```

```
answer: "임계값은 0.3으로 설정했습니다."
→ _norm("0.3") in _norm(answer)  →  True
→ key_facts score = 1.0 (1/1)
```

정규화 (`_norm`): 소문자 + 콤마/공백 제거.
숫자, 경로명, 에러명 같은 **구체적 값**에 효과적.

타입별 역할:
- `single` / `paraphrase` 질문 → **Correctness** (답변이 맞는가)
- `multihop` 질문 → **Completeness** (여러 사실이 모두 있는가)

---

## 5. LLM-as-judge (0~10점)

key_facts로 잡지 못하는 **서술형 답변의 품질** 측정.

```
질문: ...
기대 답변: ...
실제 답변: ...
→ LLM에게 0~10점 채점 요청 → 숫자만 반환
```

**신뢰성 문제와 대응:**

| 문제 | 대응 |
|---|---|
| LLM도 틀릴 수 있다 | key_facts 결정론 지표와 병행 사용 |
| 채점 기준이 흔들린다 | 동일 모델 + 동일 루브릭으로 모드 간 비교 |
| self-bias (자신의 답변에 관대) | 채점 모델과 답변 모델을 다르게 설정 가능 |

**외부 채점 옵션 (`--no-judge`)**:
답변 생성 후 별도 채점 프롬프트로 Claude(더 강력한 모델)가 채점.
`eval_data/eval_scoring_prompt.md` 템플릿 사용.

---

## 6. RAGAS 프레임워크

이 프로젝트의 평가 지표는 RAGAS 논문에서 영감을 받았다.

| RAGAS 지표 | 이 프로젝트 대응 |
|---|---|
| Context Recall | Hit Rate (정답 턴이 검색됐는가) |
| Answer Correctness | key_facts + LLM judge |
| Faithfulness | LLM judge (Phase 4~, 답변이 컨텍스트에 근거하는가) |

RAGAS는 모든 지표를 LLM으로 측정하지만, 이 프로젝트는 **결정론(key_facts) + LLM 조합**으로 비용을 줄인다.

---

## 7. QA 쌍 설계

```json
{
  "question": "이 대화를 모르면 답할 수 없는 질문",
  "expected": "정답 (간결하게)",
  "source_turns": [3, 5],    // 정답 근거 턴 인덱스 (0-based)
  "key_facts": ["35", "0.3"], // 답변에 반드시 포함돼야 할 값
  "type": "single"            // single | paraphrase | multihop
}
```

타입별 목적:
- `single`: 기본 검색 능력 측정
- `paraphrase`: 원문 단어 대신 동의어로 질문 → 벡터 검색 이점 측정용 (Phase 4)
- `multihop`: 2개 이상 턴 합쳐야 답 가능 → 인접 게이팅·KG 측정용 (Phase 5)

---

## 8. Greedy Sequential 채택 기준

```
이전 모드 대비 Correctness +0.3 이상 → 채택
이전 모드 대비 Correctness +0.3 미만 → 버림
```

0~10점 스케일에서 +0.3은 의미 있는 개선. QA 수가 적으면 (5~10개) 임계값 조정 가능.
multihop Completeness 개선도 함께 확인한다.
