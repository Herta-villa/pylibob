# pylibob

另一个 LibOneBot Python 库，旨在帮助开发者实现 [OneBot 12](https://12.onebot.dev/) 标准。

## 这是什么？

这是一个 Python 的 [LibOneBot](https://12.onebot.dev/glossary/#libonebot) 旨在帮助开发者快速实现 OneBot 12 标准。

LibOneBot 对 [OneBot Connect](https://12.onebot.dev/connect/) 和动作、事件、消息段进行了包装，便于开发者使用。

下文涉及的 OneBot 概念请参考 [OneBot 术语表](https://12.onebot.dev/glossary/)

## 安装

```shell
pip install pylibob
```

## 快速上手

```python
from __future__ import annotations

# from typing_extensions import Annotated  # python<3.9
from typing import Annotated  # python>=3.9

from pylibob.connection import HTTP, HTTPWebhook
from pylibob.connection_ws import WebSocket, WebSocketReverse
from pylibob.event import Event
from pylibob.impl import OneBotImpl
from pylibob.types import Bot

impl = OneBotImpl(
    "test",  # 实现名称
    "1.0.0",  # 实现版本
    [
        HTTP(
            host="0.0.0.0",  # HTTP 服务器监听 IP
            port=8080,  # HTTP 服务器监听端口
            event_enabled=True,  # 是否启用 get_latest_events 元动作
            event_buffer_size=20,  # 事件缓冲区大小
            access_token="access_token",  # 访问令牌
        ),
        HTTPWebhook(
            url="http://127.0.0.1:8080/onebot/v12/http/",  # Webhook 上报地址
        ),
        # WebSocket 均存在 enable_heartbeat 和 heartbeat_interval
        WebSocket(
            enable_heartbeat=True,  # 启用心跳
            heartbeat_interval=5000,  # 心跳间隔
        ),
        WebSocketReverse(url="ws://127.0.0.1:8081/onebot/v12/ws/"),
    ],
    Bot(platform="qq", user_id="1", online=True),  # 任意个数 Bot 实例
)


@impl.action("hello")
async def _(
    # 采用类型注解的方式表明参数及类型
    a: str,
    # 扩展参数使用 Annotated，第一个 metadata 会被视为参数名
    b: Annotated[int, "extra.param"],
    # 注解为 Bot 的参数不计入动作需要的参数，会内部处理传入 Bot 实例
    c: Bot,
    # 允许默认值，不传入使用默认值，不报错
    d: int = 5,
):
    # 此函数接受:
    # a (string)
    # extra.param (int)
    # d (int) (default = 5)

    # 向应用推送事件
    await impl.emit(Event(...))

    return a, b, c, d  # 返回的内容会传入到相应的 data

# 机器人准备好后（一般指机器人登录完成）
# 实现良好状态默认为 False，准备好需手动调整为 True
# impl.is_good = True
# 还要调用此方法去更新状态
# await impl.update_status()

impl.run()  # 运行
```

## 许可证

MIT
