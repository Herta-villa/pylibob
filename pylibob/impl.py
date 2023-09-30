from __future__ import annotations

import asyncio
from typing import Any, Callable, NamedTuple

from pylibob.asgi import _asgi_app
from pylibob.connection import Connection, ServerConnection
from pylibob.event import Event
from pylibob.status import (
    BAD_PARAM,
    OK,
    UNKNOWN_SELF,
    UNSUPPORTED_ACTION,
    WHO_AM_I,
)
from pylibob.types import (
    ActionHandler,
    ActionResponse,
    Bot,
    BotSelf,
    FailedActionResponse,
)
from pylibob.utils import analytic_typing, background_task

import msgspec
from msgspec import Struct, ValidationError, defstruct
import uvicorn


class ActionHandlerWithValidate(NamedTuple):
    handler: ActionHandler
    keys: set[str]
    model: type[Struct] | None
    with_bot: bool
    bot_parameter_name: str


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
        types, with_bot, bot_parameter_name = analytic_typing(func)
        self.actions[action] = ActionHandlerWithValidate(
            func,
            {type_[0] for type_ in types},
            defstruct(f"{action}ValidateModel", types),
            with_bot,
            bot_parameter_name,
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
        handler, types, model, with_bot, bot_parameter_name = action_handler
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
        if with_bot:
            params[bot_parameter_name] = bot
        try:
            msgspec.convert(params, model)
        except ValidationError as e:
            return FailedActionResponse(retcode=BAD_PARAM, message=str(e))
        new_params = {
            param: params[param] for param in params if param in types
        }
        data = await handler(**new_params)
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

    def run(self):
        host = self._get_host()
        if host is not None:
            uvicorn.run(_asgi_app, host=host[0], port=host[1])
