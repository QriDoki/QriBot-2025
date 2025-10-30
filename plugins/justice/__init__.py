#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
私聊消息日志插件
监听特定用户的私聊消息并在控制台打印
"""
from nonebot import on_message, on_command, require, get_driver
from nonebot.adapters.onebot.v11 import Bot, PrivateMessageEvent, GroupMessageEvent, MessageSegment
from nonebot.adapters.onebot.v11.event import Sender
from nonebot.rule import Rule
from openai import OpenAI
import json
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field

require("nonebot_plugin_htmlkit")
from nonebot_plugin_htmlkit import md_to_pic, html_to_pic

# 定义插件配置模型
class PluginConfig(BaseModel):
    """插件配置"""
    justice_user_id_allow_list: list[int] = Field(
        default_factory=list,
        alias="JUSTICE_USER_ID_ALLOW_LIST",
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
JUSTICE_USER_ID_ALLOW_LIST = plugin_config.justice_user_id_allow_list

# 读取 prompt 模板
PLUGIN_DIR = Path(__file__).parent
PROMPT_TEMPLATE_PATH = PLUGIN_DIR / "prompts" / "alignment_prompt.md"

def load_system_prompt() -> str:
    """加载系统 prompt"""
    try:
        with open(PROMPT_TEMPLATE_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print(f"警告: 无法读取 prompt 模板文件: {e}")
        return """你是一个公正的裁判,请客观地评价对话内容。"""



def check_user_permission(event) -> bool:
    """检查用户是否在白名单中"""
    # 同时支持私聊和群聊
    if isinstance(event, (PrivateMessageEvent, GroupMessageEvent)):
        user_id = event.user_id
        # 如果白名单为空,拒绝所有请求
        if not JUSTICE_USER_ID_ALLOW_LIST:
            return False
        return user_id in JUSTICE_USER_ID_ALLOW_LIST
    return False


# 创建命令处理器,响应白名单用户的私聊和群聊消息
justice_cmd = on_command(
    "justice",
    aliases={"蜻蜓队长", "正义", "天降正义", "裁判"},
    rule=Rule(check_user_permission),
    priority=1,
    block=False  # 不阻断消息传递,让其他插件也能处理
)


@justice_cmd.handle()
async def handle_justice_command(bot: Bot, event):
    """处理正义裁判命令"""
    print("=" * 50)

    user_id = event.user_id
    message_id = event.message_id
    
    # 判断消息来源
    is_group = isinstance(event, GroupMessageEvent)
    if is_group:
        print(f"收到来自群 {event.group_id} 中用户 {user_id} 的justice请求")
    else:
        print(f"收到来自用户 {user_id} 的justice请求")
    
    print(f"消息ID: {message_id}")
    
    try:
        # 检查是否包含 --prompts 或 --prompt=xxx 参数
        message_text = event.get_plaintext().strip()
        if "--prompts" in message_text:
            print("检测到 --prompts 参数，读取所有 prompt 文件")
            try:
                prompts_dir = PLUGIN_DIR / "prompts"
                md_files = sorted(prompts_dir.glob("*.md"))
                if not md_files:
                    message = MessageSegment.reply(event.message_id)
                    message += MessageSegment.text("未找到任何 prompt 文件")
                    await justice_cmd.send(message=message)
                    return
                combined_md = []
                for md_file in md_files:
                    try:
                        with open(md_file, "r", encoding="utf-8") as f:
                            content = f.read()
                            combined_md.append(f"# {md_file.name}\n\n{content}")
                    except Exception as e:
                        print(f"读取文件 {md_file.name} 失败: {e}")
                        combined_md.append(f"## {md_file.name}\n\n读取失败: {e}")
                final_md = "\n\n---\n\n".join(combined_md)
                try:
                    pic = await md_to_pic(md=final_md, max_width=800)
                    message = MessageSegment.reply(event.message_id)
                    message += MessageSegment.text(f"找到 {len(md_files)} 个 prompt 文件:\n")
                    message += MessageSegment.image(pic)
                    await justice_cmd.send(message=message)
                except Exception as pic_error:
                    print(f"生成图片时发生错误: {pic_error}")
                    message = MessageSegment.reply(event.message_id)
                    message += MessageSegment.text(f"找到 {len(md_files)} 个 prompt 文件，但生成图片失败\n\n{final_md[:500]}...")
                    await justice_cmd.send(message=message)
            except Exception as e:
                print(f"处理 --prompts 参数时发生错误: {e}")
                message = MessageSegment.reply(event.message_id)
                message += MessageSegment.text(f"处理失败: {e}")
                await justice_cmd.send(message=message)
            print("=" * 50)
            return

        # 检查 --test-html 参数
        if "--test-html" in message_text:
            print("检测到 --test-html 参数，读取并转换 test.html")
            try:
                test_html_path = PLUGIN_DIR / "prompts" / "test.html"
                if not test_html_path.exists():
                    message = MessageSegment.reply(event.message_id)
                    message += MessageSegment.text("未找到 test.html 文件")
                    await justice_cmd.send(message=message)
                    return
                
                # 读取 HTML 文件内容
                with open(test_html_path, "r", encoding="utf-8") as f:
                    html_content = f.read()
                
                # 将 HTML 转换为图片
                try:
                    pic96 = await html_to_pic(html=html_content, max_width=800)
                    pic220 = await html_to_pic(html=html_content, max_width=1800, dpi=220)
                    message = MessageSegment.reply(event.message_id)
                    message += MessageSegment.text("test.html 渲染结果:\n")
                    message += MessageSegment.image(pic220)
                    message += MessageSegment.image(pic96)
                    await justice_cmd.send(message=message)
                except Exception as pic_error:
                    print(f"生成图片时发生错误: {pic_error}")
                    message = MessageSegment.reply(event.message_id)
                    message += MessageSegment.text(f"生成图片失败: {pic_error}")
                    await justice_cmd.send(message=message)
            except Exception as e:
                print(f"处理 --test-html 参数时发生错误: {e}")
                message = MessageSegment.reply(event.message_id)
                message += MessageSegment.text(f"处理失败: {e}")
                await justice_cmd.send(message=message)
            print("=" * 50)
            return

        # 检查 --prompt=xxx 参数
        import re
        prompt_match = re.search(r"--prompt=([\w\-\.]+)", message_text)
        custom_prompt_path = None
        if prompt_match:
            prompt_name = prompt_match.group(1)
            # 自动补全 .md 后缀
            if not prompt_name.endswith(".md"):
                prompt_name += ".md"
            custom_prompt_path = PLUGIN_DIR / "prompts" / prompt_name

        if not (hasattr(event, 'reply') and event.reply
                and len(event.reply.message) > 0 and event.reply.message[0].type == "forward"):
            message = MessageSegment.reply(event.message_id)
            message += MessageSegment.text("请回复一条合并转发的消息\n如果超过100条 可以嵌套合并转发")
            await justice_cmd.send(message=message)
            return
        
        # 先发送提示消息
        message = MessageSegment.reply(event.message_id)
        message += MessageSegment.text("LLM中, 请稍候\n(如果生成失败也会有回复)")
        await justice_cmd.send(message=message)

        forward_content = event.reply.message[0].data.get("content")
        replyCombineForwardMessages = extractListMessage(forward_content)

        # 使用换行符拼接并打印
        usersChatText = "\n".join(replyCombineForwardMessages)

        # 加载 system prompt，优先使用 --prompt=xxx 指定的文件
        def load_custom_or_default_prompt():
            if custom_prompt_path and custom_prompt_path.exists():
                try:
                    with open(custom_prompt_path, "r", encoding="utf-8") as f:
                        return f.read()
                except Exception as e:
                    print(f"读取自定义 prompt 失败: {e}")
            # 默认
            return load_system_prompt()

        system_prompt = load_custom_or_default_prompt()

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
            print(f"LLM 评价结果: {llm_result}")

            # 生成横屏和竖屏两种格式的图片
            try:
                # 横屏格式 - 适合横屏阅读 (宽度较大)
                horizontal_pic = await md_to_pic(md=llm_result, max_width=1800, dpi=220)

                # 竖屏格式 - 适合竖屏阅读 (宽度较小)
                vertical_pic = await md_to_pic(md=llm_result, max_width=900, dpi=220)

                # 构建消息
                message = MessageSegment.reply(event.message_id)
                message += MessageSegment.text("适合横屏阅读:\n")
                message += MessageSegment.image(horizontal_pic)
                message += MessageSegment.text("\n适合竖屏阅读:\n")
                message += MessageSegment.image(vertical_pic)
                message += MessageSegment.text("\n")

                # 根据消息来源发送结果,并回复触发命令的消息
                await justice_cmd.send(message=message)
            except Exception as pic_error:
                print(f"生成图片时发生错误: {pic_error}")
                # 如果图片生成失败,发送纯文本
                message = MessageSegment.reply(event.message_id)
                message += MessageSegment.text(llm_result)
                await justice_cmd.send(message=message)

        except Exception as llm_error:
            print(f"调用 LLM 时发生错误: {llm_error}")
            error_msg = MessageSegment.reply(event.message_id)
            error_msg += MessageSegment.text(f"调用 LLM 时发生错误!")
            await justice_cmd.send(message=error_msg)
    except Exception as e:
        print(f"处理消息时发生错误: {e}")
    finally:
        print("=" * 50)

def extractListMessage(messages: list) -> list:
    res = []

    for i in messages:

        upperSender = i["sender"]["nickname"]
        for message in i["message"]:
            messageType = message["type"]
            if messageType == "forward":
                res.extend(extractListMessage(message["data"]["content"]))
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
