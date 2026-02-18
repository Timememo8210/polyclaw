"""
PolyClaw Auto Trader — Sky的自动交易策略
模拟盘，$10,000 启动资金

策略逻辑：
1. 扫描热门市场，寻找"定价偏差"机会
2. 高确定性事件（>85% 或 <15%）跳过 — 赔率太低
3. 关注中间概率（20%-80%）且交易量大的市场
4. 每次最多投入余额的5%
5. 止盈: +30% 卖出 | 止损: -25% 卖出
6. 最多同时持有10个仓位
"""
import json, os, sys, random
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(__file__))
from market_data import get_trending_markets

PORTFOLIO_FILE = os.path.join(os.path.dirname(__file__), "auto_portfolio.json")
STARTING_BALANCE = 10000.0
MAX_POSITIONS = 25
MAX_POSITION_PCT = 0.03  # 3% of balance per trade
MIN_PRICE = 0.15
MAX_PRICE = 0.85
TAKE_PROFIT = 0.15   # +15%
STOP_LOSS = -0.15     # -15%
MIN_VOLUME_24H = 50000  # minimum 24h volume

def _load():
    if os.path.exists(PORTFOLIO_FILE):
        with open(PORTFOLIO_FILE) as f:
            return json.load(f)
    return {
        "balance": STARTING_BALANCE,
        "positions": {},
        "history": [],
        "daily_snapshots": [],
        "created": datetime.now().isoformat(),
        "last_trade": None,
    }

def _save(data):
    with open(PORTFOLIO_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def _score_market(m):
    """Score a market for trading opportunity. Higher = better."""
    price = m["outcome_yes"]
    score = 0
    
    # Prefer mid-range probabilities (sweet spot: 25-75%)
    if 0.25 <= price <= 0.75:
        score += 30
    elif 0.15 <= price <= 0.85:
        score += 15
    else:
        return 0  # skip extreme odds
    
    # Volume matters — more volume = more reliable price
    vol = m["volume_24h"]
    if vol > 500000: score += 25
    elif vol > 200000: score += 20
    elif vol > 100000: score += 15
    elif vol > 50000: score += 10
    else: return 0
    
    # Liquidity bonus
    liq = m.get("liquidity", 0)
    if liq > 100000: score += 10
    elif liq > 50000: score += 5
    
    # Slight randomness for diversification
    score += random.randint(0, 10)
    
    return score

def _decide_side(m):
    """Decide YES or NO based on price analysis."""
    yes_price = m["outcome_yes"]
    no_price = m["outcome_no"]
    
    # Simple contrarian logic:
    # If YES is cheap (<40%), market might be underpricing it → buy YES
    # If YES is expensive (>60%), the NO side is cheap → buy NO
    # In the middle, pick the cheaper side
    if yes_price < 0.40:
        return "yes", yes_price
    elif yes_price > 0.60:
        return "no", no_price
    else:
        # Buy whichever is cheaper
        if yes_price <= no_price:
            return "yes", yes_price
        else:
            return "no", no_price

def run_trading_cycle():
    """Main trading cycle — called by cron."""
    data = _load()
    actions = []
    
    # 1. Fetch markets
    try:
        markets = get_trending_markets(50)
    except Exception as e:
        return {"error": f"获取市场数据失败: {e}", "actions": []}
    
    # 2. Check existing positions for take-profit / stop-loss
    markets_by_id = {m["id"]: m for m in markets}
    positions_to_close = []
    
    for key, pos in list(data["positions"].items()):
        mid = pos["market_id"]
        m = markets_by_id.get(mid)
        if not m:
            continue
        
        current_price = m["outcome_yes"] if pos["side"] == "yes" else m["outcome_no"]
        pnl_pct = (current_price - pos["avg_price"]) / pos["avg_price"] if pos["avg_price"] > 0 else 0
        
        reason = None
        if pnl_pct >= TAKE_PROFIT:
            reason = f"止盈 +{pnl_pct*100:.0f}%"
        elif pnl_pct <= STOP_LOSS:
            reason = f"止损 {pnl_pct*100:.0f}%"
        
        if reason:
            proceeds = pos["shares"] * current_price
            profit = (current_price - pos["avg_price"]) * pos["shares"]
            data["balance"] += proceeds
            data["history"].append({
                "action": "sell", "question": pos["question"], "side": pos["side"],
                "price": current_price, "shares": pos["shares"], "proceeds": round(proceeds, 2),
                "profit": round(profit, 2), "reason": reason, "time": datetime.now().isoformat()
            })
            actions.append(f"📤 卖出 | {pos['question'][:40]} | {pos['side'].upper()} | {reason} | {'赚' if profit>0 else '亏'}${abs(profit):.2f}")
            positions_to_close.append(key)
    
    for key in positions_to_close:
        del data["positions"][key]
    
    # 3. Look for new opportunities
    num_positions = len(data["positions"])
    held_market_ids = {pos["market_id"] for pos in data["positions"].values()}
    
    if num_positions < MAX_POSITIONS:
        candidates = []
        for m in markets:
            if m["id"] in held_market_ids:
                continue
            score = _score_market(m)
            if score > 0:
                candidates.append((score, m))
        
        candidates.sort(key=lambda x: -x[0])
        slots = MAX_POSITIONS - num_positions
        # Buy top candidates, max 5 new positions per cycle
        to_buy = candidates[:min(slots, 5)]
        
        for score, m in to_buy:
            side, price = _decide_side(m)
            if price <= 0 or price >= 1:
                continue
            
            amount = min(data["balance"] * MAX_POSITION_PCT, data["balance"] * 0.1)
            amount = round(min(amount, data["balance"] - 100), 2)  # keep $100 reserve
            if amount < 20:
                continue
            
            shares = amount / price
            data["balance"] -= amount
            key = f"{m['id']}_{side}"
            data["positions"][key] = {
                "market_id": m["id"], "question": m["question"], "side": side,
                "shares": round(shares, 2), "avg_price": round(price, 4),
                "bought_at": datetime.now().isoformat(), "score": score
            }
            data["history"].append({
                "action": "buy", "question": m["question"], "side": side,
                "price": price, "amount": amount, "shares": round(shares, 2),
                "score": score, "time": datetime.now().isoformat()
            })
            actions.append(f"📥 买入 | {m['question'][:40]} | {side.upper()} @ {price*100:.0f}¢ | ${amount:.0f}")
    
    data["last_trade"] = datetime.now().isoformat()
    _save(data)
    
    return {"actions": actions, "balance": round(data["balance"], 2), "positions": len(data["positions"])}

def generate_report():
    """Generate portfolio report."""
    data = _load()
    
    try:
        markets = get_trending_markets(50)
        markets_by_id = {m["id"]: m for m in markets}
    except:
        markets_by_id = {}
    
    total_value = data["balance"]
    pos_details = []
    
    for key, pos in data["positions"].items():
        m = markets_by_id.get(pos["market_id"])
        if m:
            cp = m["outcome_yes"] if pos["side"] == "yes" else m["outcome_no"]
        else:
            cp = pos["avg_price"]
        
        value = pos["shares"] * cp
        cost = pos["shares"] * pos["avg_price"]
        pnl = value - cost
        total_value += value
        
        pos_details.append({
            "question": pos["question"],
            "side": pos["side"],
            "shares": pos["shares"],
            "avg_price": pos["avg_price"],
            "current_price": round(cp, 4),
            "value": round(value, 2),
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl / cost * 100, 1) if cost > 0 else 0,
        })
    
    total_pnl = total_value - STARTING_BALANCE
    
    # Recent trades (last 24h)
    now = datetime.now()
    recent = [h for h in data["history"] if (now - datetime.fromisoformat(h["time"])).total_seconds() < 86400]
    
    return {
        "balance": round(data["balance"], 2),
        "total_value": round(total_value, 2),
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": round(total_pnl / STARTING_BALANCE * 100, 2),
        "positions": pos_details,
        "position_count": len(pos_details),
        "total_trades": len(data["history"]),
        "recent_trades_24h": len(recent),
        "recent_trades": recent[-5:],  # last 5
    }

