from __future__ import annotations

import abc
import asyncio
import signal
from typing import Any

from pylibob.asgi import asgi_app, asgi_lifespan_manager
from pylibob.utils import L_FUNC, LifespanManager, TaskManager

import uvicorn

HANDLED_SIGNALS = {
    signal.SIGINT,  # Unix kill -2(CTRL + C)
    signal.SIGTERM,  # Unix kill -15
}


class Runner(abc.ABC):
    @abc.abstractmethod
    async def run(self):
        raise NotImplementedError

    @abc.abstractmethod
    def on_startup(self, func: L_FUNC):
        raise NotImplementedError

    @abc.abstractmethod
    def on_shutdown(self, func: L_FUNC):
        raise NotImplementedError

    @abc.abstractproperty
    def lifespan_manager(self) -> LifespanManager:
        raise NotImplementedError


class ServerRunner(Runner):
    def __init__(self, host: str, port: int, **kwargs: Any) -> None:
        self.host = host
        self.port = port
        self.uvicorn_params = kwargs

    async def run(self):
        await uvicorn.Server(
            uvicorn.Config(
                asgi_app,
                host=self.host,
                port=self.port,
                **self.uvicorn_params,
            ),
        ).serve()

    def on_startup(self, func: L_FUNC):
        asgi_lifespan_manager.on_startup(func)

    def on_shutdown(self, func: L_FUNC):
        asgi_lifespan_manager.on_shutdown(func)

    @property
    def lifespan_manager(self) -> LifespanManager:
        return asgi_lifespan_manager


class ClientRunner(Runner):
    def __init__(self, task_manager: TaskManager) -> None:
        self.should_exit: asyncio.Event = asyncio.Event()
        self.force_exit: bool = False
        self.task_manager = task_manager
        self._lifespan_manager = LifespanManager()

    @property
    def lifespan_manager(self) -> LifespanManager:
        return self._lifespan_manager

    async def _loop(self):
        await self.should_exit.wait()

    def _handle_exit(self, sig, frame):
        self.should_exit.set()

    async def _shutdown(self):
        await self.lifespan_manager.shutdown()
        self.task_manager.cancel_all()

    def on_startup(self, func: L_FUNC):
        self.lifespan_manager.on_startup(func)

    def on_shutdown(self, func: L_FUNC):
        self.lifespan_manager.on_shutdown(func)

    async def run(self):
        for sig in HANDLED_SIGNALS:
            signal.signal(sig, self._handle_exit)
        await self.lifespan_manager.startup()
        await self._loop()
        await self._shutdown()
