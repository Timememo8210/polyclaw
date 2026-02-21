"""
PolyClaw Price Monitor — 价格异动监控
每分钟扫描持仓市场，价格异动>5%时触发交易周期

纯Python运行，不费Claude token
只在检测到异动时通过webhook/文件信号唤醒交易
"""
import json, os, sys, time, logging
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(__file__))

PORTFOLIO_FILE = os.path.join(os.path.dirname(__file__), "auto_portfolio.json")
PRICE_CACHE_FILE = os.path.join(os.path.dirname(__file__), "price_cache.json")
ALERT_FILE = os.path.join(os.path.dirname(__file__), "price_alerts.json")
LOG_FILE = os.path.join(os.path.dirname(__file__), "monitor.log")

# 异动阈值
ALERT_THRESHOLD = 0.05      # 5% 价格变化触发警报
SCAN_INTERVAL = 60           # 每60秒扫描一次
COOLDOWN_MINUTES = 30        # 同一市场警报冷却30分钟
MAX_ALERTS_PER_HOUR = 5      # 每小时最多触发5次交易

# Trending markets也监控（发现新机会）
SCAN_TRENDING = True
TRENDING_THRESHOLD = 0.08    # trending市场需要8%变化才报警（避免噪音）

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("price_monitor")


def load_portfolio():
    if os.path.exists(PORTFOLIO_FILE):
        with open(PORTFOLIO_FILE) as f:
            return json.load(f)
    return {"positions": {}}


def load_price_cache():
    if os.path.exists(PRICE_CACHE_FILE):
        with open(PRICE_CACHE_FILE) as f:
            return json.load(f)
    return {}


def save_price_cache(cache):
    with open(PRICE_CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)


def load_alerts():
    if os.path.exists(ALERT_FILE):
        with open(ALERT_FILE) as f:
            return json.load(f)
    return {"alerts": [], "last_trigger": None, "triggers_this_hour": 0, "hour": None}