def generate_weekly_summary():
    """Generate weekly summary."""
    data = _load()
    report = generate_report()
    
    # Count wins/losses
    sells = [h for h in data["history"] if h["action"] == "sell"]
    wins = sum(1 for s in sells if s.get("profit", 0) > 0)
    losses = sum(1 for s in sells if s.get("profit", 0) < 0)
    total_profit = sum(s.get("profit", 0) for s in sells)
    
    # Daily snapshots
    snapshots = data.get("daily_snapshots", [])
    
    return {
        **report,
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins/(wins+losses)*100, 1) if (wins+losses) > 0 else 0,
        "realized_profit": round(total_profit, 2),
        "snapshots": snapshots[-7:],
    }

def take_daily_snapshot():
    """Record daily portfolio value for tracking."""
    data = _load()
    report = generate_report()
    if "daily_snapshots" not in data:
        data["daily_snapshots"] = []
    data["daily_snapshots"].append({
        "date": datetime.now().strftime("%Y-%m-%d"),
        "total_value": report["total_value"],
        "pnl": report["total_pnl"],
        "positions": report["position_count"],
    })
    # Keep last 90 days
    data["daily_snapshots"] = data["daily_snapshots"][-90:]
    _save(data)

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "report":
        r = generate_report()
        print(json.dumps(r, indent=2, ensure_ascii=False))
    elif len(sys.argv) > 1 and sys.argv[1] == "weekly":
        r = generate_weekly_summary()
        print(json.dumps(r, indent=2, ensure_ascii=False))
    else:
        result = run_trading_cycle()
        print(json.dumps(result, indent=2, ensure_ascii=False))
