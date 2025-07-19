import telegram
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
import schedule
import time

# 你的Bot Token和User ID
TOKEN = '7908773608:AAFFqLmGkJ9zbsuymQTFzJxy5IyeN1E9M-U'
ADMIN_ID = '8041296886'

# 初始化Bot
bot = telegram.Bot(token=TOKEN)
updater = Updater(TOKEN, use_context=True)
dp = updater.dispatcher

# 儲存TRX地址驗證記錄
trx_records = {}

# 開始指令
def start(update, context):
    user = update.message.from_user.username
    update.message.reply_text(f'歡迎使用winpay小秘书 @{user}')

# 說明指令
def help_command(update, context):
    help_text = '''
    WinPay小秘书使用說明

    1. 啟動機器人
       開始
    2. 查詢說明
       說明
    3. 入款
       入款1000
    4. 查帳
       帳單
    5. TRX地址驗證
       [TRX地址]
    '''
    update.message.reply_text(help_text)

# 入款處理
def handle_message(update, context):
    message_text = update.message.text.lower()
    user = update.message.from_user.username
    if message_text.startswith('入款'):
        try:
            amount = float(message_text.replace('入款', '').strip())
            if amount > 0:
                update.message.reply_text(f'入款 {amount} 記錄成功，@{user}')
            else:
                update.message.reply_text('請輸入正數金額')
        except ValueError:
            update.message.reply_text('格式錯誤，請輸入如 入款1000')
    elif message_text == '帳單':
        update.message.reply_text('今日無交易記錄')  # 需擴展儲存邏輯
    elif is_trx_address(message_text):
        handle_trx(update, context, message_text)

# TRX地址驗證
def is_trx_address(text):
    return len(text) == 34 and text.startswith('T')

def handle_trx(update, context, address):
    user = update.message.from_user.username
    if address in trx_records:
        count = trx_records[address]['count'] + 1
        last_user = trx_records[address]['last_user']
        trx_records[address] = {'count': count, 'last_user': user}
        reply = f'驗證地址：{address}\n驗證次數：{count}\n上次發送人：{last_user}\n本次發送人：@{user}'
    else:
        trx_records[address] = {'count': 1, 'last_user': '無'}
        reply = f'驗證地址：{address}\n驗證次數：1\n上次發送人：無\n本次發送人：@{user}'
    update.message.reply_text(reply)

# 註冊處理器
dp.add_handler(CommandHandler("開始", start))
dp.add_handler(CommandHandler("說明", help_command))
dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

# 啟動Bot
def job():
    print("Running daily reset at 06:00 CST")
    trx_records.clear()  # 簡化日切邏輯

schedule.every().day.at("22:00").do(job)  # 06:00 CST = 22:00 UTC

def run_bot():
    updater.start_polling()
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == '__main__':
    run_bot()
