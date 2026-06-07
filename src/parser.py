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
        pass  # TODO

    elif block_type == "thinking":
        # TODO: ThinkingBlock 반환
        # 힌트: raw["thinking"] → ThinkingBlock의 text 필드로 정규화
        pass  # TODO

    elif block_type == "tool_use":
        # TODO: ToolUseBlock 반환
        # 힌트: name, input 필드 추출
        pass  # TODO

    elif block_type == "tool_result":
        # TODO: ToolResultBlock 반환
        # 힌트: content는 리스트 → ToolResultContentItem 리스트로 변환
        #        is_error 기본값은 False
        pass  # TODO

    elif block_type == "token_budget":
        # TODO: TokenBudgetBlock 반환
        # 힌트: remaining 필드 (None일 수 있음)
        pass  # TODO

    else:
        # TODO: FallbackBlock 반환 (손실 없이 raw 전체 보존)
        pass  # TODO


def parse_message(msg: dict) -> Turn:
    """
    단일 chat_message 딕셔너리를 Turn 모델로 변환한다.

    반환 형식: Turn(role="user"|"assistant", blocks=[...])

    노트북 실습 4 참고.
    """
    # TODO: sender → role 변환 후 content 블록 목록을 parse_block()으로 변환
    # 힌트: SENDER_TO_ROLE 딕셔너리 사용
    pass  # TODO


def parse_conversation(conv: dict) -> Session:
    """
    단일 conversation 딕셔너리를 Session 모델로 변환한다.

    반환 형식: Session(session_id, title, created_at, updated_at, turns=[...])

    노트북 실습 5 참고.
    """
    # TODO: uuid → session_id, name → title
    #        chat_messages 목록을 parse_message()로 변환해 turns 생성
    pass  # TODO


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
        pass  # TODO

    return saved
