# 导入必要的模块
from telegram.ext import Application, MessageHandler, filters
import schedule
import time
import re
import os
import asyncio
from datetime import datetime, timezone, timedelta
import pytz
import random
import string
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('/var/log/winpay_bot.log'),  # Render 可访问的日志路径
        logging.StreamHandler()  # 同时输出到终端
    ]
)
logger = logging.getLogger(__name__)

# 定义 Bot Token（从环境变量获取）
BOT_TOKEN = os.getenv("BOT_TOKEN", "7908773608:AAFFqLmGkJ9zbsuymQTFzJxy5IyeN1E9M-U")

# 定义全局变量
initial_admin_username = "WinPay06_Thomason"  # 初始最高权限管理员用户名
operators = {}  # {chat_id: {username: True}}，每个群组独立操作员列表
transactions = {}  # {chat_id: [transaction_list]}，每个群组独立记账
user_history = {}  # {chat_id: {user_id: {"username": str, "first_name": str}}}，记录成员历史
exchange_rates = {}  # {chat_id: {"deposit": float, "withdraw": float, "deposit_fee": float, "withdraw_fee": float}}，每个群组独立汇率和费率
address_verify_count = {}  # {chat_id: {"count": int, "last_user": str}}，记录地址验证次数和上次发送人
is_accounting_enabled = {}  # {chat_id: bool}，控制记账状态，默认为 True
team_groups = {}  # {队名: [群ID列表]}
scheduled_tasks = {}  # {任务ID: {"team": 队名, "template": 模板名, "time": 任务时间}}
last_file_id = {}  # {chat_id: 文件ID}
templates = {}  # {模板名: {"message": 广告文, "file_id": 文件ID}}

# 设置日志任务
def setup_schedule():
    schedule.every().day.at("00:00").do(lambda: asyncio.run(job()))

# 定义日志功能
async def job():
    logger.info(f"执行日志任务 {time.ctime()}")

# 账单处理函数
async def handle_bill(update, context):
    chat_id = str(update.message.chat_id)
    if chat_id not in transactions:
        transactions[chat_id] = []
    recent_transactions = transactions[chat_id][-6:] if len(transactions[chat_id]) >= 6 else transactions[chat_id]
    bill = "当前账单\n"
    deposit_count = sum(1 for t in recent_transactions if t.startswith("入款"))
    withdraw_count = sum(1 for t in recent_transactions if t.startswith("下发"))

    # 获取群组特定汇率和费率
    exchange_rate_deposit = exchange_rates.get(chat_id, {"deposit": 1.0})["deposit"]
    deposit_fee_rate = exchange_rates.get(chat_id, {"deposit_fee": 0.0})["deposit_fee"]
    exchange_rate_withdraw = exchange_rates.get(chat_id, {"withdraw": 1.0})["withdraw"]
    withdraw_fee_rate = exchange_rates.get(chat_id, {"withdraw_fee": 0.0})["withdraw_fee"]

    # 入款部分
    if deposit_count > 0:
        bill += f"入款（{deposit_count}笔）\n"
        for t in reversed([t for t in recent_transactions if t.startswith("入款")]):
            parts = t.split(" -> ")
            timestamp = parts[0].split()[2]
            operator = parts[1].split(" (")[1].rstrip(")")
            if "u" in parts[0]:
                amount = float(parts[0].split()[1].rstrip('u'))
                bill += f"{timestamp}  {format_amount(amount)}u ({operator})\n"
            else:
                amount = float(parts[0].split()[1])
                adjusted = float(parts[1].split()[0].rstrip('u'))
                effective_rate = 1 - deposit_fee_rate
                bill += f"{timestamp}  {format_amount(amount)}*{effective_rate:.2f}/{format_exchange_rate(exchange_rate_deposit)}={format_amount(adjusted)}u ({operator})\n"

    # 出款部分
    if withdraw_count > 0:
        if deposit_count > 0:  # 若有入款，添加空行分隔
            bill += "\n"
        bill += f"出款（{withdraw_count}笔）\n"
        for t in reversed([t for t in recent_transactions if t.startswith("下发")]):
            parts = t.split(" -> ")
            timestamp = parts[0].split()[2]
            operator = parts[1].split(" (")[1].rstrip(")")
            if "u" in parts[0]:
                amount = float(parts[0].split()[1].rstrip('u'))
                bill += f"{timestamp}  {format_amount(amount)}u ({operator})\n"
            else:
                amount = float(parts[0].split()[1])
                adjusted = float(parts[1].split()[0].rstrip('u'))
                effective_rate = 1 + withdraw_fee_rate
                bill += f"{timestamp}  {format_amount(amount)}*{effective_rate:.2f}/{format_exchange_rate(exchange_rate_withdraw)}={format_amount(adjusted)}u ({operator})\n"

    # 统计信息
    if deposit_count > 0 or withdraw_count > 0:  # 只有有交易时才显示统计
        if deposit_count > 0 or withdraw_count > 0:  # 确保有统计内容前加空行
            bill += "\n"
        # 仅在有入款时显示入款相关统计
        if deposit_count > 0:
            bill += f"入款汇率：{format_exchange_rate(exchange_rate_deposit)}  |  费率：{int(deposit_fee_rate*100)}%\n"
        # 仅在有出款时显示出款相关统计
        if withdraw_count > 0:
            bill += f"出款汇率：{format_exchange_rate(exchange_rate_withdraw)}  |  费率：{int(withdraw_fee_rate*100)}%\n"
        if deposit_count > 0 or withdraw_count > 0:  # 确保统计分段
            bill += "\n"
        # 总金额统计
        total_deposit = sum(float(t.split(" -> ")[0].split()[1].rstrip('u')) for t in transactions[chat_id] if t.startswith("入款"))
        total_deposit_adjusted = sum(float(t.split(" -> ")[1].split()[0].rstrip('u')) for t in transactions[chat_id] if t.startswith("入款"))
        total_withdraw = sum(float(t.split(" -> ")[0].split()[1].rstrip('u')) for t in transactions[chat_id] if t.startswith("下发"))
        total_withdraw_adjusted = sum(float(t.split(" -> ")[1].split()[0].rstrip('u')) for t in transactions[chat_id] if t.startswith("下发"))
        balance = total_deposit_adjusted - total_withdraw_adjusted
        if deposit_count > 0:
            bill += f"总入款：{format_amount(total_deposit)}  |  {format_amount(total_deposit_adjusted)}u\n"
        if withdraw_count > 0:
            bill += f"总出款：{format_amount(total_withdraw)}  |  {format_amount(total_withdraw_adjusted)}u\n"
        bill += f"总余额：{format_amount(balance)}u"

    await update.message.reply_text(bill if transactions[chat_id] else "无交易记录")

