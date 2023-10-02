from __future__ import annotations

from typing import Any

from pylibob.status import (
    BAD_HANDLER,
    BAD_PARAM,
    BAD_REQUEST,
    BAD_SEGMENT_DATA,
    INTERNAL_HANDLER_ERROR,
    UNKNOWN_SELF,
    UNSUPPORTED_ACTION,
    UNSUPPORTED_PARAM,
    UNSUPPORTED_SEGMENT,
    UNSUPPORTED_SEGMENT_DATA,
    WHO_AM_I,
)


class OneBotImplError(Exception):
    def __init__(
        self,
        retcode: int,
        data: Any = None,
        message: str = "",
    ) -> None:
        self.retcode = retcode
        self.data = data
        self.message = message


class BadRequest(OneBotImplError):
    def __init__(self, data: Any = None, message: str = "") -> None:
        super().__init__(BAD_REQUEST, data, message)


class BadParam(OneBotImplError):
    def __init__(self, data: Any = None, message: str = "") -> None:
        super().__init__(BAD_PARAM, data, message)


class UnsupportedAction(OneBotImplError):
    def __init__(self, data: Any = None, message: str = "") -> None:
        super().__init__(UNSUPPORTED_ACTION, data, message)


class UnsupportedParam(OneBotImplError):
    def __init__(self, data: Any = None, message: str = "") -> None:
        super().__init__(UNSUPPORTED_PARAM, data, message)


class UnsupportedSegment(OneBotImplError):
    def __init__(self, data: Any = None, message: str = "") -> None:
        super().__init__(UNSUPPORTED_SEGMENT, data, message)


class BadSegmentData(OneBotImplError):
    def __init__(self, data: Any = None, message: str = "") -> None:
        super().__init__(BAD_SEGMENT_DATA, data, message)


class UnsupportedSegmentData(OneBotImplError):
    def __init__(self, data: Any = None, message: str = "") -> None:
        super().__init__(UNSUPPORTED_SEGMENT_DATA, data, message)


class WhoAmI(OneBotImplError):
    def __init__(self, data: Any = None, message: str = "") -> None:
        super().__init__(WHO_AM_I, data, message)


class UnknownSelf(OneBotImplError):
    def __init__(self, data: Any = None, message: str = "") -> None:
        super().__init__(UNKNOWN_SELF, data, message)


class BadHandler(OneBotImplError):
    def __init__(self, data: Any = None, message: str = "") -> None:
        super().__init__(BAD_HANDLER, data, message)


class InternalHandlerError(OneBotImplError):
    def __init__(self, data: Any = None, message: str = "") -> None:
        super().__init__(INTERNAL_HANDLER_ERROR, data, message)
