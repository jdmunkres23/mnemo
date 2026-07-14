# Phase 5-1 이론 — 긴 토픽 재분할 (Dense X는 확장 경로로)

## 0. 배경: vector가 왜 baseline보다 낮게 나왔는가

Phase 4 평가 로그(`docs/memo.md` "Phase 4 후속" 절)에서 실제로 확인된 사실:

```
토픽 0 (turn 0~37, 14,285자)
  → LoRA 설정, 데이터 누수, 토크나이저 버그 등 8~9개 QA 분량이 한 토픽에 뭉쳐 있음
  → summarize_topic()이 이 전체를 2~3문장으로 압축
  → 압축된 요약 문장 하나의 임베딩이 "검색 대표값" 노릇을 함
```

`detect_topic_boundaries()`가 관대하게 경계를 잡을수록(토픽이 커질수록) 이 문제는 심해진다.
토픽 안에 사실이 여러 개 있으면, 요약 임베딩 벡터 1개가 그 사실들의 **평균적인 방향**을 가리키게 되고,
그중 어느 한 사실을 정확히 묻는 질문과의 유사도는 "그 사실 하나만 담긴 벡터"보다 낮아진다.

---

## 0.5. 설계 전에 먼저 실측한 것 — "vector가 정말 baseline보다 나아지나?"

Phase 5를 설계하기 전에, `eval_data/result/final_qa/`의 실제 평가 결과를 다시 열어 baseline과
vector를 직접 비교했다. 결과는 예상과 달랐다.

```
                  hit rate    keyfact    avg tokens
eval-long-001  baseline 0.984   8.81     2,360
               vector   0.881   8.33     4,530   ← 토큰 2배 쓰고 더 낮음

eval-short-001 baseline 1.000   9.72     2,856
               vector   1.000   10.0     3,705   ← 근소 우위, 토큰은 더 씀
```

**왜 baseline이 잘 나오는가:** baseline(`chunk_session()`)은 청크가 `CHUNK_SIZE=2000자`를
넘으면 무조건 새 청크를 시작한다. 그래서 baseline 청크는 실측상 전부 1,400~1,900자 사이였고,
vector의 6,751자짜리 토픽 같은 게 애초에 생길 수가 없다. 즉 baseline이 잘하는 건 "똑똑해서"가
아니라 **크기 상한이 구조적으로 다일루션을 막아주기 때문**이다.

**vector가 baseline에게 진 21문항 중 6개를 직접 까본 결과:**

| 질문 | 관련 토픽 크기 | 원인 |
|---|---|---|
| "temperature/top_p 기본값" | 6,751자 (다일루션 대상 토픽) | **명확한 다일루션 케이스** — 215자 요약에 이 사실이 아예 빠짐 |
| "반복 생성 문제 원인/해결" | 6,751자 | 검색은 성공(hit=1)했지만 "eos"/"repetition_penalty" 리터럴 단어 미포함 — keyfact 채점 엄격함 문제에 더 가까움 |
| 멀티홉 질문 1건 | 서로 다른 두 토픽에 걸침 | 인접 게이팅(Phase 6) 영역, 토픽 크기와 무관 |
| 나머지 3건 | 793~2,766자 (작은 토픽) | 토픽 크기와 무관 — 정답 누출/할루시네이션 의심 또는 baseline도 같이 낮은 공통 약점 |

**결론:** 6개 중 다일루션이 확실한 원인인 건 1개, 넉넉히 잡아도 2개뿐이다. 나머지는 Phase 5가
손댈 범위가 아니다. 그래서 이 Phase의 목표를 **"vector를 무조건 baseline보다 낫게 만든다"가
아니라 "진단된 다일루션만 정확히 고쳐서, 최소한 baseline과 동등하게 만든다"**로 좁힌다.

---

## 1. 설계 원칙 — MVP 먼저, 명제 추출은 확장 경로로

지금까지 이 문제를 고치는 방법으로 몇 가지가 논의됐다 (문장/명제 단위 임베딩, 하위 벡터 평균,
유사도 골짜기 탐지, turn 구조 파싱 등). 최종적으로 아래 기준으로 좁혔다:

