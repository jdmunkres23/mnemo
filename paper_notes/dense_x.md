# 논문 노트

**제목:** Dense X Retrieval: What Retrieval Granularity Should We Use?  
**저자:** Tong Chen et al.  
**발표 연도 / 학회·저널:** 2023 / arXiv (EMNLP 2024 Findings)  
**읽은 날짜:**  
**링크 / arXiv:** https://arxiv.org/abs/2312.06648  

---

## 1패스 — 전체 구조 파악

> Abstract + 섹션 제목 + Conclusion + 그림/표 제목만 훑은 후 작성

**이 논문이 다루는 문제:** RAG의 검색 단위가 검색 작업에 상당한 영향을 미치는데, 흔히 이 부분은 간과되고 있다는 것에 문제를 제기한다.

**기존 방법의 한계:** 위와 동일
    추가 : passage 단위: "extraneous details... that could distract both the retriever and the language model" — 불필요한 디테일이 검색기와 LLM 둘 다를 헷갈리게 함
    sentence 단위: "complex and compounded, and often not self-contained, lacking necessary contextual information" — 문장이 복잡하고, 대명사 등이 앞 맥락 없이는 해석 안 됨

**한 줄 요약 (초안):** 검색 단위를 명제로 설정한다.
    추가 : 검색은 명제(맥락 없이도 이해되게 재구성한 최소 사실 단위)로, 답변 생성은 원본 passage로 — 즉 검색 단위와 생성 단위를 분리한다

기타
    데이터셋: NQ, TriviaQA, WebQuestions, SQuAD, EntityQuestions
    Baseline 검색기: SimCSE, Contriever, DPR, ANCE, TAS-B, GTR
    핵심 수치: Recall@5 +9.3~+12.0 (passage 대비), downstream QA EM@100 +4.9~+7.8
    논문 자체 한계: Wikipedia만, 영어만, 검색기 6종만 테스트

---

## 2패스 — 흐름과 핵심 이해

> Introduction / Method / Experiments / Results 읽은 후 작성

**핵심 아이디어:** 검색 말뭉치에서 얼마나 자세하게 분할해서 인덱싱을 해야 하는가? -> passage/sentence/propositions 단위 중 propositions가 가장 좋다.


**실험 및 결과:** Wikipedia를 이용해서 명제 단위로 쪼갠  FACTOIDWIKI를 만들어 QA 데이터셋에서 실험을 수행

우리는 검색 말뭉치(retrieval corpus)를 서로 다른 세분성으로 인덱싱하는 것이 추론 시점에 dense retriever의 일반화 성능을 향상하기 위한 간단하고 직교적인(orthogonal) 전략이 될 수 있음을 보여줍니다. 


눈에 띈 결과:
    unsupervised 검색기(SimCSE, Contriever)가 supervised 검색기(DPR, ANCE 등)보다 명제 단위 전환 시 개선폭이 더 컸음
    (Recall@5 +9.3~+12.0). supervised는 이미 학습으로 어느 정도 뭉뚱그려진 단위도 잘 처리하는 반면,
    unsupervised는 단위가 원자적일수록 이득을 크게 본다고 해석 가능.

**한계 및 아직 못 푼 것:** 
1. wikipedia으로만 연구
2. 밀집 검색기로 bi-encoder(=dual-encoder, 동일 아키텍처의 다른 명칭) 계열만 이용, cross-encoder/rerank는 미검증
3. 영어 wikipedia만 사용

**다른 논문과의 연결:** Small-to-Big(검색은 작게 / 읽기는 크게) 자체는 RAPTOR나 일반적인 parent-document
retriever 패턴과 같은 맥락. 이 프로젝트 안에서는 명제 추출이 knowledge_graph.py의 엔티티/관계 추출과
같은 계열(원문 → LLM 후처리 → 구조화된 단위)이라는 점도 연결됨.

**내 프로젝트에 어떻게 쓸 수 있을까:** 명제 단위로 세분화하는 것은 개인 대화에서까지는 오버 엔지니어링으로 보인다. 다만, 명제의 조건을 차용해서 요약을 한다면 효율적으로 찾아내고 답변에 사용할 수 있지 않을까 싶다. 가령, 토픽 별로 나눈 후 해당 토픽의 세부 내용들을 명제 단위로 임베딩하거나 문단을 명제단위처럼 핵심을 넣어서 한 문장으로 잘 요약해낼 수 있다면 vector 모드가 좋은 성능을 낼 수 있을 것으로 보인다.

