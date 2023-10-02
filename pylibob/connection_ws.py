from __future__ import annotations

import abc
import asyncio
import json
import time
from typing import Any
from uuid import uuid4

from pylibob.asgi import asgi_app, asgi_lifespan_manager
from pylibob.connection import ClientConnection, Connection, ServerConnection
from pylibob.event import Event, MetaConnect, MetaHeartbeat
from pylibob.utils import TaskManager, authorize, background_task

from aiohttp import (
    ClientError,
    ClientSession,
    ClientWebSocketResponse,
    WSMsgType,
)
import msgspec
from starlette.status import HTTP_401_UNAUTHORIZED
from starlette.websockets import (
    WebSocket as WS,
    WebSocketDisconnect,
)
from websockets.exceptions import ConnectionClosed


class ConnectClosed(Exception):
    ...


class WSProtocol(abc.ABC):
    @abc.abstractmethod
    async def send_json(self, data: Any):
        raise NotImplementedError

    @abc.abstractmethod
    async def send_msgpack(self, data: Any):
        raise NotImplementedError

    @abc.abstractmethod
    async def receive(self) -> Any:
        raise NotImplementedError


class ServerWSProtocol(WSProtocol):
    def __init__(self, ws: WS) -> None:
        self.ws = ws

    async def send_json(self, data: Any):
        await self.ws.send_json(data)

    async def send_msgpack(self, data: Any):
        ...

    async def receive(self) -> Any:
        message = await self.ws.receive()
        self.ws._raise_on_disconnect(message)  # noqa: SLF001
        return json.loads(message["text"])


class ClientWSProtocol(WSProtocol):
    def __init__(self, ws: ClientWebSocketResponse) -> None:
        self.ws = ws

    async def send_json(self, data: Any):
        await self.ws.send_json(data)

    async def send_msgpack(self, data: Any):
        ...

    async def receive(self) -> Any:
        message = await self.ws.receive()
        if message.type in {
            WSMsgType.CLOSE,
            WSMsgType.ERROR,
            WSMsgType.CLOSED,
        }:
            raise ConnectClosed
        return json.loads(message.data)


class WebSocketConnection(Connection):
    def __init__(
        self,
        *,
        access_token: str | None = None,
        enable_heartbeat: bool = True,
        heartbeat_interval: int = 5000,
    ) -> None:
        super().__init__(access_token=access_token)
        self.enable_heartbeat = enable_heartbeat
        if heartbeat_interval <= 0:
            raise ValueError("The interval of heartbeat must be positive")
        self.heartbeat_interval = heartbeat_interval
        self.task_manager = TaskManager()
        self.ws: list[WSProtocol] = []
        self._heartbeat_run = True

    async def _heartbeat(self):
        while self._heartbeat_run:
            for ws in self.ws:
                await ws.send_json(
                    MetaHeartbeat(
                        id=str(uuid4()),
                        time=time.time(),
                        interval=self.heartbeat_interval,
                    ).dict(),
                )
            await asyncio.sleep(self.heartbeat_interval / 1000)

    async def _start_heartbeat(self):
        task = asyncio.create_task(self._heartbeat())
        background_task.add(task)
        task.add_done_callback(background_task.remove)

    async def _stop_heartbeat(self):
        self._heartbeat_run = False
        self.task_manager.cancel_all()

    def _enable_heartbeat(self):
        asgi_lifespan_manager.on_startup(self._start_heartbeat)
        asgi_lifespan_manager.on_shutdown(self._stop_heartbeat)

    async def _listen_ws(self, ws: WSProtocol):
        while True:
            message = await ws.receive()
            resp = await self.run_action(message)
            await ws.send_json(msgspec.to_builtins(resp))

    async def emit_event(self, event: Event) -> None:
        task = asyncio.create_task(
            *[ws.send_json(event.dict()) for ws in self.ws],
        )
        background_task.add(task)
        task.add_done_callback(background_task.remove)


class WebSocket(WebSocketConnection, ServerConnection):
    def __init__(
        self,
        *,
        access_token: str | None = None,
        host: str = "0.0.0.0",
        port: int = 8080,
        enable_heartbeat: bool = True,
        heartbeat_interval: int = 5000,
    ) -> None:
        super().__init__(
            access_token=access_token,
            enable_heartbeat=enable_heartbeat,
            heartbeat_interval=heartbeat_interval,
        )
        super(WebSocketConnection, self).__init__(host=host, port=port)

    def init_connection(self) -> None:
        asgi_app.add_websocket_route(
            "/",
            self.handle_ws_request,
            f"{self.impl.name}-{self.impl.version}-ws",
        )

        if self.enable_heartbeat:
            self._enable_heartbeat()

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
        ws_protocol = ServerWSProtocol(ws)
        self.ws.append(ws_protocol)
        try:
            await self._listen_ws(ws_protocol)
        except (WebSocketDisconnect, ConnectionClosed):
            self.ws.remove(ws_protocol)


class WebSocketReverse(
    ClientConnection,
    WebSocketConnection,
):
    def __init__(
        self,
        url: str,
        *,
        access_token: str | None = None,
        reconnect_interval: int = 5000,
        enable_heartbeat: bool = True,
        heartbeat_interval: int = 5000,
    ) -> None:
        super().__init__(
            url=url,
            access_token=access_token,
        )
        super(ClientConnection, self).__init__(
            enable_heartbeat=enable_heartbeat,
            heartbeat_interval=heartbeat_interval,
        )
        self.url = url
        if reconnect_interval <= 0:
            raise ValueError("The interval of reconnection must be positive")
        self.reconnect_interval = reconnect_interval

    async def connect_to_remote(self):
        async with ClientSession() as session:
            while True:
                try:
                    async with session.ws_connect(
                        self.url,
                        headers={
                            "User-Agent": self.ua,
                            "Sec-WebSocket-Protocol": (
                                f"{self.impl.onebot_version}.{self.impl.name}"
                            ),
                        },
                    ) as resp:
                        await resp.send_json(
                            MetaConnect(
                                id=str(uuid4()),
                                time=time.time(),
                                version=self.impl.impl_ver,
                            ).dict(),
                        )

                        ws_protocol = ClientWSProtocol(resp)
                        self.ws.append(ws_protocol)
                        await self._listen_ws(
                            ws=ws_protocol,
                        )
                except (ClientError, ConnectClosed, ConnectionError):
                    await asyncio.sleep(
                        self.reconnect_interval / 1000,
                    )

    async def run(self):
        self.task_manager.task_nowait(self.connect_to_remote)
