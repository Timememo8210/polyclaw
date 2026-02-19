"""
PolyClaw Auto Trader — Sky的自动交易策略
模拟盘，$10,000 启动资金

策略逻辑（信息驱动型）：
1. 扫描热门市场，结合最新新闻评估定价是否合理
2. 只在有信息优势时交易 — 没把握就不动
3. 交易频率由市场机会决定，不设硬性目标
4. 止盈/止损动态管理
5. 分散持仓，控制风险
"""
import json, os, sys, random
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(__file__))
from market_data import get_trending_markets

PORTFOLIO_FILE = os.path.join(os.path.dirname(__file__), "auto_portfolio.json")
STARTING_BALANCE = 10000.0
MAX_POSITIONS = 25
MAX_POSITION_PCT = 0.08  # 8% of balance per trade
MIN_PRICE = 0.15
MAX_PRICE = 0.85
TAKE_PROFIT = 0.08   # +8% 快速止盈
STOP_LOSS = -0.12     # -12% 止损稍宽，给波动空间
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


# Keywords for market categorization
SPORTS_KEYWORDS = ["win on 202", "win the 202", "FC ", "CF ", "AFC ", "NHL", "NBA", "NFL", "MLB",
                   "UEFA", "Champions League", "Premier League", "La Liga", "Serie A", "Ligue 1",
                   "Stanley Cup", "Super Bowl", "World Series", "match", "game on"]
POLITICS_KEYWORDS = ["Trump", "Biden", "president", "election", "Congress", "Senate", "governor",
                     "nominee", "nomination", "vote", "party", "Democrat", "Republican"]
GEOPOLITICS_KEYWORDS = ["Iran", "Russia", "Ukraine", "China", "war", "strike", "invasion",
                        "sanctions", "NATO", "military", "ceasefire", "peace", "nuclear"]
ECONOMY_KEYWORDS = ["Fed", "interest rate", "inflation", "GDP", "recession", "Bitcoin", "BTC",
                    "crypto", "tariff", "trade war", "S&P", "stock", "market crash"]

def _categorize_market(question):
    """Categorize market by type."""
    q = question.lower()
    # Check if it's a same-day/short-term sports bet
    for kw in SPORTS_KEYWORDS:
        if kw.lower() in q:
            return "sports"
    for kw in GEOPOLITICS_KEYWORDS:
        if kw.lower() in q:
            return "geopolitics"
    for kw in POLITICS_KEYWORDS:
        if kw.lower() in q:
            return "politics"
    for kw in ECONOMY_KEYWORDS:
        if kw.lower() in q:
            return "economy"
    return "other"

def _is_short_term_sports(m):
    """Detect same-day or next-day sports events — avoid these."""
    q = m.get("question", "").lower()
    # Pattern: "win on 2026-02-XX" — specific date sports bets
    import re
    if re.search(r'win on 202\d-\d{2}-\d{2}', q):
        return True
    if any(kw.lower() in q for kw in ["win on", "game on", "match on"]):
        return True
    return False

def _score_market(m):
    """Score a market for trading opportunity. Higher = better.
    
    Strategy v2: Focus on information-analyzable markets.
    - AVOID: short-term sports (no edge, pure gambling)
    - PREFER: geopolitics, politics, economy (news-analyzable)
    - OK: long-term sports (season winners, tournaments)
    """
    price = m["outcome_yes"]
    question = m.get("question", "")
    category = _categorize_market(question)
    score = 0
    
    # === HARD FILTERS ===
    # Skip short-term sports — this is where we lost $405
    if _is_short_term_sports(m):
        return 0
    
    # Skip extreme odds — no value
    if price < 0.10 or price > 0.90:
        return 0
    
    # === CATEGORY SCORING ===
    # We can analyze news for these categories
    if category == "geopolitics":
        score += 35  # Best edge: we can read news
    elif category == "economy":
        score += 30  # Fed decisions, crypto — analyzable
    elif category == "politics":
        score += 25  # Elections, nominations — lots of coverage
    elif category == "sports":
        score += 10  # Only long-term (season/tournament) gets here
    else:
        score += 15
    
    # === PRICE RANGE ===
    # Sweet spot: markets where the outcome is genuinely uncertain
    if 0.30 <= price <= 0.70:
        score += 20  # Maximum uncertainty = maximum opportunity
    elif 0.20 <= price <= 0.80:
        score += 10
    
    # === VOLUME & LIQUIDITY ===
    vol = m["volume_24h"]
    if vol > 500000: score += 20
    elif vol > 200000: score += 15
    elif vol > 100000: score += 10
    elif vol > 50000: score += 5
    else: return 0  # Too thin, skip
    
    liq = m.get("liquidity", 0)
    if liq > 100000: score += 10
    elif liq > 50000: score += 5
    
    # Small randomness for diversification (reduced from before)
    score += random.randint(0, 5)
    
    return score

def _decide_side(m):
    """Decide YES or NO based on category + price analysis.
    
    Strategy v2: category-aware decisions
    - Geopolitics: markets tend to overprice dramatic events (wars, strikes)
      → lean NO on "will X attack Y" unless price is very low
    - Economy: Fed tends to be cautious → lean toward status quo
    - Politics: incumbents/favorites tend to be slightly overpriced → look for value in underdogs
    """
    yes_price = m["outcome_yes"]
    no_price = m["outcome_no"]
    category = _categorize_market(m.get("question", ""))
    q = m.get("question", "").lower()
    
    # Geopolitics: people overestimate dramatic events
    if category == "geopolitics":
        # "Will X strike/attack Y" — markets often overprice fear
        if any(w in q for w in ["strike", "attack", "invade", "war"]):
            if yes_price > 0.35:
                return "no", no_price  # Fear is overpriced
            else:
                return "yes", yes_price  # But if it's cheap, might be real
        # "Ceasefire/peace" — markets underestimate slow diplomacy
        if any(w in q for w in ["ceasefire", "peace", "deal"]):
            if yes_price < 0.50:
                return "yes", yes_price
    
    # Economy: status quo bias works
    if category == "economy":
        if any(w in q for w in ["decrease", "increase", "crash", "recession"]):
            if yes_price > 0.50:
                return "no", no_price  # Dramatic changes less likely
            else:
                return "yes", yes_price
    
    # Default: buy the cheaper side (better risk/reward)
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
        if current_price <= 0.02 or current_price >= 0.98:
            reason = f"已结算 ({current_price*100:.0f}¢)"
        elif pnl_pct >= TAKE_PROFIT:
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
            
            amount = round(data["balance"] * MAX_POSITION_PCT, 2)
            amount = round(min(amount, data["balance"] - 500), 2)  # keep $500 reserve
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