오버 엔지니어링인 이유 : 긴 대화에서 모든 내용을 명제로 치환해서 저장하는 것은 효율적이지 못한 것으로 보인다. 질문이 들어올 때마다 명제를 매번 다 비교하는 것은 비효율적이기 때문이다. 논문에서는 데이터를 8개의 샤드로 나눈 뒤에 각 샤드 안에서 exact search(FAISS IndexFlatIP)를 하고 결과를 병합함. 이를 개인 대화에서 매번 이용하기란 쉽지 않다. 샤드를 나누는 것도 어려울 뿐더러 몇 번 질문을 위해서 인덱스를 구축하는 건 이메일을 보내기 위해서 슈퍼 컴퓨터를 사용하는 것과 같다.

다만 이 아이디어를 차용해서 요약에 핵심적인 내용들을 담아낸다거나 요약을 구축하는데에 명제 단위를 사용하는 것은 후에 그래프 래그를 구축할 때 적용해볼 수도 있을 것 같다.

PAPERS.md 연결 표 확인 후 내 말로 재해석:
    PAPERS.md는 Proposition→dense_x 모드, Passage(읽기 단위)→원본 대화 텍스트, Small-to-Big→Phase 4에서
    토픽 요약으로 이미 부분 적용된 것으로 매핑해둠. 내 해석: Phase 4는 "요약으로 검색 / 원문으로 읽기"까지만
    한 절반짜리 Small-to-Big이고, Dense X는 그 "요약"마저 명제로 더 쪼개 검색 정밀도를 올리자는 것 —
    즉 이미 있는 아이디어의 연장이지 완전히 새로운 개념은 아님.

---

## 3패스 — 구현 목표로 깊이 읽기

> 수식·알고리즘을 따라가며 재현 가능한 수준으로 읽은 후 작성

**방법론 이해:** 
1. 다음과 같이 검색 단위를 명제 단위로 설정한다.

propositions의 조건
    1. Each proposition should correspond to a distinct piece of meaning in text, where the composition of all propositions would represent the semantics of the entire text.
    2. A proposition should be minimal, i.e. it cannot be further split into separate propositions.
    3. A proposition should be contextualized and self-contained (Choi et al., 2021). A proposition should include all the necessary context from the text (e.g. coreference) to interpret its meaning.
-> 정리 : 원문 의미를 빠짐없이 커버하면서(조건1), 더는 쪼갤 수 없고(조건2), 맥락 없이도 단독으로
   해석 가능한(조건3, 대명사 등 해결) 최소 단위로 corpus를 쪼갠다. 

2. dense 벡터로 임베딩해서 저장한다.
3. 질문이 들어오면 임베딩과 코사인/내적 유사도를 비교해 top-k를 찾는다. 논문의 실제 구현은 8개 샤드 각각에서 처음부터 exact search(FAISS IndexFlatIP)를 수행하고 그 결과를 병합하는 방식 



이해가 안 된 부분:

**의문점 / 납득 안 되는 부분:**샤드를 나누는 분류 기준이 무엇일지 궁금했음.
    -> 확인 결과: 의미적 분류 기준은 없음. 1M 유닛씩 묶어 여러 GPU에 나눠 인코딩한 뒤 그대로 8개로 쪼갠 것 — 순전히 리소스(메모리/연산) 제약에 따른 기계적 분할.

**한 줄 요약 (최종):** 명제 단위 검색은 문장/문단 단위보다 성능은 확실히 좋지만, 그 대가로 인덱스 크기와 연산 비용이 크게 늘어나는 트레이드오프(FactoidWiki ~768GB)이며, 세션 단위로 다루는 이 프로젝트 규모에서는 명제를 전면 도입하기보다 그 설계 원칙(자립성·최소 단위)만 차용해 토픽 요약의 정보 밀도를 높이는 데 쓰는 편이 실용적이다.

---

## 기타 메모
