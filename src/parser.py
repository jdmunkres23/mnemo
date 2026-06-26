# parser.py
# 역할: Claude.ai 내보내기 JSON(conversations.json)을 내부 session.json으로 변환한다.
# 연결: server.py의 /api/sessions 엔드포인트 및 CLI `python -m parser`가 이 모듈을 호출한다.
# 참고 노트북: notebooks/phase1_parser.ipynb (실습 4, 5)

from __future__ import annotations
import json
from pathlib import Path

from src.models import (
    Block,
    FallbackBlock,
    Session,
    TextBlock,
    ThinkingBlock,
    TokenBudgetBlock,
    ToolResultBlock,
    ToolResultContentItem,
    ToolUseBlock,
    Turn,
)

# sender 필드 → role 매핑
# Claude.ai 내보내기: "human" | "assistant"
# 내부 스키마:       "user"  | "assistant"
SENDER_TO_ROLE = {
    "human": "user",
    "assistant": "assistant",
}


def parse_block(raw: dict) -> Block:
    """
    raw 블록 딕셔너리를 적절한 Block 모델로 변환한다.

    반환 형식: TextBlock | ThinkingBlock | ToolUseBlock |
               ToolResultBlock | TokenBudgetBlock | FallbackBlock

    노트북 실습 4 참고.
    """
    block_type = raw.get("type")

    if block_type == "text":
        # TODO: TextBlock 반환
        # 힌트: raw["text"] 그대로 사용
        return TextBlock(type='text', text=raw['text'])

    elif block_type == "thinking":
        return ThinkingBlock(type="thinking", thinking=raw["thinking"])

    elif block_type == "tool_use":
        # TODO: ToolUseBlock 반환
        # 힌트: name, input 필드 추출
        return ToolUseBlock(type='tool_use', name=raw['name'], input=raw['input'])

    elif block_type == "tool_result":
        # TODO: ToolResultBlock 반환
        # 힌트: content는 리스트 → ToolResultContentItem 리스트로 변환
        #        is_error 기본값은 False
        return ToolResultBlock(type='tool_result', name=raw['name'], content=raw['content'], is_error=raw.get('is_error', False))

    elif block_type == "token_budget":
        # TODO: TokenBudgetBlock 반환
        # 힌트: remaining 필드 (None일 수 있음)
        return TokenBudgetBlock(type='token_budget', remaining=raw.get('remaining'))

    else:
        # TODO: FallbackBlock 반환 (손실 없이 raw 전체 보존)
        return FallbackBlock(type=raw['type'], raw=raw)


def parse_message(msg: dict) -> Turn:
    """
    단일 chat_message 딕셔너리를 Turn 모델로 변환한다.

    반환 형식: Turn(role="user"|"assistant", blocks=[...])

    노트북 실습 4 참고.
    """
    # TODO: sender → role 변환 후 content 블록 목록을 parse_block()으로 변환
    # 힌트: SENDER_TO_ROLE 딕셔너리 사용
    role = SENDER_TO_ROLE[msg['sender']]
    blocks = [parse_block(b) for b in msg['content']]
    return Turn(role=role, blocks=blocks)


_ROOT_SENTINEL = "00000000-0000-4000-8000-000000000000"


def _build_branch_paths(msgs: list[dict]) -> list[list[dict]]:
    """parent_message_uuid 트리를 순회해 루트→리프 경로를 모두 반환한다.
    (phase3_branch_eda.md 참고)

    구현 순서:
    1. {uuid: msg} 역방향 맵 구성
    2. parent가 _ROOT_SENTINEL이거나 맵에 없으면 roots에 추가
       그 외: children[parent].append(uuid)
    3. collect(uid, path) 재귀: 자식 없으면 [path+[uid]], 있으면 자식마다 재귀
    4. 각 root에서 collect 호출 → uuid 경로를 실제 msg 객체 경로로 변환
    """
    uuid_map = {m["uuid"]: m for m in msgs}
    children: dict[str, list[str]] = {}
    roots: list[str] = []

    for m in msgs:
        parent = m.get("parent_message_uuid")
        if parent is None or parent == _ROOT_SENTINEL or parent not in uuid_map:
            roots.append(m["uuid"])
        else:
            children.setdefault(parent, []).append(m["uuid"])

    def collect(uid: str, path: list[str]) -> list[list[str]]:
        path = path + [uid]
        if uid not in children:
            return [path]
        result = []
        for child in children[uid]:
            result.extend(collect(child, path))
        return result

    all_paths = []
    for root in roots:
        all_paths.extend(collect(root, []))

    return [[uuid_map[uid] for uid in path] for path in all_paths]


