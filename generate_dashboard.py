"""Generate static HTML dashboard from auto_portfolio.json"""
import json, os, sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from auto_trader import generate_report, generate_weekly_summary, _load

OUTPUT = os.path.join(os.path.dirname(__file__), "docs", "dashboard.html")

def generate():
    data = _load()
    report = generate_report()
    
    pnl_class = "pos" if report["total_pnl"] >= 0 else "neg"
    pnl_sign = "+" if report["total_pnl"] >= 0 else ""
    now = datetime.now().strftime("%Y-%m-%d %H:%M PST")
    
    # Positions HTML
    if report["positions"]:
        pos_rows = ""
        for p in report["positions"]:
            pc = "pos" if p["pnl"] >= 0 else "neg"
            ps = "+" if p["pnl"] >= 0 else ""
            side_cls = "yes" if p["side"] == "yes" else "no"
            pos_rows += f"""<tr>
                <td><span class="side {side_cls}">{p['side'].upper()}</span></td>
                <td class="q">{p['question']}</td>
                <td>{p['shares']:.0f}</td>
                <td>{p['avg_price']*100:.0f}¢</td>
                <td>{p['current_price']*100:.0f}¢</td>
                <td>${p['value']:.2f}</td>
                <td class="{pc}">{ps}${p['pnl']:.2f} ({ps}{p['pnl_pct']}%)</td>
            </tr>"""
        pos_html = f"""<table>
            <thead><tr><th></th><th>市场</th><th>股数</th><th>成本</th><th>现价</th><th>市值</th><th>盈亏</th></tr></thead>
            <tbody>{pos_rows}</tbody>
        </table>"""
    else:
        pos_html = '<div class="empty">暂无持仓</div>'
    
    # History HTML
    history = data.get("history", [])
    if history:
        hist_rows = ""
        for h in reversed(history[-20:]):
            if h["action"] == "settle":
                continue  # skip settle entries in display
            action_cls = "buy" if h["action"] == "buy" else "sell"
            action_txt = "买入" if h["action"] == "buy" else "卖出"
            side_cls = "yes" if h.get("side") == "yes" else "no"
            t = datetime.fromisoformat(h["time"]).strftime("%m/%d %H:%M")
            if h["action"] == "buy":
                detail = f"-${h['amount']:.0f}"
            else:
                detail = f"+${h.get('proceeds',0):.0f}"
                profit = h.get('profit', 0)
                detail += f" ({'赚' if profit>=0 else '亏'}${abs(profit):.1f})"
            reason = h.get("reason", "")
            hist_rows += f"""<tr>
                <td><span class="action {action_cls}">{action_txt}</span></td>
                <td><span class="side {side_cls}">{h['side'].upper()}</span></td>
                <td class="q">{h.get('question','')[:50]}</td>
                <td>{h.get('shares',0):.0f}股 @ {h['price']*100:.0f}¢</td>
                <td>{detail}</td>
                <td class="dim">{reason}</td>
                <td class="dim">{t}</td>
            </tr>"""
        hist_html = f"""<table><thead><tr><th></th><th></th><th>市场</th><th>详情</th><th>金额</th><th>原因</th><th>时间</th></tr></thead><tbody>{hist_rows}</tbody></table>"""
    else:
        hist_html = '<div class="empty">暂无记录</div>'
    
    # Snapshots chart data
    snapshots = data.get("daily_snapshots", [])
    chart_labels = json.dumps([s["date"][-5:] for s in snapshots[-30:]])
    chart_values = json.dumps([s["total_value"] for s in snapshots[-30:]])
    
    # Win/loss stats
    sells = [h for h in history if h["action"] == "sell"]
    wins = sum(1 for s in sells if s.get("profit",0)>0)
    losses = sum(1 for s in sells if s.get("profit",0)<0)
    wr = round(wins/(wins+losses)*100) if (wins+losses)>0 else 0
    realized = sum(s.get("profit",0) for s in sells)

    html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>🐾 PolyClaw Dashboard</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0d1117;color:#c9d1d9;min-height:100vh}}
