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

    def to_dict(self) -> dict[str, Any]:
        # sourcery skip: dict-assign-update-to-union
        dic = {
            "self": {
                "platform": self.platform,
                "user_id": self.user_id,
            },
            "online": self.online,
        }
        if self.extra is not None:
            dic.update(
                {f"{self.platform}.{k}": v for k, v in self.extra.items()},
            )
        return dic


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
