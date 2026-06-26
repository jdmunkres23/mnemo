# Phase 3-4 이론 — RAG 평가 파이프라인

## 0. 왜 기존 지표를 쓰지 않는가

RAG 평가에 BLEU, ROUGE 같은 전통적 NLP 지표를 쓰지 않는 이유:

BLEU·ROUGE는 생성된 텍스트와 정답 텍스트의 **단어 겹침**을 측정한다.

```
정답:   "청크 크기는 2000이다"
답변:   "chunk size는 2000글자로 설정됐습니다"
→ 같은 의미지만 단어가 달라 BLEU 점수 낮음
```

RAG는 같은 사실을 다른 표현으로 답해도 정답이다.
의미 기반 평가가 필요하고, 이것이 RAGAS와 LLM-as-judge를 쓰는 이유다.

---

## 1. 왜 평가하는가

RAG를 구현했다고 해서 잘 동작한다고 할 수 없다.
"느낌상 좋다"는 것을 수치로 바꾸지 않으면 Phase 4 개선이 실제로 나아졌는지 알 수 없다.

평가가 필요한 이유:
- 개선의 효과를 정량화: "Phase 4가 Phase 3보다 얼마나 좋은가"
- 퇴화 방지: 새 기능이 기존 기능을 망가뜨리지 않았는지 확인
- 의사결정 기준: Greedy Sequential 채택 기준 (Correctness +0.3)

## 2. 신뢰 있는 QA 쌍이란

**핵심 원칙:** AI가 이미 아는 것을 테스트하면 RAG를 평가하는 게 아니다.

좋은 QA:
- "이 대화에서 설정한 chunk_size는?" → 대화 없이 AI가 알 수 없음
- "어떤 파일 경로를 수정했다고 했나?" → 대화 특정 정보

나쁜 QA:
- "fastembed는 무엇인가?" → AI가 이미 알고 있음, RAG 불필요

**QA 쌍 스키마:**
```json
{
  "question":     "이 대화에서 설정한 chunk_size 기본값은?",
  "expected":     "2000",
  "source_turns": [3],
  "key_facts":    ["2000"],
  "type":         "single"
}
```

`source_turns`: 정답이 있는 turn 인덱스 (0-based) → Hit Rate 계산에 사용.
`key_facts`: 답변에 반드시 포함돼야 할 핵심 값 → Correctness/Completeness 계산에 사용.
`type`: `single` | `paraphrase` | `multihop`

## 3. RAGAS 영감

이 프로젝트의 평가 지표는 RAGAS 프레임워크에서 영감을 받았다.

| 지표 | 측정 방식 | 특징 |
|------|----------|------|
| Hit Rate | `source_turns ∩ 검색된 턴 범위` | 결정론, LLM 불필요 |
| Correctness | key_facts 포함 비율 + LLM judge | single/paraphrase 질문 |
| Completeness | key_facts 포함 비율 + LLM judge | multihop 질문 |
| Token Usage | 요청당 평균 토큰 수 | 효율성 측정 |

## 4. Hit Rate (결정론 지표)

```
source_turns = [2, 5]          # QA 스키마에 명시된 정답 turn
included_turns = {0, 1, 2, 3}  # 검색된 청크의 turn_start~turn_end 범위

Hit Rate = |source_turns ∩ included_turns| / |source_turns|
         = |{2}| / 2 = 0.5
```

LLM 없이 집합 연산으로 계산 → 매 실행마다 동일한 값.

Phase 3 baseline에서는 고정 크기 청크가 주제 경계를 무시해 Hit Rate가 낮을 수 있다.
Phase 4 vector에서 개선됐는지 비교하는 기준이 된다.

## 5. key_facts 결정론 채점

답변 텍스트에 핵심 값이 포함됐는가를 단순 문자열 매칭으로 판단.

```python
def _norm(s):
    return s.lower().replace(",", "").replace(" ", "")

# "1,024" → "1024", "Hi There" → "hithere"
# _norm(fact) in _norm(answer) 로 확인
```

- `key_facts = ["2000"]`: "청크 크기는 2000글자" → ✓
- `key_facts = ["2000", "500"]`: 둘 다 있어야 1.0

## 6. LLM-as-judge

key_facts로 잡지 못하는 서술형 답변 품질을 LLM이 0~10점으로 채점.

**논문 배경 (Zheng et al., 2023, NeurIPS):**
사람 평가자 대신 강력한 LLM(GPT-4)이 답변 품질을 채점.
사람 평가와 80% 이상 일치함을 보임 → 비용 절감 + 재현 가능한 평가.

```
[프롬프트 설계 원칙]
1. 기준 명시: 채점 기준을 구체적으로 설명
2. 참조 제공: 기대 답변을 함께 제공
3. 출력 제한: "숫자만 출력" → 파싱 용이
4. 저비용: max_tokens=10 (숫자 하나면 충분)
```

**알려진 편향:**
- **Position Bias**: 먼저 제시된 답변을 더 높게 평가하는 경향
- **Verbosity Bias**: 길고 자세한 답변을 더 높게 평가하는 경향
- **Self-Enhancement Bias**: 자신이 생성한 것과 비슷한 답변 선호

완화 방법:
- 모든 모드를 같은 모델·같은 프롬프트로 채점 → 편향이 동일하게 적용되어 상대 비교에서 상쇄됨
- temperature=0.0으로 결정론적 출력

## 7. Greedy Sequential 채택 기준

```
이전 모드 대비 Correctness +0.3 이상 → 채택
이전 모드 대비 Correctness +0.3 미만 → 버림
```

## 8. 프로젝트 연결

```
evaluator.py
  compute_hit()        → Hit Rate 계산
  keyfact_score()      → key_facts 결정론 채점
  build_judge_prompt() → LLM judge 프롬프트 생성
  parse_judge_score()  → LLM 출력에서 점수 파싱
  judge_answers()      → 모든 결과에 judge 점수 추가
  run_baseline()       → search() 기반 RAG → 답변 생성 → 지표 계산
```

참고 논문: RAGAS (Es et al., 2023), "Judging LLM-as-a-Judge" (Zheng et al., 2023)
