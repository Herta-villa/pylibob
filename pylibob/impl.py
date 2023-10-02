from __future__ import annotations

import asyncio
import inspect
import sys
from typing import Any, Callable, NamedTuple, cast

from pylibob.connection import Connection, ServerConnection
from pylibob.connection_ws import WebSocketReverse
from pylibob.event import Event
from pylibob.runner import ClientRunner, ServerRunner
from pylibob.status import (
    BAD_PARAM,
    OK,
    UNKNOWN_SELF,
    UNSUPPORTED_ACTION,
    UNSUPPORTED_PARAM,
    WHO_AM_I,
)
from pylibob.types import (
    ActionHandler,
    ActionResponse,
    Bot,
    BotSelf,
    FailedActionResponse,
)
from pylibob.utils import (
    TaskManager,
    TypingType,
    analytic_typing,
    background_task,
)

import msgspec
from msgspec import Struct, ValidationError, defstruct

if sys.version_info >= (3, 9):
    from typing import Annotated
else:
    from typing_extensions import Annotated


class ActionHandlerWithValidate(NamedTuple):
    handler: ActionHandler
    keys: set[str]
    typing_types: dict[str, tuple[type, TypingType]]
    model: type[Struct] | None


class OneBotImpl:
    def __init__(
        self,
        name: str,
        version: str,
        conns: list[Connection],
        *bots: Bot,
        onebot_version: str = "12",
    ) -> None:
        self.conns = conns
        self.conn_types = set()
        self.name = name
        self.version = version
        self.onebot_version = onebot_version
        self.is_good = True
        self.actions: dict[str, ActionHandlerWithValidate] = {}
        if not bots:
            raise ValueError("OneBotImpl needs at least one bot")
        self.bots: dict[str, Bot] = {
            f"{bot.platform}.{bot.user_id}": bot for bot in bots
        }

        if not conns:
            raise ValueError(
                "Connections are empty, "
                "OneBotImpl needs at least one connection to start",
            )
        for conn in conns:
            if conn.__class__ in self.conn_types:
                continue
            conn._impl = self  # noqa: SLF001
            conn.init_connection()
            self.conn_types.add(conn.__class__)

        self.register_action_handler("get_status", self.action_get_status)
        self.register_action_handler("get_version", self.action_get_version)
        self.register_action_handler(
            "get_supported_actions",
            self.action_get_supported_actions,
        )

    @property
    def impl_ver(self) -> dict[str, str]:
        return {
            "impl": self.name,
            "version": self.version,
            "onebot_version": self.onebot_version,
        }

    def register_action_handler(
        self,
        action: str,
        func: ActionHandler,
    ) -> ActionHandler:
        types = analytic_typing(func)
        keys = set()
        types_dict = {}
        struct_type = []
        for name, type_, default, typing_type in types:
            keys.add(name)
            types_dict[name] = type_, typing_type
            if default is inspect.Parameter.empty:
                struct_type.append((name, type_))
            else:
                struct_type.append((name, type_, default))
        self.actions[action] = ActionHandlerWithValidate(
            func,
            keys,
            types_dict,
            defstruct(f"{action}ValidateModel", struct_type),
        )
        return func

    def action(
        self,
        action: str,
    ) -> Callable[[ActionHandler], ActionHandler]:
        def wrapper(
            func: ActionHandler,
        ) -> ActionHandler:
            self.register_action_handler(action, func)
            return func

        return wrapper

    async def handle_action(
        self,
        action: str,
        params: dict[str, Any],
        bot_self: BotSelf | None = None,
        echo: str | None = None,
    ) -> ActionResponse:
        action_handler = self.actions.get(action)
        if not action_handler:
            return FailedActionResponse(
                retcode=UNSUPPORTED_ACTION,
                message="action is not supported",
            )
        handler, keys, types, model = action_handler
        if len(self.bots) > 1 and not bot_self:
            return FailedActionResponse(
                retcode=WHO_AM_I,
                message="bot is not detect",
            )

        bot_id = (
            f"{bot_self['platform']}.{bot_self['user_id']}" if bot_self else ""
        )
        if bot_id and bot_id not in self.bots:
            return FailedActionResponse(
                retcode=UNKNOWN_SELF,
                message=f"bot {bot_id} is not exist",
            )
        bot = self.bots.get(bot_id) or next(iter(self.bots.values()))

        for name, type_detail in types.items():
            type_, typing_type = type_detail
            if typing_type is TypingType.BOT:
                params[name] = bot
            elif typing_type is TypingType.ANNOTATED:
                param_real_name = cast(Annotated, type_).__metadata__[0]
                params[name] = params.pop(param_real_name, None)

        try:
            msgspec.convert(params, model)
        except ValidationError as e:
            return FailedActionResponse(retcode=BAD_PARAM, message=str(e))
        if extra_params := set(params) - set(keys):
            return FailedActionResponse(
                retcode=UNSUPPORTED_PARAM,
                message=f"Don't support params: {', '.join(extra_params)}",
            )
        data = await handler(**params)
        return ActionResponse(status="ok", retcode=OK, data=data, echo=echo)

    async def emit(self, event: Event) -> None:
        task = asyncio.create_task(
            *[conn.emit_event(event) for conn in self.conns],
        )
        background_task.add(task)
        task.add_done_callback(background_task.remove)

    async def action_get_version(self):
        """[元动作]获取版本信息
        https://12.onebot.dev/interface/meta/actions/#get_version
        """
        return self.impl_ver

    async def action_get_supported_actions(
        self,
    ):
        """[元动作]获取支持的动作列表
        https://12.onebot.dev/interface/meta/actions/#get_supported_actions
        """
        return list(self.actions.keys())

    async def action_get_status(self):
        """[元动作]获取运行状态
        https://12.onebot.dev/interface/meta/actions/#get_status
        """
        return {
            "good": self.is_good,
            "bots": [bot.to_dict() for bot in self.bots.values()],
        }

    def _get_host(self) -> tuple[str, int] | None:
        return next(
            (
                (conn.host, conn.port)
                for conn in self.conns
                if isinstance(conn, ServerConnection)
            ),
            None,
        )

    def _get_ws_reverse(self) -> WebSocketReverse | None:
        return next(
            (
                conn
                for conn in self.conns
                if isinstance(conn, WebSocketReverse)
            ),
            None,
        )

    def run(self):
        host = self._get_host()
        ws_reverse = self._get_ws_reverse()

        if host is not None:
            runner = ServerRunner(*host)
            if ws_reverse:

                async def _stop():
                    ws_reverse.task_manager.cancel_all()

                runner.on_startup(ws_reverse.run)
                runner.on_shutdown(_stop)
        elif ws_reverse:
            runner = ClientRunner(ws_reverse.task_manager)
            runner.on_startup(ws_reverse.run)
        else:
            runner = ClientRunner(TaskManager())

        if ws_reverse:
            runner.on_startup(ws_reverse._start_heartbeat)  # noqa: SLF001
            runner.on_shutdown(ws_reverse._stop_heartbeat)  # noqa: SLF001

        asyncio.run(runner.run())
