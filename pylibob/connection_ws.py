from __future__ import annotations

import abc
import asyncio
import json
import logging
import time
from typing import Any
from uuid import uuid4

from pylibob.asgi import asgi_app, asgi_lifespan_manager
from pylibob.connection import ClientConnection, Connection, ServerConnection
from pylibob.event import Event, MetaConnect, MetaHeartbeat
from pylibob.types import ContentType
from pylibob.utils import TaskManager, authorize, background_task

from aiohttp import (
    ClientError,
    ClientSession,
    ClientWebSocketResponse,
    WSMsgType,
)
import msgpack
import msgspec
from starlette.status import HTTP_401_UNAUTHORIZED
from starlette.websockets import (
    WebSocket as WS,
    WebSocketDisconnect,
)
from websockets.exceptions import ConnectionClosed

logger = logging.getLogger("pylibob.connection_ws")


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
    async def receive(self) -> tuple[ContentType, Any]:
        raise NotImplementedError


class ServerWSProtocol(WSProtocol):
    def __init__(self, ws: WS) -> None:
        self.ws = ws

    async def send_json(self, data: Any) -> None:
        logger.debug(f"[SEND_JSON => {self.ws.url}] {data}")
        await self.ws.send_json(data)

    async def send_msgpack(self, data: Any):
        logger.debug(f"[SEND_MSGPACK => {self.ws.url}] {data}")
        await self.ws.send_bytes(msgpack.packb(data))  # type: ignore

    async def receive(self) -> tuple[ContentType, Any]:
        message = await self.ws.receive()
        self.ws._raise_on_disconnect(message)  # noqa: SLF001
        if "text" in message:
            # JSON
            data = json.loads(message["text"])
            content_type = ContentType.JSON
        else:
            # MessagePack
            data = msgpack.unpackb(message["bytes"])
            content_type = ContentType.MSGPACK
        logger.debug(f"[RECEIVE({content_type.name}) <= {self.ws.url}] {data}")
        return content_type, data


class ClientWSProtocol(WSProtocol):
    def __init__(self, ws: ClientWebSocketResponse) -> None:
        self.ws = ws

    async def send_json(self, data: Any):
        logger.debug(
            f"[SEND_JSON => {self.ws._response.url}] {data}",  # noqa: SLF001
        )
        await self.ws.send_json(data)

    async def send_msgpack(self, data: Any):
        logger.debug(
            "[SEND_MSGPACK => "
            f"{self.ws._response.url}] {data}",  # noqa: SLF001
        )
        await self.ws.send_bytes(msgpack.packb(data))  # type: ignore

    async def receive(self) -> Any:
        message = await self.ws.receive()
        if message.type in {
            WSMsgType.CLOSE,
            WSMsgType.ERROR,
            WSMsgType.CLOSED,
        }:
            raise ConnectClosed
        if message.type == WSMsgType.TEXT:
            # JSON
            data = json.loads(message.data)
            content_type = ContentType.JSON
        else:
            # MessagePack
            data = msgpack.unpackb(message.data)
            content_type = ContentType.MSGPACK
        logger.debug(
            f"[RECEIVE({content_type.name}) <= "
            f"{self.ws._response.url}] {data}",  # noqa: SLF001
        )
        return content_type, data


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

    async def _heartbeat(self) -> None:
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
        logger.info(f"启动 {self.__class__.__name__} 心跳服务")
        task = asyncio.create_task(self._heartbeat())
        background_task.add(task)
        task.add_done_callback(background_task.remove)

    async def _stop_heartbeat(self):
        logger.info(f"停止 {self.__class__.__name__} 心跳服务")
        self._heartbeat_run = False
        self.task_manager.cancel_all()

    async def _listen_ws(self, ws: WSProtocol):
        while True:
            content_type, message = await ws.receive()
            resp = await self.run_action(message)
            send_func = (
                ws.send_json
                if content_type == ContentType.JSON
                else ws.send_msgpack
            )
            await send_func(msgspec.to_builtins(resp))

    async def emit_event(self, event: Event) -> None:
        for ws in self.ws:
            task = asyncio.create_task(ws.send_json(event.dict()))
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
        self.logger = logging.getLogger("pylibob.connection_ws.websocket")

    def _enable_heartbeat(self):
        asgi_lifespan_manager.on_startup(self._start_heartbeat)
        asgi_lifespan_manager.on_shutdown(self._stop_heartbeat)

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
            self.logger.warning(f"{ws.url} 鉴权失败")
            await ws.close(HTTP_401_UNAUTHORIZED)
        await ws.accept()
        self.logger.info(f"接受连接: {ws.url}")
        ws_protocol = ServerWSProtocol(ws)
        await ws_protocol.send_json(
            MetaConnect(
                id=str(uuid4()),
                time=time.time(),
                version=self.impl.impl_ver,
            ).dict(),
        )
        self.ws.append(ws_protocol)
        try:
            await self._listen_ws(ws_protocol)
        except (WebSocketDisconnect, ConnectionClosed):
            self.logger.warning(f"连接中断: {ws.url}")
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
        self.logger = logging.getLogger(
            "pylibob.connection_ws.websocket_reverse",
        )

    async def connect_to_remote(self):
        async with ClientSession() as session:
            self.logger.info(f"尝试连接到反向 WS 服务器: {self.url}")
            ws_protocol: ClientWSProtocol | None = None
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
                        ws_protocol = ClientWSProtocol(resp)
                        self.ws.append(ws_protocol)
                        await ws_protocol.send_json(
                            MetaConnect(
                                id=str(uuid4()),
                                time=time.time(),
                                version=self.impl.impl_ver,
                            ).dict(),
                        )
                        self.logger.info(
                            f"连接到反向 WS 服务器 {self.url} 成功",
                        )
                        await self._listen_ws(
                            ws=ws_protocol,
                        )
                except (ClientError, ConnectClosed, ConnectionError) as e:
                    if ws_protocol:
                        self.ws.remove(ws_protocol)
                        ws_protocol = None
                    self.logger.warning(
                        f"连接到反向 WS 服务器 {self.url} 失败: {e}, "
                        f"将在 {self.reconnect_interval} 毫秒后重连",
                    )
                    await asyncio.sleep(
                        self.reconnect_interval / 1000,
                    )
                finally:
                    if ws_protocol:
                        self.ws.remove(ws_protocol)
                        ws_protocol = None

    async def run(self):
        self.task_manager.task_nowait(self.connect_to_remote)
