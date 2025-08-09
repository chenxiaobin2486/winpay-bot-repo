<div className="date-picker">
                <input
                    type="date"
                    value={selectedDate}
                    onChange={handleDateChange}
                    max={new Date().toISOString().split('T')[0]}
                    min={new Date(new Date().setDate(new Date().getDate() - 30)).toISOString().split('T')[0]}
                />
            </div>
            {loading && <div className="spinner"></div>}
            {error && <div className="error">{error}</div>}
            {!loading && !error && (
                <>
                    <table className="bill-table">
                        <thead>
                            <tr><th colSpan="7">{selectedDate} 交易记录</th></tr>
                            <tr>
                                <th>时间</th><th>金额</th><th>下发/入款</th><th>费率</th><th>汇率</th><th>换算金额</th><th className="operator-col">操作员</th>
                            </tr>
                        </thead>
                        <tbody>
                            {transactions.map((tx, i) => (
                                <tr key={i}>
                                    <td>{tx.time}</td>
                                    <td className={tx.type === '入款' ? 'text-success' : 'text-danger'}>{tx.amount}</td>
                                    <td>{tx.type}</td>
                                    <td>{(tx.fee * 100).toFixed(2)}%</td>
                                    <td>{tx.rate.toFixed(2)}</td>
                                    <td>{tx.converted.toFixed(2)}u</td>
                                    <td>{tx.operator}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                    {totalPages > 1 && (
                        <nav className="mt-3">
                            <ul className="pagination justify-content-center">
                                {Array.from({ length: totalPages }, (_, i) => i + 1).map(p => (
                                    <li key={p} className={`page-item ${p === page ? 'active' : ''}`}>
                                        <button className="page-link" onClick={() => handlePageChange(p)}>{p}</button>
                                    </li>
                                ))}
                            </ul>
                        </nav>
                    )}
                </>
            )}
        </div>
    );
}

export default App;
