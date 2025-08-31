import re
from datetime import datetime, timezone, timedelta
import pytz
from telegram.ext import Application, ApplicationBuilder, MessageHandler, filters
import telegram.ext
from flask import Flask, jsonify, request
from flask_cors import CORS
import asyncio
import os
import threading

app = Flask(__name__)
CORS(app)

BOT_TOKEN = os.getenv("BOT_TOKEN", "8401029616:AAH75qtZCE05RX-qieHIQO3TwylmIAwC8nM")
initial_admin_username = "juyuanzhifu_01"
operating_groups = {}
transactions = {}
user_history = {}
exchange_rates = {}
address_verify_count = {}
is_accounting_enabled = {}
team_groups = {}
scheduled_tasks = {}
last_file_id = {}
last_file_message = {}
templates = {}

def format_amount(amount):
    if float(amount).is_integer():
        return str(int(float(amount)))
    return f"{float(amount):.2f}".rstrip('0').rstrip('.')

def format_exchange_rate(rate):
    if float(rate).is_integer():
        return str(int(float(rate)))
    formatted = f"{float(rate):.3f}"
    return formatted.rstrip('0').rstrip('.')

async def handle_bill(update, context):
    chat_id = str(update.message.chat_id)
    if chat_id not in transactions:
        transactions[chat_id] = []
    recent_transactions = transactions[chat_id][-6:] if len(transactions[chat_id]) >= 6 else transactions[chat_id]
    deposit_count = sum(1 for t in transactions[chat_id] if t.startswith("入款"))
    withdraw_count = sum(1 for t in transactions[chat_id] if t.startswith("下发"))
    bill = "当前账单\n"

    exchange_rate_deposit = exchange_rates.get(chat_id, {"deposit": 1.0})["deposit"]
    deposit_fee_rate = exchange_rates.get(chat_id, {"deposit_fee": 0.0})["deposit_fee"]
    exchange_rate_withdraw = exchange_rates.get(chat_id, {"withdraw": 1.0})["withdraw"]
    withdraw_fee_rate = exchange_rates.get(chat_id, {"withdraw_fee": 0.0})["withdraw_fee"]

    if deposit_count > 0:
        bill += f"入款（{deposit_count}笔）\n"
        for t in reversed([t for t in recent_transactions if t.startswith("入款")]):
            parts = t.split(" -> ")
            timestamp = parts[0].split()[2]
            operator = parts[-1].split("operator=")[1].rstrip("]")
            if len(parts) == 1:
                amount = float(parts[0].split()[1].rstrip('u'))
                bill += f"{timestamp}  {format_amount(amount)}u    {operator}\n"
            else:
                amount = float(parts[0].split()[1].rstrip('u'))
                adjusted = float(parts[1].split()[0].rstrip('u'))
                rate_info = parts[1].split("[rate=")[1].rstrip("]").split(", fee=")
                historical_rate = float(rate_info[0])
                historical_fee = float(rate_info[1].split(",")[0])
                effective_rate = 1 - historical_fee
                bill += f"{timestamp}  {format_amount(amount)} * {format_amount(effective_rate)} / {format_exchange_rate(historical_rate)} = {format_amount(adjusted)}u    {operator}\n"

    if withdraw_count > 0:
        if deposit_count > 0:
            bill += "\n"
        bill += f"出款（{withdraw_count}笔）\n"
        for t in reversed([t for t in recent_transactions if t.startswith("下发")]):
            parts = t.split(" -> ")
            timestamp = parts[0].split()[2]
            operator = parts[-1].split("operator=")[1].rstrip("]")
            if len(parts) == 1:
                amount = float(parts[0].split()[1].rstrip('u'))
                bill += f"{timestamp}  {format_amount(amount)}u    {operator}\n"
            else:
                amount = float(parts[0].split()[1].rstrip('u'))
                adjusted = float(parts[1].split()[0].rstrip('u'))
                rate_info = parts[1].split("[rate=")[1].rstrip("]").split(", fee=")
                historical_rate = float(rate_info[0])
                historical_fee = float(rate_info[1].split(",")[0])
                effective_rate = 1 + historical_fee
                bill += f"{timestamp}  {format_amount(amount)} * {format_amount(effective_rate)} / {format_exchange_rate(historical_rate)} = {format_amount(adjusted)}u    {operator}\n"

    if deposit_count > 0 or withdraw_count > 0:
        if deposit_count > 0 or withdraw_count > 0:
            bill += "\n"
        if deposit_count > 0:
            bill += f"入款汇率：{format_exchange_rate(exchange_rate_deposit)}  |  费率：{format_amount(deposit_fee_rate*100)}%\n"
        if withdraw_count > 0:
            bill += f"出款汇率：{format_exchange_rate(exchange_rate_withdraw)}  |  费率：{format_amount(withdraw_fee_rate*100)}%\n"
        if deposit_count > 0 or withdraw_count > 0:
            bill += "\n"
        total_deposit = sum(float(t.split()[1].rstrip('u')) for t in transactions[chat_id] if t.startswith("入款"))
        total_deposit_adjusted = sum(float(t.split(" -> ")[1].split()[0].rstrip('u')) if "->" in t else float(t.split()[1].rstrip('u')) for t in transactions[chat_id] if t.startswith("入款"))
        total_withdraw = sum(float(t.split()[1].rstrip('u')) for t in transactions[chat_id] if t.startswith("下发"))
        total_withdraw_adjusted = sum(float(t.split(" -> ")[1].split()[0].rstrip('u')) if "->" in t else float(t.split()[1].rstrip('u')) for t in transactions[chat_id] if t.startswith("下发"))
        balance = total_deposit_adjusted - total_withdraw_adjusted
        if deposit_count > 0:
            bill += f"总入款：{format_amount(total_deposit)}  |  {format_amount(total_deposit_adjusted)}u\n"
        if withdraw_count > 0:
            bill += f"总出款：{format_amount(total_withdraw)}  |  {format_amount(total_withdraw_adjusted)}u\n"
        bill += f"总余额：{format_amount(balance)}u"

    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    keyboard = [[InlineKeyboardButton("查看完整账单", url=f"https://bill-web-app.onrender.com/Telegram/BillReport?group_id={chat_id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(
        chat_id=chat_id,
        text=bill if transactions[chat_id] else "当前暂无交易记录，老板速度来单",
        reply_markup=reply_markup
    )

async def welcome_new_member(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    if chat_id not in user_history:
        user_history[chat_id] = {}
    if update.message and update.message.new_chat_members:
        for member in update.message.new_chat_members:
            user_id = str(member.id)
            username = member.username
            first_name = member.first_name.strip() if member.first_name else None
            nickname = first_name or username or "新朋友"
            timestamp = datetime.now(pytz.timezone("Asia/Bangkok")).strftime("%Y年%m月%d日 %H:%M")

            user_history[chat_id][user_id] = {"username": username, "first_name": first_name}
            print(f"[{datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%H:%M:%S')}] 新用户记录: {user_id}, username={username}, first_name={first_name}")
            await context.bot.send_message(chat_id=chat_id, text=f"热烈欢迎 {nickname} 来到本群，入金叫卡找聚元，光速到账似火箭")

            if user_id in user_history[chat_id]:
                old_data = user_history[chat_id][user_id].copy()
                old_username = old_data["username"]
                old_first_name = old_data["first_name"]
                if username and username != old_username and first_name == old_first_name:
                    warning = f"⚠️警告提示⚠️ ({first_name}) 的用户名不一致\n之前用户名：@{old_username}\n现在用户名：@{username}\n修改时间：{timestamp}\n请注意查证‼️"
                    await context.bot.send_message(chat_id=chat_id, text=warning)
                    print(f"[{datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%H:%M:%S')}] 用户名变更警告: {first_name}, 之前 @{old_username}, 现在 @{username}")
                elif first_name and first_name != old_first_name and username == old_username:
                    warning = f"⚠️警告提示⚠️ (@{username}) 的昵称不一致\n之前昵称：{old_first_name}\n现在昵称：{first_name}\n修改时间：{timestamp}\n请注意查证‼️"
                    await context.bot.send_message(chat_id=chat_id, text=warning)
                    print(f"[{datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%H:%M:%S')}] 昵称变更警告: @{username}, 之前 {old_first_name}, 现在 {first_name}")

async def handle_message(update, context):
    global operating_groups, transactions, user_history, address_verify_count, is_accounting_enabled, exchange_rates, team_groups, scheduled_tasks, last_file_id, last_file_message, templates
    message_text = ''.join(c for c in update.message.text if c.isprintable()).strip() if update.message.text else ""
    chat_id = str(update.message.chat_id)
    user_id = str(update.message.from_user.id)
    username = update.message.from_user.username
    first_name = update.message.from_user.first_name.strip() if update.message.from_user.first_name else None
    operator_name = first_name or username
    print(f"[{datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%H:%M:%S')}] 收到消息: '{message_text}' 从用户 {user_id}, username: {username}, chat_id: {chat_id}")

    if chat_id not in operating_groups:
        operating_groups[chat_id] = {initial_admin_username: True}
    if chat_id not in transactions:
        transactions[chat_id] = []
    if chat_id not in user_history:
        user_history[chat_id] = {}
    if chat_id not in address_verify_count:
        address_verify_count[chat_id] = {"count": 0, "last_user": None}
    if chat_id not in is_accounting_enabled:
        is_accounting_enabled[chat_id] = True
    if chat_id not in last_file_id:
        last_file_id[chat_id] = None
    if chat_id not in last_file_message:
        last_file_message[chat_id] = None
    if chat_id not in exchange_rates:
        exchange_rates[chat_id] = {"deposit": 1.0, "withdraw": 1.0, "deposit_fee": 0.0, "withdraw_fee": 0.0}

    if user_id not in user_history[chat_id]:
        user_history[chat_id][user_id] = {"username": username, "first_name": first_name}
        print(f"[{datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%H:%M:%S')}] 新用户记录: {user_id}, username={username}, first_name={first_name}")
    else:
        old_data = user_history[chat_id][user_id].copy()
        old_username = old_data["username"]
        old_first_name = old_data["first_name"]
        timestamp = datetime.now(pytz.timezone("Asia/Bangkok")).strftime("%Y年%m月%d日 %H:%M")
        if username and username != old_username and first_name == old_first_name:
            warning = f"⚠️警告提示⚠️ ({first_name}) 的用户名不一致\n之前用户名：@{old_username}\n现在用户名：@{username}\n修改时间：{timestamp}\n请注意查证‼️"
            await context.bot.send_message(chat_id=chat_id, text=warning)
            print(f"[{datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%H:%M:%S')}] 用户名变更警告: {first_name}, 之前 @{old_username}, 现在 @{username}")
        elif first_name and first_name != old_first_name and username == old_username:
            warning = f"⚠️警告提示⚠️ (@{username}) 的昵称不一致\n之前昵称：{old_first_name}\n现在昵称：{first_name}\n修改时间：{timestamp}\n请注意查证‼️"
            await context.bot.send_message(chat_id=chat_id, text=warning)
            print(f"[{datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%H:%M:%S')}] 昵称变更警告: @{username}, 之前 {old_first_name}, 现在 {first_name}")

    if update.message.chat.type == "private" and (update.message.animation or update.message.document or update.message.video or update.message.photo):
        file_id = None
        file_type = None
        if update.message.animation:
            file_id = update.message.animation.file_id
            file_type = "动图"
        elif update.message.document:
            file_id = update.message.document.file_id
            file_type = "视频"
        elif update.message.video:
            file_id = update.message.video.file_id
            file_type = "视频"
        elif update.message.photo and len(update.message.photo) > 0:
            file_id = update.message.photo[-1].file_id
            file_type = "图片"
        if file_id:
            caption = update.message.caption or update.message.text or None
            print(f"[{datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%H:%M:%S')}] 处理文件消息，类型: {file_type}, 文件ID: {file_id}, 文本: {caption or '无'}")
            last_file_id[chat_id] = file_id
            last_file_message[chat_id] = {"file_id": file_id, "caption": caption}
            await context.bot.send_message(chat_id=chat_id, text=f"{file_type}文件 ID: {file_id}")
        elif update.message.video or update.message.document or update.message.animation or update.message.photo:
            print(f"[{datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%H:%M:%S')}] 文件处理失败，未识别到有效文件ID")
            await context.bot.send_message(chat_id=chat_id, text="无法识别文件，请确保发送的是动图、视频或图片文件")
        return

    # Handle commands first
    if not any(message_text.startswith(cmd) or message_text == cmd for cmd in [
        "开始", "停止记账", "恢复记账", "说明", "入款", "+", "下发", "设置操作员", "删除操作员",
        "设置入款汇率", "设置入款费率", "设置下发汇率", "设置下发费率", "账单", "+0", "删除",
        "删除账单", "日切", "操作员列表", "编队", "删除", "编辑", "任务", "任务列表", "群发说明", "拉停"
    ]):
        # Arithmetic calculation with reply to original message
        arithmetic_pattern = r'^\d+[\d\s\.\-+*/×()÷]*$'
        if re.match(arithmetic_pattern, message_text):
            print(f"[{datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%H:%M:%S')}] 匹配到算术表达式: {message_text}")
            try:
                expression = message_text.replace('÷', '/').replace('×', '*').replace('x', '*').replace('−', '-')
                result = eval(expression, {"__builtins__": {}}, {})
                if isinstance(result, (int, float)):
                    if isinstance(result, float) and result.is_integer():
                        result = int(result)
                    else:
                        result = round(result, 2)
                    response = f"{message_text}={result}"
                    print(f"[{datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%H:%M:%S')}] 算术结果: {response}")
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=response,
                        reply_to_message_id=update.message.message_id
                    )
                return
            except Exception as e:
                print(f"[{datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%H:%M:%S')}] 忽略无效算术表达式: {message_text}, 错误: {str(e)}")
                return
        # TRX address validation
        elif re.match(r'^[T][123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz]{33}$', message_text):
            print(f"[{datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%H:%M:%S')}] 匹配到 TRX 地址验证: {message_text}")
            try:
                current_user = f"@{username}" if username else "未知用户"
                address_verify_count[chat_id]["count"] += 1
                last_user = address_verify_count[chat_id]["last_user"] or "无"
                address_verify_count[chat_id]["last_user"] = current_user
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"{message_text}\n验证次数：{address_verify_count[chat_id]['count']}\n本次发送人：{current_user}\n上次发送人：{last_user}"
                )
            except Exception as e:
                print(f"[{datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%H:%M:%S')}] 地址验证错误: {str(e)}")
                await context.bot.send_message(chat_id=chat_id, text="地址验证失败，请稍后再试或联系管理员")
            return
        else:
            if message_text.startswith('T'):
                invalid_chars = [c for c in message_text if c not in 'T123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz']
                if invalid_chars or len(message_text) != 34:
                    print(f"[{datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%H:%M:%S')}] 地址格式错误: {message_text}, 长度={len(message_text)}, 非法字符={invalid_chars}")
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=f"地址格式错误：{message_text}\n长度：{len(message_text)}（应为34）\n非法字符：{invalid_chars or '无'}\nTRON地址应以'T'开头，仅含 1-9, A-Z, a-z（排除0, I, O, l）"
                    )
            print(f"[{datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%H:%M:%S')}] 未匹配任何逻辑，输入: {message_text}")
            return

    is_operator = username and (username in operating_groups.get(chat_id, {}) or 
                              (update.message.chat.type == "private" and username in operating_groups.get("private", {})))
    if not is_operator and message_text not in ["账单", "+0", "说明"]:
        if username:
            await context.bot.send_message(chat_id=chat_id, text=f"@{username}非操作员，请联系管理员设置权限")
        return

    # 新增“拉停”指令
    if message_text == "拉停":
        if is_operator and is_accounting_enabled.get(chat_id, True):
            print(f"[{datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%H:%M:%S')}] 匹配到 '拉停' 指令")
            warning_message = "‼️❌**车况异常，停止入金**❌‼️\n" * 3
            await context.bot.send_message(
                chat_id=chat_id,
                text=warning_message.rstrip(),
                parse_mode="Markdown",
                reply_to_message_id=update.message.message_id if update.message.reply_to_message else None
            )
            return

    if message_text == "编队列表" and update.message.chat.type == "private":
        print(f"[{datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%H:%M:%S')}] 匹配到 '编队列表' 指令")
        if username and (username in operating_groups.get("private", {}) or username == initial_admin_username):
            if team_groups:
                response = "编队列表：\n" + "\n".join(f"{team}: {', '.join(groups)}" for team, groups in sorted(team_groups.items()))
            else:
                response = "无编队"
            print(f"[{datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%H:%M:%S')}] 编队列表响应: {response}")
            await context.bot.send_message(chat_id=chat_id, text=response)
        else:
            await context.bot.send_message(chat_id=chat_id, text=f"仅操作员可查看编队列表，请联系管理员设置权限")
        return

    if message_text == "开始":
        if is_operator:
            print(f"[{datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%H:%M:%S')}] 匹配到 '开始' 指令")
            transactions[chat_id].clear()
            is_accounting_enabled[chat_id] = True
            await context.bot.send_message(chat_id=chat_id, text="欢迎使用聚元支付小助手，入金叫卡找聚元，光速到账似火箭")

    elif message_text == "停止记账":
        if is_operator:
            print(f"[{datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%H:%M:%S')}] 匹配到 '停止记账' 指令")
            is_accounting_enabled[chat_id] = False
            await context.bot.send_message(chat_id=chat_id, text="已暂停记账功能")

    elif message_text == "恢复记账":
        if is_operator:
            print(f"[{datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%H:%M:%S')}] 匹配到 '恢复记账' 指令")
            is_accounting_enabled[chat_id] = True
            await context.bot.send_message(chat_id=chat_id, text="记账功能已恢复")

    elif message_text == "说明":
        if is_operator or message_text == "说明":
            print(f"[{datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%H:%M:%S')}] 匹配到 '说明' 指令")
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
停止入金：拉停
            """
            await context.bot.send_message(chat_id=chat_id, text=help_text)

    elif (message_text.startswith("入款") or message_text.startswith("+")) and message_text != "+0":
        if is_operator and is_accounting_enabled.get(chat_id, True):
            print(f"[{datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%H:%M:%S')}] 匹配到 '入款' 或 '+' 指令，金额: {message_text.replace('入款', '').replace('+', '').strip()}")
            try:
                amount_str = message_text.replace("入款", "").replace("+", "").strip()
                beijing_tz = pytz.timezone("Asia/Shanghai")
                utc_time = update.message.date.replace(tzinfo=timezone.utc)
                timestamp = utc_time.astimezone(beijing_tz).strftime("%H:%M")
                date = utc_time.astimezone(beijing_tz).strftime("%Y-%m-%d")
                exchange_rate_deposit = exchange_rates[chat_id]["deposit"]
                deposit_fee_rate = exchange_rates[chat_id]["deposit_fee"]
                if update.message.reply_to_message:
                    reply_user = update.message.reply_to_message.from_user
                    operator_name = reply_user.first_name.strip() if reply_user.first_name else reply_user.username
                else:
                    operator_name = first_name or username
                if amount_str.lower().endswith('u'):
                    amount = float(amount_str.rstrip('uU'))
                    transaction = f"入款 {format_amount(amount)}u {timestamp} {date} [operator={operator_name}]"
                    transactions[chat_id].append(transaction)
                    await handle_bill(update, context)
                else:
                    amount = float(amount_str)
                    adjusted_amount = amount * (1 - deposit_fee_rate) / exchange_rate_deposit
                    transaction = f"入款 {format_amount(amount)} {timestamp} {date} -> {format_amount(adjusted_amount)}u [rate={exchange_rate_deposit}, fee={deposit_fee_rate}, operator={operator_name}]"
                    transactions[chat_id].append(transaction)
                    await handle_bill(update, context)
            except ValueError:
                await context.bot.send_message(chat_id=chat_id, text="请输入正确金额，例如：入款1000 或 +1000 或 +100u")

    elif message_text.startswith("下发"):
        if is_operator and is_accounting_enabled.get(chat_id, True):
            print(f"[{datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%H:%M:%S')}] 匹配到 '下发' 指令，金额: {message_text.replace('下发', '').strip()}")
            try:
                amount_str = message_text.replace("下发", "").strip()
                beijing_tz = pytz.timezone("Asia/Shanghai")
                utc_time = update.message.date.replace(tzinfo=timezone.utc)
                timestamp = utc_time.astimezone(beijing_tz).strftime("%H:%M")
                date = utc_time.astimezone(beijing_tz).strftime("%Y-%m-%d")
                exchange_rate_withdraw = exchange_rates[chat_id]["withdraw"]
                withdraw_fee_rate = exchange_rates[chat_id]["withdraw_fee"]
                if update.message.reply_to_message:
                    reply_user = update.message.reply_to_message.from_user
                    operator_name = reply_user.first_name.strip() if reply_user.first_name else reply_user.username
                else:
                    operator_name = first_name or username
                if amount_str.lower().endswith('u'):
                    amount = float(amount_str.rstrip('uU'))
                    transaction = f"下发 {format_amount(amount)}u {timestamp} {date} [operator={operator_name}]"
                    transactions[chat_id].append(transaction)
                    await handle_bill(update, context)
                else:
                    amount = float(amount_str)
                    adjusted_amount = amount * (1 + withdraw_fee_rate) / exchange_rate_withdraw
                    transaction = f"下发 {format_amount(amount)} {timestamp} {date} -> {format_amount(adjusted_amount)}u [rate={exchange_rate_withdraw}, fee={withdraw_fee_rate}, operator={operator_name}]"
                    transactions[chat_id].append(transaction)
                    await handle_bill(update, context)
            except ValueError:
                await context.bot.send_message(chat_id=chat_id, text="请输入正确金额，例如：下发500 或 下发50u")

    elif message_text.startswith("设置操作员"):
        if is_operator and is_accounting_enabled.get(chat_id, True):
            print(f"[{datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%H:%M:%S')}] 匹配到 '设置操作员' 指令，参数: {message_text.replace('设置操作员', '').strip()}")
            operator = message_text.replace("设置操作员", "").strip()
            if operator.startswith("@"):
                operator = operator[1:]
                if chat_id not in operating_groups:
                    operating_groups[chat_id] = {}
                operating_groups[chat_id][operator] = True
                if "private" not in operating_groups:
                    operating_groups["private"] = {}
                operating_groups["private"][operator] = True
                await context.bot.send_message(chat_id=chat_id, text=f"已将 @{operator} 设置为操作员")
            else:
                await context.bot.send_message(chat_id=chat_id, text="请使用格式：设置操作员 @用户名")

    elif message_text.startswith("删除操作员"):
        if is_operator and is_accounting_enabled.get(chat_id, True):
            print(f"[{datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%H:%M:%S')}] 匹配到 '删除操作员' 指令，参数: {message_text.replace('删除操作员', '').strip()}")
            operator = message_text.replace("删除操作员", "").strip()
            if operator.startswith("@"):
                operator = operator[1:]
                if chat_id in operating_groups and operator in operating_groups[chat_id]:
                    del operating_groups[chat_id][operator]
                    if "private" in operating_groups and operator in operating_groups["private"]:
                        del operating_groups["private"][operator]
                    await context.bot.send_message(chat_id=chat_id, text=f"已删除 @{operator} 操作员权限")
                else:
                    await context.bot.send_message(chat_id=chat_id, text=f"@{operator} 不是当前群组的操作员")
            else:
                await context.bot.send_message(chat_id=chat_id, text="请使用格式：删除操作员 @用户名")

    elif message_text.startswith("设置入款汇率"):
        if is_operator and is_accounting_enabled.get(chat_id, True):
            print(f"[{datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%H:%M:%S')}] 匹配到 '设置入款汇率' 指令，汇率: {message_text.replace('设置入款汇率', '').strip()}")
            try:
                rate = float(message_text.replace("设置入款汇率", "").strip())
                exchange_rates[chat_id]["deposit"] = round(rate, 3)
                await context.bot.send_message(chat_id=chat_id, text=f"设置成功入款汇率 {format_exchange_rate(exchange_rates[chat_id]['deposit'])}")
            except ValueError:
                await context.bot.send_message(chat_id=chat_id, text="请输入正确汇率，例如：设置入款汇率0.98")

    elif message_text.startswith("设置入款费率"):
        if is_operator and is_accounting_enabled.get(chat_id, True):
            print(f"[{datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%H:%M:%S')}] 匹配到 '设置入款费率' 指令，费率: {message_text.replace('设置入款费率', '').strip()}")
            try:
                rate = float(message_text.replace("设置入款费率", "").strip()) / 100
                exchange_rates[chat_id]["deposit_fee"] = rate
                await context.bot.send_message(chat_id=chat_id, text=f"设置成功入款费率 {format_amount(rate*100)}%")
            except ValueError:
                await context.bot.send_message(chat_id=chat_id, text="请输入正确费率，例如：设置入款费率4.5")

    elif message_text.startswith("设置下发汇率"):
        if is_operator and is_accounting_enabled.get(chat_id, True):
            print(f"[{datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%H:%M:%S')}] 匹配到 '设置下发汇率' 指令，汇率: {message_text.replace('设置下发汇率', '').strip()}")
            try:
                rate = float(message_text.replace("设置下发汇率", "").strip())
                exchange_rates[chat_id]["withdraw"] = round(rate, 3)
                await context.bot.send_message(chat_id=chat_id, text=f"设置成功下发汇率 {format_exchange_rate(exchange_rates[chat_id]['withdraw'])}")
            except ValueError:
                await context.bot.send_message(chat_id=chat_id, text="请输入正确汇率，例如：设置下发汇率1.25")

    elif message_text.startswith("设置下发费率"):
        if is_operator and is_accounting_enabled.get(chat_id, True):
            print(f"[{datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%H:%M:%S')}] 匹配到 '设置下发费率' 指令，费率: {message_text.replace('设置下发费率', '').strip()}")
            try:
                rate = float(message_text.replace("设置下发费率", "").strip()) / 100
                exchange_rates[chat_id]["withdraw_fee"] = rate
                await context.bot.send_message(chat_id=chat_id, text=f"设置成功下发费率 {format_amount(rate*100)}%")
            except ValueError:
                await context.bot.send_message(chat_id=chat_id, text="请输入正确费率，例如：设置下发费率4.5")

    elif message_text == "账单" or message_text == "+0":
        if is_operator or message_text in ["账单", "+0"]:
            print(f"[{datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%H:%M:%S')}] 匹配到 '账单' 或 '+0' 指令")
            await handle_bill(update, context)

    elif message_text == "删除":
        if is_operator and is_accounting_enabled.get(chat_id, True):
            print(f"[{datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%H:%M:%S')}] 匹配到 '删除' 指令")
            if update.message.reply_to_message:
                original_message = update.message.reply_to_message.text.strip()
                print(f"[{datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%H:%M:%S')}] 尝试删除，原始消息: '{original_message}'")
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
                                await context.bot.send_message(chat_id=chat_id, text=f"入款 {format_amount(amount)}{'u' if has_u else ''} 已被撤销")
                                await handle_bill(update, context)
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
                                await context.bot.send_message(chat_id=chat_id, text=f"下发 {format_amount(amount)}{'u' if has_u else ''} 已被撤销")
                                await handle_bill(update, context)
                                return
            await context.bot.send_message(chat_id=chat_id, text="无法撤销此消息，请确保回复正确的入款或下发记录")

    elif message_text == "删除账单":
        if is_operator and is_accounting_enabled.get(chat_id, True):
            print(f"[{datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%H:%M:%S')}] 匹配到 '删除账单' 指令")
            transactions[chat_id].clear()
            await context.bot.send_message(chat_id=chat_id, text="当前账单已结算💰，重新开始记账")

    elif message_text == "日切" and username == initial_admin_username:
        if is_operator and is_accounting_enabled.get(chat_id, True):
            print(f"[{datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%H:%M:%S')}] 匹配到 '日切' 指令")
            transactions[chat_id].clear()
            await context.bot.send_message(chat_id=chat_id, text="交易记录已清空")

    elif message_text == "操作员列表":
        if is_operator and is_accounting_enabled.get(chat_id, True):
            print(f"[{datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%H:%M:%S')}] 匹配到 '操作员列表' 指令")
            op_list = ", ".join([f"@{op}" for op in operating_groups.get(chat_id, {})])
            private_op_list = ", ".join([f"@{op}" for op in operating_groups.get("private", {})]) if "private" in operating_groups else "无"
            await context.bot.send_message(chat_id=chat_id, text=f"当前群组操作员列表: {op_list if op_list else '无'}\n私聊操作员列表: {private_op_list}")

    if update.message.chat.type == "private":
        if message_text == "群发说明":
            help_text = """
