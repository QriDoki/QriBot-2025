#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prompts 管理模块
负责加载和管理 prompt 模板文件
"""
from pathlib import Path
from typing import Optional, Dict
from nonebot import logger
import yaml
import re

# 插件目录路径
PLUGIN_DIR = Path(__file__).parent
SYSTEM_PROMPT_JUSTICE_PATH = PLUGIN_DIR / "prompts" / "alignment_prompt.md"
SYSTEM_PROMPT_ANA_PATH = PLUGIN_DIR / "prompts" / "how_to_say.md"
SYSTEM_PROMPT_POV_PATH = PLUGIN_DIR / "prompts" / "pov.md"
SYSTEM_PROMPT_BLANK_PATH = PLUGIN_DIR / "prompts" / "blank.md"
EMPTY_CSS_PATH = PLUGIN_DIR / "empty.css"

# 全局变量: alias -> 文件路径的映射字典
PROMPT_ALIAS_MAP: Dict[str, str] = {}

# Trigger 配置
triggers = {
    "justice": {
        "promptFilePath": SYSTEM_PROMPT_JUSTICE_PATH,
        "aliases": ["蜻蜓队长", "正义", "天降正义", "裁判", "对线"]
    },
    "ana": {
        "promptFilePath": SYSTEM_PROMPT_ANA_PATH,
        "aliases": ["analyse", "分析", "怎么说", "如何评价"]
    },
    "pov": {
        "promptFilePath": SYSTEM_PROMPT_POV_PATH,
        "aliases": ["观点"]
    },
    "blank": {
        "promptFilePath": SYSTEM_PROMPT_POV_PATH,
        "aliases": ["空白", "空提示词", "无", "无提示词"]
    }
}


def parse_yaml_front_matter(file_path: Path) -> tuple[Optional[dict], str]:
    """
    解析 Markdown 文件的 YAML front matter
    返回: (front_matter_dict, content_without_front_matter)
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # 匹配 YAML front matter (以 --- 开头和结尾)
        pattern = r'^---\s*\n(.*?)\n---\s*\n(.*)$'
        match = re.match(pattern, content, re.DOTALL)
        
        if match:
            yaml_content = match.group(1)
            markdown_content = match.group(2)
            front_matter = yaml.safe_load(yaml_content)
            return front_matter, markdown_content
        else:
            return None, content
    except Exception as e:
        logger.opt(exception=True).error(f"解析 YAML front matter 失败 ({file_path.name}): {e}")
        return None, ""


def load_prompt_aliases() -> Dict[str, str]:
    """
    加载所有 prompt 文件,构建 alias -> 文件路径的映射字典
    也包含文件名(带/不带.md后缀)作为key
    返回: {alias: file_path_str}
    """
    alias_map = {}
    prompts_dir = PLUGIN_DIR / "prompts"
    
    if not prompts_dir.exists():
        logger.warning(f"prompts 目录不存在: {prompts_dir}")
        return alias_map
    
    md_files = sorted(prompts_dir.glob("*.md"))
    for md_file in md_files:
        try:
            file_path_str = str(md_file)
            file_name_with_ext = md_file.name
            file_name_without_ext = md_file.stem

            # 注册文件名 (带和不带后缀)
            alias_map[file_name_with_ext] = file_path_str
            alias_map[file_name_without_ext] = file_path_str
            logger.info(f"注册文件名: '{file_name_with_ext}' & '{file_name_without_ext}' -> {file_name_with_ext}")

            # 解析并注册 YAML front matter 中的 alias
            front_matter, _ = parse_yaml_front_matter(md_file)
            if front_matter and "alias" in front_matter:
                aliases = front_matter["alias"]
                if isinstance(aliases, list):
                    for alias in aliases:
                        if isinstance(alias, str):
                            alias_map[alias] = file_path_str
                            logger.info(f"注册 YAML alias: '{alias}' -> {md_file.name}")
        except Exception as e:
            logger.opt(exception=True).error(f"处理文件 {md_file.name} 时出错: {e}")
    
    logger.success(f"共加载 {len(alias_map)} 个 prompt alias (包含文件名)")
    return alias_map


def load_system_prompt() -> str:
    """加载系统 prompt"""
    try:
        with open(SYSTEM_PROMPT_JUSTICE_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        # 移除 YAML front matter 后返回
        _, markdown_content = parse_yaml_front_matter(SYSTEM_PROMPT_JUSTICE_PATH)
        return markdown_content if markdown_content else content
    except Exception as e:
        logger.opt(exception=True).error(f"警告: 无法读取 prompt 模板文件: {e}")
        return """你是一个公正的裁判,请客观地评价对话内容。"""


def load_prompt_content(path: Path) -> str:
    """从指定路径加载并解析 prompt 内容"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        # 移除 YAML front matter 后返回
        _, markdown_content = parse_yaml_front_matter(path)
        return markdown_content if markdown_content else content
    except Exception as e:
        logger.opt(exception=True).error(f"警告: 无法读取 prompt 模板文件({path.name}): {e}")
        return """你是一个公正的裁判,请客观地评价对话内容。"""


# 在模块加载时构建 alias 映射
PROMPT_ALIAS_MAP = load_prompt_aliases()