# 格式化金额函数
def format_amount(amount):
    formatted = f"{amount:.2f}"
    if formatted.endswith(".00"):
        return str(int(amount))
    return formatted

# 格式化汇率函数
def format_exchange_rate(rate):
    formatted = f"{rate:.3f}"
    if formatted.endswith("0"):
        return f"{rate:.2f}"
    return formatted

# 欢迎新成员
async def welcome_new_member(update, context):
    chat_id = str(update.message.chat_id)
    chat_title = update.message.chat.title or "未知群组"
    if chat_id not in user_history:
        user_history[chat_id] = {}
    if update.message and update.message.new_chat_members:
        for member in update.message.new_chat_members:
            user_id = str(member.id)
            username = member.username or "未知用户"
            first_name = member.first_name.strip() if member.first_name else None
            user_history[chat_id][user_id] = {"username": username, "first_name": first_name}
            nickname = first_name or username or "新朋友"
            logger.info(f"新人加入群组 '{chat_title}' (ID: {chat_id}), 用户: @{username}, 昵称: {nickname}")
            await update.message.reply_text(f"欢迎 {nickname} 来到本群")

# 群发执行函数
async def send_broadcast(context, task):
    team_name = task["team"]
    template_name = task["template"]
    if team_name in team_groups and template_name in templates:
        template = templates[template_name]
        for group_id in team_groups[team_name]:
            try:
                if template["file_id"]:
                    await context.bot.send_animation(chat_id=group_id, animation=template["file_id"], caption=template["message"])
                else:
                    await context.bot.send_message(chat_id=group_id, text=template["message"])
                logger.info(f"已发送群发至群组 ID: {group_id}")
            except Exception as e:
                logger.error(f"发送群发至群组 ID: {group_id} 失败: {e}")

# 处理图片消息
async def handle_photo(update, context):
    chat_id = str(update.message.chat_id)
    chat_type = update.message.chat.type
    chat_title = update.message.chat.title or "私聊"
    username = update.message.from_user.username or "未知用户"
    logger.info(f"收到图片消息 从{'群组' if chat_type != 'private' else '私聊'} '{chat_title}' (ID: {chat_id}), 用户: @{username}")
    if chat_type == "private":
        file_id = update.message.photo[-1].file_id
        last_file_id[chat_id] = file_id
        await update.message.reply_text(f"图片文件 ID: {file_id}")

# 处理动画消息（动图）
async def handle_animation(update, context):
    chat_id = str(update.message.chat_id)
    chat_type = update.message.chat.type
    chat_title = update.message.chat.title or "私聊"
    username = update.message.from_user.username or "未知用户"
    logger.info(f"收到动画消息 从{'群组' if chat_type != 'private' else '私聊'} '{chat_title}' (ID: {chat_id}), 用户: @{username}")
    if chat_type == "private":
        file_id = update.message.animation.file_id
        last_file_id[chat_id] = file_id
        await update.message.reply_text(f"动图文件 ID: {file_id}")

