# Phase 3 추가 EDA — 대화 브랜치 구조 분석

---

## 1. 개요

[MARKDOWN 셀]

Claude.ai 내보내기 데이터에는 대화 브랜치 정보가 담겨 있다.
사용자가 메시지를 편집하거나 응답을 재생성하면 대화가 트리 구조로 갈라진다.

이 노트북에서 확인할 것:
- 각 메시지에 `parent_message_uuid` 필드가 있는가
- 브랜치가 있는 대화가 얼마나 되는가
- 트리를 어떻게 경로(path)로 변환하는가

---

## 2. 데이터 로드

[CODE 셀]

```python
import json
from pathlib import Path

with open("../data/conversations.json", encoding="utf-8") as f:
    data = json.load(f)

print(f"전체 대화 수: {len(data)}")

# 첫 번째 대화의 첫 번째 메시지 필드 확인
msg = data[0]["chat_messages"][0]
print("\n메시지 최상위 키:")
print(list(msg.keys()))
```

---

## 3. parent_message_uuid 확인

[MARKDOWN 셀]

각 메시지에는 `parent_message_uuid`가 있다.
루트 메시지(대화의 첫 번째 사용자 메시지)는 고정된 sentinel 값을 부모로 가진다.

```
ROOT_SENTINEL = "00000000-0000-4000-8000-000000000000"
```

[CODE 셀]

```python
ROOT_SENTINEL = "00000000-0000-4000-8000-000000000000"

msg = data[0]["chat_messages"][0]
print("uuid          :", msg["uuid"])
print("parent_uuid   :", msg["parent_message_uuid"])
print("루트 여부      :", msg["parent_message_uuid"] == ROOT_SENTINEL)
```

---

## 4. 브랜치 탐지

[MARKDOWN 셀]

같은 `parent_message_uuid`를 가진 메시지가 2개 이상이면 그 지점에서 브랜치가 생긴 것이다.

```
parent A → child B1   (브랜치 1)
         → child B2   (브랜치 2)
```

[CODE 셀]

```python
from collections import Counter

branched = []

for conv in data:
    msgs = conv.get("chat_messages", [])
    parents = [m["parent_message_uuid"] for m in msgs]
    counts = Counter(parents)
    if any(v > 1 for v in counts.values()):
        branched.append(conv)

print(f"전체 대화       : {len(data)}")
print(f"브랜치 있는 대화 : {len(branched)}")
print(f"비율            : {len(branched)/len(data)*100:.1f}%")
```

---

## 5. 트리 구조 시각화

[MARKDOWN 셀]

브랜치가 있는 대화 하나를 골라 메시지 간 부모-자식 관계를 출력해본다.

[CODE 셀]

```python
conv = branched[0]
msgs = conv["chat_messages"]

print(f"대화 제목: {conv.get('name', '(없음)')}")
print(f"메시지 수: {len(msgs)}\n")

# 각 메시지의 uuid(앞 8자)와 parent(앞 8자)를 출력
for m in msgs:
    uid = m["uuid"][:8]
    parent = m["parent_message_uuid"][:8]
    sender = m["sender"]
    print(f"  {sender:9}  uuid={uid}  parent={parent}")
```

[CODE 셀]

```python
# 어느 uuid가 자식을 2개 이상 가지는지 확인 → 브랜치 포인트
by_uuid = {m["uuid"]: m for m in msgs}
children = {}

for m in msgs:
    p = m["parent_message_uuid"]
    if p in by_uuid:
        children.setdefault(p, []).append(m["uuid"])

print("브랜치 포인트 (자식 2개 이상인 메시지):")
for uid, kids in children.items():
    if len(kids) > 1:
        sender = by_uuid[uid]["sender"]
        print(f"  {uid[:8]} ({sender}) → 자식 {len(kids)}개")
        for k in kids:
            print(f"    └─ {k[:8]} ({by_uuid[k]['sender']})")
```

---

## 6. 경로 추출 알고리즘

