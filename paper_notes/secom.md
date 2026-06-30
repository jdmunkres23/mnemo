# 논문 노트

**제목:** On Memory Construction and Retrieval for Personalized Conversational Agents  
**저자:** Zhuoshi Pan, Qianhui Wu, Huiqiang Jiang, Xufang Luo, Hao Cheng, Dongsheng Li, Yuqing Yang, Chin-Yew Lin, H. Vicky Zhao, Lili Qiu, Jianfeng Gao  
**발표 연도 / 학회·저널:** 2025 / ICLR 2025  
**읽은 날짜:**  
**링크 / arXiv:** https://arxiv.org/abs/2502.05589  

---

## 1패스 — 전체 구조 파악

> Abstract + 섹션 제목 + Conclusion + 그림/표 제목만 훑은 후 작성

**이 논문이 다루는 문제:** 장기 대화 에이전트를 위한 RAG 이용시 메모리 세분성(Granularity)에 따르는 성능 차이

**기존 방법의 한계:** 턴 단위, 세션 단위, 요약 기반보다 SECOM 방식이 낫다고 주장하지만, 각 방식의 한계는 잘 모르겠음.

추가 : 턴 단위 → 관련 정보가 여러 턴에 흩어져 있어, 검색 결과가 단편적·불완전
세션 단위 → 한 세션에 무관한 주제가 섞여 노이즈가 포함됨
요약 기반 → 요약 과정에서 구체적 수치·사실 등 세부 정보가 소실


**한 줄 요약 (초안):** 의미론적인 단위로 나누어서 메모리를 구성하고 요약하자.

추가 : "장기 대화의 맥락 파악을 위해, 정보 손실이 발생하는 '요약' 대신 대화를 주제별로 일관된 '세그먼트(Segment)' 단위로 분할하고, 불필요한 중복을 제거(Denoising)하여 메모리의 효율과 정확도를 높이자."
---

## 2패스 — 흐름과 핵심 이해

> Introduction / Method / Experiments / Results 읽은 후 작성

**핵심 아이디어:** 토픽 별로 메모리 뱅크를 만든 후 요청이 들어오면 노이즈를 제거한 메모리 뱅크 기반으로 응답을 한다.

**실험 및 결과:** GPT4Score, BLEU, Rouge2, BERTScore 모든 지표에서 SeCom 방식이 월등한 결과를 가져옴

눈에 띈 결과:

**한계 및 아직 못 푼 것:** 모르겠음.

**다른 논문과의 연결:** 
1. 노이즈 제거 모듈 관련 논문 = LLMLingua (Jiang et al., 2023b) & LLMLingua-2 (Pan et al., 2024)
2. 대화 분할 관련 논문 = LumberChunker (Duarte et al., 2024) segments narrative documents into semantically coherent chunks using Gemini.

**내 프로젝트에 어떻게 쓸 수 있을까:** 청크가 너무 긴 경우에 노이즈 제거하는 것은 유의미할 것으로 보임. 무료 api를 사용하고 있기 때문에 질문-대답으로 이루어진 턴을 모두 토픽 분할에 쓰는 것은 어려울 것으로 보인다. 

추가 : 노이즈 제거를 위해서는 

PAPERS.md 연결 표 확인 후 내 말로 재해석:

---

## 3패스 — 구현 목표로 깊이 읽기

> 수식·알고리즘을 따라가며 재현 가능한 수준으로 읽은 후 작성

**방법론 이해:**
1. 토픽 별로 나누어 메모리 뱅크를 만든다. 
2. 요청이 들어오면 메모리 뱅크에서 노이즈를 제거한 메모리 뱅크를 동적으로 만든다.
3. 메모리 뱅크에서 대답을 만들어낸다. 

이해가 안 된 부분:

**의문점 / 납득 안 되는 부분:** 만약 이전의 이야기가 뒤에 다시나오거나 하면 어떻게 처리하는지 잘 모르겠음. 

추가 : 요청이 들어오면 검색을 통해 관련 세그먼트들을 가져와서 노이즈 제거한 메모리 뱅크를 만들어냄. 따라서, 문제가 되지 않음.

**한 줄 요약 (최종):** 토픽 별로 메모리 뱅크를 만들고 노이즈를 제거한 후에 응답한다.

---

## 기타 메모