# 处理视频消息
async def handle_video(update, context):
    chat_id = str(update.message.chat_id)
    chat_type = update.message.chat.type
    chat_title = update.message.chat.title or "私聊"
    username = update.message.from_user.username or "未知用户"
    logger.info(f"收到视频消息 从{'群组' if chat_type != 'private' else '私聊'} '{chat_title}' (ID: {chat_id}), 用户: @{username}")
    if chat_type == "private":
        file_id = update.message.video.file_id
        last_file_id[chat_id] = file_id
        await update.message.reply_text(f"视频文件 ID: {file_id}")

# 处理所有文本消息
async def handle_text(update, context):
    global operators, transactions, user_history, address_verify_count, is_accounting_enabled, exchange_rates, team_groups, scheduled_tasks, last_file_id, templates
    message_text = update.message.text.strip()
    chat_id = str(update.message.chat_id)
    user_id = str(update.message.from_user.id)
    username = update.message.from_user.username or "未知用户"
    first_name = update.message.from_user.first_name.strip() if update.message.from_user.first_name else None
    operator_name = first_name or "未知用户"
    chat_type = update.message.chat.type
    chat_title = update.message.chat.title or "私聊"
    logger.info(f"收到消息: '{message_text}' 从{'群组' if chat_type != 'private' else '私聊'} '{chat_title}' (ID: {chat_id}), 用户: @{username}")

    if chat_id not in operators:
        operators[chat_id] = {initial_admin_username: True}
    if chat_id not in transactions:
        transactions[chat_id] = []
    if chat_id not in user_history:
        user_history[chat_id] = {}
    if chat_id not in address_verify_count:
        address_verify_count[chat_id] = {"count": 0, "last_user": None}
    if chat_id not in is_accounting_enabled:
        is_accounting_enabled[chat_id] = True  # 默认启用记账
    if chat_id not in last_file_id:
        last_file_id[chat_id] = None
    if chat_id not in exchange_rates:
        exchange_rates[chat_id] = {"deposit": 1.0, "withdraw": 1.0, "deposit_fee": 0.0, "withdraw_fee": 0.0}

    # 更新或记录用户历史
    if user_id not in user_history[chat_id]:
        user_history[chat_id][user_id] = {"username": username, "first_name": first_name}
    else:
        old_data = user_history[chat_id][user_id]
        old_username = old_data["username"]
        old_first_name = old_data["first_name"]
        if username and username != old_username and first_name == old_first_name:
            await update.message.reply_text(
                f"⚠️警告⚠️{first_name} 用户名不一致\n之前用户名@{old_username}\n现在用户名@{username}\n请注意查证‼️"
            )
            logger.warning(f"用户名变更警告: {first_name}, 之前 @{old_username}, 现在 @{username}, 在{'群组' if chat_type != 'private' else '私聊'} '{chat_title}' (ID: {chat_id})")
        elif first_name and first_name != old_first_name and username == old_username:
            await update.message.reply_text(
                f"⚠️警告⚠️@{username} 昵称不一致\n之前昵称{old_first_name}\n现在昵称{first_name}\n请注意查证‼️"
            )
            logger.warning(f"昵称变更警告: @{username}, 之前 {old_first_name}, 现在 {first_name}, 在{'群组' if chat_type != 'private' else '私聊'} '{chat_title}' (ID: {chat_id})")
        user_history[chat_id][user_id] = {"username": username, "first_name": first_name}

    # 记账功能
    if message_text == "开始":
        if username and username in operators.get(chat_id, {}):
            logger.info(f"匹配到 '开始' 指令, 在{'群组' if chat_type != 'private' else '私聊'} '{chat_title}' (ID: {chat_id})")
            transactions[chat_id].clear()  # 清空当前账单，重新开始记账
            is_accounting_enabled[chat_id] = True  # 确保启用记账
            await update.message.reply_text("欢迎使用winpay小秘书，我将全天为你服务")

    elif message_text == "停止记账":
        if username and username in operators.get(chat_id, {}):
            logger.info(f"匹配到 '停止记账' 指令, 在{'群组' if chat_type != 'private' else '私聊'} '{chat_title}' (ID: {chat_id})")
            is_accounting_enabled[chat_id] = False  # 暂停记账功能
            await update.message.reply_text("已暂停记账功能")

    elif message_text == "恢复记账":
        if username and username in operators.get(chat_id, {}):
            logger.info(f"匹配到 '恢复记账' 指令, 在{'群组' if chat_type != 'private' else '私聊'} '{chat_title}' (ID: {chat_id})")
            is_accounting_enabled[chat_id] = True  # 恢复记账功能
            await update.message.reply_text("记账功能已恢复")

    elif message_text == "说明":
        if username and username in operators.get(chat_id, {}) and is_accounting_enabled.get(chat_id, True):
            logger.info(f"匹配到 '说明' 指令, 在{'群组' if chat_type != 'private' else '私聊'} '{chat_title}' (ID: {chat_id})")
            help_text = """
可用指令：
开始使用：开始
记入入款：入款 或 +100 或 +100u/U
记入下发：下发 100 或 下发 50u/U
设置操作员：设置操作员 @用户名
删除操作员：删除操作员 @用户名
设置入款汇率
设置入款费率
设置下发汇率
设置下发费率
查看交易记录：账单 或 +0 
撤销交易记录 - 回复入款或下发消息+删除
清空账单：删除账单
查看操作员：操作员列表
            """
            await update.message.reply_text(help_text)

    elif (message_text.startswith("入款") or message_text.startswith("+")) and message_text != "+0":
        if username and username in operators.get(chat_id, {}) and is_accounting_enabled.get(chat_id, True):
            logger.info(f"匹配到 '入款' 或 '+' 指令，金额: {message_text.replace('入款', '').replace('+', '').strip()}, 在{'群组' if chat_type != 'private' else '私聊'} '{chat_title}' (ID: {chat_id})")
            try:
                amount_str = message_text.replace("入款", "").replace("+", "").strip()
                beijing_tz = pytz.timezone("Asia/Shanghai")
                utc_time = update.message.date.replace(tzinfo=timezone.utc)
                timestamp = utc_time.astimezone(beijing_tz).strftime("%H:%M")
                exchange_rate_deposit = exchange_rates[chat_id]["deposit"]
                deposit_fee_rate = exchange_rates[chat_id]["deposit_fee"]
                if amount_str.lower().endswith('u'):
                    amount = float(amount_str.rstrip('uU'))
                    transaction = f"入款 {format_amount(amount)}u {timestamp} -> {format_amount(amount)}u ({operator_name})"
                elif amount_str.endswith(".0") or amount_str.endswith(".00"):
                    amount = float(amount_str.rstrip('.0').rstrip('.00'))
                    adjusted_amount = amount * (1 - deposit_fee_rate) / exchange_rate_deposit
                    transaction = f"入款 {format_amount(amount)} {timestamp} -> {format_amount(adjusted_amount)}u ({operator_name})"
                else:
                    amount = float(amount_str)
                    adjusted_amount = amount * (1 - deposit_fee_rate) / exchange_rate_deposit
                    transaction = f"入款 {format_amount(amount)} {timestamp} -> {format_amount(adjusted_amount)}u ({operator_name})"
                transactions[chat_id].append(transaction)
                await handle_bill(update, context)
            except ValueError:
                await update.message.reply_text("请输入正确金额，例如：入款1000 或 +1000 或 +100u")

    elif message_text.startswith("下发"):
        if username and username in operators.get(chat_id, {}) and is_accounting_enabled.get(chat_id, True):
            logger.info(f"匹配到 '下发' 指令，金额: {message_text.replace('下发', '').strip()}, 在{'群组' if chat_type != 'private' else '私聊'} '{chat_title}' (ID: {chat_id})")
            try:
                amount_str = message_text.replace("下发", "").strip()
                beijing_tz = pytz.timezone("Asia/Shanghai")
                utc_time = update.message.date.replace(tzinfo=timezone.utc)
                timestamp = utc_time.astimezone(beijing_tz).strftime("%H:%M")
                exchange_rate_withdraw = exchange_rates[chat_id]["withdraw"]
                withdraw_fee_rate = exchange_rates[chat_id]["withdraw_fee"]
                if amount_str.lower().endswith('u'):
                    amount = float(amount_str.rstrip('uU'))
                    transaction = f"下发 {format_amount(amount)}u {timestamp} -> {format_amount(amount)}u ({operator_name})"
                elif amount_str.endswith(".0") or amount_str.endswith(".00"):
                    amount = float(amount_str.rstrip('.0').rstrip('.00'))
                    adjusted_amount = amount * (1 + withdraw_fee_rate) / exchange_rate_withdraw
                    transaction = f"下发 {format_amount(amount)} {timestamp} -> {format_amount(adjusted_amount)}u ({operator_name})"
                else:
                    amount = float(amount_str)
                    adjusted_amount = amount * (1 + withdraw_fee_rate) / exchange_rate_withdraw
                    transaction = f"下发 {format_amount(amount)} {timestamp} -> {format_amount(adjusted_amount)}u ({operator_name})"
                transactions[chat_id].append(transaction)
                await handle_bill(update, context)
            except ValueError:
                await update.message.reply_text("请输入正确金额，例如：下发500 或 下发50u")

    elif message_text.startswith("设置操作员"):
        if username and username in operators.get(chat_id, {}) and is_accounting_enabled.get(chat_id, True):
            logger.info(f"匹配到 '设置操作员' 指令，参数: {message_text.replace('设置操作员', '').strip()}, 在{'群组' if chat_type != 'private' else '私聊'} '{chat_title}' (ID: {chat_id})")
            operator = message_text.replace("设置操作员", "").strip()
            if operator.startswith("@"):
                operator = operator[1:]  # 移除 @ 符号
                if chat_id not in operators:
                    operators[chat_id] = {}
                operators[chat_id][operator] = True
                await update.message.reply_text(f"已将 @{operator} 设置为操作员")
            else:
                await update.message.reply_text("请使用格式：设置操作员 @用户名")

    elif message_text.startswith("删除操作员"):
        if username and username in operators.get(chat_id, {}) and is_accounting_enabled.get(chat_id, True):
            logger.info(f"匹配到 '删除操作员' 指令，参数: {message_text.replace('删除操作员', '').strip()}, 在{'群组' if chat_type != 'private' else '私聊'} '{chat_title}' (ID: {chat_id})")
            operator = message_text.replace("删除操作员", "").strip()
            if operator.startswith("@"):
                operator = operator[1:]  # 移除 @ 符号
                if chat_id in operators and operator in operators[chat_id]:
                    del operators[chat_id][operator]
                    await update.message.reply_text(f"已删除 @{operator} 的操作员权限")
                else:
                    await update.message.reply_text(f"@{operator} 不是操作员")
            else:
                await update.message.reply_text("请使用格式：删除操作员 @用户名")

    elif message_text.startswith("设置入款汇率"):
        if username and username in operators.get(chat_id, {}) and is_accounting_enabled.get(chat_id, True):
            logger.info(f"匹配到 '设置入款汇率' 指令，汇率: {message_text.replace('设置入款汇率', '').strip()}, 在{'群组' if chat_type != 'private' else '私聊'} '{chat_title}' (ID: {chat_id})")
            try:
                rate = float(message_text.replace("设置入款汇率", "").strip())
                exchange_rates[chat_id]["deposit"] = round(rate, 3)
                await update.message.reply_text(f"设置成功入款汇率 {format_exchange_rate(exchange_rates[chat_id]['deposit'])}")
            except ValueError:
                await update.message.reply_text("请输入正确汇率，例如：设置入款汇率0.98")

    elif message_text.startswith("设置入款费率"):
        if username and username in operators.get(chat_id, {}) and is_accounting_enabled.get(chat_id, True):
            logger.info(f"匹配到 '设置入款费率' 指令，费率: {message_text.replace('设置入款费率', '').strip()}, 在{'群组' if chat_type != 'private' else '私聊'} '{chat_title}' (ID: {chat_id})")
            try:
                rate = float(message_text.replace("设置入款费率", "").strip()) / 100
                exchange_rates[chat_id]["deposit_fee"] = rate
                await update.message.reply_text(f"设置成功入款费率 {int(rate*100)}%")
            except ValueError:
                await update.message.reply_text("请输入正确费率，例如：设置入款费率8")

    elif message_text.startswith("设置下发汇率"):
        if username and username in operators.get(chat_id, {}) and is_accounting_enabled.get(chat_id, True):
            logger.info(f"匹配到 '设置下发汇率' 指令，汇率: {message_text.replace('设置下发汇率', '').strip()}, 在{'群组' if chat_type != 'private' else '私聊'} '{chat_title}' (ID: {chat_id})")
            try:
                rate = float(message_text.replace("设置下发汇率", "").strip())
                exchange_rates[chat_id]["withdraw"] = round(rate, 3)
                await update.message.reply_text(f"设置成功下发汇率 {format_exchange_rate(exchange_rates[chat_id]['withdraw'])}")
            except ValueError:
                await update.message.reply_text("请输入正确汇率，例如：设置下发汇率1.25")

    elif message_text.startswith("设置下发费率"):
        if username and username in operators.get(chat_id, {}) and is_accounting_enabled.get(chat_id, True):
            logger.info(f"匹配到 '设置下发费率' 指令，费率: {message_text.replace('设置下发费率', '').strip()}, 在{'群组' if chat_type != 'private' else '私聊'} '{chat_title}' (ID: {chat_id})")
            try:
                rate = float(message_text.replace("设置下发费率", "").strip()) / 100
                exchange_rates[chat_id]["withdraw_fee"] = rate
                await update.message.reply_text(f"设置成功下发费率 {int(rate*100)}%")
            except ValueError:
                await update.message.reply_text("请输入正确费率，例如：设置下发费率8")

    elif message_text == "账单" or message_text == "+0":
        if username and username in operators.get(chat_id, {}) and is_accounting_enabled.get(chat_id, True):
            logger.info(f"匹配到 '账单' 或 '+0' 指令, 在{'群组' if chat_type != 'private' else '私聊'} '{chat_title}' (ID: {chat_id})")
            await handle_bill(update, context)

    elif message_text == "删除":
        if username and username in operators.get(chat_id, {}) and is_accounting_enabled.get(chat_id, True):
            logger.info(f"匹配到 '删除' 指令, 在{'群组' if chat_type != 'private' else '私聊'} '{chat_title}' (ID: {chat_id})")
            if update.message.reply_to_message:
                original_message = update.message.reply_to_message.text.strip()
                logger.info(f"尝试删除，原始消息: '{original_message}', 在{'群组' if chat_type != 'private' else '私聊'} '{chat_title}' (ID: {chat_id})")
                if original_message.startswith("+") and not original_message == "+0":
                    amount_str = original_message.replace("+", "").strip()
                    amount = float(amount_str.rstrip('uU'))
                    has_u = amount_str.lower().endswith('u')
                    for t in transactions[chat_id][:]:
                        if t.startswith("入款"):
                            t_amount = float(t.split(" -> ")[0].split()[1].rstrip('u'))
                            t_has_u = t.split()[1].endswith('u')
                            if t_amount == amount and has_u == t_has_u:
                                transactions[chat_id].remove(t)
                                await update.message.reply_text(f"入款 {format_amount(amount)}{'u' if has_u else ''} 已被撤销")
                                await handle_bill(update, context)  # 自动显示账单
                                return
                elif original_message.startswith("下发"):
                    amount_str = original_message.replace("下发", "").strip()
                    amount = float(amount_str.rstrip('uU'))
                    has_u = amount_str.lower().endswith('u')
                    for t in transactions[chat_id][:]:
                        if t.startswith("下发"):
                            t_amount = float(t.split(" -> ")[0].split()[1].rstrip('u'))
                            t_has_u = t.split()[1].endswith('u')
                            if t_amount == amount and has_u == t_has_u:
                                transactions[chat_id].remove(t)
                                await update.message.reply_text(f"下发 {format_amount(amount)}{'u' if has_u else ''} 已被撤销")
                                await handle_bill(update, context)  # 自动显示账单
                                return
                await update.message.reply_text("无法撤销此消息，请确保回复正确的入款或下发记录")
            else:
                await update.message.reply_text("请回复目标交易相关消息以删除")

    elif message_text == "删除账单":
        if username and username in operators.get(chat_id, {}) and is_accounting_enabled.get(chat_id, True):
            logger.info(f"匹配到 '删除账单' 指令, 在{'群组' if chat_type != 'private' else '私聊'} '{chat_title}' (ID: {chat_id})")
            transactions[chat_id].clear()
            await update.message.reply_text("今日已清账💰，重新开始记账")

    elif message_text == "日切" and username == initial_admin_username:
        if username in operators.get(chat_id, {}) and is_accounting_enabled.get(chat_id, True):
            logger.info(f"匹配到 '日切' 指令, 在{'群组' if chat_type != 'private' else '私聊'} '{chat_title}' (ID: {chat_id})")
            transactions[chat_id].clear()
            await update.message.reply_text("交易记录已清空")

    elif message_text == "操作员列表":
        if username and username in operators.get(chat_id, {}) and is_accounting_enabled.get(chat_id, True):
            logger.info(f"匹配到 '操作员列表' 指令, 在{'群组' if chat_type != 'private' else '私聊'} '{chat_title}' (ID: {chat_id})")
            op_list = ", ".join([f"@{op}" for op in operators.get(chat_id, {})])
            await update.message.reply_text(f"当前操作员列表: {op_list}" if op_list else "当前无操作员")

    elif re.match(r'^[T][a-km-zA-HJ-NP-Z1-9]{33}$', message_text):
        if is_accounting_enabled.get(chat_id, True):
            logger.info(f"匹配到 TRX 地址验证: {message_text}, 在{'群组' if chat_type != 'private' else '私聊'} '{chat_title}' (ID: {chat_id})")
            chat_id = str(update.message.chat_id)
            current_user = f"@{username}" if username else "未知用户"
            address_verify_count[chat_id]["count"] += 1
            last_user = address_verify_count[chat_id]["last_user"] or "无"
            address_verify_count[chat_id]["last_user"] = current_user
            await update.message.reply_text(
                f"{message_text}\n"
                f"验证次数：{address_verify_count[chat_id]['count']}\n"
                f"本次发送人：{current_user}\n"
                f"上次发送人：{last_user}"
            )

    # 群发功能（仅私聊有效）
    if update.message.chat.type == "private":
        # 显示群发说明
        if message_text == "群发说明":
            logger.info(f"匹配到 '群发说明' 指令, 在私聊 (ID: {chat_id})")
            help_text = """
### 群发指令说明

**注意**：此说明仅在私聊中通过指令 `群发说明` 查看，所有群发相关功能仅在私聊中有效，所有操作员均可使用。

1. **获取群 ID 的方式**  
   - 方法：  
     1. 打开 Telegram 应用，进入目标群聊。  
     2. 点击群聊名称进入群组信息页面。  
     3. 点击“添加成员”或“邀请链接”（需要管理员权限），复制群 ID（例如 `-1001234567890`）。  
     4. 在私聊中手动输入群 ID 使用 `编队` 指令。  
   - 注意：群 ID 需为数字格式，例如 `-1001234567890`。

2. **编辑模板**  
   - 指令：`编辑 模板名 广告文`  
   - 功能：创建或更新指定模板名对应的广告文，并自动关联最近在私聊发送的动图、视频或图片文件 ID。  
   - 示例：  
     - 先发送一个 `.gif` 文件，机器人回复文件 ID。  
     - 然后输入 `编辑 模板1 欢迎体验我们的服务！`  
     - 结果：模板 `模板1` 记录广告文“欢迎体验我们的服务！”及相关文件 ID。  
   - 注意：若模板已存在，则覆盖原有内容。

3. **创建群发任务**  
   - 指令：`任务 队名 时间 模板名`  
   - 功能：为指定编队（队名）设置群发任务，使用指定模板的广告文和文件 ID，时间格式为 `HH:MM`（24小时制）。  
   - 示例：`任务 广告队 17:00 模板1`  
   - 结果：机器人生成唯一任务 ID（例如 `12345`），回复“任务已创建，任务 ID: 12345，请回复 `确认 12345` 执行”。  
   - 时间处理：以服务器时间（+07）为准，若时间已过当天自动调整为次日。

4. **确认任务**  
   - 指令：`确认 任务ID`  
   - 功能：确认执行指定任务 ID 对应的群发任务。  
   - 示例：`确认 12345`  
   - 结果：任务按设定时间执行，向编队中的所有群组发送模板内容。

5. **取消任务**  
   - 指令：`任务 队名 -1`  
   - 功能：取消指定队名的待执行任务。  
   - 示例：`任务 广告队 -1`  
   - 结果：若存在对应队名的任务，则取消并回复“任务已取消”。

6. **创建/更新编队**  
   - 指令：`编队 队名 群ID, 群ID`  
   - 功能：创建或更新指定队名对应的群组列表，使用逗号分隔多个群 ID。  
   - 示例：`编队 广告队 -1001234567890, -1009876543210`  
   - 结果：成功时回复“编队已更新”，若群 ID 无效则回复“任务目标有误请检查”。

7. **从编队删除群组**  
   - 指令：`删除 队名 群ID, 群ID`  
   - 功能：从指定队名中删除一个或多个群 ID。  
   - 示例：`删除 广告队 -1001234567890`  
   - 结果：成功时回复“群组已从编队移除”，若队名或群 ID 无效则回复“任务目标有误请检查”。

### 注意事项
- **私聊限制**：以上指令仅在私聊与机器人对话时有效。
- **文件支持**：支持动图（`.gif`）、视频（`.mp4`）和图片（`.jpg/.png`），需先在私聊发送文件以获取文件 ID。
- **时间调整**：若设定时间已过当天，自动调整为次日。
- **错误处理**：编队不存在或群 ID 无效时，回复“任务目标有误请检查”。
            """
            await update.message.reply_text(help_text)

        # 其余群发逻辑
        if message_text.startswith("编辑 "):
            logger.info(f"匹配到 '编辑' 指令，参数: {message_text.replace('编辑 ', '')}, 在私聊 (ID: {chat_id})")
            parts = message_text.split(" ", 2)
            if len(parts) == 3 and parts[1] and parts[2]:
                template_name = parts[1]
                message = parts[2]
                file_id = last_file_id.get(chat_id)
                if file_id:
                    templates[template_name] = {"message": message, "file_id": file_id}
                    await update.message.reply_text(f"模板 {template_name} 已更新")
                else:
                    await update.message.reply_text("请先发送动图、视频或图片以获取文件 ID")
            else:
                await update.message.reply_text("使用格式：编辑 模板名 广告文")

        if message_text.startswith("任务 ") and not message_text.endswith("-1"):
            logger.info(f"匹配到 '任务' 指令，参数: {message_text.replace('任务 ', '')}, 在私聊 (ID: {chat_id})")
            parts = message_text.split(" ", 3)
            if len(parts) == 4 and parts[1] and parts[2] and parts[3]:
                team_name, time_str, template_name = parts[1], parts[2], parts[3]
                try:
                    current_time = datetime.now(pytz.timezone("Asia/Bangkok"))
                    scheduled_time = current_time.replace(hour=int(time_str.split(":")[0]), minute=int(time_str.split(":")[1]), second=0, microsecond=0)
                    if scheduled_time < current_time:
                        scheduled_time += timedelta(days=1)
                    task_id = ''.join(random.choices(string.ascii_letters + string.digits, k=5))
                    scheduled_tasks[task_id] = {"team": team_name, "template": template_name, "time": scheduled_time}
                    await update.message.reply_text(f"任务已创建，任务 ID: {task_id}，请回复 `确认 {task_id}` 执行")
                except (ValueError, IndexError):
                    await update.message.reply_text("时间格式错误，请使用 HH:MM，例如 17:00")

        if message_text.startswith("确认 "):
            logger.info(f"匹配到 '确认' 指令，任务 ID: {message_text.replace('确认 ', '').strip()}, 在私聊 (ID: {chat_id})")
            task_id = message_text.replace("确认 ", "").strip()
            if task_id in scheduled_tasks:
                task = scheduled_tasks[task_id]
                team_name, template_name = task["team"], task["template"]
                if team_name in team_groups and template_name in templates:
                    schedule.every().day.at(task["time"].strftime("%H:%M")).do(
                        lambda t=task: asyncio.run(send_broadcast(context, t))
                    ).tag(task_id)
                    await update.message.reply_text(f"任务 {task_id} 已计划，等待执行")
                    del scheduled_tasks[task_id]  # 移除待确认任务
                else:
                    await update.message.reply_text("任务目标有误请检查")
            else:
                await update.message.reply_text("无效的任务 ID")

        if message_text.startswith("任务 ") and message_text.endswith("-1"):
            logger.info(f"匹配到 '任务取消' 指令，队名: {message_text.replace('任务 ', '').replace('-1', '').strip()}, 在私聊 (ID: {chat_id})")
            team_name = message_text.replace("任务 ", "").replace("-1", "").strip()
            for task_id, task in list(scheduled_tasks.items()):
                if task["team"] == team_name:
                    schedule.clear(task_id)
                    del scheduled_tasks[task_id]
                    await update.message.reply_text("任务已取消")
                    break
            else:
                await update.message.reply_text("无此队名的待执行任务")

        if message_text.startswith("编队 "):
            logger.info(f"匹配到 '编队' 指令，参数: {message_text.replace('编队 ', '')}, 在私聊 (ID: {chat_id})")
            parts = message_text.split(" ", 2)
            if len(parts) == 3 and parts[1] and parts[2]:
                team_name = parts[1]
                group_ids = [gid.strip() for gid in parts[2].split(",") if gid.strip()]
                try:
                    for gid in group_ids:
                        int(gid)  # 验证群 ID 是否为整数
                    team_groups[team_name] = group_ids
                    await update.message.reply_text("编队已更新")
                except ValueError:
                    await update.message.reply_text("任务目标有误请检查")
            else:
                await update.message.reply_text("使用格式：编队 队名 群ID, 群ID")

        if message_text.startswith("删除 "):
            logger.info(f"匹配到 '删除编队' 指令，参数: {message_text.replace('删除 ', '')}, 在私聊 (ID: {chat_id})")
            parts = message_text.split(" ", 2)
            if len(parts) == 3 and parts[1] and parts[2]:
                team_name = parts[1]
                group_ids = [gid.strip() for gid in parts[2].split(",") if gid.strip()]
                if team_name in team_groups:
                    for gid in group_ids:
                        if gid in team_groups[team_name]:
                            team_groups[team_name].remove(gid)
                    if not team_groups[team_name]:
                        del team_groups[team_name]
                    await update.message.reply_text("群组已从编队移除")
                else:
                    await update.message.reply_text("任务目标有误请检查")
            else:
                await update.message.reply_text("使用格式：删除 队名 群ID, 群ID")

