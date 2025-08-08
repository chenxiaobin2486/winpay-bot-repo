from flask import Flask, request, render_template_string
import os

app = Flask(__name__)

# 模拟交易数据 (替换为实际数据源，如文件或数据库)
transactions = {
    '-1001234567890': [('2025-08-01', 100, 'Payment 1'), ('2025-08-02', 50, 'Payment 2')],
    '-1009876543210': [('2025-08-03', 75, 'Payment 3'), ('2025-08-04', 25, 'Payment 4')]
}

@app.route('/Telegram/BillReport')
def bill_report():
    group_id = request.args.get('group_id')
    
    # 如果指定 group_id，则显示该群组的账单；否则显示所有群组
    if group_id and group_id in transactions:
        bills = transactions[group_id]
        html = f"""
        <h1>Complete Bill for Group {group_id}</h1>
        <table border="1">
            <tr><th>Date</th><th>Amount</th><th>Description</th></tr>
            {' '.join(f'<tr><td>{date}</td><td>{amount}</td><td>{desc}</td></tr>' for date, amount, desc in bills)}
        </table>
        <p>Total: {sum(amount for _, amount, _ in bills)} units</p>
        """
    else:
        html = "<h1>All Groups' Complete Bills</h1>"
        for gid, bills in transactions.items():
            html += f"<h2>Group {gid}</h2>"
            html += """
            <table border="1">
                <tr><th>Date</th><th>Amount</th><th>Description</th></tr>
                {}
            </table>
            <p>Total: {} units</p>
            """.format(
                ' '.join(f'<tr><td>{date}</td><td>{amount}</td><td>{desc}</td></tr>' for date, amount, desc in bills),
                sum(amount for _, amount, _ in bills)
            )

    return html

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
