#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QriBot 机器人入口文件
"""
import nonebot
from nonebot.adapters.onebot.v11 import Adapter as OneBotV11Adapter
from nonebot.log import logger, default_format
from pathlib import Path

# 配置日志文件路径
logs_dir = Path("logs")
logs_dir.mkdir(exist_ok=True)

# 添加日志文件输出
logger.add(
    logs_dir / "error.log",
    level="ERROR",
    format=default_format,
    rotation="1 week",  # 每周轮转一次
    retention="1 month",  # 保留一个月
    encoding="utf-8"
)

logger.add(
    logs_dir / "info.log",
    level="INFO",
    format=default_format,
    rotation="1 day",  # 每天轮转一次
    retention="7 days",  # 保留7天
    encoding="utf-8"
)

# 初始化 NoneBot
nonebot.init()

# 注册适配器
driver = nonebot.get_driver()
driver.register_adapter(OneBotV11Adapter)

# 加载插件
# 方式1: 加载单个插件
# nonebot.load_plugin("nonebot_plugin_echo")

# 方式2: 加载插件目录
nonebot.load_plugins("plugins")

# 方式3: 加载内置插件
nonebot.load_builtin_plugins("echo")

# 方式4: 从 pyproject.toml 加载插件配置
# nonebot.load_from_toml("pyproject.toml")

if __name__ == "__main__":
    # 启动机器人
    nonebot.run()
