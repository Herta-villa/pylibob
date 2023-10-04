from __future__ import annotations

from typing import Literal

from pylibob.event.base import Event
from pylibob.segment import Segment


class MessageEvent(Event, kw_only=True):
    type: Literal["message"] = "message"  # noqa: A003


class PrivateMessageEvent(MessageEvent, kw_only=True):
    detail_type: Literal["private"] = "private"
    message_id: str
    message: list[Segment]
    alt_message: str = ""
    user_id: str


class GroupMessageEvent(MessageEvent, kw_only=True):
    detail_type: Literal["group"] = "group"
    message_id: str
    message: list[Segment]
    alt_message: str = ""
    group_id: str
    user_id: str


class ChannelMessageEvent(MessageEvent, kw_only=True):
    detail_type: Literal["channel"] = "channel"
    message_id: str
    message: list[Segment]
    alt_message: str = ""
    guild_id: str
    user_id: str
    channel_id: str
