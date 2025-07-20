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

# 设置日志任务
def setup_schedule():
    schedule.every().day.at("00:00").do(lambda: asyncio.run(job()))

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

    if deposit_count > 0:
        bill += f"入款（{deposit_count}笔）\n"
        for t in reversed([t for t in recent_transactions if t.startswith("入款")]):
            parts = t.split(" -> ")
            amount = float(parts[0].split()[1].rstrip('u'))
            adjusted = float(parts[1].split()[0].rstrip('u'))
            timestamp = parts[0].split()[2]
            operator = parts[1].split(" (由 ")[1].rstrip(")")
            effective_rate = 1 - deposit_fee_rate
            amount_str = f"{int(amount)}" if amount.is_integer() else f"{amount:.2f}"
            adjusted_str = f"{int(adjusted)}" if adjusted.is_integer() else f"{adjusted:.2f}"
            bill += f"{timestamp}  {amount_str}*{effective_rate:.2f}/{format_exchange_rate(exchange_rate_deposit)}={adjusted_str}u  ({operator})\n"

    if withdraw_count > 0:
        bill += f"出款（{withdraw_count}笔）\n"
        for t in reversed([t for t in recent_transactions if t.startswith("下发")]):
            parts = t.split(" -> ")
            amount = float(parts[0].split()[1].rstrip('u'))
            adjusted = float(parts[1].split()[0].rstrip('u'))
            timestamp = parts[0].split()[2]
            operator = parts[1].split(" (由 ")[1].rstrip(")")
            effective_rate = 1 + withdraw_fee_rate
            amount_str = f"{int(amount)}" if amount.is_integer() else f"{amount:.2f}"
            adjusted_str = f"{int(adjusted)}" if adjusted.is_integer() else f"{adjusted:.2f}"
            bill += f"{timestamp}  {amount_str}*{effective_rate:.2f}/{format_exchange_rate(exchange_rate_withdraw)}={adjusted_str}u  ({operator})\n"

    total_deposit = sum(float(t.split(" -> ")[0].split()[1].rstrip('u')) for t in transactions[chat_id] if t.startswith("入款"))
    total_deposit_adjusted = sum(float(t.split(" -> ")[1].split()[0].rstrip('u')) for t in transactions[chat_id] if t.startswith("入款"))
    total_withdraw = sum(float(t.split(" -> ")[0].split()[1].rstrip('u')) for t in transactions[chat_id] if t.startswith("下发"))
    total_withdraw_adjusted = sum(float(t.split(" -> ")[1].split()[0].rstrip('u')) for t in transactions[chat_id] if t.startswith("下发"))
    balance = total_deposit_adjusted - total_withdraw_adjusted
    balance_str = f"{int(balance)}" if balance.is_integer() else f"{balance:.2f}"

    bill += f"\n入款汇率：{format_exchange_rate(exchange_rate_deposit)}  |  费率：{int(deposit_fee_rate*100)}%\n"
    if withdraw_count > 0:
        bill += f"出款汇率：{format_exchange_rate(exchange_rate_withdraw)}  |  费率：{int(withdraw_fee_rate*100)}%\n"
    if deposit_count > 0:
        bill += f"总入款：{int(total_deposit)}  |  {int(total_deposit_adjusted)}u\n"
    if withdraw_count > 0:
        bill += f"总出款：{int(total_withdraw)}  |  {int(total_withdraw_adjusted)}u\n"
    bill += f"总余额：{balance_str}u"

    await update.message.reply_text(bill if transactions[chat_id] else "无交易记录")

# 格式化汇率函数
def format_exchange_rate(rate):
    return f"{rate:.3f}" if abs(rate * 1000 % 10) >= 1 else f"{rate:.2f}"

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