[MARKDOWN 셀]

트리를 루트→리프 경로 목록으로 변환한다.
각 경로가 하나의 "브랜치 대화"가 된다.

```
트리:
  root
   └── A
         ├── B1  (리프 → 경로 1: [A, B1])
         └── B2
               └── C  (리프 → 경로 2: [A, B2, C])
```

[CODE 셀]

```python
ROOT_SENTINEL = "00000000-0000-4000-8000-000000000000"

def build_paths(msgs):
    by_uuid = {m["uuid"]: m for m in msgs}
    children = {}
    roots = []

    for m in msgs:
        parent = m.get("parent_message_uuid", "")
        if parent == ROOT_SENTINEL or parent not in by_uuid:
            roots.append(m["uuid"])
        else:
            children.setdefault(parent, []).append(m["uuid"])

    def collect(uid, path):
        path = path + [uid]
        if uid not in children:
            return [path]           # 리프: 경로 완성
        result = []
        for child in children[uid]:
            result.extend(collect(child, path))
        return result

    all_paths = []
    for root_id in roots:
        all_paths.extend(collect(root_id, []))

    return [[by_uuid[uid] for uid in path] for path in all_paths]


paths = build_paths(msgs)
print(f"경로(브랜치) 수: {len(paths)}")
for i, path in enumerate(paths):
    print(f"  경로 {i+1}: 메시지 {len(path)}개")
```

---

## 7. 공통 구간(trunk) 추출

[MARKDOWN 셀]

모든 경로가 공유하는 앞부분(trunk)과 갈라지는 부분(branches)으로 분리한다.
trunk는 `Session.turns`에, branches는 `Session.branches`에 저장된다.

[CODE 셀]

```python
def common_prefix_len(paths):
    if not paths:
        return 0
    min_len = min(len(p) for p in paths)
    for i in range(min_len):
        uid = paths[0][i]["uuid"]
        if not all(p[i]["uuid"] == uid for p in paths):
            return i
    return min_len


trunk_len = common_prefix_len(paths)
print(f"공통 구간(trunk) 길이: {trunk_len}개 메시지")

for i, path in enumerate(paths):
    branch_part = path[trunk_len:]
    print(f"  브랜치 {i+1}: {len(branch_part)}개 메시지")
    for m in branch_part:
        print(f"    [{m['sender']}] {str(m.get('text',''))[:40]}")
```

---

## 8. 전체 통계

[CODE 셀]

```python
total = len(data)
total_sessions = 0
branch_counts = Counter()

for conv in data:
    paths = build_paths(conv.get("chat_messages", []))
    n = len(paths)
    total_sessions += n
    branch_counts[n] += 1

print(f"원본 대화 수     : {total}")
print(f"변환 후 세션 수  : {total_sessions}")
print()
print("브랜치 수별 분포:")
for k in sorted(branch_counts):
    label = "브랜치 없음" if k == 1 else f"브랜치 {k}개"
    print(f"  {label:12}: {branch_counts[k]}개 대화")
```

---

## 9. 결론

[MARKDOWN 셀]

| 항목 | 값 |
|------|---|
| 전체 대화 | 224개 |
| 브랜치 있는 대화 | 23개 (10%) |
| 변환 후 총 세션 | 224개 (브랜치를 인라인으로 처리하므로 세션 수 동일) |

**설계 결정:**
- 브랜치를 별도 세션으로 분리하지 않고 **`Session.branches`** 필드에 저장
- 뷰어에서 공통 구간 렌더링 후 `← 1/2 →` 네비게이터로 전환
- RAG는 `turns`(trunk) + `branches` 전체를 같은 세션 컨텍스트로 사용

**parser.py 핵심 함수:**
- `_build_branch_paths(msgs)` — 트리 재구성 + 루트→리프 경로 반환
- `_common_prefix_len(paths)` — 공통 구간 길이 계산
- `parse_conversation(conv)` — trunk/branches 분리해서 `Session` 반환
