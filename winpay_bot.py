# 導入必要的模組
from telegram.ext import Updater, CommandHandler, MessageHandler
import telegram.ext.filters  # 匯入 filters 模組
import schedule
import time

# 定義 Bot Token（建議從環境變量獲取）
BOT_TOKEN = "7908773608:AAFFqLmGkJ9zbsuymQTFzJxy5IyeN1E9M-U"  # 確保與環境變量 BOT_TOKEN 一致

# 定義全局變量（示例，根據你的需求調整）
operators = {"8041296886": True}  # 操作員清單
transactions = []  # 交易記錄
exchange_rate_deposit = 1.0  # 入款匯率
exchange_rate_withdraw = 1.0  # 下發匯率
fee_rate = 0.0  # 費率

# 處理 /start 指令
def start(update, context):
    user = update.message.from_user.username
    update.message.reply_text(f"歡迎使用winpay小秘书 @{user}")

# 處理說明指令
def help_command(update, context):
    help_text = "可用指令：\n開始 - 開始使用\n入款 <金額> - 記錄入款\n下發 <金額> - 申請下發\n設置操作員 <用戶名> - 設置操作員\n設置入款匯率 <數值> - 設置入款匯率\n設置下發匯率 <數值> - 設置下發匯率\n設置費率 <數值> - 設置費率\n帳單 - 查看交易記錄\n刪除入款 - 刪除最新入款\n日切 - 清空記錄（僅限操作員）\nTRX地址驗證 - 驗證TRX地址"
    update.message.reply_text(help_text)

# 處理無斜杠指令（如開始、入款）
def handle_message(update, context):
    message_text = update.message.text.strip()
    user_id = str(update.message.from_user.id)

    if message_text == "開始":
        start(update, context)
    elif message_text.startswith("入款"):
        try:
            amount = float(message_text.replace("入款", "").strip())
            adjusted_amount = amount * exchange_rate_deposit * (1 - fee_rate)
            transactions.append(f"入款 {amount} -> {adjusted_amount} (由 {user_id})")
            update.message.reply_text(f"入款 {amount} 記錄成功，調整後金額：{adjusted_amount}")
        except ValueError:
            update.message.reply_text("請輸入正確金額，例如：入款1000")
    elif message_text.startswith("下發"):
        try:
            amount = float(message_text.replace("下發", "").strip())
            if user_id in operators:
                adjusted_amount = amount * exchange_rate_withdraw * (1 - fee_rate)
                transactions.append(f"下發 {amount} -> {adjusted_amount} (由 {user_id})")
                update.message.reply_text(f"下發 {amount} 申請成功，調整後金額：{adjusted_amount}")
            else:
                update.message.reply_text("僅限操作員執行下發")
        except ValueError:
            update.message.reply_text("請輸入正確金額，例如：下發500")
    elif message_text.startswith("設置操作員"):
        if user_id == "8041296886":
            operator = message_text.replace("設置操作員", "").strip()
            operators[operator] = True
            update.message.reply_text(f"已將 @{operator} 設置為操作員")
        else:
            update.message.reply_text("僅限最高管理員設置操作員")
    elif message_text.startswith("設置入款匯率"):
        try:
            rate = float(message_text.replace("設置入款匯率", "").strip())
            exchange_rate_deposit = rate
            update.message.reply_text(f"入款匯率設置為 {rate}")
        except ValueError:
            update.message.reply_text("請輸入正確匯率，例如：設置入款匯率1.5")
    elif message_text.startswith("設置下發匯率"):
        try:
            rate = float(message_text.replace("設置下發匯率", "").strip())
            exchange_rate_withdraw = rate
            update.message.reply_text(f"下發匯率設置為 {rate}")
        except ValueError:
            update.message.reply_text("請輸入正確匯率，例如：設置下發匯率1.5")
    elif message_text.startswith("設置費率"):
        try:
            rate = float(message_text.replace("設置費率", "").strip())
            fee_rate = rate
            update.message.reply_text(f"費率設置為 {rate}")
        except ValueError:
            update.message.reply_text("請輸入正確費率，例如：設置費率0.05")
    elif message_text == "帳單":
        update.message.reply_text("\n".join(transactions) if transactions else "無交易記錄")
    elif message_text == "刪除入款":
        if transactions and transactions[-1].startswith("入款"):
            removed = transactions.pop()
            update.message.reply_text(f"已刪除最新入款記錄：{removed}")
        else:
            update.message.reply_text("無入款記錄可刪除")
    elif message_text == "日切" and user_id == "8041296886":
        transactions.clear()
        update.message.reply_text("交易記錄已清空")
    elif re.match(r'^[T][a-km-zA-HJ-NP-Z1-9]{33}$', message_text):
        update.message.reply_text("TRX地址驗證成功")
    else:
        update.message.reply_text("未知指令，請輸入說明查看幫助")

# 定義日誌功能（示例）
def job():
    print("執行日誌任務", time.ctime())

# 設置日誌任務
schedule.every().day.at("00:00").do(job)

# 主函數
def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    # 註冊指令處理器
    dp.add_handler(CommandHandler("開始", start))
    dp.add_handler(CommandHandler("說明", help_command))

    # 註冊無斜杠指令處理器
    dp.add_handler(MessageHandler(telegram.ext.filters.COMMAND, handle_message))  # 處理命令
    dp.add_handler(MessageHandler(telegram.ext.filters.TEXT & ~telegram.ext.filters.COMMAND, handle_message))  # 處理文本

    # 啟動 Bot
    updater.start_polling()
    schedule.run_all()  # 立即執行所有任務
    updater.idle()

if __name__ == '__main__':
    main()
