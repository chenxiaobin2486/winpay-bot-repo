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
exchange_rate_withdraw = 1.0
fee_rate = 0.0

# 处理所有消息
async def handle_message(update, context):
    message_text = update.message.text.strip()
    user_id = str(update.message.from_user.id)

    if message_text == "开始":
        user = update.message.from_user.username
        await update.message.reply_text(f"欢迎使用winpay小秘书 @{user}")
    elif message_text == "说明":
        help_text = "可用指令：\n开始 - 开始使用\n入款 <金额> - 记录入款\n下发 <金额> - 申请下发\n设置操作员 <用户名> - 设置操作员\n设置入款汇率 <数值> - 设置入款汇率\n设置下发汇率 <数值> - 设置下发汇率\n设置费率 <数值> - 设置费率\n账单 - 查看交易记录\n删除入款 - 删除最新入款\n日切 - 清空记录（仅限操作员）\nTRX地址验证 - 验证TRX地址"
        await update.message.reply_text(help_text)
    elif message_text.startswith("入款"):
        try:
            amount = float(message_text.replace("入款", "").strip())
            adjusted_amount = amount * exchange_rate_deposit * (1 - fee_rate)
            transactions.append(f"入款 {amount} -> {adjusted_amount} (由 {user_id})")
            await update.message.reply_text(f"入款 {amount} 记录成功，调整后金额：{adjusted_amount}")
        except ValueError:
            await update.message.reply_text("请输入正确金额，例如：入款1000")
    elif message_text.startswith("下发"):
        try:
            amount = float(message_text.replace("下发", "").strip())
            if user_id in operators:
                adjusted_amount = amount * exchange_rate_withdraw * (1 - fee_rate)
                transactions.append(f"下发 {amount} -> {adjusted_amount} (由 {user_id})")
                await update.message.reply_text(f"下发 {amount} 申请成功，调整后金额：{adjusted_amount}")
            else:
                await update.message.reply_text("仅限操作员执行下发")
        except ValueError:
            await update.message.reply_text("请输入正确金额，例如：下发500")
    elif message_text.startswith("设置操作员"):
        if user_id == "8041296886":
            operator = message_text.replace("设置操作员", "").strip()
            operators[operator] = True
            await update.message.reply_text(f"已将 @{operator} 设置为操作员")
        else:
            await update.message.reply_text("仅限最高管理员设置操作员")
    elif message_text.startswith("设置入款汇率"):
        try:
            rate = float(message_text.replace("设置入款汇率", "").strip())
            exchange_rate_deposit = rate
            await update.message.reply_text(f"入款汇率设置为 {rate}")
        except ValueError:
            await update.message.reply_text("请输入正确汇率，例如：设置入款汇率1.5")
    elif message_text.startswith("设置下发汇率"):
        try:
            rate = float(message_text.replace("设置下发汇率", "").strip())
            exchange_rate_withdraw = rate
            await update.message.reply_text(f"下发汇率设置为 {rate}")
        except ValueError:
            await update.message.reply_text("请输入正确汇率，例如：设置下发汇率1.5")
    elif message_text.startswith("设置费率"):
        try:
            rate = float(message_text.replace("设置费率", "").strip())
            fee_rate = rate
            await update.message.reply_text(f"费率设置为 {rate}")
        except ValueError:
            await update.message.reply_text("请输入正确费率，例如：设置费率0.05")
    elif message_text == "账单":
        await update.message.reply_text("\n".join(transactions) if transactions else "无交易记录")
    elif message_text == "删除入款":
        if transactions and transactions[-1].startswith("入款"):
            removed = transactions.pop()
            await update.message.reply_text(f"已删除最新入款记录：{removed}")
        else:
            await update.message.reply_text("无入款记录可删除")
    elif message_text == "日切" and user_id == "8041296886":
        transactions.clear()
        await update.message.reply_text("交易记录已清空")
    elif re.match(r'^[T][a-km-zA-HJ-NP-Z1-9]{33}$', message_text):
        await update.message.reply_text("TRX地址验证成功")
    else:
        await update.message.reply_text("未知指令，请输入说明查看帮助")

# 定义日志功能
async def job():
    print("执行日志任务", time.ctime())

# 设置日志任务
def setup_schedule():
    schedule.every().day.at("00:00").do(lambda: asyncio.run(job()))

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
    external_url = os.getenv("RENDER_EXTERNAL_URL", "winpay-bot-repo.onrender.com")
    if not external_url:
        print("错误：RENDER_EXTERNAL_URL 未设置")
        return
    webhook_url = f"https://{external_url}/webhook"
    print(f"设置 Webhook URL: {webhook_url}")
    try:
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