def _common_prefix_len(paths: list[list[dict]]) -> int:
    """모든 경로의 공통 앞부분(trunk) 길이를 반환한다.
    (phase3_branch_eda.md 참고)

    힌트: paths[0][i]["uuid"] 가 모든 경로의 i번째 uuid와 같으면 공통.
    """
    if not paths:
        return 0
    min_len = min(len(p) for p in paths)
    for i in range(min_len):
        uid = paths[0][i]["uuid"]
        if not all(p[i]["uuid"] == uid for p in paths):
            return i
    return min_len


def parse_conversation(conv: dict) -> Session:
    """
    단일 conversation 딕셔너리를 Session 모델로 변환한다.

    반환 형식: Session(session_id, title, created_at, updated_at, turns=[...], branches=...)
    - 브랜치 없음: branches=None, turns=전체 메시지
    - 브랜치 있음: turns=trunk(공통 앞부분), branches=분기 이후 각 경로

    힌트:
    - _build_branch_paths(msgs) 로 모든 경로 구하기
    - 경로 1개 → 브랜치 없음, branches=None
    - 경로 2개+ → _common_prefix_len() 으로 trunk 길이 계산
      trunk_turns = paths[0][:trunk_len] → parse_message() 적용
      branches = [path[trunk_len:] → parse_message() 적용] for each path
    """
    session_id = conv['uuid']
    title = conv['name']
    msgs = conv.get('chat_messages', [])

    paths = _build_branch_paths(msgs) if msgs else []  # TODO: 위 두 함수 구현 후 동작

    if not paths or len(paths) == 1:
        # 브랜치 없음: 기존 방식 유지
        turns = [parse_message(t) for t in (paths[0] if paths else msgs)]
        return Session(session_id=session_id, title=title,
                       created_at=conv['created_at'], updated_at=conv['updated_at'],
                       turns=turns, branches=None)

    trunk_len = _common_prefix_len(paths)
    trunk_turns = [parse_message(m) for m in paths[0][:trunk_len]]
    branches = [[parse_message(m) for m in path[trunk_len:]] for path in paths]
    return Session(session_id=session_id, title=title,
                   created_at=conv['created_at'], updated_at=conv['updated_at'],
                   turns=trunk_turns, branches=branches)



def parse_export(export_path: str | Path, output_dir: str | Path) -> list[Path]:
    """
    conversations.json 파일 전체를 파싱해 output_dir에 session별 JSON으로 저장한다.

    저장 형식: {output_dir}/{session_id}.json  (Session.model_dump_json() 사용)
    반환: 저장된 파일 경로 목록

    노트북 실습 5 참고.
    """
    export_path = Path(export_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(export_path, encoding="utf-8") as f:
        conversations = json.load(f)

    saved: list[Path] = []
    for conv in conversations:
        # TODO: parse_conversation() 호출 후 session.model_dump_json(indent=2)으로 저장
        # 힌트: output_dir / f"{session.session_id}.json"
        session = parse_conversation(conv)
        out_path = output_dir / f"{session.session_id}.json"
        out_path.write_text(session.model_dump_json(indent=2), encoding="utf-8")
        saved.append(out_path)

    return saved


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Claude.ai 내보내기 JSON → session.json 변환")
    ap.add_argument("--input", required=True, help="conversations.json 경로")
    ap.add_argument("--output-dir", default="conversations", help="출력 디렉토리 (기본: conversations)")
    args = ap.parse_args()

    saved = parse_export(args.input, args.output_dir)
    print(f"{len(saved)}개 세션 저장 완료 → {args.output_dir}")
