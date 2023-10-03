from __future__ import annotations

from typing import Any

from msgspec import Struct


class Segment(Struct):
    type: str  # noqa: A003
    data: dict[str, Any]


def Text(text: str, **extra: Any) -> Segment:
    return Segment(type="text", data={"text": text, **extra})


def Image(file_id: str, **extra: Any) -> Segment:
    return Segment(type="image", data={"file_id": file_id, **extra})


def Mention(user_id: str, **extra: Any) -> Segment:
    return Segment(type="mention", data={"user_id": user_id, **extra})


def MentionAll(**extra: Any) -> Segment:
    return Segment(type="mention_all", data=extra)


def Voice(file_id: str, **extra: Any) -> Segment:
    return Segment(type="voice", data={"file_id": file_id, **extra})


def Audio(file_id: str, **extra: Any) -> Segment:
    return Segment(type="audio", data={"file_id": file_id, **extra})


def Video(file_id: str, **extra: Any) -> Segment:
    return Segment(type="video", data={"file_id": file_id, **extra})


def File(file_id: str, **extra: Any) -> Segment:
    return Segment(type="file", data={"file_id": file_id, **extra})


def Location(
    latitude: float,
    longitude: float,
    title: str,
    content: str,
    **extra: Any,
) -> Segment:
    return Segment(
        type="location",
        data={
            "latitude": latitude,
            "longitude": longitude,
            "title": title,
            "content": content,
            **extra,
        },
    )


def Reply(message_id: str, user_id: str, **extra: Any) -> Segment:
    return Segment(
        type="reply",
        data={"message_id": message_id, "user_id": user_id, **extra},
    )