# 主函数
async def main():
    port = int(os.getenv("PORT", "10000"))
    logger.info(f"Listening on port: {port}")

    application = Application.builder().token(BOT_TOKEN).build()

    # 检查 Webhook 状态
    try:
        webhook_info = await application.bot.get_webhook_info()
        logger.info(f"当前 Webhook 状态: {webhook_info}")
    except Exception as e:
        logger.error(f"获取 Webhook 状态失败: {e}")

    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
    application.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE, handle_photo))
    application.add_handler(MessageHandler(filters.ANIMATION & filters.ChatType.PRIVATE, handle_animation))
    application.add_handler(MessageHandler(filters.VIDEO & filters.ChatType.PRIVATE, handle_video))
    application.add_handler(MessageHandler(filters.TEXT, handle_text))

    # 添加 schedule 线程以确保定时任务运行
    import threading
    def run_schedule():
        while True:
            schedule.run_pending()
            time.sleep(60)
    threading.Thread(target=run_schedule, daemon=True).start()

    setup_schedule()

    external_url = os.getenv("RENDER_EXTERNAL_URL", "winpay-bot-repo.onrender.com").strip()
    if not external_url:
        logger.error("错误：RENDER_EXTERNAL_URL 未设置")
        return
    if not external_url.startswith("http"):
        webhook_url = f"https://{external_url}/webhook"
    else:
        webhook_url = external_url + "/webhook"
    logger.info(f"设置 Webhook URL: {webhook_url}")
    try:
        logger.info("尝试启动 Webhook...")
        await application.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path="/webhook",
            webhook_url=webhook_url
        )
    except Exception as e:
        logger.error(f"Webhook 设置失败: {e}")

if __name__ == '__main__':
    asyncio.run(main())
