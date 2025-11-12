#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
私聊消息日志插件
监听特定用户的私聊消息并在控制台打印
"""
from xmlrpc.client import SYSTEM_ERROR

from nonebot import on_message, on_command, require, get_driver, logger
from nonebot.adapters.onebot.v11 import Bot, PrivateMessageEvent, GroupMessageEvent, MessageSegment
from nonebot.adapters.onebot.v11.event import Sender
from nonebot.rule import Rule
from openai import OpenAI
import json
from pathlib import Path
from typing import Optional, Dict
from pydantic import BaseModel, Field
import re
import yaml
from nonebot.params import CommandStart, Command, RawCommand
from typing import Annotated

require("nonebot_plugin_htmlkit")
from nonebot_plugin_htmlkit import md_to_pic, html_to_pic

# 定义插件配置模型
class PluginConfig(BaseModel):
    """插件配置"""
    ana_user_id_allow_list: list[int] = Field(
        default_factory=list,
        alias="ANA_USER_ID_ALLOW_LIST",
        description="允许使用正义裁判功能的用户ID白名单"
    )
    openai_api_key: Optional[str] = Field(
        default=None,
        alias="OPENAI_API_KEY",
        description="OpenAI API Key"
    )
    openai_api_base: Optional[str] = Field(
        default=None,
        alias="OPENAI_API_BASE",
        description="OpenAI API Base URL"
    )
    openai_model: str = Field(
        default="gpt-3.5-turbo",
        alias="OPENAI_MODEL",
        description="OpenAI 模型名称"
    )

# 获取插件配置
driver = get_driver()
plugin_config = PluginConfig.model_validate(driver.config.model_dump(), extra="allow", by_alias=False, by_name=True)

# 使用配置中的白名单
ANA_USER_ID_ALLOW_LIST = plugin_config.ana_user_id_allow_list

# 读取 prompt 模板
PLUGIN_DIR = Path(__file__).parent
SYSTEM_PROMPT_JUSTICE_PATH = PLUGIN_DIR / "prompts" / "alignment_prompt.md"
SYSTEM_PROMPT_ANA_PATH = PLUGIN_DIR / "prompts" / "alignment_prompt.md"
EMPTY_CSS_PATH = PLUGIN_DIR / "empty.css"

# 全局变量：alias -> 文件路径的映射字典
PROMPT_ALIAS_MAP: Dict[str, str] = {}

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
    加载所有 prompt 文件，构建 alias -> 文件路径的映射字典
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

# 在模块加载时构建 alias 映射
PROMPT_ALIAS_MAP = load_prompt_aliases()



def check_user_permission(event) -> bool:
    """检查用户是否在白名单中"""
    # 同时支持私聊和群聊
    if isinstance(event, (PrivateMessageEvent, GroupMessageEvent)):
        user_id = event.user_id
        # 如果白名单为空,拒绝所有请求
        if not ANA_USER_ID_ALLOW_LIST:
            return False
        return user_id in ANA_USER_ID_ALLOW_LIST
    return False

triggers = {
    "justice": {
        "promptFilePath": SYSTEM_PROMPT_JUSTICE_PATH,
        "aliases": ["蜻蜓队长", "正义", "天降正义", "裁判"]
    },
    "ana": {
        "promptFilePath": SYSTEM_PROMPT_ANA_PATH,
        "aliases": ["analyse", "分析", "怎么说", "如何评价"]
    }
}

# 从 triggers 字典中收集所有别名
def get_all_aliases() -> set[str]:
    """从 triggers 字典中收集所有别名(包括 key 和 aliases)"""
    all_aliases = set()
    for trigger_key, trigger_config in triggers.items():
        all_aliases.add(trigger_key)  # 添加 key
        all_aliases.update(trigger_config["aliases"])  # 添加 aliases
    return all_aliases

# 从 triggers 生成命令到 prompt 文件路径的映射
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

commandToPromptFilePath = build_command_to_prompt_map()

# 创建命令处理器,响应白名单用户的私聊和群聊消息
forward_ana_cmd = on_command(
    "ana",
    aliases=get_all_aliases(),
    rule=Rule(check_user_permission),
    priority=1,
    block=False  # 不阻断消息传递,让其他插件也能处理
)


@forward_ana_cmd.handle()
async def handle_ana_command(bot: Bot, event, command: Annotated[tuple[str, ...], Command()]):
    """处理正义裁判命令"""
    logger.info("=" * 50)

    trigger = command[0]

    user_id = event.user_id
    message_id = event.message_id
    
    # 判断消息来源
    is_group = isinstance(event, GroupMessageEvent)
    if is_group:
        logger.info(f"收到来自群 {event.group_id} 中用户 {user_id} 的ana请求")
    else:
        logger.info(f"收到来自用户 {user_id} 的ana请求")
    
    logger.info(f"消息ID: {message_id}")
    
    try:
        # 检查是否包含 --prompts 或 --prompt=xxx 参数
        message_text = event.get_plaintext().strip()
        if "--prompts" in message_text:
            logger.info("检测到 --prompts 参数，刷新并读取所有 prompt 文件")
            
            # 刷新 alias 映射
            global PROMPT_ALIAS_MAP
            PROMPT_ALIAS_MAP = load_prompt_aliases()

            try:
                prompts_dir = PLUGIN_DIR / "prompts"
                md_files = sorted(prompts_dir.glob("*.md"))
                if not md_files:
                    message = MessageSegment.reply(event.message_id)
                    message += MessageSegment.text("未找到任何 prompt 文件")
                    await forward_ana_cmd.send(message=message)
                    return
                combined_md = []
                
                for md_file in md_files:
                    try:
                        with open(md_file, "r", encoding="utf-8") as f:
                            content = f.read()
                        
                        # 为每个文件添加标题、别名和内容
                        combined_md.append(f"# {md_file.name}\n\n{content}")
                    except Exception as e:
                        logger.opt(exception=True).error(f"读取文件 {md_file.name} 失败: {e}")
                        combined_md.append(f"## {md_file.name}\n\n读取失败: {e}")
                final_md = "\n\n---\n\n".join(combined_md)
                try:
                    pic = await md_to_pic(md=final_md, max_width=900, dpi=220, allow_refit=False, css_path=EMPTY_CSS_PATH)
                    message = MessageSegment.reply(event.message_id)
                    message += MessageSegment.text(f"找到 {len(md_files)} 个 prompt 文件:\n")
                    message += MessageSegment.image(pic)
                    await forward_ana_cmd.send(message=message)
                except Exception as pic_error:
                    logger.opt(exception=True).error(f"生成图片时发生错误: {pic_error}")
                    message = MessageSegment.reply(event.message_id)
                    message += MessageSegment.text(f"找到 {len(md_files)} 个 prompt 文件，但生成图片失败\n\n{final_md[:500]}...")
                    await forward_ana_cmd.send(message=message)
            except Exception as e:
                logger.opt(exception=True).error(f"处理 --prompts 参数时发生错误: {e}")
                message = MessageSegment.reply(event.message_id)
                message += MessageSegment.text(f"处理失败: {e}")
                await forward_ana_cmd.send(message=message)
            logger.info("=" * 50)
            return

        # 检查 --test-html 参数
        if "--test-html" in message_text:
            logger.info("检测到 --test-html 参数，读取并转换 test.html")
            try:
                test_html_path = PLUGIN_DIR / "prompts" / "test.html"
                if not test_html_path.exists():
                    message = MessageSegment.reply(event.message_id)
                    message += MessageSegment.text("未找到 test.html 文件")
                    await forward_ana_cmd.send(message=message)
                    return
                
                # 读取 HTML 文件内容
                with open(test_html_path, "r", encoding="utf-8") as f:
                    html_content = f.read()
                
                # 将 HTML 转换为图片
                try:
                    pic220 = await html_to_pic(html=html_content, max_width=1800, dpi=220)
                    pic96 = await html_to_pic(html=html_content, max_width=800)
                    message = MessageSegment.reply(event.message_id)
                    message += MessageSegment.text("test.html 渲染结果:\n")
                    message += MessageSegment.image(pic220)
                    message += MessageSegment.image(pic96)
                    await forward_ana_cmd.send(message=message)
                except Exception as pic_error:
                    logger.opt(exception=True).error(f"生成图片时发生错误: {pic_error}")
                    message = MessageSegment.reply(event.message_id)
                    message += MessageSegment.text(f"生成图片失败: {pic_error}")
                    await forward_ana_cmd.send(message=message)
            except Exception as e:
                logger.opt(exception=True).error(f"处理 --test-html 参数时发生错误: {e}")
                message = MessageSegment.reply(event.message_id)
                message += MessageSegment.text(f"处理失败: {e}")
                await forward_ana_cmd.send(message=message)
            logger.info("=" * 50)
            return

        # 检查 --prompt=xxx 参数
        import re
        prompt_match = re.search(r"--prompt=([\w\-\.]+)", message_text)
        custom_prompt_path = None
        if prompt_match:
            prompt_name = prompt_match.group(1)
            # 从 alias map 中查找路径
            if prompt_name in PROMPT_ALIAS_MAP:
                custom_prompt_path = Path(PROMPT_ALIAS_MAP[prompt_name])
                logger.info(f"通过 alias '{prompt_name}' 找到 prompt 文件: {custom_prompt_path.name}")
            else:
                # 兼容旧的逻辑,自动补全 .md 后缀
                if not prompt_name.endswith(".md"):
                    prompt_name += ".md"
                custom_prompt_path = PLUGIN_DIR / "prompts" / prompt_name
                logger.warning(f"在 alias map 中未找到 '{prompt_name}', 尝试直接拼接路径: {custom_prompt_path}")

        if not (hasattr(event, 'reply') and event.reply
                and len(event.reply.message) > 0 and event.reply.message[0].type == "forward"):
            message = MessageSegment.reply(event.message_id)
            message += MessageSegment.text("请回复一条合并转发的消息\n如果超过100条 可以嵌套合并转发")
            await forward_ana_cmd.send(message=message)
            return

        # --- 决定并加载 system prompt ---
        # 优先使用 --prompt 参数指定的 prompt
        # 否则根据触发命令从 commandToPromptFilePath 中获取对应的 prompt
        prompt_to_use_path = None
        if custom_prompt_path and custom_prompt_path.exists():
            prompt_to_use_path = custom_prompt_path
        elif trigger in commandToPromptFilePath:
            prompt_to_use_path = commandToPromptFilePath[trigger]
        else:
            # 兜底使用默认 prompt
            prompt_to_use_path = SYSTEM_PROMPT_ANA_PATH
            logger.warning(f"触发命令 '{trigger}' 未在 commandToPromptFilePath 中找到,使用默认 prompt")

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

        system_prompt = load_prompt_content(prompt_to_use_path)
        prompt_filename = prompt_to_use_path.name
        logger.info(f"使用 prompt 文件: {prompt_filename}")

        # 先发送提示消息和系统提示词图片
        try:
            # 将系统提示词转换为图片
            prompt_pic = await md_to_pic(md=system_prompt, max_width=900, dpi=220, allow_refit=False, css_path=EMPTY_CSS_PATH)
            message = MessageSegment.reply(event.message_id)
            message += MessageSegment.text(f"LLM中, 请稍候\n(如果生成失败也会有回复)\n\n使用的系统提示词 ({prompt_filename}):\n")
            message += MessageSegment.image(prompt_pic)
            await forward_ana_cmd.send(message=message)
        except Exception as prompt_pic_error:
            logger.opt(exception=True).error(f"生成系统提示词图片时发生错误: {prompt_pic_error}")
            # 如果图片生成失败,发送纯文本提示
            message = MessageSegment.reply(event.message_id)
            message += MessageSegment.text(f"LLM中, 请稍候\n(如果生成失败也会有回复)\n使用prompt: {prompt_filename}")
            await forward_ana_cmd.send(message=message)

        forward_content = event.reply.message[0].data.get("content")
        replyCombineForwardMessages = messageToSimple(forward_content)

        # 使用换行符拼接并打印
        usersChatText = json.dumps(replyCombineForwardMessages, ensure_ascii=False)
        # 调用 LLM 获取评价
        try:
            client = OpenAI(
                api_key=plugin_config.openai_api_key,
                base_url=plugin_config.openai_api_base
            )

            response = client.chat.completions.create(
                model=plugin_config.openai_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": usersChatText}
                ]
            )

            llm_result = response.choices[0].message.content
            logger.success(f"LLM 评价结果: {llm_result}")

            # 生成横屏和竖屏两种格式的图片
            try:
                # 横屏格式 - 适合横屏阅读 (宽度较大)
                # horizontal_pic = await md_to_pic(md=llm_result, max_width=1800, dpi=220, allow_refit=False, css_path=EMPTY_CSS_PATH)

                # 竖屏格式 - 适合竖屏阅读 (宽度较小)
                vertical_pic = await md_to_pic(md=llm_result, max_width=900, dpi=220, allow_refit=False, css_path=EMPTY_CSS_PATH)

                # 构建消息
                message = MessageSegment.reply(event.message_id)
                # message += MessageSegment.text("适合横屏阅读:\n")
                # message += MessageSegment.image(horizontal_pic)
                # message += MessageSegment.text("\n适合竖屏阅读:\n")
                message += MessageSegment.text(f"\n使用prompt文件: {prompt_filename}\n")
                message += MessageSegment.image(vertical_pic)

                # 根据消息来源发送结果,并回复触发命令的消息
                await forward_ana_cmd.send(message=message)
            except Exception as pic_error:
                logger.opt(exception=True).error(f"生成图片时发生错误: {pic_error}")
                # 如果图片生成失败,发送纯文本
                message = MessageSegment.reply(event.message_id)
                message += MessageSegment.text(llm_result)
                message += MessageSegment.text(f"\n(prompt: {prompt_filename})")
                await forward_ana_cmd.send(message=message)

        except Exception as llm_error:
            logger.opt(exception=True).error(f"调用 LLM 时发生错误: {llm_error}")
            error_msg = MessageSegment.reply(event.message_id)
            error_msg += MessageSegment.text(f"调用 LLM 时发生错误!")
            await forward_ana_cmd.send(message=error_msg)
    except Exception as e:
        logger.opt(exception=True).error(f"处理消息时发生错误: {e}")
    finally:
        logger.info("=" * 50)

# def extractListMessage(messages: list) -> list:
#     res = []
#
#     for i in messages:
#         upperSender = i["sender"]["nickname"]
#         for message in i["message"]:
#             messageType = message["type"]
#             if messageType == "forward":
#                 res.extend(extractListMessage(message["data"]["content"]))
#             if messageType == "text":
#                 res.append(f"{upperSender}: {message['data']['text']}")
#     return res

def messageToSimple(messages: list) -> list:
    res = []

    for i in messages:
        upperSender = i["sender"]["nickname"]
        for message in i["message"]:
            messageType = message["type"]
            if messageType == "forward":
                res.append([upperSender, "合并转发", messageToSimple(message["data"]["content"])])
            if messageType == "text":
                res.append(f"{upperSender}: {message['data']['text']}")
    return res


# # 创建消息处理器，只响应特定用户的私聊消息
# private_msg_logger = on_message(
#     rule=Rule(check_user_permission),
#     priority=1,
#     block=False  # 不阻断消息传递，让其他插件也能处理
# )
#
# @private_msg_logger.handle()
# async def handle_private_message(bot: Bot, event: PrivateMessageEvent):
#     messagePlain = await extractMessage(bot, event, event.message)
#     """处理私聊消息"""
#     print("=" * 50)
#     user_id = event.user_id
#     message_text = event.get_plaintext()
#     message_id = event.message_id
#
#     print(f"[私聊消息] 来自用户 {user_id} 的消息:")
#     print(f"消息ID: {message_id}")
#     print(f"消息内容: {message_text}")
#     print(f"完整消息: {event.message}")
#     print("=" * 50)
#
#
# async def extractMessage(bot: Bot, event: PrivateMessageEvent | GroupMessageEvent, messages: [MessageSegment]):
#     res = []
#     for msg in messages:
#         messageType = msg.type if hasattr(msg, 'type') else msg["type"]
#         if messageType == "forward":
#             forwardMsg = await bot.get_forward_msg(id=msg.data["id"])
#             res.extend(extractListMessage(forwardMsg["messages"]))
#         if messageType == "text":
#             res.append(event.sender.nickname + ": " + msg.data["text"])
#     return res
