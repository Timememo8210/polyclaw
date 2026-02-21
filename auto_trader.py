"""
PolyClaw Auto Trader v4 — 结构性策略
模拟盘，$10,000 启动资金

核心理念：放弃"信息差"幻觉，拥抱结构性优势
- 策略1: 恐惧溢价 — 市场高估戏剧性事件，买NO
- 策略2: 高概率收割 — 88%+确定事件，快进快出
- 策略3: 价格动量 — 跟随异动方向，不猜原因
- 策略4: 低概率彩票 — 小额分散，赌赔率
- 绝对禁止: 同主题反复开仓、单场体育、"分析新闻选方向"
"""
import json, os, sys, random, re
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(__file__))
from market_data import get_trending_markets

PORTFOLIO_FILE = os.path.join(os.path.dirname(__file__), "auto_portfolio.json")
TRIGGER_FILE = os.path.join(os.path.dirname(__file__), "trigger_trade.json")
STARTING_BALANCE = 10000.0

# === 通用参数 ===
MAX_POSITIONS = 25
MIN_RESERVE = 200          # 最低保留现金
MAX_TOPIC_POSITIONS = 2    # 同主题最多2个仓位

# === 策略1: 恐惧溢价 (Fear Premium) ===
FEAR_POSITION_PCT = 0.12   # 12%仓位
FEAR_TAKE_PROFIT = 0.15    # +15% 让利润跑
FEAR_STOP_LOSS = -0.08     # -8% 快速止损
FEAR_MIN_VOLUME = 100000

# === 策略2: 高概率收割 (Probability Grinding) ===
HP_POSITION_PCT = 0.10     # 10%仓位
HP_MIN_PRICE = 0.88
HP_MAX_PRICE = 0.96
HP_TAKE_PROFIT = 0.04      # +4% 快速止盈
HP_STOP_LOSS = -0.06       # -6% 止损
HP_MAX_POSITIONS = 5
HP_MIN_VOLUME = 200000     # 需要好的流动性

# === 策略3: 价格动量 (Momentum) ===
MOM_POSITION_PCT = 0.10    # 10%仓位
MOM_TAKE_PROFIT = 0.12     # +12% 止盈
MOM_STOP_LOSS = -0.08      # -8% 止损

# === 策略4: 低概率彩票 (Longshot) ===
LS_ENABLED = True
LS_MIN_PRICE = 0.001
LS_MAX_PRICE = 0.05
LS_MAX_PER_TRADE = 80      # 单笔上限$80
LS_MAX_POSITIONS = 8
LS_TAKE_PROFIT = 2.0       # +200%
LS_STOP_LOSS = -0.60
LS_MIN_DAYS_TO_EXPIRY = 7

# === 关键词 ===
SPORTS_SINGLE_GAME = [
    " vs. ", " vs ", "win on 202", "game on", "match on",
    "spread:", "spread ", "over/under", "moneyline", "total points", "total goals",
    "celtics", "warriors", "lakers", "rockets", "hornets", "knicks", "nets",
    "heat", "bucks", "76ers", "nuggets", "suns", "thunder", "cavaliers",
    "pacers", "pistons", "hawks", "bulls", "mavericks", "spurs", "clippers",
    "kings", "grizzlies", "pelicans", "timberwolves", "trail blazers",
    "jazz", "wizards", "raptors", "magic",
]

FEAR_KEYWORDS = {
    "war": ["strike", "attack", "invade", "invasion", "war ", "bomb", "military action"],
    "collapse": ["crash", "recession", "default", "collapse", "crisis"],
    "extreme": ["nuclear", "assassination", "coup", "martial law"],
}

TOPIC_KEYWORDS = [
    "iran", "russia", "ukraine", "china", "taiwan", "israel", "bitcoin", "btc",
    "fed", "trump", "biden", "canada", "alien", "anthropic", "google", "openai",
    "nato", "north korea", "venezuela",
]


def _load():
    if os.path.exists(PORTFOLIO_FILE):
        with open(PORTFOLIO_FILE) as f:
            return json.load(f)
    return {
        "balance": STARTING_BALANCE, "positions": {}, "history": [],
        "daily_snapshots": [], "created": datetime.now().isoformat(), "last_trade": None,
    }

