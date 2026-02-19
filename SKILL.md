---
name: polyclaw
description: "Polymarket prediction market auto-trading system. Use when managing simulated or real trading on Polymarket: viewing portfolio, executing trades, generating reports, updating dashboard, or adjusting strategy. Also triggers for questions about prediction markets, trading strategy, or PolyClaw status."
---

# PolyClaw — Polymarket 自动交易系统

## 核心原则

1. **信息差是唯一的交易理由** — 有信息差就重仓，没信息差不动
2. **禁止短期体育赛事** — 单场比赛结果无法分析，是纯赌博
3. **优先级：地缘政治 > 经济/美联储 > 政治选举 > 长期体育**
4. **快进快出 + 信息驱动** — 止盈8%就跑，止损12%止血

## 环境

```bash
cd /Users/openclaw_timememo/.openclaw/workspace
source polyclaw-env/bin/activate
```

## 文件结构

- `polyclaw/auto_trader.py` — 交易引擎（买/卖/止盈止损/报告）
- `polyclaw/market_data.py` — Polymarket Gamma API 数据抓取
- `polyclaw/news_scanner.py` — 免费新闻扫描 + 价格异动检测
- `polyclaw/generate_dashboard.py` — 生成静态HTML仪表盘
- `polyclaw/auto_portfolio.json` — 模拟盘持仓数据
- `polyclaw/market_snapshot.json` — 市场快照（用于异动对比）
- `polyclaw/docs/dashboard.html` — GitHub Pages 仪表盘

## 命令

```bash
# 执行一轮交易（自动买卖）
python polyclaw/auto_trader.py

# 查看持仓报告
python polyclaw/auto_trader.py report

# 周报
python polyclaw/auto_trader.py weekly

# 检测价格异动
python -c "
from polyclaw.market_data import get_trending_markets
from polyclaw.news_scanner import load_snapshot, save_snapshot, scan_polymarket_movers
import json
old = load_snapshot()
new = get_trending_markets(50)
movers = scan_polymarket_movers(old, new)
save_snapshot(new)
print(json.dumps(movers[:10], indent=2, ensure_ascii=False))
"

# 更新仪表盘并推送
python polyclaw/generate_dashboard.py
cd polyclaw && git add -A && git commit -m '📊 更新仪表盘' --allow-empty && git push
```

## 交易决策流程

1. 获取持仓 + 市场数据
2. 检测价格异动（与上次快照对比）
3. 查新闻找信息差（web_fetch AP/Reuters，按需）
4. 对比新闻 vs 市场价格 → 发现错误定价？
   - 市场没反映新闻 → 重仓买入
   - 市场反应过度 → 反向操作
   - 基本面变化 → 果断平仓
   - 无信息差 → 不交易
5. 更新仪表盘推送 GitHub

## 策略参数

- 启动资金：$10,000
- 单笔仓位：余额 15%
- 最大持仓数：25
- 止盈：+8%
- 止损：-12%
- 最低保留余额：$200
- 已结算市场（价格<2¢或>98¢）自动清仓

## 市场分类与决策偏好

- **地缘冲突**：市场高估恐惧 → 偏向买 NO（"不会打"）
- **经济/美联储**：倾向维持现状 → 偏向 NO（"不会大动"）
- **政治**：寻找被低估的候选人
- **体育**：仅做赛季/锦标赛长线

## 免费信息源

- Polymarket 量价分析（价格波动5%+ 或 交易量暴增3x）
- AP News: https://apnews.com/hub/world-news
- Reuters 中东: https://www.reuters.com/world/middle-east/
- ESPN（仅长期体育）: https://www.espn.com/

## Cron 任务

- 自动交易：每天6次（6/9/12/15/18/21点 PST）
- 早报：6AM PST → Discord #polyclaw
- 晚报：6PM PST → Discord #polyclaw + daily snapshot
- 周报：周日 10AM PST → Discord #polyclaw

## 仪表盘

https://timememo8210.github.io/polyclaw/dashboard.html
每次交易后自动更新。

## GitHub

https://github.com/Timememo8210/polyclaw
