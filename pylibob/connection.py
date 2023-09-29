from __future__ import annotations

from asyncio import Queue
from dataclasses import asdict
import json
from typing import TYPE_CHECKING, Any

from pylibob.asgi import _asgi_app
from pylibob.status import BAD_REQUEST
from pylibob.types import (
    ActionResponse,
    Bot,
    BotSelf,
    ContentType,
    Event,
    FailedActionResponse,
)
from pylibob.utils import authorize, detect_content_type

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.status import (
    HTTP_401_UNAUTHORIZED,
    HTTP_415_UNSUPPORTED_MEDIA_TYPE,
)

if TYPE_CHECKING:
    from pylibob.impl import OneBotImpl


class Connection:
    def __init__(
        self,
        *,
        access_token: str | None = None,
    ) -> None:
        self.access_token = access_token
        self._impl: "OneBotImpl" | None = None
        super().__init__()

    @property
    def impl(self) -> "OneBotImpl":
        if self._impl is None:
            raise ValueError("OneBotImpl is not initialed")
        return self._impl

    async def run_action(
        self,
        content_type: ContentType,
        raw: bytes,
    ) -> ActionResponse:
        if content_type == ContentType.MSGPACK:
            # 暂不支持 MessagePack
            return FailedActionResponse(
                retcode=BAD_REQUEST,
                message="OneBotImpl doesn't support MessagePack",
            )

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return FailedActionResponse(
                retcode=BAD_REQUEST,
                message="Invalid JSON",
            )

        if not (action := data.get("action")):
            return FailedActionResponse(
                retcode=BAD_REQUEST,
                message="`action` is not exist.",
            )
        if (params := data.get("params")) is None:
            return FailedActionResponse(
                retcode=BAD_REQUEST,
                message="`params` is not exist.",
            )
        echo = data.get("echo")
        bot_self: BotSelf = data.get("self")
        return await self.impl.handle_action(action, params, bot_self, echo)

    def init_connection(self) -> None:
        pass

    async def emit_event(self, event: Event) -> None:
        raise NotImplementedError


class HTTP(Connection):
    def __init__(
        self,
        *,
        access_token: str | None = None,
        host: str = "0.0.0.0",
        port: int = 8080,
        event_enabled: bool = True,
        event_buffer_size: int = 20,
    ) -> None:
        super().__init__(access_token=access_token)
        self.host = host
        self.port = port
        self.event_queue: Queue[Event] | None = (
            Queue(maxsize=event_buffer_size) if event_enabled else None
        )

    async def receive_http_request(self, request: Request) -> Response:
        # 鉴权
        if not authorize(self.access_token, request):
            # 如果鉴权失败，必须返回 HTTP 状态码 401 Unauthorized
            return Response(status_code=HTTP_401_UNAUTHORIZED)
        # 检查 Content-Type
        if not (
            content_type := detect_content_type(
                request.headers.get("Content-Type") or "",
            )
        ):
            return Response(status_code=HTTP_415_UNSUPPORTED_MEDIA_TYPE)
        resp = await self.run_action(
            content_type=content_type,
            raw=await request.body(),
        )
        return JSONResponse(
            asdict(
                resp,
                dict_factory=lambda x: {
                    k: v for k, v in x if v is not None
                },  # Exclude None
            ),
        )

    async def action_get_latest_events(self, params: dict[str, Any], bot: Bot):
        limit = params.get("limit", 0)
        # TODO: long polling
        timeout = params.get("timeout", 0)  # noqa: F841
        assert self.event_queue
        times = 1
        events = []
        while not self.event_queue.empty() and (limit == 0 or times <= limit):
            events.append(await self.event_queue.get())
            times += 1
        return events

    def init_connection(self) -> None:
        _asgi_app.add_route(
            "/",
            self.receive_http_request,
            ["POST"],
            f"{self.impl.name}-{self.impl.version}-http",
            False,
        )
        if self.event_queue:
            self.impl.actions[
                "get_latest_events"
            ] = self.action_get_latest_events

    async def emit_event(self, event: Event) -> None:
        if self.event_queue:
            if self.event_queue.full():
                self.event_queue.get_nowait()  # pop the oldest event
            self.event_queue.put_nowait(event)