def _save(data):
    with open(PORTFOLIO_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _is_single_game_sports(q):
    q_lower = q.lower()
    for kw in SPORTS_SINGLE_GAME:
        if kw in q_lower:
            return True
    if re.search(r'win on 202\d-\d{2}-\d{2}', q_lower):
        return True
    return False


def _get_topics(q):
    """Extract topic keywords from question."""
    q_lower = q.lower()
    return {kw for kw in TOPIC_KEYWORDS if kw in q_lower}


def _is_fear_market(q):
    """Check if market is fear-driven (war, crash, etc)."""
    q_lower = q.lower()
    for category, keywords in FEAR_KEYWORDS.items():
        for kw in keywords:
            if kw in q_lower:
                return True, category
    return False, None


def _held_topics(data):
    """Get all topics currently held, with their sides."""
    topics = {}  # topic -> set of sides
    for pos in data["positions"].values():
        for t in _get_topics(pos["question"]):
            if t not in topics:
                topics[t] = set()
            topics[t].add(pos["side"])
    return topics


def _topic_ok(question, side, data):
    """Check if we can open this position without topic conflict."""
    new_topics = _get_topics(question)
    held = _held_topics(data)
    
    for t in new_topics:
        if t in held:
            # 同主题数量限制
            count = sum(1 for pos in data["positions"].values() 
                       if t in _get_topics(pos["question"]))
            if count >= MAX_TOPIC_POSITIONS:
                return False
            # 禁止同主题反方向（这是之前最大的亏损来源）
            if side not in held[t] and len(held[t]) > 0:
                return False
    return True


def _check_expiry_days(q):
    """Estimate days to expiry from question text. Returns None if can't determine."""
    today = datetime.now()
    patterns = [
        r'(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2}),?\s*(\d{4})?',
        r'by\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+(\d{1,2})',
    ]
    for pat in patterns:
        match = re.search(pat, q.lower())
        if match:
            try:
                import dateutil.parser
                parsed = dateutil.parser.parse(match.group(0), default=today)
                return (parsed - today).days
            except:
                pass
    return None


# ============================================================
# STRATEGY 1: Fear Premium — 恐惧溢价
# ============================================================
def _find_fear_trades(markets, data):
    """Find fear-driven markets where NO is underpriced."""
    candidates = []
    
    for m in markets:
        if _is_single_game_sports(m["question"]):
            continue
        if m["volume_24h"] < FEAR_MIN_VOLUME:
            continue
        
        is_fear, fear_type = _is_fear_market(m["question"])
        if not is_fear:
            continue
        
        yes_price = m["outcome_yes"]
        no_price = m["outcome_no"]
        
        # 恐惧类市场：YES通常被高估（人们怕坏事发生）
        # 只在YES > 20%时买NO（太低说明市场已经不怕了）
        if yes_price < 0.20 or yes_price > 0.80:
            continue
        
        if not _topic_ok(m["question"], "no", data):
            continue
        
        # 已持有的跳过
        if m["id"] in {pos["market_id"] for pos in data["positions"].values()}:
            continue
        
        score = 0
        # YES越高 = 恐惧越大 = NO越便宜 = 机会越好
        if yes_price > 0.50: score += 30
        elif yes_price > 0.35: score += 20
        else: score += 10
        
        # 流动性加分
        if m["volume_24h"] > 500000: score += 15
        elif m["volume_24h"] > 200000: score += 10
        
        candidates.append((score, m))
    
    return sorted(candidates, key=lambda x: -x[0])


# ============================================================
# STRATEGY 2: High Probability Grinding — 高概率收割
# ============================================================
def _find_hp_trades(markets, data):
    """Find high-probability markets (88-96%) for safe grinding."""
    candidates = []
    
    hp_count = sum(1 for pos in data["positions"].values() if pos.get("strategy") == "hp")
    if hp_count >= HP_MAX_POSITIONS:
        return []
    
    for m in markets:
        if _is_single_game_sports(m["question"]):
            continue
        if m["volume_24h"] < HP_MIN_VOLUME:
            continue
        
        yes_price = m["outcome_yes"]
        no_price = m["outcome_no"]
        
        # 找概率高的那边
        if yes_price >= no_price:
            high_side, high_price = "yes", yes_price
        else:
            high_side, high_price = "no", no_price
        
        if high_price < HP_MIN_PRICE or high_price > HP_MAX_PRICE:
            continue
        
        if not _topic_ok(m["question"], high_side, data):
            continue
        
        if m["id"] in {pos["market_id"] for pos in data["positions"].values()}:
            continue
        
        score = 0
        # 越接近88%利润空间越大
        if high_price <= 0.90: score += 20
        elif high_price <= 0.92: score += 15
        elif high_price <= 0.94: score += 10
        else: score += 5
        
        if m["volume_24h"] > 500000: score += 15
        elif m["volume_24h"] > 300000: score += 10
        
        candidates.append((score, m, high_side))
    
    return sorted(candidates, key=lambda x: -x[0])


# ============================================================
# STRATEGY 3: Momentum — 价格动量（跟随异动）
# ============================================================
def _find_momentum_trades(markets, data):
    """React to price alerts from monitor. Buy in the direction of movement."""
    if not os.path.exists(TRIGGER_FILE):
        return []
    
    try:
        with open(TRIGGER_FILE) as f:
            trigger = json.load(f)
    except:
        return []
    
    # 只处理最近10分钟的trigger
    triggered_at = trigger.get("triggered_at", "")
    try:
        trigger_time = datetime.fromisoformat(triggered_at)
        if (datetime.now() - trigger_time).total_seconds() > 600:
            return []
    except:
        return []
    
    if trigger.get("status") == "momentum_processed":
        return []
    
    candidates = []
    markets_by_id = {m["id"]: m for m in markets}
    
    for alert in trigger.get("alerts", []):
        mid = alert.get("market_id")
        m = markets_by_id.get(mid)
        if not m:
            continue
        
        if _is_single_game_sports(m["question"]):
            continue
        
        if m["id"] in {pos["market_id"] for pos in data["positions"].values()}:
            continue
        
        old_price = alert.get("old_price", 0)
        new_price = alert.get("new_price", 0)
        change = new_price - old_price
        
        # 跟随动量方向
        if change > 0:
            side = "yes"  # YES在涨，跟着买YES
            price = new_price
        else:
            side = "no"   # YES在跌，买NO
            price = m["outcome_no"]
        
        if not _topic_ok(m["question"], side, data):
            continue
        
        score = int(abs(alert.get("change_pct", 0)) * 5)  # 变化越大分越高
        candidates.append((score, m, side))
    
    # Mark as processed
    trigger["status"] = "momentum_processed"
    with open(TRIGGER_FILE, "w") as f:
        json.dump(trigger, f, indent=2, ensure_ascii=False)
    
    return sorted(candidates, key=lambda x: -x[0])


# ============================================================
# STRATEGY 4: Longshot — 低概率彩票
# ============================================================
def _find_longshot_trades(markets, data):
    """Find ultra-low probability markets for lottery plays."""
    if not LS_ENABLED:
        return []
    
    ls_count = sum(1 for pos in data["positions"].values() if pos.get("strategy") == "ls")
    if ls_count >= LS_MAX_POSITIONS:
        return []
    
    candidates = []
    for m in markets:
        yes_price = m["outcome_yes"]
        if yes_price < LS_MIN_PRICE or yes_price > LS_MAX_PRICE:
            continue
        if _is_single_game_sports(m["question"]):
            continue
        if m["id"] in {pos["market_id"] for pos in data["positions"].values()}:
            continue
        
        # 检查到期日
        days = _check_expiry_days(m["question"])
        if days is not None and days < LS_MIN_DAYS_TO_EXPIRY:
            continue
        
        score = 20
        if m["volume_24h"] > 100000: score += 15
        elif m["volume_24h"] > 50000: score += 10
        
        if yes_price <= 0.01: score += 15
        elif yes_price <= 0.03: score += 10
        
        # 地缘政治/政治更容易出黑天鹅
        is_fear, _ = _is_fear_market(m["question"])
        if is_fear: score += 10
        
        candidates.append((score, m))
    
    return sorted(candidates, key=lambda x: -x[0])


# ============================================================
# MAIN TRADING CYCLE
# ============================================================
def run_trading_cycle():
    data = _load()
    actions = []
    
    # 1. Fetch markets
    try:
        markets = get_trending_markets(100)
    except Exception as e:
        return {"error": f"获取市场数据失败: {e}", "actions": []}
    
    markets_by_id = {m["id"]: m for m in markets}
    
    # 2. 止盈止损检查
    positions_to_close = []
    for key, pos in list(data["positions"].items()):
        m = markets_by_id.get(pos["market_id"])
        if not m:
            continue
        
        current_price = m["outcome_yes"] if pos["side"] == "yes" else m["outcome_no"]
        pnl_pct = (current_price - pos["avg_price"]) / pos["avg_price"] if pos["avg_price"] > 0 else 0
        
        strategy = pos.get("strategy", "fear")
        if strategy == "hp":
            tp, sl = HP_TAKE_PROFIT, HP_STOP_LOSS
        elif strategy == "ls":
            tp, sl = LS_TAKE_PROFIT, LS_STOP_LOSS
        elif strategy == "momentum":
            tp, sl = MOM_TAKE_PROFIT, MOM_STOP_LOSS
        else:
            tp, sl = FEAR_TAKE_PROFIT, FEAR_STOP_LOSS
        
        reason = None
        if current_price <= 0.002 or current_price >= 0.98:
            reason = f"已结算 ({current_price*100:.1f}¢)"
        elif pnl_pct >= tp:
            reason = f"止盈 +{pnl_pct*100:.0f}%"
        elif pnl_pct <= sl:
            reason = f"止损 {pnl_pct*100:.0f}%"
        
        if reason:
            proceeds = pos["shares"] * current_price
            profit = (current_price - pos["avg_price"]) * pos["shares"]
            data["balance"] += proceeds
            data["history"].append({
                "action": "sell", "question": pos["question"], "side": pos["side"],
                "price": current_price, "shares": pos["shares"], "proceeds": round(proceeds, 2),
                "profit": round(profit, 2), "reason": reason, "strategy": strategy,
                "time": datetime.now().isoformat()
            })
            emoji = {"fear": "🛡️", "hp": "💎", "momentum": "⚡", "ls": "🎰"}.get(strategy, "📤")
            actions.append(f"{emoji} 卖出 | {pos['question'][:40]} | {reason} | {'赚' if profit>0 else '亏'}${abs(profit):.2f}")
            positions_to_close.append(key)
    
    for key in positions_to_close:
        del data["positions"][key]
    
    num_positions = len(data["positions"])
    
    # 3. 策略1: 恐惧溢价 — 买NO
    if num_positions < MAX_POSITIONS:
        fear_trades = _find_fear_trades(markets, data)
        for score, m in fear_trades[:2]:  # 每周期最多2个
            amount = round(min(data["balance"] * FEAR_POSITION_PCT, data["balance"] - MIN_RESERVE), 2)
            if amount < 30:
                break
            no_price = m["outcome_no"]
            if no_price <= 0 or no_price >= 1:
                continue
            shares = amount / no_price
            data["balance"] -= amount
            key = f"fear_{m['id']}_no"
            data["positions"][key] = {
                "market_id": m["id"], "question": m["question"], "side": "no",
                "shares": round(shares, 2), "avg_price": round(no_price, 4),
                "bought_at": datetime.now().isoformat(), "strategy": "fear", "score": score
            }
            data["history"].append({
                "action": "buy", "question": m["question"], "side": "no",
                "price": no_price, "amount": amount, "shares": round(shares, 2),
                "strategy": "fear", "time": datetime.now().isoformat()
            })
            actions.append(f"🛡️ 恐惧溢价 | {m['question'][:40]} | NO @ {no_price*100:.0f}¢ | ${amount:.0f}")
            num_positions += 1
    
    # 4. 策略2: 高概率收割
    if num_positions < MAX_POSITIONS:
        hp_trades = _find_hp_trades(markets, data)
        for score, m, side in hp_trades[:2]:
            amount = round(min(data["balance"] * HP_POSITION_PCT, data["balance"] - MIN_RESERVE), 2)
            if amount < 50:
                break
            price = m["outcome_yes"] if side == "yes" else m["outcome_no"]
            if price <= 0 or price >= 1:
                continue
            shares = amount / price
            data["balance"] -= amount
            key = f"hp_{m['id']}_{side}"
            data["positions"][key] = {
                "market_id": m["id"], "question": m["question"], "side": side,
                "shares": round(shares, 2), "avg_price": round(price, 4),
                "bought_at": datetime.now().isoformat(), "strategy": "hp", "score": score
            }
            data["history"].append({
                "action": "buy", "question": m["question"], "side": side,
                "price": price, "amount": amount, "shares": round(shares, 2),
                "strategy": "hp", "time": datetime.now().isoformat()
            })
            actions.append(f"💎 高概率 | {m['question'][:40]} | {side.upper()} @ {price*100:.0f}¢ | ${amount:.0f}")
            num_positions += 1
    
    # 5. 策略3: 价格动量
    if num_positions < MAX_POSITIONS:
        mom_trades = _find_momentum_trades(markets, data)
        for score, m, side in mom_trades[:2]:
            amount = round(min(data["balance"] * MOM_POSITION_PCT, data["balance"] - MIN_RESERVE), 2)
            if amount < 30:
                break
            price = m["outcome_yes"] if side == "yes" else m["outcome_no"]
            if price <= 0 or price >= 1:
                continue
            shares = amount / price
            data["balance"] -= amount
            key = f"mom_{m['id']}_{side}"
            data["positions"][key] = {
                "market_id": m["id"], "question": m["question"], "side": side,
                "shares": round(shares, 2), "avg_price": round(price, 4),
                "bought_at": datetime.now().isoformat(), "strategy": "momentum", "score": score
            }
            data["history"].append({
                "action": "buy", "question": m["question"], "side": side,
                "price": price, "amount": amount, "shares": round(shares, 2),
                "strategy": "momentum", "time": datetime.now().isoformat()
            })
            actions.append(f"⚡ 动量 | {m['question'][:40]} | {side.upper()} @ {price*100:.0f}¢ | ${amount:.0f}")
            num_positions += 1
    
    # 6. 策略4: 低概率彩票
    if num_positions < MAX_POSITIONS:
        ls_trades = _find_longshot_trades(markets, data)
        for score, m in ls_trades[:2]:
            amount = round(min(LS_MAX_PER_TRADE, data["balance"] - MIN_RESERVE), 2)
            if amount < 5:
                break
            yes_price = m["outcome_yes"]
            limit_price = round(max(yes_price * 0.75, 0.001), 4)
            shares = amount / limit_price
            data["balance"] -= amount
            key = f"ls_{m['id']}_yes"
            data["positions"][key] = {
                "market_id": m["id"], "question": m["question"], "side": "yes",
                "shares": round(shares, 2), "avg_price": limit_price,
                "bought_at": datetime.now().isoformat(), "strategy": "ls", "score": score
            }
            data["history"].append({
                "action": "buy", "question": m["question"], "side": "yes",
                "price": limit_price, "amount": amount, "shares": round(shares, 2),
                "strategy": "ls", "time": datetime.now().isoformat()
            })
            actions.append(f"🎰 彩票 | {m['question'][:40]} | YES @ {limit_price*100:.1f}¢ | ${amount:.0f}")
            num_positions += 1
    
    data["last_trade"] = datetime.now().isoformat()
    _save(data)
    
    return {"actions": actions, "balance": round(data["balance"], 2), "positions": len(data["positions"])}


def generate_report():
    data = _load()
    try:
        markets = get_trending_markets(100)
        markets_by_id = {m["id"]: m for m in markets}
    except:
        markets_by_id = {}
    
    total_value = data["balance"]
    pos_details = []
    
    for key, pos in data["positions"].items():
        m = markets_by_id.get(pos["market_id"])
        cp = m["outcome_yes"] if m and pos["side"] == "yes" else (m["outcome_no"] if m else pos["avg_price"])
        
        value = pos["shares"] * cp
        cost = pos["shares"] * pos["avg_price"]
        pnl = value - cost
        total_value += value
        
        pos_details.append({
            "question": pos["question"], "side": pos["side"],
            "shares": pos["shares"], "avg_price": pos["avg_price"],
            "current_price": round(cp, 4), "value": round(value, 2),
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl / cost * 100, 1) if cost > 0 else 0,
            "strategy": pos.get("strategy", "unknown"),
        })
    
    total_pnl = total_value - STARTING_BALANCE
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
        "recent_trades": recent[-5:],
    }


