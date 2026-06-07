# models.py
# 역할: Claude.ai 내보내기 데이터를 위한 Pydantic 스키마 정의.
#       파서가 raw JSON을 이 모델로 변환하고, 서버가 이 모델을 직렬화해 클라이언트에 전달한다.
# 연결: parser.py가 이 모델을 사용해 session.json을 생성한다.
# 참고 노트북: notebooks/phase1_parser.ipynb

from __future__ import annotations
from typing import Any, Literal, Union
from pydantic import BaseModel, Field


# ────────────────────────────────────────────────────────────
# 블록 타입별 모델
# ────────────────────────────────────────────────────────────

class TextBlock(BaseModel):
    type: Literal["text"]
    text: str

    # TODO (노트북 실습 1): 위 필드만으로 완성. 노트북에서 구현 후 여기에 옮기세요.


class ThinkingBlock(BaseModel):
    type: Literal["thinking"]
    text: str  # 원본 'thinking' 필드를 'text'로 정규화 (파서에서 변환)

    # TODO (노트북 실습 1): 노트북에서 구현 후 여기에 옮기세요.


class ToolUseBlock(BaseModel):
    type: Literal["tool_use"]
    name: str
    input: dict[str, Any]

    # TODO (노트북 실습 2): 노트북에서 구현 후 여기에 옮기세요.


class ToolResultContentItem(BaseModel):
    type: str
    text: str = ""

    # TODO (노트북 실습 2): 노트북에서 구현 후 여기에 옮기세요.


class ToolResultBlock(BaseModel):
    type: Literal["tool_result"]
    name: str
    content: list[ToolResultContentItem]
    is_error: bool = False

    # TODO (노트북 실습 2): 노트북에서 구현 후 여기에 옮기세요.


class TokenBudgetBlock(BaseModel):
    type: Literal["token_budget"]
    remaining: int | None = None

    # TODO (노트북 실습 2): 노트북에서 구현 후 여기에 옮기세요.


class FallbackBlock(BaseModel):
    """알 수 없는 블록 타입을 손실 없이 보존하는 폴백 모델."""
    type: str
    raw: dict[str, Any]

    # TODO (노트북 실습 2): 노트북에서 구현 후 여기에 옮기세요.


# 판별 유니온: type 필드로 올바른 모델을 자동 선택한다.
# 참고: Pydantic v2 discriminated union
Block = Union[
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
    ToolResultBlock,
    TokenBudgetBlock,
    FallbackBlock,
]


# ────────────────────────────────────────────────────────────
# Turn / Session 모델
# ────────────────────────────────────────────────────────────

class Turn(BaseModel):
    role: Literal["user", "assistant"]
    blocks: list[Block]

    # TODO (노트북 실습 3): 노트북에서 구현 후 여기에 옮기세요.


class Session(BaseModel):
    session_id: str
    title: str
    created_at: str   # ISO8601
    updated_at: str   # ISO8601
    turns: list[Turn]

    # TODO (노트북 실습 3): 노트북에서 구현 후 여기에 옮기세요.
