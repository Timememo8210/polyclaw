"""Paper trading engine - simulated trades with fake money"""
import json
import os
from datetime import datetime

DATA_FILE = os.path.join(os.path.dirname(__file__), "portfolio.json")
STARTING_BALANCE = 1000.0  # $1000 USDC 模拟资金

def _load():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE) as f:
            return json.load(f)
    return {
        "balance": STARTING_BALANCE,
        "positions": {},  # market_id -> {question, side, shares, avg_price, bought_at}
        "history": [],    # completed trades
        "created": datetime.now().isoformat(),
    }

def _save(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_portfolio():
    return _load()

def buy(market_id, question, side, price, amount):
    """
    Buy shares.
    side: 'yes' or 'no'
    price: current price (0-1)
    amount: USD to spend
    """
    data = _load()
    if amount > data["balance"]:
        return {"error": f"余额不足。当前: ${data['balance']:.2f}, 需要: ${amount:.2f}"}
    if price <= 0 or price >= 1:
        return {"error": f"价格异常: {price}"}
    
    shares = amount / price
    data["balance"] -= amount
    
    key = f"{market_id}_{side}"
    if key in data["positions"]:
        pos = data["positions"][key]
        total_shares = pos["shares"] + shares
        pos["avg_price"] = (pos["shares"] * pos["avg_price"] + shares * price) / total_shares
        pos["shares"] = total_shares
    else:
        data["positions"][key] = {
            "market_id": market_id,
            "question": question,
            "side": side,
            "shares": shares,
            "avg_price": price,
            "bought_at": datetime.now().isoformat(),
        }
    
    data["history"].append({
        "action": "buy",
        "market_id": market_id,
        "question": question,
        "side": side,
        "price": price,
        "amount": amount,
        "shares": shares,
        "time": datetime.now().isoformat(),
    })
    
    _save(data)
    return {
        "ok": True,
        "action": "买入",
        "question": question,
        "side": side.upper(),
        "shares": round(shares, 2),
        "price": price,
        "cost": amount,
        "balance": round(data["balance"], 2),
    }

def sell(market_id, side, price, shares=None):
    """Sell shares. If shares=None, sell all."""
    data = _load()
    key = f"{market_id}_{side}"
    
    if key not in data["positions"]:
        return {"error": "没有该持仓"}
    
    pos = data["positions"][key]
    sell_shares = shares or pos["shares"]
    if sell_shares > pos["shares"]:
        return {"error": f"持仓不足。当前: {pos['shares']:.2f} 股"}
    
    proceeds = sell_shares * price
    data["balance"] += proceeds
    
    profit = (price - pos["avg_price"]) * sell_shares
    
    pos["shares"] -= sell_shares
    if pos["shares"] < 0.01:
        del data["positions"][key]
    
    data["history"].append({
        "action": "sell",
        "market_id": market_id,
        "question": pos["question"],
        "side": side,
        "price": price,
        "shares": sell_shares,
        "proceeds": proceeds,
        "profit": profit,
        "time": datetime.now().isoformat(),
    })
    
    _save(data)
    return {
        "ok": True,
        "action": "卖出",
        "question": pos["question"],
        "side": side.upper(),
        "shares": round(sell_shares, 2),
        "price": price,
        "proceeds": round(proceeds, 2),
        "profit": round(profit, 2),
        "balance": round(data["balance"], 2),
    }

def get_pnl(current_prices=None):
    """Calculate total P&L. current_prices: {market_id_side: price}"""
    data = _load()
    total_invested = STARTING_BALANCE - data["balance"]
    positions_value = 0
    
    details = []
    for key, pos in data["positions"].items():
        current = current_prices.get(key, pos["avg_price"]) if current_prices else pos["avg_price"]
        value = pos["shares"] * current
        cost = pos["shares"] * pos["avg_price"]
        pnl = value - cost
        positions_value += value
        details.append({
            "question": pos["question"],
            "side": pos["side"],
            "shares": round(pos["shares"], 2),
            "avg_price": round(pos["avg_price"], 4),
            "current_price": round(current, 4),
            "value": round(value, 2),
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl / cost * 100, 1) if cost > 0 else 0,
        })
    
    total_value = data["balance"] + positions_value
    total_pnl = total_value - STARTING_BALANCE
    
    return {
        "balance": round(data["balance"], 2),
        "positions_value": round(positions_value, 2),
        "total_value": round(total_value, 2),
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": round(total_pnl / STARTING_BALANCE * 100, 1),
        "positions": details,
        "trade_count": len(data["history"]),
    }

def reset():
    """Reset portfolio"""
    if os.path.exists(DATA_FILE):
        os.remove(DATA_FILE)
    return {"ok": True, "message": "模拟账户已重置，余额 $1,000"}
