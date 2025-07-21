# 导入必要的模块
from telegram.ext import Application, MessageHandler, filters
import telegram.ext
import schedule
import time
import re
import os
import asyncio
from datetime import datetime, timezone
import pytz
import requests

# 定义 Bot Token（从环境变量获取）
BOT_TOKEN = os.getenv("BOT_TOKEN", "7908773608:AAFFqLmGkJ9zbsuymQTFzJxy5IyeN1E9M-U")

# 定义全局变量
initial_admin_username = "WinPay06_Thomason"  # 初始最高权限管理员用户名
operators = {}  # {chat_id: {username: True}}，每个群组独立操作员列表
transactions = {}  # {chat_id: [transaction_list]}，每个群组独立记账
user_history = {}  # {chat_id: {user_id: {"username": str, "first_name": str}}}，记录成员历史
exchange_rate_deposit = 1.0
deposit_fee_rate = 0.0
exchange_rate_withdraw = 1.0
withdraw_fee_rate = 0.0
teams = {}  # {team_name: [chat_id, ...]}，存储群组编队
broadcast_config = {}  # {team_name: {"file_id": str, "ad_text": str, "times": list}}，存储群发配置，支持多次推送
retry_attempts = 3  # 重试次数

# 设置日志任务
def setup_schedule():
    schedule.clear()
    for team_name, config in broadcast_config.items():
        if "times" in config and config["times"]:
            for time_str in config["times"]:
                schedule.every().day.at(time_str).do(send_broadcast, team_name)

# 定义日志功能
async def job():
    print("执行日志任务", time.ctime())