def generate_weekly_summary():
    data = _load()
    report = generate_report()
    
    sells = [h for h in data["history"] if h["action"] == "sell"]
    wins = sum(1 for s in sells if s.get("profit", 0) > 0)
    losses = sum(1 for s in sells if s.get("profit", 0) < 0)
    total_profit = sum(s.get("profit", 0) for s in sells)
    
    # 按策略统计
    strategy_stats = {}
    for s in sells:
        st = s.get("strategy", "unknown")
        if st not in strategy_stats:
            strategy_stats[st] = {"wins": 0, "losses": 0, "profit": 0}
        if s.get("profit", 0) > 0:
            strategy_stats[st]["wins"] += 1
        else:
            strategy_stats[st]["losses"] += 1
        strategy_stats[st]["profit"] += s.get("profit", 0)
    
    return {
        **report,
        "wins": wins, "losses": losses,
        "win_rate": round(wins/(wins+losses)*100, 1) if (wins+losses) > 0 else 0,
        "realized_profit": round(total_profit, 2),
        "strategy_stats": {k: {**v, "profit": round(v["profit"], 2)} for k, v in strategy_stats.items()},
        "snapshots": data.get("daily_snapshots", [])[-7:],
    }


def take_daily_snapshot():
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
    data["daily_snapshots"] = data["daily_snapshots"][-90:]
    _save(data)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "report":
        r = generate_report()
        print(json.dumps(r, indent=2, ensure_ascii=False))
    elif len(sys.argv) > 1 and sys.argv[1] == "weekly":
        r = generate_weekly_summary()
        print(json.dumps(r, indent=2, ensure_ascii=False))
    else:
        result = run_trading_cycle()
        print(json.dumps(result, indent=2, ensure_ascii=False))
