from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal, TypedDict


class BotSelf(TypedDict):
    platform: str
    user_id: str


@dataclass
class Bot:
    platform: str
    user_id: str
    online: bool
    extra: dict[str, Any] | None = None

    def __hash__(self) -> int:
        return hash((self.platform, self.user_id))


class ContentType(str, Enum):
    JSON = "application/json"
    MSGPACK = "application/msgpack"


@dataclass
class ActionResponse:
    status: Literal["ok", "failed"]
    retcode: int
    data: Any = None
    message: str | None = None
    echo: str | None = None


def FailedActionResponse(
    retcode: int,
    data: Any = None,
    message: str | None = None,
    echo: str | None = None,
):
    return ActionResponse(
        "failed",
        retcode,
        data=data,
        message=message,
        echo=echo,
    )


@dataclass
class Event:
    id: str  # noqa: A003
    time: float
    type: Literal["meta", "message", "notice", "request"]  # noqa: A003
    detail_type: str
    sub_type: str
    self: BotSelf | None = None
