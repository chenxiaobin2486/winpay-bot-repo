# 导入必要的模块
from telegram.ext import Application, MessageHandler
import telegram.ext.filters
import schedule
import time
import re
import os
import asyncio

# 定义 Bot Token（从环境变量获取）
BOT_TOKEN = os.getenv("BOT_TOKEN", "7908773608:AAFFqLmGkJ9zbsuymQTFzJxy5IyeN1E9M-U")

# 定义全局变量
operators = {"8041296886": True}
transactions = []
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
    # 获取最近 6 笔交易
    recent_transactions = transactions[-6:] if len(transactions) >= 6 else transactions
    bill = "账单\n"
    deposit_count = sum(1 for t in recent_transactions if t.startswith("入款"))
    withdraw_count = sum(1 for t in recent_transactions if t.startswith("下发"))

    # 入款部分
    if deposit_count > 0:
        bill += f"入款（{deposit_count}笔）\n"
        for t in reversed([t for t in recent_transactions if t.startswith("入款")]):
            amount = float(t.split(" -> ")[0].split()[1])
            adjusted = float(t.split(" -> ")[1].split()[0])
            effective_rate = 1 - deposit_fee_rate
            amount_str = f"{int(amount)}" if amount.is_integer() else f"{amount:.2f}"
            adjusted_str = f"{int(adjusted)}" if adjusted.is_integer() else f"{adjusted:.2f}"
            bill += f"{amount_str}*{effective_rate:.2f}/{exchange_rate_deposit:.3f}={adjusted_str}u\n"

    # 出款部分（若有出款）
    if withdraw_count > 0:
        bill += f"出款（{withdraw_count}笔）\n"
        for t in reversed([t for t in recent_transactions if t.startswith("下发")]):
            amount = float(t.split(" -> ")[0].split()[1])
            adjusted = float(t.split(" -> ")[1].split()[0])
            effective_rate = 1 + withdraw_fee_rate
            amount_str = f"{int(amount)}" if amount.is_integer() else f"{amount:.2f}"
            adjusted_str = f"{int(adjusted)}" if adjusted.is_integer() else f"{adjusted:.2f}"
            bill += f"{amount_str}*{effective_rate:.2f}/{exchange_rate_withdraw:.3f}={adjusted_str}u\n"

    # 统计信息
    total_deposit = sum(float(t.split(" -> ")[0].split()[1]) for t in transactions if t.startswith("入款"))
    total_deposit_adjusted = sum(float(t.split(" -> ")[1].split()[0]) for t in transactions if t.startswith("入款"))
    total_withdraw = sum(float(t.split(" -> ")[0].split()[1]) for t in transactions if t.startswith("下发"))
    total_withdraw_adjusted = sum(float(t.split(" -> ")[1].split()[0]) for t in transactions if t.startswith("下发"))
    balance = total_deposit_adjusted - total_withdraw_adjusted
    balance_str = f"{int(balance)}" if balance.is_integer() else f"{balance:.2f}"

    bill += f"入款汇率：{exchange_rate_deposit:.3f}  |  费率：{int(deposit_fee_rate*100)}%\n"
    if withdraw_count > 0:
        bill += f"出款汇率：{exchange_rate_withdraw:.3f}  |  费率：{int(withdraw_fee_rate*100)}%\n"
    bill += f"总入款：{int(total_deposit)}  |  {int(total_deposit_adjusted)}u\n"
    if withdraw_count > 0:
        bill += f"总出款：{int(total_withdraw)}  |  {int(total_withdraw_adjusted)}u\n"
    bill += f"总余额：{balance_str}u"

    await update.message.reply_text(bill if transactions else "无交易记录")

