#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QriBot 机器人入口文件
"""
import nonebot
from nonebot.adapters.onebot.v11 import Adapter as OneBotV11Adapter

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