### 群发指令说明

**注意**：此说明仅在私聊中通过指令 `群发说明` 查看，所有群发相关功能仅在私聊中有效，所有操作员均可使用。当前版本暂不支持群发任务调度，请升级到 SuperGrok 订阅计划以启用完整群发功能，详情请访问 https://x.ai/grok。

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

3. **创建/更新编队**  
   - 指令：`编队 队名 群ID, 群ID`  
   - 功能：创建或更新指定队名对应的群组列表，使用逗号分隔多个群 ID。  
   - 示例：`编队 广告队 -1001234567890, -1009876543210`  
   - 结果：成功时回复“编队已更新”，若群 ID 无效则回复“任务目标有误请检查”。

4. **从编队删除群组**  
   - 指令：`删除 队名 群ID, 群ID`  
   - 功能：从指定队名中删除一个或多个群 ID。  
   - 示例：`删除 广告队 -1001234567890`  
   - 结果：成功时回复“群组已从编队移除”，若队名或群 ID 无效则回复“任务目标有误请检查”。

### 注意事项
- **私聊限制**：以上指令仅在私聊与机器人对话时有效。
- **文件支持**：支持动图（`.gif`）、视频（`.mp4`）和图片（`.jpg/.png`），发送文件后自动返回文件 ID。
- **调度功能**：任务调度（如 `任务` 和 `任务列表`）当前不可用，请升级到 SuperGrok 订阅计划以启用，详情请访问 https://x.ai/grok。
- **错误处理**：编队不存在或群 ID 无效时，回复“任务目标有误请检查”。
            """
            await context.bot.send_message(chat_id=chat_id, text=help_text)

        if message_text.startswith("编队 "):
            parts = message_text.split(" ", 2)
            if len(parts) == 3 and parts[1] and parts[2]:
                team_name = parts[1]
                if username and (username in operating_groups.get("private", {}) or username == initial_admin_username):
                    try:
                        group_ids = [gid.strip() for gid in re.split(r'[,，]', parts[2]) if gid.strip()]
                        if not group_ids:
                            raise ValueError("群ID列表为空")
                        for gid in group_ids:
                            if not gid.startswith("-") or not gid[1:].isdigit():
                                raise ValueError(f"无效群ID: {gid}")
                        team_groups[team_name] = list(set(team_groups.get(team_name, []) + group_ids))
                        print(f"[{datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%H:%M:%S')}] 编队输入: 队名={team_name}, 群ID={group_ids}")
                        await context.bot.send_message(chat_id=chat_id, text=f"编队已更新: {team_name}，包含群组: {', '.join(group_ids)}")
                    except ValueError as e:
                        print(f"[{datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%H:%M:%S')}] 编队解析失败: {e}")
                        await context.bot.send_message(chat_id=chat_id, text=f"任务目标有误请检查: {e}")
                else:
                    await context.bot.send_message(chat_id=chat_id, text=f"仅操作员可执行此操作，请联系管理员设置权限")
            else:
                await context.bot.send_message(chat_id=chat_id, text="使用格式：编队 队名 群ID,群ID")
            return

        if message_text.startswith("删除 "):
            parts = message_text.split(" ", 2)
            if len(parts) == 3 and parts[1] and parts[2]:
                team_name = parts[1]
                if username and (username in operating_groups.get("private", {}) or username == initial_admin_username):
                    try:
                        group_ids = [gid.strip() for gid in re.split(r'[,，]', parts[2]) if gid.strip()]
                        if not group_ids:
                            raise ValueError("群ID列表为空")
                        if team_name in team_groups:
                            for gid in group_ids:
                                if gid in team_groups[team_name]:
                                    team_groups[team_name].remove(gid)
                            if not team_groups[team_name]:
                                del team_groups[team_name]
                            print(f"[{datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%H:%M:%S')}] 删除群组: 队名={team_name}, 群ID={group_ids}")
                            await context.bot.send_message(chat_id=chat_id, text="群组已从编队移除")
                        else:
                            await context.bot.send_message(chat_id=chat_id, text="任务目标有误请检查: 编队不存在")
                    except ValueError as e:
                        print(f"[{datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%H:%M:%S')}] 删除解析失败: {e}")
                        await context.bot.send_message(chat_id=chat_id, text=f"任务目标有误请检查: {e}")
                else:
                    await context.bot.send_message(chat_id=chat_id, text=f"仅操作员可执行此操作，请联系管理员设置权限")
            else:
                await context.bot.send_message(chat_id=chat_id, text="使用格式：删除 队名 群ID,群ID")
            return

        if message_text.startswith("编辑 "):
            parts = message_text.split(" ", 2)
            if len(parts) == 3 and parts[1] and parts[2]:
                template_name = parts[1]
                message = parts[2]
                if username and (username in operating_groups.get("private", {}) or username == initial_admin_username):
                    file_id = last_file_id.get(chat_id)
                    if file_id:
                        templates[template_name] = {"message": message, "file_id": file_id}
                        await context.bot.send_message(chat_id=chat_id, text=f"模板 {template_name} 已更新")
                    else:
                        await context.bot.send_message(chat_id=chat_id, text="请先发送动图、视频或图片以获取文件 ID")
                else:
                    await context.bot.send_message(chat_id=chat_id, text=f"仅操作员可执行此操作，请联系管理员设置权限")
            else:
                await context.bot.send_message(chat_id=chat_id, text="使用格式：编辑 模板名 广告文")

        if message_text.startswith("任务 ") or message_text == "任务列表":
            await context.bot.send_message(chat_id=chat_id, text="群发任务功能当前不可用，请升级到 SuperGrok 订阅计划以启用，详情请访问 https://x.ai/grok")

@app.route('/get_transactions/<chat_id>')
def get_transactions_api(chat_id):
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 50))
        date = request.args.get('date')
        transactions_list = transactions.get(chat_id, [])
        
        if date:
            transactions_list = [t for t in transactions_list if date in t]
        
        total = len(transactions_list)
        start = (page - 1) * per_page
        end = start + per_page
        paginated_transactions = transactions_list[start:end]
        print(f"[{datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%H:%M:%S')}] API 请求: /get_transactions/{chat_id}, page={page}, per_page={per_page}, date={date or '无'}, 返回 {len(paginated_transactions)} 条记录")
        return jsonify({
            'transactions': paginated_transactions,
            'total': total,
            'page': page,
            'per_page': per_page
        })
    except Exception as e:
        print(f"[{datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%H:%M:%S')}] API 错误: {e}")
        return jsonify({'error': str(e)}), 500

async def error_handler(update, context):
    print(f"[{datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%H:%M:%S')}] 错误: {context.error}")
    if update and update.message:
        await context.bot.send_message(
            chat_id=update.message.chat_id,
            text="抱歉，机器人遇到错误，请稍后再试或联系管理员。"
        )

def run_flask():
    flask_port = int(os.getenv("FLASK_PORT", 5001))
    print(f"[{datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%H:%M:%S')}] Starting Flask with gunicorn on port {flask_port}")
    from gunicorn.app.base import BaseApplication

    class FlaskApplication(BaseApplication):
        def __init__(self, app, options=None):
            self.options = options or {}
            self.application = app
            super().__init__()

        def load_config(self):
            for key, value in self.options.items():
                self.cfg.set(key, value)

        def load(self):
            return self.application

    options = {
        'bind': f'0.0.0.0:{flask_port}',
        'workers': 2,
        'timeout': 120,
        'accesslog': '-',
        'errorlog': '-',
    }
    FlaskApplication(app, options).run()

def run_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    app_bot = ApplicationBuilder().token(BOT_TOKEN).build()
    app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app_bot.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
    app_bot.add_error_handler(error_handler)
    app_bot.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 10000)),
        url_path=f"/{BOT_TOKEN}",
        webhook_url=f"{os.getenv('RENDER_EXTERNAL_URL')}/{BOT_TOKEN}"
    )
    print(f"[{datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%H:%M:%S')}] Bot webhook started on port {os.getenv('PORT', 10000)}")
    loop.run_forever()

if __name__ == '__main__':
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()
    run_bot()
