from __future__ import annotations

from typing import Literal

from pylibob.event.base import Event
from pylibob.types import Status


class MetaEvent(
    Event,
    kw_only=True,
):
    type: Literal["meta"] = "meta"  # noqa: A003


class MetaConnectEvent(
    MetaEvent,
    kw_only=True,
):
    detail_type: Literal["connect"] = "connect"
    version: dict[str, str]


class MetaHeartbeatEvent(
    MetaEvent,
    kw_only=True,
):
    detail_type: Literal["heartbeat"] = "heartbeat"
    interval: int


class MetaStatusUpdateEvent(
    MetaEvent,
    kw_only=True,
):
    detail_type: Literal["status_update"] = "status_update"
    status: Status
