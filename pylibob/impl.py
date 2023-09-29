from __future__ import annotations

import asyncio
from typing import Any, Callable, Coroutine, Dict

from pylibob.connection import Connection
from pylibob.status import OK, UNKNOWN_SELF, UNSUPPORTED_ACTION, WHO_AM_I
from pylibob.types import (
    ActionResponse,
    Bot,
    BotSelf,
    Event,
    FailedActionResponse,
)

ACTION_HANDLER = Callable[
    [Dict[str, Any], Bot],
    Coroutine[Any, Any, Any],
]
background_task = set()


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
        self.name = name
        self.version = version
        self.onebot_version = onebot_version
        self.is_good = True
        self.actions: dict[str, ACTION_HANDLER] = {}
        if not bots:
            raise ValueError("OneBotImpl needs at least one bot")
        self.bots: dict[str, Bot] = {
            f"{bot.platform}.{bot.user_id}": bot for bot in bots
        }

        for conn in conns:
            conn._impl = self  # noqa: SLF001
            conn.init_connection()

        self.actions["get_version"] = self.action_get_version

    async def handle_action(
        self,
        action: str,
        params: dict[str, Any],
        bot_self: BotSelf | None = None,
        echo: str | None = None,
    ) -> ActionResponse:
        handler = self.actions.get(action)
        if not handler:
            return FailedActionResponse(
                retcode=UNSUPPORTED_ACTION,
                message="action is not supported",
            )

        if len(self.bots) > 1:
            if not bot_self:
                return FailedActionResponse(
                    retcode=WHO_AM_I,
                    message="bot is not detect",
                )
            bot_id = f"{bot_self['platform']}.{bot_self['user_id']}"
            if bot_id not in self.bots:
                return FailedActionResponse(
                    retcode=UNKNOWN_SELF,
                    message=f"bot {bot_id} is not exist",
                )
            bot = bot_self[bot_id]
        else:
            bot = next(iter(self.bots.values()))

        data = await handler(params, bot)
        return ActionResponse("ok", OK, data, echo=echo)

    async def emit(self, event: Event) -> None:
        task = asyncio.create_task(
            *[conn.emit_event(event) for conn in self.conns],
        )
        background_task.add(task)
        task.add_done_callback(background_task.remove)

    async def action_get_version(self, params: dict[str, Any], bot: Bot):
        """[元动作]获取版本信息
        https://12.onebot.dev/interface/meta/actions/#get_version
        """
        return {
            "impl": self.name,
            "version": self.version,
            "onebot_version": self.onebot_version,
        }

    async def action_get_supported_actions(
        self,
        params: dict[str, Any],
        bot: Bot,
    ):
        """[元动作]获取支持的动作列表
        https://12.onebot.dev/interface/meta/actions/#get_supported_actions
        """
        return list(self.actions.keys())

    async def get_status(self, params: dict[str, Any], bot: Bot):
        """[元动作]获取运行状态
        https://12.onebot.dev/interface/meta/actions/#get_status
        """
        return {
            "good": self.is_good,
            "bots": [bot.to_dict() for bot in self.bots.values()],
        }
