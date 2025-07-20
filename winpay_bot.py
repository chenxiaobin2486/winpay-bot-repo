# 導入必要的模組
from telegram.ext import Application, MessageHandler
import telegram.ext.filters
import schedule
import time
import re
import os
import asyncio

# 定義 Bot Token（從環境變量獲取）
BOT_TOKEN = os.getenv("BOT_TOKEN", "7908773608:AAFFqLmGkJ9zbsuymQTFzJxy5IyeN1E9M-U")

# 定義全局變量
operators = {"8041296886": True}
transactions = []
exchange_rate_deposit = 1.0
exchange_rate_withdraw = 1.0
fee_rate = 0.0

# 處理所有訊息
async def handle_message(update, context):
    message_text = update.message.text.strip()
    user_id = str(update.message.from_user.id)

    if message_text == "開始":
        user = update.message.from_user.username
        await update.message.reply_text(f"歡迎使用winpay小秘书 @{user}")
    elif message_text == "說明":
        help_text = "可用指令：\n開始 - 開始使用\n入款 <金額> - 記錄入款\n下發 <金額> - 申請下發\n設置操作員 <用戶名> - 設置操作員\n設置入款匯率 <數值> - 設置入款匯率\n設置下發匯率 <數值> - 設置下發匯率\n設置費率 <數值> - 設置費率\n帳單 - 查看交易記錄\n刪除入款 - 刪除最新入款\n日切 - 清空記錄（僅限操作員）\nTRX地址驗證 - 驗證TRX地址"
        await update.message.reply_text(help_text)
    elif message_text.startswith("入款"):
        try:
            amount = float(message_text.replace("入款", "").strip())
            adjusted_amount = amount * exchange_rate_deposit * (1 - fee_rate)
            transactions.append(f"入款 {amount} -> {adjusted_amount} (由 {user_id})")
            await update.message.reply_text(f"入款 {amount} 記錄成功，調整後金額：{adjusted_amount}")
        except ValueError:
            await update.message.reply_text("請輸入正確金額，例如：入款1000")
    elif message_text.startswith("下發"):
        try:
            amount = float(message_text.replace("下發", "").strip())
            if user_id in operators:
                adjusted_amount = amount * exchange_rate_withdraw * (1 - fee_rate)
                transactions.append(f"下發 {amount} -> {adjusted_amount} (由 {user_id})")
                await update.message.reply_text(f"下發 {amount} 申請成功，調整後金額：{adjusted_amount}")
            else:
                await update.message.reply_text("僅限操作員執行下發")
        except ValueError:
            await update.message.reply_text("請輸入正確金額，例如：下發500")
    elif message_text.startswith("設置操作員"):
        if user_id == "8041296886":
            operator = message_text.replace("設置操作員", "").strip()
            operators[operator] = True
            await update.message.reply_text(f"已將 @{operator} 設置為操作員")
        else:
            await update.message.reply_text("僅限最高管理員設置操作員")
    elif message_text.startswith("設置入款匯率"):
        try:
            rate = float(message_text.replace("設置入款匯率", "").strip())
            exchange_rate_deposit = rate
            await update.message.reply_text(f"入款匯率設置為 {rate}")
        except ValueError:
            await update.message.reply_text("請輸入正確匯率，例如：設置入款匯率1.5")
    elif message_text.startswith("設置下發匯率"):
        try:
            rate = float(message_text.replace("設置下發匯率", "").strip())
            exchange_rate_withdraw = rate
            await update.message.reply_text(f"下發匯率設置為 {rate}")
        except ValueError:
            await update.message.reply_text("請輸入正確匯率，例如：設置下發匯率1.5")
    elif message_text.startswith("設置費率"):
        try:
            rate = float(message_text.replace("設置費率", "").strip())
            fee_rate = rate
            await update.message.reply_text(f"費率設置為 {rate}")
        except ValueError:
            await update.message.reply_text("請輸入正確費率，例如：設置費率0.05")
    elif message_text == "帳單":
        await update.message.reply_text("\n".join(transactions) if transactions else "無交易記錄")
    elif message_text == "刪除入款":
        if transactions and transactions[-1].startswith("入款"):
            removed = transactions.pop()
            await update.message.reply_text(f"已刪除最新入款記錄：{removed}")
        else:
            await update.message.reply_text("無入款記錄可刪除")
    elif message_text == "日切" and user_id == "8041296886":
        transactions.clear()
        await update.message.reply_text("交易記錄已清空")
    elif re.match(r'^[T][a-km-zA-HJ-NP-Z1-9]{33}$', message_text):
        await update.message.reply_text("TRX地址驗證成功")
    else:
        await update.message.reply_text("未知指令，請輸入說明查看幫助")

# 定義日誌功能
async def job():
    print("執行日誌任務", time.ctime())

# 設置日誌任務
def setup_schedule():
    schedule.every().day.at("00:00").do(lambda: asyncio.run(job()))

# 主函數
def main():
    # 獲取 Render 環境變量 PORT
    port = int(os.getenv("PORT", "10000"))

    # 使用 ApplicationBuilder 初始化並設置 Webhook
    application = Application.builder().token(BOT_TOKEN).build()

    # 註冊訊息處理器
    application.add_handler(MessageHandler(telegram.ext.filters.TEXT, handle_message))

    # 設置 schedule 任務
    setup_schedule()

    # 設置 Webhook（使用 Render 的公共 URL）
    webhook_url = f"https://{os.getenv('RENDER_EXTERNAL_URL', 'winpay-bot-repo.onrender.com')}/webhook"
    application.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path="/webhook",
        webhook_url=webhook_url
    )

if __name__ == '__main__':
    main()
