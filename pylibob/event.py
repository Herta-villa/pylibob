# ruff: noqa: A003
from __future__ import annotations

from typing import Any, Literal

from pylibob.types import Bot

import msgspec


class Event(msgspec.Struct, dict=True, kw_only=True):
    id: str
    time: float
    type: Literal["meta", "message", "notice", "request"]
    detail_type: str
    sub_type: str = ""
    self: Bot | None = None
    _extra: dict[str, Any] | None = None
    _platform: str = ""

    def dict(self) -> dict[str, Any]:
        # sourcery skip: dict-assign-update-to-union
        raw = {
            k: v
            for k, v in msgspec.structs.asdict(self).items()
            if v is not None
        }
        if extra := raw.pop("_extra", None):
            raw.update(
                {
                    f"{raw.pop('_platform', '')}.{k}": v
                    for k, v in extra.items()
                },
            )
        if bot_self := raw.get("self"):
            raw["self"] = {
                "platform": bot_self["platform"],
                "user_id": bot_self["user_id"],
            }
        return raw


class MetaEvent(
    Event,
    kw_only=True,
    dict=True,
):
    type: Literal["meta"] = "meta"


class MetaConnect(
    MetaEvent,
    kw_only=True,
    dict=True,
):
    detail_type: Literal["connect"] = "connect"
    version: dict[str, str]
