#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
命令处理模块
定义和管理命令处理器
"""
from nonebot import on_command
from nonebot.rule import Rule
from pathlib import Path
from typing import Dict
from .prompts import triggers


def get_all_aliases() -> set[str]:
    """从 triggers 字典中收集所有别名(包括 key 和 aliases)"""
    all_aliases = set()
    for trigger_key, trigger_config in triggers.items():
        all_aliases.add(trigger_key)  # 添加 key
        all_aliases.update(trigger_config["aliases"])  # 添加 aliases
    return all_aliases


def build_command_to_prompt_map() -> Dict[str, Path]:
    """从 triggers 字典生成命令到 prompt 文件路径的映射"""
    command_map = {}
    for trigger_key, trigger_config in triggers.items():
        prompt_file_path = trigger_config["promptFilePath"]
        # 将 key 映射到 prompt 文件路径
        command_map[trigger_key] = prompt_file_path
        # 将所有 aliases 也映射到同一个 prompt 文件路径
        for alias in trigger_config["aliases"]:
            command_map[alias] = prompt_file_path
    return command_map


# 生成命令到 prompt 文件路径的映射
commandToPromptFilePath = build_command_to_prompt_map()


def create_forward_ana_cmd(check_permission_func, config):
    """
    创建命令处理器
    
    Args:
        check_permission_func: 权限检查函数
        config: 插件配置对象
    
    Returns:
        命令处理器实例
    """
    return on_command(
        "ana",
        aliases=get_all_aliases(),
        rule=Rule(check_permission_func),
        priority=1,
        block=False
    )
