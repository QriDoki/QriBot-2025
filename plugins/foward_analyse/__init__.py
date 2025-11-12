#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
私聊消息日志插件
监听特定用户的私聊消息并在控制台打印
"""
from nonebot import require, get_driver, logger
from nonebot.adapters.onebot.v11 import Bot, PrivateMessageEvent, GroupMessageEvent, MessageSegment
from openai import OpenAI
import json
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field
import re
from nonebot.params import Command
from typing import Annotated

require("nonebot_plugin_htmlkit")
from nonebot_plugin_htmlkit import md_to_pic, html_to_pic

# 导入 prompts 模块
from .prompts import (
    PLUGIN_DIR,
    PROMPT_ALIAS_MAP,
    SYSTEM_PROMPT_ANA_PATH,
    EMPTY_CSS_PATH,
    parse_yaml_front_matter,
    load_prompt_aliases,
    load_prompt_content
)

# 导入 cmd_ana 模块
from .cmd_ana import commandToPromptFilePath, create_forward_ana_cmd

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


# 创建命令处理器,响应白名单用户的私聊和群聊消息
forward_ana_cmd = create_forward_ana_cmd(check_user_permission, plugin_config)


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
            from . import prompts
            prompts.PROMPT_ALIAS_MAP = load_prompt_aliases()

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
        prompt_match = re.search(r"--prompt=([\w\-\.]+)", message_text)
        custom_prompt_path = None
        if prompt_match:
            prompt_name = prompt_match.group(1)
            # 从 prompts 模块的 alias map 中查找路径
            from . import prompts
            if prompt_name in prompts.PROMPT_ALIAS_MAP:
                custom_prompt_path = Path(prompts.PROMPT_ALIAS_MAP[prompt_name])
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