1. **Groq 호출을 늘리지 않는다** — 지금도 토픽 경계 탐지(세션당 5회×2단계) + 토픽당 요약 1회를
   쓰고 있다. 여기에 토픽마다 추가 호출을 얹으면 rate limit 부담이 커진다.
2. **baseline과 다른 걸 해야 한다** — 그냥 글자 수로 다시 자르기만 하면 baseline이 이미 하고
   있는 걸 토픽 내부에서 반복하는 것뿐이라 존재 이유가 없다. 다만 baseline이 실측으로 이미
   효과가 검증된 방식이므로, **그 방식 자체를 재사용하는 것은 문제가 아니다** — 토픽 경계라는
   상위 구조 안에서 보조 수단으로 쓰는 것과, 토픽 구조 자체를 버리고 전면 채택하는 것은 다르다.
3. **과분할하지 않는다** — 작은/중간 토픽은 이미 잘 작동한다(0.5절 실측). 문제가 없는 곳을
   건드리지 않는다.

이 세 기준을 동시에 만족하는 가장 단순한 방법: **긴 토픽만, 이미 있는 `chunk_session()`을
그 토픽의 turn 범위 안에서 재사용해 여러 개의 작은 조각으로 나누고, 각 조각에 이미 있는
`summarize_topic()`을 그대로 돌린다.** 새 프롬프트도, 새 Groq 호출 종류도 없다 — 기존 두
함수를 다른 스코프에 다시 쓰는 것뿐이다.

```
[MVP] 긴 토픽 → chunk_session() 재사용으로 재분할 → 조각마다 summarize_topic() 재사용
      → 조각마다 별도 임베딩 (합치지 않음)
        ↓ (평가해서 부족하면)
[확장] 명제 추출(extract_propositions, Dense X 스타일) 도입 — 아래 4절 참고
```

---

## 2. MVP 메커니즘

### 2.1 재분할 — `split_long_topic()`

`build_topics()`가 만든 토픽 하나가 `CHUNK_SIZE`(2000자, baseline과 동일 상수)보다 크면,
그 토픽의 turn 범위만 떼어내 `chunk_session()`에 다시 넣는다.

```
topic = {"text": "...(6751자)...", "turn_start": 34, "turn_end": 49, "position": 4}

session["turns"][34:50] 를 잘라서 임시 세션으로 만듦
  → chunk_session(임시_세션, chunk_size=2000) 호출 (Phase 3에 이미 있는 함수, 그대로 재사용)
  → 2~4개의 sub-chunk 반환 (각자 자기 turn_start/turn_end를 가짐, 단 임시 세션 기준 상대 인덱스)
  → 원래 topic["turn_start"]만큼 offset을 더해 절대 turn 인덱스로 보정
```

`chunk_session()`은 이미 Phase 3에서 검증됐고(baseline이 이 함수로 만든 청크가 지금 vector보다
잘 나오고 있다), 인접 청크끼리 turn 1개가 겹치는 특성이 있다 — 이건 버그가 아니라 경계에서
내용이 아예 빠지는 걸 막아주는 작은 안전판으로 보면 된다.

작은 토픽(`CHUNK_SIZE` 이하)은 `chunk_session()`이 애초에 청크 1개만 반환하므로,
`split_long_topic()`을 모든 토픽에 그냥 걸어도 작은 토픽은 원래 그대로 통과한다 —
"긴 토픽만 처리"를 위한 별도 분기가 필요 없다.

### 2.2 조각별 요약 — 기존 `summarize_topic()` 재사용

각 sub-chunk의 `text`를 `summarize_topic()`에 그대로 넣는다. 새 함수 아님, 새 프롬프트 아님.
차이는 입력이 이제 최대 2000자 근처라 `topic_text[:4000]` truncation에 걸릴 일이 거의 없다는
것뿐이다 — 즉 이 MVP는 "다일루션"과 "truncation 실패" 두 문제를 동시에 줄인다.

