from __future__ import annotations

from pylibob.types import ContentType

from starlette.requests import HTTPConnection


def detect_content_type(type_: str) -> ContentType | None:
    try:
        return ContentType(type_)
    except ValueError:
        return None


def authorize(access_token: str | None, request: HTTPConnection) -> bool:
    if access_token is None:
        return True
    # 首先检查请求头中是否存在 Authorization 头
    if (
        request_token := request.headers.get("Authorization")
    ) and request_token == f"Bearer {access_token}":
        return True
    # 继续检查是否存在 access_token URL query 参数
    return bool(
        (request_token := request.query_params.get("access_token"))
        and request_token == access_token,
    )
