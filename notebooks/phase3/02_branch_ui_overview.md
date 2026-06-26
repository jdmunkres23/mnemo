# Phase 3-2 개요 — 브랜치 UI (`app.js` 추가 사항)

> JS 프론트엔드 영역. 노트북/실습 없음. 구조와 흐름만 파악한다.

---

## 브랜치란?

Claude.ai에서 메시지를 편집하거나 응답을 재생성하면 대화가 **트리 구조**로 갈라진다.
파서(Phase 1)는 이를 trunk(공통 앞부분) + branches(분기 경로들)로 변환해 저장한다.

```json
{
  "turns": [...],         // trunk: 분기 전 공통 구간
  "branches": [           // 분기 이후 각 경로
    [{...}, {...}],       // 경로 0
    [{...}, {...}]        // 경로 1
  ]
}
```

---

## app.js에 추가된 것

### 1. 상태 변수

```javascript
let _activeBranchIdx = 0;    // 현재 보여주는 브랜치 인덱스
let _activeBranches = null;  // session.branches 값 (null = 브랜치 없음)
```

### 2. 세션 목록 — 브랜치 뱃지

```javascript
// renderSidebar() 내부
${s.has_branches ? '<i class="ti ti-git-branch branch-badge"></i>' : ''}
```

`has_branches`는 `/api/sessions`가 반환하는 필드 (`bool(raw.get("branches"))`).

### 3. 턴 렌더링 분리 (`renderTurnEl` / `renderTurns`)

Phase 2의 `renderConv()`가 전체를 한 번에 그렸다면,
Phase 3에서는 턴 단위로 분리해 브랜치 교체 시 재렌더링이 가능하게 했다.

```javascript
function renderTurnEl(turn)        // 턴 하나 → DOM 엘리먼트
function renderTurns(turns, container)  // 턴 배열 → container에 추가
```

### 4. 브랜치 내비게이터 (`renderBranchSection`)

```javascript
function renderBranchSection(container) {
  // ← [1 / 3] → 네비게이터 + 현재 브랜치 턴 렌더링
}
function switchBranch(delta) {
  // _activeBranchIdx 갱신 → renderBranchSection 재호출
}
```

UI 모습:
```
─────────────────────────────────────────────
  ←   2 / 3   →          ← 브랜치 내비게이터
─────────────────────────────────────────────
  [사용자] 편집된 메시지
  [AI] 재생성된 응답
```

### 5. 대화 로드 흐름 (`loadConv`)

```javascript
_activeBranchIdx = 0;
_activeBranches = session.branches || null;

renderTurns(session.turns, inner);              // trunk 먼저 렌더링

if (_activeBranches && _activeBranches.length > 1) {
  renderBranchSection(inner);                   // 브랜치 있으면 내비게이터 추가
}
```

### 6. AI 채팅 패널 연동

```javascript
// loadConv() 내부: 세션이 바뀔 때 AI 채팅 패널도 초기화
if (typeof initAIChat === 'function') initAIChat(id);
```

`initAIChat`은 `chat.js`에서 정의된다. `app.js`는 존재 여부를 확인 후 호출 — 로딩 순서에 관계없이 안전하게 연동된다.

### 7. sessionMap 공유

```javascript
window.sessionMap = sessionMap;  // chat.js에서 세션 제목 접근용
```

`window.` 으로 전역 등록해 다른 스크립트 파일에서도 접근 가능하게 했다.

---

## 요약

| 추가 항목 | 역할 |
|---|---|
| `_activeBranchIdx`, `_activeBranches` | 현재 브랜치 상태 |
| `renderTurnEl()` / `renderTurns()` | 턴 단위 렌더링 분리 |
| `renderBranchSection()` | 브랜치 내비게이터 렌더링 |
| `switchBranch(delta)` | 브랜치 전환 |
| `initAIChat(id)` 호출 | AI 채팅 패널 세션 동기화 |
| `window.sessionMap` | chat.js와 세션 데이터 공유 |
