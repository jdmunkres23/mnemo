# 메모

## 브랜치 전략

- `main`: Phase 0까지 공통 작업
- `solution/main`: 정답 구현체. Phase 1부터 완성된 코드 먼저 작성
- `learning/main`: 포트폴리오 메인 (면접관이 보는 브랜치). 교육용 노트북 + 직접 탐색 결과

---

## Phase 0 EDA 결론

### 파서 설계 핵심 결정

**`text` 필드 vs `content` 블록**
- `text` 필드는 모바일 UI 렌더링용 (artifact 플레이스홀더 문자열 삽입됨)
- **파서는 반드시 `content` 블록 사용**

**블록 타입별 처리**
- `thinking` 블록: 내용은 `text`가 아닌 `thinking` 필드에 있음
- `token_budget` 블록: 파서에서 무시, RAG 제외
- 알 수 없는 타입: `RawBlock(type=, raw={})` 폴백으로 보존 + 경고 로그

**tool_use ↔ tool_result 페어링**
- `tool_use.id` ↔ `tool_result.tool_use_id` 로 매칭
- `tool_result` 1개에 `tool_use_id = None` (데이터 결함, 파서에서 None 체크만 추가)
- 매칭 안 되는 `tool_use`는 `create_file` 타입 — 결과 없는 단방향 동작이므로 정상

### RAG 포함 여부

| 블록 | RAG |
|---|---|
| `text` | ✅ 핵심 컨텍스트 |
| `thinking` | ❌ 제외 |
| `tool_use` (artifacts) | 🔶 title + 앞 500자, 별도 인덱스 |
| `tool_use` (나머지) | ❌ 제외 |
| `tool_result` (knowledge) | 🔶 포함 고려 (웹검색 결과) |
| `tool_result` (나머지) | ❌ 제외 |
| `token_budget` | ❌ 제외 |

### artifact 처리 방향 (미결 → 결정)
- RAG 포함하되 전체가 아닌 **title + content 앞 500자** 별도 인덱스
- 검색은 요약본, 히트 시 원본 전달 (Small-to-Big)
- Phase 5 평가 후 전략 재검토