### 2.3 저장 — `vector_index.json` 스키마 변경 없음

`{text, summary, embedding, position, turn_start, turn_end}` 스키마를 그대로 유지한다.
긴 토픽은 이 스키마의 엔트리를 **여러 개** 만들 뿐이다 (같은 `position` 값을 공유해도 무방 —
어차피 turn_start/turn_end로 구분되고, `search_vector()`는 지금도 리스트를 순서 상관없이
flat하게 스캔한다). **`search_vector()`, `route_query()`, `build_retrieval_context()`,
`evaluator.py`의 `run_vector()` — 전부 코드 변경이 필요 없다.** 이미 "엔트리 목록에서 top-k
뽑기"만 하기 때문에, 엔트리가 토픽 1개당 1개든 여러 개든 신경 쓰지 않는다.

```python
# build_vector_index() 내부, 기존 루프를 이렇게 바꾸면 됨 (개념 흐름):
entries = []
for topic in topics:
    pieces = split_long_topic(session, topic)          # 작은 토픽이면 [topic] 그대로
    for piece in pieces:
        summary = summarize_topic(piece["text"], api_key)
        entries.append({**piece, "summary": summary})

embeddings = embed_texts([e["summary"] for e in entries])
for e, emb in zip(entries, embeddings):
    e["embedding"] = list(emb)
# entries를 그대로 vector_index.json에 저장 (기존과 동일한 리스트 포맷)
```

### 2.4 "여러 벡터 중 최댓값"이 공짜로 됨

지난 논의에서 "토픽 하나를 여러 벡터로 쪼갤 때, 평균이 아니라 최댓값으로 점수를 매겨야 한다"는
결론이 있었다(ColBERT의 MaxSim과 같은 원리). 이 설계에서는 **그걸 위한 코드를 따로 안 짜도 된다**
— 애초에 평균을 낼 상위 벡터 자체를 안 만들고, 조각들을 flat한 리스트에 넣어 `search_vector()`가
그중 가장 유사도 높은 것부터 top-k를 뽑기 때문에, 결과적으로 "그 토픽의 여러 벡터 중 최댓값이
살아남는" 것과 동일한 효과가 자연히 발생한다.

---

## 3. 이 설계가 baseline과 다른 점

| | baseline (`chunk_session`) | MVP (긴 토픽만 재분할) |
|---|---|---|
| 분할 기준 | 세션 전체를 처음부터 글자 수로 자름, 토픽 경계 무시 | 먼저 의미 단위(토픽)로 나눈 뒤, 그 안에서 크기 초과분만 글자 수로 보조 분할 |
| 짧은 대화 | 여전히 여러 청크로 쪼개짐(주제 무관) | 토픽 하나 그대로 유지 (요약 임베딩, Small-to-Big 이점 유지) |
| 검색 텍스트 | 청크 원문 | 요약(Small) → 매칭되면 원문(Big) 전달 |

핵심 차이는 "언제 글자 수 분할을 쓰는가"다. baseline은 **처음부터 끝까지** 글자 수만 본다.
MVP는 **의미 경계(토픽)를 먼저 존중하고, 그 경계 안에서 너무 커진 부분에만** 같은 도구를 보조로
쓴다. 그래서 대부분의 (작은) 토픽은 여전히 Small-to-Big의 이점(요약 검색 + 원문 전달)을 그대로
가져가고, 문제가 확인된 긴 토픽만 baseline과 비슷한 안전장치를 얻는다.

---

## 4. 확장 경로 — Dense X 명제 단위 임베딩 (MVP로 부족할 때만)

MVP를 평가했을 때 여전히 부족하면(예: sub-chunk 하나에 여전히 서로 다른 사실이 2~3개씩 남아
다일루션이 완전히 안 없어지는 경우), 다음 단계로 명제(proposition) 단위 추출을 도입한다.

### Dense X Retrieval (Chen et al., 2023) 논문 배경

