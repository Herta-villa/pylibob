from __future__ import annotations

from typing import Literal

from pylibob.event.base import Event


class NoticeEvent(Event, kw_only=True):
    type: Literal["notice"] = "notice"  # noqa: A003


class FriendIncreaseEvent(NoticeEvent, kw_only=True):
    detail_type: Literal["friend_increase"] = "friend_increase"
    user_id: str


class FriendDecreaseEvent(NoticeEvent, kw_only=True):
    detail_type: Literal["friend_decrease"] = "friend_decrease"
    user_id: str


class GroupMemberIncreaseEvent(NoticeEvent, kw_only=True):
    detail_type: Literal["group_member_increase"] = "group_member_increase"
    sub_type: str
    group_id: str
    user_id: str
    operator_id: str


class GroupMemberDecreaseEvent(NoticeEvent, kw_only=True):
    detail_type: Literal["group_member_decrease"] = "group_member_decrease"
    sub_type: str
    group_id: str
    user_id: str
    operator_id: str


class GroupMessageDeleteEvent(NoticeEvent, kw_only=True):
    detail_type: Literal["group_message_delete"] = "group_message_delete"
    sub_type: str
    group_id: str
    message_id: str
    user_id: str
    operator_id: str


class GuildMemberIncreaseEvent(NoticeEvent, kw_only=True):
    detail_type: Literal["guild_member_increase"] = "guild_member_increase"
    sub_type: str
    guild_id: str
    user_id: str
    operator_id: str


class GuildMemberDecreaseEvent(NoticeEvent, kw_only=True):
    detail_type: Literal["guild_member_decrease"] = "guild_member_decrease"
    sub_type: str
    guild_id: str
    user_id: str
    operator_id: str


class ChannelMemberIncreaseEvent(NoticeEvent, kw_only=True):
    detail_type: Literal["channel_member_increase"] = "channel_member_increase"
    sub_type: str
    guild_id: str
    channel_id: str
    user_id: str
    operator_id: str


class ChannelMemberDecreaseEvent(NoticeEvent, kw_only=True):
    detail_type: Literal["channel_member_decrease"] = "channel_member_decrease"
    sub_type: str
    guild_id: str
    channel_id: str
    user_id: str
    operator_id: str


class ChannelMessageDeleteEvent(NoticeEvent, kw_only=True):
    detail_type: Literal["channel_message_delete"] = "channel_message_delete"
    sub_type: str
    guild_id: str
    channel_id: str
    message_id: str
    user_id: str
    operator_id: str


class ChannelCreateEvent(NoticeEvent, kw_only=True):
    detail_type: Literal["channel_create"] = "channel_create"
    guild_id: str
    channel_id: str
    operator_id: str


class ChannelDeleteEvent(NoticeEvent, kw_only=True):
    detail_type: Literal["channel_delete"] = "channel_delete"
    guild_id: str
    channel_id: str
    operator_id: str
