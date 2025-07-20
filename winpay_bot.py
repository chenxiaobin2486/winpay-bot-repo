import telegram
from telegram.ext import Updater, CommandHandler, MessageHandler
from telegram.ext.filters import Filters  # 分開匯入 Filters
import schedule
import time

# 你的Bot Token和User ID
TOKEN = '7908773608:AAFFqLmGkJ9zbsuymQTFzJxy5IyeN1E9M-U'
ADMIN_ID = '8041296886'

# 初始化Bot
bot = telegram.Bot(token=TOKEN)
updater = Updater(TOKEN, use_context=True)
dp = updater.dispatcher

# 儲存數據
transactions = {}  # 交易記錄 {用戶名: [金額, 類型]}
trx_records = {}   # TRX驗證記錄 {地址: {'count': int, 'last_user': str}}
rates = {'deposit_rate': 1.0, 'deposit_fee': 0.0, 'withdraw_rate': 1.0, 'withdraw_fee': 0.0}
operators = set()  # 操作員名單

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
    2. 添加操作員
       設置操作員 @用戶名
    3. 設置匯率/費率
       設置入款匯率 [數值]
       設置入款費率 [數值]
       設置下發匯率 [數值]
       設置下發費率 [數值]
    4. 入款
       入款1000
    5. 下發
       下發500
    6. 查帳
       帳單
    7. 刪除入款/出款
       刪除入款、刪除出款 或 回覆帳單消息+刪除
    8. TRX地址驗證
       [TRX地址]
    9. 日切
       日切
    '''
    update.message.reply_text(help_text)

# 設置操作員
def set_operator(update, context):
    if str(update.message.from_user.id) != ADMIN_ID:
        update.message.reply_text('僅限管理員設置')
        return
    args = update.message.text.split()
    if len(args) != 2 or not args[1].startswith('@'):
        update.message.reply_text('格式錯誤，使用：設置操作員 @用戶名')
        return
    operator = args[1]
    operators.add(operator)
    update.message.reply_text(f'已添加操作員 {operator}')

# 設置匯率/費率
def set_rate(update, context):
    if str(update.message.from_user.id) != ADMIN_ID:
        update.message.reply_text('僅限管理員設置')
        return
    args = update.message.text.split()
    if len(args) != 3 or not args[2].replace('.', '').isdigit():
        update.message.reply_text('格式錯誤，使用：設置[入款/下發][匯率/費率] [數值]')
        return
    rate_type = args[1]
    value = float(args[2])
    if rate_type == '入款匯率':
        rates['deposit_rate'] = value
    elif rate_type == '入款費率':
        rates['deposit_fee'] = value
    elif rate_type == '下發匯率':
        rates['withdraw_rate'] = value
    elif rate_type == '下發費率':
        rates['withdraw_fee'] = value
    else:
        update.message.reply_text('無效類型')
        return
    update.message.reply_text(f'已設置 {rate_type} 為 {value}')

# 入款處理
def handle_deposit(update, context):
    user = update.message.from_user.username
    message_text = update.message.text.lower()
    if message_text.startswith('入款'):
        try:
            amount = float(message_text.replace('入款', '').strip())
            if amount <= 0:
                update.message.reply_text('請輸入正數金額')
                return
            adjusted_amount = amount * rates['deposit_rate'] - rates['deposit_fee']
            if user not in transactions:
                transactions[user] = []
            transactions[user].append([adjusted_amount, '入款'])
            update.message.reply_text(f'入款 {amount} 調整後 {adjusted_amount:.2f} 記錄成功，@{user}')
        except ValueError:
            update.message.reply_text('格式錯誤，請輸入如 入款1000')

# 下發處理
def handle_withdraw(update, context):
    user = update.message.from_user.username
    if user not in operators and str(update.message.from_user.id) != ADMIN_ID:
        update.message.reply_text('僅限操作員或管理員下發')
        return
    message_text = update.message.text.lower()
    if message_text.startswith('下發'):
        try:
            amount = float(message_text.replace('下發', '').strip())
            if amount <= 0:
                update.message.reply_text('請輸入正數金額')
                return
            adjusted_amount = amount * rates['withdraw_rate'] - rates['withdraw_fee']
            if user not in transactions:
                transactions[user] = []
            transactions[user].append([adjusted_amount, '下發'])
            update.message.reply_text(f'下發 {amount} 調整後 {adjusted_amount:.2f} 記錄成功，@{user}')
        except ValueError:
            update.message.reply_text('格式錯誤，請輸入如 下發500')

# 查帳
def check_bill(update, context):
    user = update.message.from_user.username
    if user not in transactions or not transactions[user]:
        update.message.reply_text('今日無交易記錄')
        return
    bill = '\n'.join([f'{t[1]} {t[0]:.2f}' for t in transactions[user]])
    update.message.reply_text(f'@{user} 帳單：\n{bill}')

# 刪除功能
def delete_transaction(update, context):
    user = update.message.from_user.username
    if user not in operators and str(update.message.from_user.id) != ADMIN_ID:
        update.message.reply_text('僅限操作員或管理員刪除')
        return
    message_text = update.message.text.lower()
    if message_text == '刪除入款' or message_text == '刪除出款':
        if user in transactions and transactions[user]:
            last_type = transactions[user][-1][1]
            if (message_text == '刪除入款' and last_type == '入款') or \
               (message_text == '刪除出款' and last_type == '下發'):
                transactions[user].pop()
                update.message.reply_text(f'已刪除最新{last_type}')
            else:
                update.message.reply_text('無匹配交易可刪除')
        else:
            update.message.reply_text('無交易記錄')
    elif update.message.reply_to_message:
        replied_user = update.message.reply_to_message.from_user.username
        if replied_user in transactions:
            transactions[replied_user].clear()
            update.message.reply_text(f'@{replied_user} 帳單已清除')

# TRX地址驗證
def is_trx_address(text):
    return len(text) == 34 and text.startswith('T')

def handle_trx(update, context):
    user = update.message.from_user.username
    message_text = update.message.text
    if is_trx_address(message_text):
        if message_text in trx_records:
            count = trx_records[message_text]['count'] + 1
            last_user = trx_records[message_text]['last_user']
            trx_records[message_text] = {'count': count, 'last_user': user}
            reply = f'驗證地址：{message_text}\n驗證次數：{count}\n上次發送人：{last_user}\n本次發送人：@{user}'
        else:
            trx_records[message_text] = {'count': 1, 'last_user': '無'}
            reply = f'驗證地址：{message_text}\n驗證次數：1\n上次發送人：無\n本次發送人：@{user}'
        update.message.reply_text(reply)

# 日切
def job():
    print("Running daily reset at 06:00 CST")
    transactions.clear()
    trx_records.clear()

schedule.every().day.at("22:00").do(job)  # 06:00 CST = 22:00 UTC

# 註冊處理器
dp.add_handler(CommandHandler("開始", start))
dp.add_handler(CommandHandler("說明", help_command))
dp.add_handler(CommandHandler("設置操作員", set_operator))
dp.add_handler(CommandHandler("設置入款匯率", set_rate))
dp.add_handler(CommandHandler("設置入款費率", set_rate))
dp.add_handler(CommandHandler("設置下發匯率", set_rate))
dp.add_handler(CommandHandler("設置下發費率", set_rate))
dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

def handle_message(update, context):
    message_text = update.message.text.lower()
    if message_text.startswith('入款'):
        handle_deposit(update, context)
    elif message_text.startswith('下發'):
        handle_withdraw(update, context)
    elif message_text == '帳單':
        check_bill(update, context)
    elif message_text in ['刪除入款', '刪除出款']:
        delete_transaction(update, context)
    elif is_trx_address(update.message.text):
        handle_trx(update, context)
    elif message_text == '日切' and str(update.message.from_user.id) == ADMIN_ID:
        job()
        update.message.reply_text('已執行日切')

# 啟動Bot
def run_bot():
    updater.start_polling()
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == '__main__':
    run_bot()
