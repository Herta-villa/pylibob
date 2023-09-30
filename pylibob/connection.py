from __future__ import annotations

import asyncio
from asyncio import Queue
import json
import time
from typing import TYPE_CHECKING
from uuid import uuid4

from pylibob.asgi import _asgi_app
from pylibob.event import Event, MetaConnect
from pylibob.status import BAD_REQUEST
from pylibob.types import (
    ActionResponse,
    BotSelf,
    ContentType,
    FailedActionResponse,
)
from pylibob.utils import (
    authorize,
    background_task,
    detect_content_type,
)

import msgspec
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.status import (
    HTTP_401_UNAUTHORIZED,
    HTTP_415_UNSUPPORTED_MEDIA_TYPE,
)
from starlette.websockets import (
    WebSocket as WS,
    WebSocketDisconnect,
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


class ServerConnection(Connection):
    def __init__(
        self,
        *,
        access_token: str | None = None,
        host: str = "0.0.0.0",
        port: int = 8080,
    ) -> None:
        super().__init__(access_token=access_token)
        self.host = host
        self.port = port


class HTTP(ServerConnection):
    def __init__(
        self,
        *,
        access_token: str | None = None,
        host: str = "0.0.0.0",
        port: int = 8080,
        event_enabled: bool = True,
        event_buffer_size: int = 20,
    ) -> None:
        super().__init__(access_token=access_token, host=host, port=port)
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
        return JSONResponse(msgspec.to_builtins(resp))

    async def action_get_latest_events(self, limit: int = 0, timeout: int = 0):
        # TODO: long polling
        assert self.event_queue
        times = 1
        events = []
        while not self.event_queue.empty() and (limit == 0 or times <= limit):
            events.append((await self.event_queue.get()).dict())
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
            self.impl.register_action_handler(
                "get_latest_events",
                self.action_get_latest_events,
            )

    async def emit_event(self, event: Event) -> None:
        if self.event_queue:
            if self.event_queue.full():
                self.event_queue.get_nowait()  # pop the oldest event
            self.event_queue.put_nowait(event)


class WebSocket(ServerConnection):
    def __init__(
        self,
        *,
        access_token: str | None = None,
        host: str = "0.0.0.0",
        port: int = 8080,
    ) -> None:
        super().__init__(access_token=access_token, host=host, port=port)
        self.ws: list[WS] = []

    def init_connection(self) -> None:
        _asgi_app.add_websocket_route(
            "/",
            self.handle_ws_request,
            f"{self.impl.name}-{self.impl.version}-ws",
        )

    async def handle_ws_request(self, ws: WS):
        if not authorize(self.access_token, ws):
            # 如果鉴权失败，必须返回 HTTP 状态码 401 Unauthorized
            await ws.close(HTTP_401_UNAUTHORIZED)
        await ws.accept()

        await ws.send_json(
            MetaConnect(
                id=str(uuid4()),
                time=time.time(),
                version=self.impl.impl_ver,
            ).dict(),
        )
        self.ws.append(ws)
        try:
            while True:
                message = await ws.receive()
                ws._raise_on_disconnect(message)  # noqa: SLF001
                resp = await self.run_action(ContentType.JSON, message["text"])
                await ws.send_json(msgspec.to_builtins(resp))
        except WebSocketDisconnect:
            self.ws.remove(ws)

    async def emit_event(self, event: Event) -> None:
        task = asyncio.create_task(
            *[ws.send_json(event.dict()) for ws in self.ws],
        )
        background_task.add(task)
        task.add_done_callback(background_task.remove)