# 处理所有消息
async def handle_message(update, context):
    global exchange_rate_deposit, deposit_fee_rate, exchange_rate_withdraw, withdraw_fee_rate
    message_text = update.message.text.strip()
    user_id = str(update.message.from_user.id)
    print(f"收到消息: '{message_text}' 从用户 {user_id}")

    if message_text == "开始":
        print("匹配到 '开始' 指令")
        user = update.message.from_user.username
        await update.message.reply_text(f"欢迎使用winpay小秘书 @{user}")
    elif message_text == "说明":
        print("匹配到 '说明' 指令")
        help_text = "可用指令：\n开始 - 开始使用\n入款 <金额> 或 +<金额> - 记录入款\n下发 <金额> - 申请下发\n设置操作员 <用户名> - 设置操作员\n设置入款汇率 <数值> - 设置入款汇率\n设置入款费率 <数值> - 设置入款费率\n设置下发汇率 <数值> - 设置下发汇率\n设置下发费率 <数值> - 设置下发费率\n账单 或 +0 - 查看交易记录\n删除 - 删除指定交易记录\n日切 - 清空记录（仅限操作员）\nTRX地址验证 - 验证TRX地址"
        await update.message.reply_text(help_text)
    elif (message_text.startswith("入款") or message_text.startswith("+")) and message_text != "+0":
        print(f"匹配到 '入款' 或 '+' 指令，金额: {message_text.replace('入款', '').replace('+', '').strip()}")
        try:
            amount = float(message_text.replace("入款", "").replace("+", "").strip())
            adjusted_amount = amount * (1 - deposit_fee_rate) / exchange_rate_deposit
            amount_str = f"{int(amount)}" if amount.is_integer() else f"{amount:.2f}"
            adjusted_str = f"{int(adjusted_amount)}" if adjusted_amount.is_integer() else f"{adjusted_amount:.2f}"
            transaction = f"入款 {amount_str} -> {adjusted_str} (由 {user_id})"
            transactions.append(transaction)
            # 直接显示账单
            await handle_bill(update, context)
        except ValueError:
            await update.message.reply_text("请输入正确金额，例如：入款1000 或 +1000")
    elif message_text.startswith("下发"):
        print(f"匹配到 '下发' 指令，金额: {message_text.replace('下发', '').strip()}")
        try:
            amount = float(message_text.replace("下发", "").strip())
            if user_id in operators:
                adjusted_amount = amount * (1 + withdraw_fee_rate) / exchange_rate_withdraw
                amount_str = f"{int(amount)}" if amount.is_integer() else f"{amount:.2f}"
                adjusted_str = f"{int(adjusted_amount)}" if adjusted_amount.is_integer() else f"{adjusted_amount:.2f}"
                transaction = f"下发 {amount_str} -> {adjusted_str} (由 {user_id})"
                transactions.append(transaction)
                # 直接显示账单
                await handle_bill(update, context)
            else:
                await update.message.reply_text("仅限操作员执行下发")
        except ValueError:
            await update.message.reply_text("请输入正确金额，例如：下发500")
    elif message_text.startswith("设置操作员"):
        print(f"匹配到 '设置操作员' 指令，用户名: {message_text.replace('设置操作员', '').strip()}")
        if user_id == "8041296886":
            operator = message_text.replace("设置操作员", "").strip()
            operators[operator] = True
            await update.message.reply_text(f"已将 @{operator} 设置为操作员")
        else:
            await update.message.reply_text("仅限最高管理员设置操作员")
    elif message_text.startswith("设置入款汇率"):
        print(f"匹配到 '设置入款汇率' 指令，汇率: {message_text.replace('设置入款汇率', '').strip()}")
        try:
            rate = float(message_text.replace("设置入款汇率", "").strip())
            exchange_rate_deposit = round(rate, 2)  # 限制两位小数
            await update.message.reply_text(f"设置成功入款汇率 {exchange_rate_deposit:.2f}")
        except ValueError:
            await update.message.reply_text("请输入正确汇率，例如：设置入款汇率0.94")
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
            exchange_rate_withdraw = round(rate, 2)  # 限制两位小数
            await update.message.reply_text(f"设置成功下发汇率 {exchange_rate_withdraw:.2f}")
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
            target_text = update.message.reply_to_message.text
            if "账单" in target_text:  # 检查是否为账单消息
                for line in target_text.split("\n"):
                    if line.startswith("入款 ") and any(str(amount) in line for amount in [t.split(" -> ")[0].split()[1] for t in transactions if t.startswith("入款")]):
                        amount_str = line.split("*")[0].split()[-1]
                        amount = float(amount_str.replace("u", ""))
                        for t in transactions[:]:
                            if t.startswith("入款"):
                                trans_amount = float(t.split(" -> ")[0].split()[1])
                                if trans_amount == amount:
                                    transactions.remove(t)
                                    adjusted = float(t.split(" -> ")[1].split()[0])
                                    adjusted_str = f"{int(adjusted)}" if adjusted.is_integer() else f"{adjusted:.2f}"
                                    await update.message.reply_text(f"入款 {amount_str} -> {adjusted_str}u 这条消息删除功能为删除这笔入款记录")
                                    return
                    elif line.startswith("下发 ") and any(str(amount) in line for amount in [t.split(" -> ")[0].split()[1] for t in transactions if t.startswith("下发")]):
                        amount_str = line.split("*")[0].split()[-1]
                        amount = float(amount_str.replace("u", ""))
                        for t in transactions[:]:
                            if t.startswith("下发"):
                                trans_amount = float(t.split(" -> ")[0].split()[1])
                                if trans_amount == amount:
                                    transactions.remove(t)
                                    adjusted = float(t.split(" -> ")[1].split()[0])
                                    adjusted_str = f"{int(adjusted)}" if adjusted.is_integer() else f"{adjusted:.2f}"
                                    await update.message.reply_text(f"下发 {amount_str} -> {adjusted_str}u 这条消息删除功能为删除这笔出款记录")
                                    return
                await update.message.reply_text("未找到对应的交易记录")
            else:
                await update.message.reply_text("请回复目标交易相关消息")
        else:
            await update.message.reply_text("请回复目标交易相关消息以删除")
    elif message_text == "日切" and user_id == "8041296886":
        print("匹配到 '日切' 指令")
        transactions.clear()
        await update.message.reply_text("交易记录已清空")
    elif re.match(r'^[T][a-km-zA-HJ-NP-Z1-9]{33}$', message_text):
        print("匹配到 TRX 地址验证")
        await update.message.reply_text("TRX地址验证成功")
    else:
        print(f"未匹配到任何指令: '{message_text}'")
        await update.message.reply_text("未知指令，请输入说明查看帮助")

# 主函数
def main():
    # 获取 Render 环境变量 PORT
    port = int(os.getenv("PORT", "10000"))
    print(f"Listening on port: {port}")

    # 使用 ApplicationBuilder 初始化并设置 Webhook
    application = Application.builder().token(BOT_TOKEN).build()

    # 注册消息处理器
    application.add_handler(MessageHandler(telegram.ext.filters.TEXT, handle_message))

    # 设置 schedule 任务
    setup_schedule()

    # 设置 Webhook（使用 Render 的公共 URL）
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