.header{{background:linear-gradient(135deg,#161b22,#1a1f2e);border-bottom:1px solid #30363d;padding:24px 32px;text-align:center}}
.header h1{{font-size:28px;margin-bottom:8px}}.header h1 span{{color:#58a6ff}}
.header .updated{{color:#484f58;font-size:13px}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:16px;max-width:1000px;margin:24px auto;padding:0 24px}}
.card{{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:20px;text-align:center}}
.card .label{{font-size:12px;color:#8b949e;margin-bottom:4px}}
.card .val{{font-size:24px;font-weight:700}}
.pos{{color:#3fb950}}.neg{{color:#f85149}}
.section{{max-width:1000px;margin:24px auto;padding:0 24px}}
.section h2{{font-size:18px;margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid #21262d}}
table{{width:100%;border-collapse:collapse;background:#161b22;border:1px solid #30363d;border-radius:12px;overflow:hidden;font-size:13px}}
thead{{background:#21262d}}
th{{padding:10px 12px;text-align:left;color:#8b949e;font-weight:600;font-size:12px}}
td{{padding:10px 12px;border-top:1px solid #21262d}}
td.q{{max-width:250px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
td.dim{{color:#484f58;font-size:12px}}
.side{{padding:2px 6px;border-radius:4px;font-size:10px;font-weight:700}}
.side.yes{{background:#238636;color:#fff}}.side.no{{background:#da3633;color:#fff}}
.action{{padding:2px 6px;border-radius:4px;font-size:10px;font-weight:700}}
.action.buy{{background:#1f6feb;color:#fff}}.action.sell{{background:#6e40c9;color:#fff}}
.empty{{padding:30px;text-align:center;color:#484f58}}
.chart-box{{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:20px;margin-bottom:16px}}
canvas{{width:100%!important;max-height:200px}}
.footer{{text-align:center;padding:32px;color:#484f58;font-size:12px}}
.footer a{{color:#58a6ff;text-decoration:none}}
@media(max-width:600px){{
  .cards{{grid-template-columns:repeat(2,1fr);gap:10px}}
  table{{font-size:11px}}td.q{{max-width:120px}}
  th,td{{padding:6px 8px}}
}}
</style>
</head>
<body>
<div class="header">
  <h1>🐾 <span>PolyClaw</span> 自动交易仪表盘</h1>
  <div class="updated">最后更新: {now}</div>
</div>

<div class="cards">
  <div class="card"><div class="label">💰 账户总值</div><div class="val">${report['total_value']:,.2f}</div></div>
  <div class="card"><div class="label">📊 总盈亏</div><div class="val {pnl_class}">{pnl_sign}${report['total_pnl']:.2f}<br><span style="font-size:14px">({pnl_sign}{report['total_pnl_pct']}%)</span></div></div>
  <div class="card"><div class="label">💵 可用余额</div><div class="val">${report['balance']:,.2f}</div></div>
  <div class="card"><div class="label">📋 持仓数</div><div class="val">{report['position_count']}/10</div></div>
  <div class="card"><div class="label">🔄 总交易次数</div><div class="val">{report['total_trades']}</div></div>
  <div class="card"><div class="label">🎯 胜率</div><div class="val">{wr}%<br><span style="font-size:12px;color:#8b949e">{wins}胜 {losses}负</span></div></div>
</div>

<div class="section">
  <h2>📈 资产曲线</h2>
  <div class="chart-box">
    <canvas id="chart"></canvas>
    {f'<div class="empty">数据积累中，明天开始显示曲线</div>' if len(snapshots)<2 else ''}
  </div>
</div>

<div class="section">
  <h2>📋 当前持仓</h2>
  {pos_html}
</div>

<div class="section">
  <h2>📜 交易记录（最近20笔）</h2>
  {hist_html}
</div>

<div class="footer">
  🐾 PolyClaw — 模拟交易，不涉及真实资金 | <a href="https://github.com/Timememo8210/polyclaw">GitHub</a><br>
  由 Sky ☁️ 全自动运营 | 启动资金 $10,000
</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<script>
const labels = {chart_labels};
const values = {chart_values};
if (labels.length >= 2) {{
  new Chart(document.getElementById('chart'), {{
    type: 'line',
    data: {{
      labels,
      datasets: [{{
        label: '账户总值 ($)',
        data: values,
        borderColor: '#58a6ff',
        backgroundColor: 'rgba(88,166,255,0.1)',
        fill: true,
        tension: 0.3,
        pointRadius: 3,
      }}, {{
        label: '起始资金',
        data: values.map(() => 10000),
        borderColor: '#30363d',
        borderDash: [5,5],
        pointRadius: 0,
      }}]
    }},
    options: {{
      responsive: true,
      plugins: {{ legend: {{ labels: {{ color: '#8b949e' }} }} }},
      scales: {{
        x: {{ ticks: {{ color: '#484f58' }}, grid: {{ color: '#21262d' }} }},
        y: {{ ticks: {{ color: '#484f58' }}, grid: {{ color: '#21262d' }} }}
      }}
    }}
  }});
}}
</script>
</body>
</html>"""
    
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "w") as f:
        f.write(html)
    return OUTPUT

if __name__ == "__main__":
    path = generate()
    print(f"Dashboard generated: {path}")