**핵심 질문:** 검색 인덱스의 단위를 passage로 할지, sentence로 할지, 아니면 그보다 더 작게
할지 — 이 granularity 선택 자체가 성능에 큰 영향을 준다는 걸 정면에서 실험한 논문.

**"좋은 명제"의 3가지 기준:**

1. **원자성 (Atomicity)** — 하나의 명제는 하나의 사실만 담는다.
2. **탈맥락화 (Decontextualization)** — 대명사·생략된 주어를 원래 지시 대상으로 치환해
   원문 없이도 그 자체로 의미가 완결되게 만든다.
3. **최소성 (Minimality)** — 필요한 만큼만, 더 이상 쪼갤 수 없는 단위까지만 나눈다.

**실험 결과 요지:** passage/sentence 단위보다 명제 단위 인덱싱이 5개 QA 데이터셋에서
일관되게 높은 recall을 보임. 인덱스 크기는 늘지만 정확도 향상이 그 비용을 상회.

### MVP와의 차이

| | MVP (sub-chunk 요약) | 확장 (명제 추출) |
|---|---|---|
| 조각당 사실 수 | 여러 개 가능 (다일루션 감소, 완전 제거는 아님) | 1개 (다일루션 원천 제거) |
| 필요 프롬프트 | 없음 (기존 함수 재사용) | 새 프롬프트(`extract_propositions`) 필요 |
| Groq 호출 | 토픽당 조각 수만큼 (기존과 유사한 수준) | 조각당 명제 추출 1회 (MVP와 호출 수는 비슷하나, 이산적 판단이 아니라 안정성 이슈는 낮음) |
| 과분할 위험 | 낮음 | 있음 (조각을 문장 단위까지 쪼개므로) |

명제 추출 프롬프트 원칙(도입 시 그대로 적용):
- 각 사실은 맥락 없이 독립적으로 이해 가능 (탈맥락화)
- 고유명사·경로·에러명은 원문 그대로 포함
- 하나의 사실 = 하나의 문장 (원자성 + 최소성)

```
입력 (sub-chunk text):
  [사용자] 추론 샘플링 기본값 알려줘. 서빙은 뭘로 했어?
  [AI] temperature 0.7, top_p 0.9로 정했습니다. 추론 서빙은 vLLM으로, 8000번 포트에 띄웠습니다.

출력 (명제 목록):
  ["추론 샘플링 temperature 기본값은 0.7이다.",
   "추론 샘플링 top_p 기본값은 0.9이다.",
   "추론 서빙은 vLLM을 사용했다.",
   "추론 서빙은 8000번 포트에 띄웠다."]
```

이 경로로 갈 때도 저장 스키마는 그대로 유지된다 — `text`(그 명제가 나온 조각 원문 또는 명제
자체), `summary` 대신 명제 텍스트를 직접 임베딩 대상으로 쓰면 되므로 `search_vector()`는
여전히 코드 변경이 필요 없다.

---

## 5. 프로젝트 연결

```
indexer.py
  split_long_topic()   → (신규) 긴 토픽을 chunk_session() 재사용으로 재분할
  build_vector_index() → (수정) 토픽마다 split_long_topic() 결과 각각에 summarize_topic() 적용
  summarize_topic()    → (재사용, 변경 없음)
  search_vector()      → (변경 없음) flat 리스트 top-k 그대로
  extract_propositions() → (확장 경로, MVP 평가 후 필요할 때만 추가)

evaluator.py
  run_vector()          → (변경 없음) build_vector_index()가 만든 결과물을 그대로 소비

평가:
  vector(MVP 적용 전) vs vector(MVP 적용 후) vs baseline 3자 비교
  0.5절에서 확인한 실패 문항(특히 "temperature/top_p" 케이스)이 고쳐지는지 우선 확인
  baseline과 최소 동률 이상이 되는지가 1차 성공 기준
```

참고 논문:
- Dense X Retrieval (Chen et al., 2023) — 확장 경로(명제 단위)의 학술 근거
- SeCom (ICLR 2025) — Phase 4 토픽 분할의 근거, 이번 MVP는 그 위에 baseline의 안전장치를 보조로 얹은 것
