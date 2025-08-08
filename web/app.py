from flask import Flask, render_template, request
import os
import requests

app = Flask(__name__)

# 配置 winpay_bot API URL
BOT_API_URL = os.getenv("BOT_API_URL", "https://your-winpay-bot.onrender.com") + ":5001"  # 添加端口

@app.route('/Telegram/BillReport')
def bill_report():
    group_id = request.args.get('group_id')
    if not group_id:
        return "缺少 group_id 参数", 400
    
    try:
        response = requests.get(f"{BOT_API_URL}/get_transactions/{group_id}")
        response.raise_for_status()
        transactions = response.json()
    except requests.RequestException as e:
        return f"无法获取交易数据: {str(e)}", 500
    
    return render_template('bill.html', group_id=group_id, transactions=transactions)

@app.route('/health')
def health_check():
    return "OK", 200

if __name__ == '__main__':
    port = int(os.getenv("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
