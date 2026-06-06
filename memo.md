# 메모

## Artifact 블록 처리 방향 (미결)

**배경:**
- AI 채팅 RAG 컨텍스트는 현재 `text` 블록만 사용하도록 설계
- 그러나 `tool_use` (artifacts)에 실제 코드/문서 내용이 담겨 있어, text만으로는 "그때 짠 코드 어떻게 했었지?" 같은 질문에 답 못함
- artifact 전체 내용을 RAG에 포함하면 Groq 무료 tier rate limit 문제 발생 가능

**Phase 0 EDA에서 확인할 것:**
- 전체 대화 중 artifact(`tool_use`) 블록이 몇 개나 있는지
- artifact 하나당 평균/최대 길이 (토큰 수)
- artifact 타입 분포 (`application/vnd.ant.code`, 문서 등)

**EDA 후 결정할 것:**
- artifact를 RAG에 포함할지 여부
- 포함한다면 전체 vs title+앞 N자 vs 별도 인덱스 중 어떤 방식으로
