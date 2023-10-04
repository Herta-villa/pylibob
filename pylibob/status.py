"""OneBot 动作响应状态码 `retcode`。"""
from __future__ import annotations

OK = 0

# 1xxxx 动作请求错误（Request Error）
BAD_REQUEST = 10001
UNSUPPORTED_ACTION = 10002
BAD_PARAM = 10003
UNSUPPORTED_PARAM = 10004
UNSUPPORTED_SEGMENT = 10005
BAD_SEGMENT_DATA = 10006
UNSUPPORTED_SEGMENT_DATA = 10007
WHO_AM_I = 10101
UNKNOWN_SELF = 10102

# 2xxxx 动作处理器错误（Handler Error）
BAD_HANDLER = 20001
INTERNAL_HANDLER_ERROR = 20002