# 处理所有消息
async def handle_message(update, context):
    global exchange_rate_deposit, deposit_fee_rate, exchange_rate_withdraw, withdraw_fee_rate, operators, transactions, user_history
    message_text = update.message.text.strip()
    chat_id = str(update.message.chat_id)
    user_id = str(update.message.from_user.id)
    username = update.message.from_user.username
    first_name = update.message.from_user.first_name.strip() if update.message.from_user.first_name else None
    operator_name = first_name or "未知用户"
    print(f"收到消息: '{message_text}' 从用户 {user_id}, username: {username}, chat_id: {chat_id}")
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

    if message_text == "开始":
        if username and username in operators.get(chat_id, {}):
            print("匹配到 '开始' 指令")
            await update.message.reply_text("欢迎使用winpay小秘书")
    elif message_text == "说明":
        if username and username in operators.get(chat_id, {}):
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
        if username and username in operators.get(chat_id, {}):
            print(f"匹配到 '入款' 或 '+' 指令，金额: {message_text.replace('入款', '').replace('+', '').strip()}")
            try:
                amount_str = message_text.replace("入款", "").replace("+", "").strip()
                beijing_tz = pytz.timezone("Asia/Shanghai")
                utc_time = update.message.date.replace(tzinfo=timezone.utc)
                timestamp = utc_time.astimezone(beijing_tz).strftime("%H:%M")
                if amount_str.lower().endswith('u'):
                    amount = float(amount_str.rstrip('uU'))
                    transaction = f"入款 {amount}u {timestamp} -> {amount}u (由 {operator_name})"
                else:
                    amount = float(amount_str)
                    adjusted_amount = amount * (1 - deposit_fee_rate) / exchange_rate_deposit
                    amount_str = f"{int(amount)}" if amount.is_integer() else f"{amount:.2f}"
                    adjusted_str = f"{int(adjusted_amount)}" if adjusted_amount.is_integer() else f"{adjusted_amount:.2f}"
                    transaction = f"入款 {amount_str} {timestamp} -> {adjusted_str}u (由 {operator_name})"
                transactions[chat_id].append(transaction)
                await handle_bill(update, context)
            except ValueError:
                await update.message.reply_text("请输入正确金额，例如：入款1000 或 +1000 或 +100u")
    elif message_text.startswith("下发"):
        if username and username in operators.get(chat_id, {}):
            print(f"匹配到 '下发' 指令，金额: {message_text.replace('下发', '').strip()}")
            try:
                amount_str = message_text.replace("下发", "").strip()
                beijing_tz = pytz.timezone("Asia/Shanghai")
                utc_time = update.message.date.replace(tzinfo=timezone.utc)
                timestamp = utc_time.astimezone(beijing_tz).strftime("%H:%M")
                if amount_str.lower().endswith('u'):
                    amount = float(amount_str.rstrip('uU'))
                    transaction = f"下发 {amount}u {timestamp} -> {amount}u (由 {operator_name})"
                    transactions[chat_id].append(transaction)
                    await handle_bill(update, context)
                else:
                    amount = float(amount_str)
                    adjusted_amount = amount * (1 + withdraw_fee_rate) / exchange_rate_withdraw
                    amount_str = f"{int(amount)}" if amount.is_integer() else f"{amount:.2f}"
                    adjusted_str = f"{int(adjusted_amount)}" if adjusted_amount.is_integer() else f"{adjusted_amount:.2f}"
                    transaction = f"下发 {amount_str} {timestamp} -> {adjusted_str}u (由 {operator_name})"
                    transactions[chat_id].append(transaction)
                    await handle_bill(update, context)
            except ValueError:
                await update.message.reply_text("请输入正确金额，例如：下发500 或 下发50u")
    elif message_text.startswith("设置操作员"):
        if username and username in operators.get(chat_id, {}):
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
        if username and username in operators.get(chat_id, {}):
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
        if username and username in operators.get(chat_id, {}):
            print(f"匹配到 '设置入款汇率' 指令，汇率: {message_text.replace('设置入款汇率', '').strip()}")
            try:
                rate = float(message_text.replace("设置入款汇率", "").strip())
                exchange_rate_deposit = round(rate, 3)
                await update.message.reply_text(f"设置成功入款汇率 {format_exchange_rate(exchange_rate_deposit)}")
            except ValueError:
                await update.message.reply_text("请输入正确汇率，例如：设置入款汇率0.98")
    elif message_text.startswith("设置入款费率"):
        if username and username in operators.get(chat_id, {}):
            print(f"匹配到 '设置入款费率' 指令，费率: {message_text.replace('设置入款费率', '').strip()}")
            try:
                rate = float(message_text.replace("设置入款费率", "").strip()) / 100
                deposit_fee_rate = rate
                await update.message.reply_text(f"设置成功入款费率 {int(rate*100)}%")
            except ValueError:
                await update.message.reply_text("请输入正确费率，例如：设置入款费率8")
    elif message_text.startswith("设置下发汇率"):
        if username and username in operators.get(chat_id, {}):
            print(f"匹配到 '设置下发汇率' 指令，汇率: {message_text.replace('设置下发汇率', '').strip()}")
            try:
                rate = float(message_text.replace("设置下发汇率", "").strip())
                exchange_rate_withdraw = round(rate, 3)
                await update.message.reply_text(f"设置成功下发汇率 {format_exchange_rate(exchange_rate_withdraw)}")
            except ValueError:
                await update.message.reply_text("请输入正确汇率，例如：设置下发汇率1.25")
    elif message_text.startswith("设置下发费率"):
        if username and username in operators.get(chat_id, {}):
            print(f"匹配到 '设置下发费率' 指令，费率: {message_text.replace('设置下发费率', '').strip()}")
            try:
                rate = float(message_text.replace("设置下发费率", "").strip()) / 100
                withdraw_fee_rate = rate
                await update.message.reply_text(f"设置成功下发费率 {int(rate*100)}%")
            except ValueError:
                await update.message.reply_text("请输入正确费率，例如：设置下发费率8")
    elif message_text == "账单" or message_text == "+0":
        if username and username in operators.get(chat_id, {}):
            print("匹配到 '账单' 或 '+0' 指令")
            await handle_bill(update, context)
    elif message_text == "删除":
        if username and username in operators.get(chat_id, {}):
            print("匹配到 '删除' 指令")
            if update.message.reply_to_message:
                original_message = update.message.reply_to_message.text.strip()
                print(f"尝试删除，原始消息: '{original_message}'")
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
                                await update.message.reply_text(f"入款 {int(amount)}{'u' if has_u else ''} 已被撤销")
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
                                await update.message.reply_text(f"下发 {int(amount)}{'u' if has_u else ''} 已被撤销")
                                return
                await update.message.reply_text("无法撤销此消息，请确保回复正确的入款或下发记录")
            else:
                await update.message.reply_text("请回复目标交易相关消息以删除")
    elif message_text == "删除账单":
        if username and username in operators.get(chat_id, {}):
            print("匹配到 '删除账单' 指令")
            transactions[chat_id].clear()
            await update.message.reply_text("账单已清空，重新记账开始")
    elif message_text == "日切" and username == initial_admin_username:
        if username in operators.get(chat_id, {}):
            print("匹配到 '日切' 指令")
            transactions[chat_id].clear()
            await update.message.reply_text("交易记录已清空")
    elif message_text == "操作员列表":
        if username and username in operators.get(chat_id, {}):
            print("匹配到 '操作员列表' 指令")
            op_list = ", ".join([f"@{op}" for op in operators.get(chat_id, {})])
            await update.message.reply_text(f"当前操作员列表: {op_list}" if op_list else "当前无操作员")
    elif re.match(r'^[T][a-km-zA-HJ-NP-Z1-9]{33}$', message_text):
        print("匹配到 TRX 地址验证")
        await update.message.reply_text("TRX地址验证成功")

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
