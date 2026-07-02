# Opus에게 보낼 요청 — 쿼리 라우팅 평가용 QA 보강

## 같이 첨부해야 할 것
이 파일과 함께 아래 세 개를 그대로 붙여넣어줘:
1. `eval_data/eval_data_prompt.md` 전체 내용 (지금까지의 규칙 v1/v2)
2. `eval_data/eval-short-001.qa_pairs.json`, `eval_data/eval-long-001.qa_pairs.json` 전체 내용 (기존 QA)
3. `eval-short-001`, `eval-long-001`의 session.json 전체 내용 (원본 대화)
   → analytical 질문은 "전체 흐름/패턴"을 물어야 해서, QA 쌍만으로는 못 만들고
     실제 대화 내용을 봐야 만들 수 있음

---

## 상황 설명

이 프로젝트(AI 대화 뷰어 + RAG)는 `eval_data_prompt.md`를 기준으로 네가 이미
`eval-short-001`, `eval-long-001` session.json + QA 23개(짧은 대화 8개, 긴 대화 15개)를
만들어줬어. 이건 "검색 전략이 얼마나 잘 찾아내는가"(baseline vs vector vs ...)를
비교하는 용도였고, 그래서 모든 질문이 "이 대화 없이는 답할 수 없는" retrieval 전용이었어.

이번에 새로 추가한 기능은 **쿼리 라우팅**이야. 질문이 들어오면 바로 검색하지 않고,
먼저 세 가지로 분류해:

- `simple`: 이 대화 세션과 무관한 일반 지식 (세션 없이 LLM이 바로 답할 수 있음)
- `analytical`: 세션이 있어야 하지만 구체적 수치 없이 전체 흐름/패턴만으로 답 가능
- `retrieval`: 특정 수치, 파일명, 에러명, 결정 사항 등 구체적 사실이 필요 (지금 있는 23개가 이 타입)

이 분류가 "실제로 효율적인가"(불필요한 검색을 줄이는가)를 증명하려면, retrieval 질문만으론
검증이 안 돼. simple/analytical 질문이 테스트셋에 섞여 있어야 "검색을 건너뛰어도 되는 질문을
실제로 건너뛰는가"를 토큰 사용량 + 정답률로 비교할 수 있어.

## 코드베이스에서 확인된 제약 조건 (반드시 반영)

1. **숫자·파일 확장자·경로가 포함된 질문은 분류기 이전에 정규식으로 강제로 retrieval 처리됨.**
   simple/analytical 질문에 숫자, `.py`/`.json` 같은 확장자, `/`나 `\` 경로가 들어가면
   안 됨. 들어가면 분류기 자체를 테스트하지 못하고 의미 없는 결과가 나옴.

2. **기존 `type` 필드(single/paraphrase/multihop)는 retrieval 질문 전용 분류라서
   simple/analytical 질문에는 쓰면 안 됨.** evaluator.py가 타입별 평균 점수를 낼 때
   같이 묶여서 통계가 오염됨. simple/analytical 항목은 `type` 필드를 아예 비우거나
   생략.

3. 기존 retrieval QA 23개의 질문/정답 내용은 그대로 두고, 새 필드
   `expected_query_type: "retrieval"`만 추가.

## 요청 사항

1. `eval_data_prompt.md`에 v2처럼 이어지는 **v3 섹션**을 작성해줘 (기존 문서 톤/형식 유지).
   - simple/analytical 정의와 좋은 예시/나쁜 예시
   - 위 제약 조건(숫자·확장자·경로 금지, type 필드 미사용) 명시
   - 수량 기준 제안 (예: 짧은 대화 simple+analytical 합 5~6개, 긴 대화 8~10개 — 적절하다고
     판단하는 비율로 네가 정해도 됨)
2. 같은 세션(`eval-short-001`, `eval-long-001`)을 재사용해서, 위 기준에 맞는 simple/analytical
   QA를 새로 만들고, 기존 23개 QA에 `expected_query_type: "retrieval"`을 추가한
   **전체 qa_pairs.json 두 개**를 다시 출력해줘.

세션 대화 내용(session.json) 자체는 변경하지 않아도 돼 — 이미 있는 대화로 충분히
simple/analytical 질문을 만들 수 있어.