# 账单处理函数
async def handle_bill(update, context):
    chat_id = str(update.message.chat_id)
    if chat_id not in transactions:
        transactions[chat_id] = []
    recent_transactions = transactions[chat_id][-6:] if len(transactions[chat_id]) >= 6 else transactions[chat_id]
    bill = "当前账单\n"
    deposit_count = sum(1 for t in recent_transactions if t.startswith("入款"))
    withdraw_count = sum(1 for t in recent_transactions if t.startswith("下发"))

    # 入款部分
    if deposit_count > 0:
        bill += f"入款（{deposit_count}笔）\n"
        for t in reversed([t for t in recent_transactions if t.startswith("入款")]):
            parts = t.split(" -> ")
            timestamp = parts[0].split()[2]
            operator = parts[1].split(" (")[1].rstrip(")") if len(parts) > 1 and " (" in parts[1] else "未知操作员"
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
            operator = parts[1].split(" (")[1].rstrip(")") if len(parts) > 1 and " (" in parts[1] else "未知操作员"
            if "u" in parts[0]:
                amount = float(parts[0].split()[1].rstrip('u'))
                bill += f"{timestamp}  {format_amount(amount)}u ({operator})\n"
            else:
                amount = float(parts[0].split()[1])
                adjusted = float(parts[1].split()[0].rstrip('u'))
                effective_rate = 1 + withdraw_fee_rate
                bill += f"{timestamp}  {format_amount(amount)}*{effective_rate:.2f}/{format_exchange_rate(exchange_rate_withdraw)}={format_amount(adjusted)}u ({operator})\n"

    # 统计信息
    if deposit_count > 0 or withdraw_count > 0:
        if deposit_count > 0 or withdraw_count > 0:
            bill += "\n"
        if deposit_count > 0:
            bill += f"入款汇率：{format_exchange_rate(exchange_rate_deposit)}  |  费率：{int(deposit_fee_rate*100)}%\n"
        if withdraw_count > 0:
            bill += f"出款汇率：{format_exchange_rate(exchange_rate_withdraw)}  |  费率：{int(withdraw_fee_rate*100)}%\n"
        if deposit_count > 0 or withdraw_count > 0:
            bill += "\n"
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
async def welcome_new_member(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    if chat_id not in user_history:
        user_history[chat_id] = {}
    if update.message and update.message.new_chat_members:
        for member in update.message.new_chat_members:
            user_id = str(member.id)
            username = member.username
            first_name = member.first_name.strip() if member.first_name else None
            user_history[chat_id][user_id] = {"username": username, "first_name": first_name}
            nickname = first_name or username or "新朋友"
            await update.message.reply_text(f"欢迎 {nickname} 来到本群")

# 优化后的群发消息推送
async def send_broadcast(team_name):
    if team_name in teams and team_name in broadcast_config:
        config = broadcast_config[team_name]
        file_id = config["file_id"]
        ad_text = config["ad_text"]
        target_chats = teams[team_name]
        success_count = 0
        failed_chats = []

        async def send_to_chat(chat_id):
            nonlocal success_count, failed_chats
            for attempt in range(retry_attempts):
                try:
                    if file_id.startswith("video"):
                        await context.bot.send_video(chat_id=chat_id, video=file_id, caption=ad_text)
                    else:
                        await context.bot.send_animation(chat_id=chat_id, animation=file_id, caption=ad_text)
                    success_count += 1
                    break
                except telegram.error.RetryAfter as e:
                    await asyncio.sleep(e.retry_after)
                except telegram.error.NetworkError:
                    if attempt < retry_attempts - 1:
                        await asyncio.sleep(2 ** attempt)  # 指数退避
                    else:
                        failed_chats.append(chat_id)
                except Exception as e:
                    print(f"发送到 {chat_id} 失败: {e}")
                    failed_chats.append(chat_id)
                    break

        await asyncio.gather(*(send_to_chat(chat_id) for chat_id in target_chats))
        operator_chat_id = next(iter(operators.keys()))  # 使用第一个操作员的 chat_id 反馈
        status_msg = f"群发完成 - 队 {team_name}\n成功: {success_count}/{len(target_chats)}"
        if failed_chats:
            status_msg += f"\n失败群组: {failed_chats}"
        await context.bot.send_message(chat_id=operator_chat_id, text=status_msg)

# 处理所有消息
async def handle_message(update, context):
    global exchange_rate_deposit, deposit_fee_rate, exchange_rate_withdraw, withdraw_fee_rate, operators, transactions, user_history, teams, broadcast_config
    message_text = update.message.text.strip()
    chat_id = str(update.message.chat_id)
    user_id = str(update.message.from_user.id)
    username = update.message.from_user.username
    first_name = update.message.from_user.first_name.strip() if update.message.from_user.first_name else None
    operator_name = first_name or "未知用户"
    print(f"收到消息: '{message_text}' 从用户 {user_id}, username: {username}, chat_id: {chat_id}, 类型: {update.message.chat.type}")
    print(f"当前操作员列表: {operators.get(chat_id, {})}")

    if chat_id not in operators:
        operators[chat_id] = {initial_admin_username: True}
    if chat_id not in transactions:
        transactions[chat_id] = []
    if chat_id not in user_history:
        user_history[chat_id] = {}

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
            print(f"用户名变更警告: {first_name}, 之前 @{old_username}, 现在 @{username}")
        elif first_name and first_name != old_first_name and username == old_username:
            await update.message.reply_text(
                f"⚠️警告⚠️@{username} 昵称不一致\n之前昵称{old_first_name}\n现在昵称{first_name}\n请注意查证‼️"
            )
            print(f"昵称变更警告: @{username}, 之前 {old_first_name}, 现在 {first_name}")
        user_history[chat_id][user_id] = {"username": username, "first_name": first_name}

    # 记账相关指令（私聊和群组均有效）
    if (message_text in ["开始", "说明", "账单", "+0", "操作员列表", "删除账单", "日切"] or
        message_text.startswith(("入款", "+", "下发", "设置操作员", "删除操作员", "设置入款汇率",
                                "设置入款费率", "设置下发汇率", "设置下发费率"))):
        if not username or username not in operators.get(chat_id, {}):
            print(f"用户 {username} 没有操作员权限")
            return
        print(f"用户 {username} 有权限，处理指令: {message_text}")
        if message_text == "开始":
            print("匹配到 '开始' 指令")
            await update.message.reply_text("欢迎使用winpay小秘书")
        elif message_text == "说明":
            print("匹配到 '说明' 指令")
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
            print(f"匹配到 '入款' 或 '+' 指令，金额: {message_text.replace('入款', '').replace('+', '').strip()}")
            try:
                amount_str = message_text.replace("入款", "").replace("+", "").strip()
                beijing_tz = pytz.timezone("Asia/Shanghai")
                utc_time = update.message.date.replace(tzinfo=timezone.utc)
                timestamp = utc_time.astimezone(beijing_tz).strftime("%H:%M")
                if amount_str.lower().endswith('u'):
                    amount = float(amount_str.rstrip('uU'))
                    transaction = f"入款 {format_amount(amount)}u {timestamp} -> {format_amount(amount)}u ({operator_name})"
                else:
                    amount = float(amount_str)
                    adjusted_amount = amount * (1 - deposit_fee_rate) / exchange_rate_deposit
                    transaction = f"入款 {format_amount(amount)} {timestamp} -> {format_amount(adjusted_amount)}u ({operator_name})"
                transactions[chat_id].append(transaction)
                print(f"交易记录添加: {transaction}")
                await handle_bill(update, context)
            except ValueError:
                await update.message.reply_text("请输入正确金额，例如：入款1000 或 +1000 或 +100u")
        elif message_text.startswith("下发"):
            print(f"匹配到 '下发' 指令，金额: {message_text.replace('下发', '').strip()}")
            try:
                amount_str = message_text.replace("下发", "").strip()
                beijing_tz = pytz.timezone("Asia/Shanghai")
                utc_time = update.message.date.replace(tzinfo=timezone.utc)
                timestamp = utc_time.astimezone(beijing_tz).strftime("%H:%M")
                if amount_str.lower().endswith('u'):
                    amount = float(amount_str.rstrip('uU'))
                    transaction = f"下发 {format_amount(amount)}u {timestamp} -> {format_amount(amount)}u ({operator_name})"
                else:
                    amount = float(amount_str)
                    adjusted_amount = amount * (1 + withdraw_fee_rate) / exchange_rate_withdraw
                    transaction = f"下发 {format_amount(amount)} {timestamp} -> {format_amount(adjusted_amount)}u ({operator_name})"
                transactions[chat_id].append(transaction)
                print(f"交易记录添加: {transaction}")
                await handle_bill(update, context)
            except ValueError:
                await update.message.reply_text("请输入正确金额，例如：下发500 或 下发50u")
        elif message_text.startswith("设置操作员"):
            print(f"匹配到 '设置操作员' 指令，参数: {message_text.replace('设置操作员', '').strip()}")
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
            print(f"匹配到 '删除操作员' 指令，参数: {message_text.replace('删除操作员', '').strip()}")
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
            print(f"匹配到 '设置入款汇率' 指令，汇率: {message_text.replace('设置入款汇率', '').strip()}")
            try:
                rate = float(message_text.replace("设置入款汇率", "").strip())
                exchange_rate_deposit = round(rate, 3)
                await update.message.reply_text(f"设置成功入款汇率 {format_exchange_rate(exchange_rate_deposit)}")
            except ValueError:
                await update.message.reply_text("请输入正确汇率，例如：设置入款汇率0.98")
        elif message_text.startswith("设置入款费率"):
            print(f"匹配到 '设置入款费率' 指令，费率: {message_text.replace('设置入款费率', '').strip()}")
            try:
                rate = float(message_text.replace("设置入款费率", "").strip()) / 100
                deposit_fee_rate = rate
                await update.message.reply_text(f"设置成功入款费率 {int(rate*100)}%")
            except ValueError:
                await update.message.reply_text("请输入正确费率，例如：设置入款费率8")
        elif message_text.startswith("设置下发汇率"):
            print(f"匹配到 '设置下发汇率' 指令，汇率: {message_text.replace('设置下发汇率', '').strip()}")
            try:
                rate = float(message_text.replace("设置下发汇率", "").strip())
                exchange_rate_withdraw = round(rate, 3)
                await update.message.reply_text(f"设置成功下发汇率 {format_exchange_rate(exchange_rate_withdraw)}")
            except ValueError:
                await update.message.reply_text("请输入正确汇率，例如：设置下发汇率1.25")
        elif message_text.startswith("设置下发费率"):
            print(f"匹配到 '设置下发费率' 指令，费率: {message_text.replace('设置下发费率', '').strip()}")
            try:
                rate = float(message_text.replace("设置下发费率", "").strip()) / 100
                withdraw_fee_rate = rate
                await update.message.reply_text(f"设置成功下发费率 {int(rate*100)}%")
            except ValueError:
                await update.message.reply_text("请输入正确费率，例如：设置下发费率8")
        elif message_text == "账单" or message_text == "+0":
            print("匹配到 '账单' 或 '+0' 指令")
            await handle_bill(update, context)
        elif message_text == "删除":
            print("匹配到 '删除' 指令")
            if update.message.reply_to_message:
                original_message = update.message.reply_to_message.text.strip()
                print(f"尝试删除，原始消息: '{original_message}'")
                print(f"当前交易记录: {transactions.get(chat_id, [])}")
                if original_message.startswith("+") and not original_message == "+0":
                    amount_match = re.search(r'\+(\d+\.?\d*)[uU]?', original_message)
                    if amount_match:
                        amount = float(amount_match.group(1))
                        has_u = 'u' in original_message.lower()
                        for t in transactions[chat_id][:]:
                            if t.startswith("入款"):
                                t_parts = t.split(" -> ")[0].split()
                                t_amount_str = t_parts[1].rstrip('u')
                                t_amount = float(t_amount_str)
                                t_has_u = t_amount_str.endswith('u')
                                if abs(t_amount - amount) < 0.01 and has_u == t_has_u:  # 允许微小浮点误差
                                    transactions[chat_id].remove(t)
                                    await update.message.reply_text(f"入款 {format_amount(amount)}{'u' if has_u else ''} 已被撤销")
                                    return
                elif original_message.startswith("下发"):
                    amount_match = re.search(r'下发\s*(\d+\.?\d*)[uU]?', original_message)
                    if amount_match:
                        amount = float(amount_match.group(1))
                        has_u = 'u' in original_message.lower().split()[1] if len(original_message.split()) > 1 else False
                        for t in transactions[chat_id][:]:
                            if t.startswith("下发"):
                                t_parts = t.split(" -> ")[0].split()
                                t_amount_str = t_parts[1].rstrip('u')
                                t_amount = float(t_amount_str)
                                t_has_u = t_amount_str.endswith('u')
                                if abs(t_amount - amount) < 0.01 and has_u == t_has_u:  # 允许微小浮点误差
                                    transactions[chat_id].remove(t)
                                    await update.message.reply_text(f"下发 {format_amount(amount)}{'u' if has_u else ''} 已被撤销")
                                    return
                await update.message.reply_text("无法撤销此消息，请确保回复正确的入款或下发记录")
            else:
                await update.message.reply_text("请回复目标交易相关消息以删除")
        elif message_text == "删除账单":
            print("匹配到 '删除账单' 指令")
            transactions[chat_id].clear()
            await update.message.reply_text("本日账单已结算，重新开始记账")
        elif message_text == "日切" and username == initial_admin_username:
            if username in operators.get(chat_id, {}):
                print("匹配到 '日切' 指令")
                transactions[chat_id].clear()
                await update.message.reply_text("交易记录已清空")
        elif message_text == "操作员列表":
            print("匹配到 '操作员列表' 指令")
            op_list = ", ".join([f"@{op}" for op in operators.get(chat_id, {})])
            await update.message.reply_text(f"当前操作员列表: {op_list}" if op_list else "当前无操作员")
        elif re.match(r'^[T][a-km-zA-HJ-NP-Z1-9]{33}$', message_text):
            print("匹配到 TRX 地址验证")
            await update.message.reply_text("TRX地址验证成功")

    # 群发相关指令（仅私聊有效）
    elif update.message.chat.type == 'private':
        if username and username in operators.get(chat_id, {}):
            if message_text.startswith("编队") or message_text.startswith(tuple(f"{team} " for team in teams.keys())) or message_text.startswith(("群发", "查询群发", "预览", "ID")):
                if message_text.startswith("编队"):
                    print(f"匹配到 '编队' 指令，参数: {message_text.replace('编队', '').strip()}")
                    try:
                        parts = message_text.replace("编队", "").strip().split(" ", 1)
                        if len(parts) == 2:
                            team_name = parts[0].strip()
                            chat_ids = [int(x.strip()) for x in parts[1].split(",")]
                            teams[team_name] = chat_ids
                            await update.message.reply_text(f"已创建或更新队 {team_name}: {chat_ids}")
                        else:
                            await update.message.reply_text("格式错误，请使用：编队 (队名) 群ID,群ID")
                    except ValueError:
                        await update.message.reply_text("群ID必须为数字")
                elif any(message_text.startswith(f"{team} ") for team in teams.keys()):
                    print(f"匹配到队管理指令，参数: {message_text}")
                    parts = message_text.split(" ", 1)
                    team_name = parts[0]
                    action = parts[1].split()[0] if len(parts) > 1 else ""
                    chat_ids = [int(x.strip()) for x in parts[1].split()[1].split(",")] if len(parts) > 1 and len(parts[1].split()) > 1 else []
                    if action == "添加" and team_name in teams:
                        teams[team_name].extend(chat_ids)
                        teams[team_name] = list(set(teams[team_name]))  # 去除重复
                        await update.message.reply_text(f"已向 {team_name} 队添加: {chat_ids}")
                    elif action == "删除" and team_name in teams:
                        teams[team_name] = [cid for cid in teams[team_name] if cid not in chat_ids]
                        await update.message.reply_text(f"已从 {team_name} 队删除: {chat_ids}")
                    else:
                        await update.message.reply_text(f"格式错误，请使用：(队名) 添加 群ID,群ID 或 (队名) 删除 群ID,群ID")
                elif message_text.startswith("群发"):
                    print(f"匹配到 '群发' 指令，参数: {message_text.replace('群发', '').strip()}")
                    if update.message.reply_to_message:
                        reply_msg = update.message.reply_to_message
                        ad_text = reply_msg.text or ""
                        if reply_msg.animation:
                            file_id = reply_msg.animation.file_id
                            file = await context.bot.get_file(file_id)
                            await file.download_to_drive()  # 验证文件可用性
                        elif reply_msg.video:
                            file_id = reply_msg.video.file_id
                            file = await context.bot.get_file(file_id)
                            await file.download_to_drive()  # 验证文件可用性
                        else:
                            await update.message.reply_text("请回复包含动图或视频的消息")
                            return
                        parts = message_text.replace("群发", "").strip().split()
                        if len(parts) >= 2:
                            team_name = parts[0]
                            times = parts[1:]  # 支持多个时间
                            if team_name in teams:
                                valid_times = []
                                for time_str in times:
                                    if time_str == "-1":
                                        if team_name in broadcast_config:
                                            del broadcast_config[team_name]
                                            schedule.clear()
                                            setup_schedule()
                                            await update.message.reply_text(f"已取消 {team_name} 队的群发设置")
                                        else:
                                            await update.message.reply_text(f"{team_name} 队无群发设置")
                                        return
                                    try:
                                        datetime.strptime(time_str, "%H:%M")
                                        valid_times.append(time_str)
                                    except ValueError:
                                        await update.message.reply_text(f"时间 {time_str} 格式错误，请使用 HH:MM")
                                        return
                                if valid_times:
                                    broadcast_config[team_name] = {
                                        "file_id": file_id,
                                        "ad_text": ad_text,
                                        "times": valid_times
                                    }
                                    schedule.clear()
                                    setup_schedule()
                                    await update.message.reply_text(f"已为 {team_name} 队设置群发: {', '.join(valid_times)}")
                            else:
                                await update.message.reply_text(f"队 {team_name} 不存在")
                        else:
                            await update.message.reply_text("格式错误，请使用：群发 队名 时间1 时间2 ... 或 群发 队名 -1")
                    else:
                        await update.message.reply_text("请回复包含动图或视频的消息")
                elif message_text == "查询群发":
                    print("匹配到 '查询群发' 指令")
                    if broadcast_config:
                        response = "当前群发设置:\n"
                        for team, config in broadcast_config.items():
                            if config["times"]:
                                for time_str in config["times"]:
                                    response += f"{team} - {time_str} - [{'视频' if config['file_id'].startswith('video') else '动图'}预览] {config['file_id']}\n{config['ad_text']}\n"
                        await update.message.reply_text(response.strip())
                    else:
                        await update.message.reply_text("暂无群发设置")
                elif message_text == "预览":
                    print("匹配到 '预览' 指令")
                    if chat_id in broadcast_config and broadcast_config[chat_id]["times"]:
                        config = broadcast_config[chat_id]
                        preview_text = f"[{'视频' if config['file_id'].startswith('video') else '动图'}预览] {config['file_id']}\n{config['ad_text']}"
                        await update.message.reply_text(preview_text)
                    else:
                        await update.message.reply_text("暂无群发设置或已取消")
                elif message_text == "ID":
                    print("匹配到 'ID' 指令")
                    if update.message.reply_to_message:
                        reply_msg = update.message.reply_to_message
                        if reply_msg.animation:
                            file_id = reply_msg.animation.file_id
                            await update.message.reply_text(f"文件 ID: {file_id}")
                        elif reply_msg.video:
                            file_id = reply_msg.video.file_id
                            await update.message.reply_text(f"文件 ID: {file_id}")
                        else:
                            await update.message.reply_text("请回复包含动图或视频的消息")
                    else:
                        await update.message.reply_text("请回复包含动图或视频的消息")
            elif message_text == "群发说明":
                print("匹配到 '群发说明' 指令")
                if username in operators.get(chat_id, {}):
                    help_text = """
群发相关指令：
编队 (队名) 群ID,群ID        - 创建或覆盖指定队的群组
(队名) 添加 群ID,群ID        - 向指定队添加群组
(队名) 删除 群ID,群ID        - 从指定队删除群组
群发 队名 时间                - 设置队名定时发送广告（时间格式: HH:MM）
群发 队名 -1                  - 取消指定队的群发设置
查询群发                      - 查看当前所有群发设置
预览                          - 查看当前广告内容预览
ID                            - 回复动图/视频消息获取文件 ID
                    """
                    await update.message.reply_text(help_text)
                else:
                    await update.message.reply_text("您没有权限查看群发说明")

# 主函数
def main():
    port = int(os.getenv("PORT", "10000"))
    print(f"Listening on port: {port}")

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
    application.add_handler(MessageHandler(telegram.ext.filters.TEXT, handle_message))

    setup_schedule()

    external_url = os.getenv("RENDER_EXTERNAL_URL", "winpay-bot-repo.onrender.com").strip()
    if not external_url:
        print("错误：RENDER_EXTERNAL_URL 未设置")
        return
    if not external_url.startswith("http"):
        webhook_url = f"https://{external_url}/webhook"
    else:
        webhook_url = external_url + "/webhook"
    print(f"设置 Webhook URL: {webhook_url}")
    try:
        print("尝试启动 Webhook...")
        application.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path="/webhook",
            webhook_url=webhook_url
        )
    except Exception as e:
        print(f"Webhook 设置失败: {e}")

if __name__ == '__main__':
    main()