def save_alerts(data):
    with open(ALERT_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def fetch_market_prices(market_ids):
    """Fetch current prices for specific markets from Gamma API."""
    from market_data import get_trending_markets
    try:
        markets = get_trending_markets(100)
        prices = {}
        for m in markets:
            prices[m["id"]] = {
                "yes": m["outcome_yes"],
                "no": m["outcome_no"],
                "question": m["question"],
                "volume_24h": m["volume_24h"],
            }
        return prices
    except Exception as e:
        log.error(f"Failed to fetch prices: {e}")
        return {}


def check_price_movements(current_prices, cached_prices):
    """Compare current vs cached prices, return alerts."""
    alerts = []
    
    for mid, cur in current_prices.items():
        if mid not in cached_prices:
            continue
        
        old = cached_prices[mid]
        old_yes = old.get("yes", 0)
        cur_yes = cur["yes"]
        
        if old_yes <= 0.001:
            continue
        
        pct_change = abs(cur_yes - old_yes) / old_yes
        
        # Different thresholds for held vs trending
        threshold = ALERT_THRESHOLD  # default 5%
        
        if pct_change >= threshold:
            direction = "📈" if cur_yes > old_yes else "📉"
            alerts.append({
                "market_id": mid,
                "question": cur.get("question", "Unknown"),
                "old_price": old_yes,
                "new_price": cur_yes,
                "change_pct": round(pct_change * 100, 1),
                "direction": direction,
                "time": datetime.now().isoformat(),
            })
    
    return alerts


def should_trigger_trade(alert_data):
    """Check cooldown and rate limits."""
    now = datetime.now()
    current_hour = now.strftime("%Y-%m-%d-%H")
    
    # Reset hourly counter
    if alert_data.get("hour") != current_hour:
        alert_data["hour"] = current_hour
        alert_data["triggers_this_hour"] = 0
    
    if alert_data["triggers_this_hour"] >= MAX_ALERTS_PER_HOUR:
        log.info(f"Rate limited: {alert_data['triggers_this_hour']} triggers this hour")
        return False
    
    return True


def trigger_trading_cycle(alerts):
    """Write alert file to signal that a trading cycle should run.
    
    The cron job or a watcher can check this file and invoke the trader.
    """
    alert_summary = []
    for a in alerts:
        alert_summary.append(
            f"{a['direction']} {a['question'][:50]} | {a['old_price']*100:.0f}¢→{a['new_price']*100:.0f}¢ ({a['change_pct']:+.1f}%)"
        )
    
    trigger = {
        "triggered_at": datetime.now().isoformat(),
        "alerts": alerts,
        "summary": alert_summary,
        "status": "pending",  # pending → processed
    }
    
    trigger_file = os.path.join(os.path.dirname(__file__), "trigger_trade.json")
    with open(trigger_file, "w") as f:
        json.dump(trigger, f, indent=2, ensure_ascii=False)
    
    log.info(f"🚨 TRADE TRIGGERED: {len(alerts)} alerts")
    for s in alert_summary:
        log.info(f"  {s}")
    
    return trigger_file


def run_monitor_loop():
    """Main monitoring loop — runs forever."""
    log.info("=" * 50)
    log.info("🔍 PolyClaw Price Monitor started")
    log.info(f"   Scan interval: {SCAN_INTERVAL}s")
    log.info(f"   Alert threshold: {ALERT_THRESHOLD*100}%")
    log.info(f"   Max triggers/hour: {MAX_ALERTS_PER_HOUR}")
    log.info("=" * 50)
    
    while True:
        try:
            # 1. Load current state
            portfolio = load_portfolio()
            cache = load_price_cache()
            alert_data = load_alerts()
            
            # 2. Get held market IDs
            held_ids = {pos["market_id"] for pos in portfolio.get("positions", {}).values()}
            
            # 3. Fetch current prices
            current_prices = fetch_market_prices(held_ids)
            
            if not current_prices:
                log.warning("No prices fetched, sleeping...")
                time.sleep(SCAN_INTERVAL)
                continue
            
            # 4. Check for movements
            new_alerts = check_price_movements(current_prices, cache)
            
            # 5. Filter for held positions (priority) and cooldown
            now = datetime.now()
            cooled_alerts = []
            for a in new_alerts:
                # Check cooldown
                last_alert_time = None
                for prev in alert_data.get("alerts", [])[-50:]:
                    if prev["market_id"] == a["market_id"]:
                        try:
                            last_alert_time = datetime.fromisoformat(prev["time"])
                        except:
                            pass
                
                if last_alert_time and (now - last_alert_time).total_seconds() < COOLDOWN_MINUTES * 60:
                    continue
                
                # Held positions get priority
                a["is_held"] = a["market_id"] in held_ids
                cooled_alerts.append(a)
            
            # 6. Trigger if we have alerts
            if cooled_alerts and should_trigger_trade(alert_data):
                trigger_trading_cycle(cooled_alerts)
                alert_data["triggers_this_hour"] = alert_data.get("triggers_this_hour", 0) + 1
                alert_data["last_trigger"] = now.isoformat()
                alert_data["alerts"] = alert_data.get("alerts", []) + cooled_alerts
                # Keep last 200 alerts
                alert_data["alerts"] = alert_data["alerts"][-200:]
                save_alerts(alert_data)
            else:
                if not new_alerts:
                    log.debug("No price movements detected")
            
            # 7. Update cache
            save_price_cache(current_prices)
            
        except Exception as e:
            log.error(f"Monitor error: {e}", exc_info=True)
        
        time.sleep(SCAN_INTERVAL)


def run_once():
    """Single scan — useful for testing."""
    portfolio = load_portfolio()
    cache = load_price_cache()
    
    held_ids = {pos["market_id"] for pos in portfolio.get("positions", {}).values()}
    current_prices = fetch_market_prices(held_ids)
    
    if not current_prices:
        print("❌ No prices fetched")
        return
    
    print(f"📊 Scanned {len(current_prices)} markets, {len(held_ids)} held")
    
    if cache:
        alerts = check_price_movements(current_prices, cache)
        if alerts:
            print(f"\n🚨 {len(alerts)} price movements:")
            for a in alerts:
                print(f"  {a['direction']} {a['question'][:50]} | {a['change_pct']:+.1f}%")
        else:
            print("✅ No significant movements")
    else:
        print("📝 First run — caching prices")
    
    save_price_cache(current_prices)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "once":
        run_once()
    else:
        run_monitor_loop()
