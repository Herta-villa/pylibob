from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Coroutine, Literal, TypedDict, cast

from msgspec import Struct


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

    def to_dict(self) -> BotSelf:
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
        return cast(BotSelf, dic)


class ContentType(str, Enum):
    JSON = "application/json"
    MSGPACK = "application/msgpack"


class ActionResponse(Struct, kw_only=True):
    status: Literal["ok", "failed"]
    retcode: int
    data: Any = None
    message: str | None = None
    echo: str | None = None


class FailedActionResponse(ActionResponse, kw_only=True):
    status: Literal["failed"] = "failed"


ActionHandler = Callable[
    ...,
    Coroutine[Any, Any, Any],
]


class Status(TypedDict):
    good: bool
    bots: list[BotSelf]
