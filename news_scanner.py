"""免费新闻扫描 — 0成本信息源"""
import httpx, json, re
from datetime import datetime

NEWS_SOURCES = [
    {"name": "Reuters Top", "url": "https://www.reuters.com/world/", "focus": "geopolitics"},
    {"name": "AP News", "url": "https://apnews.com/hub/world-news", "focus": "world"},
    {"name": "ESPN", "url": "https://www.espn.com/", "focus": "sports"},
]

def scan_polymarket_movers(markets_before, markets_after):
    """Detect significant price movements between two snapshots."""
    movers = []
    before_map = {m["id"]: m for m in markets_before}
    
    for m in markets_after:
        prev = before_map.get(m["id"])
        if not prev:
            continue
        
        price_change = abs(m["outcome_yes"] - prev["outcome_yes"])
        vol_ratio = m["volume_24h"] / max(prev["volume_24h"], 1)
        
        if price_change >= 0.05:  # 5%+ price move
            movers.append({
                "question": m["question"],
                "id": m["id"],
                "price_before": prev["outcome_yes"],
                "price_after": m["outcome_yes"],
                "change": m["outcome_yes"] - prev["outcome_yes"],
                "volume_24h": m["volume_24h"],
                "signal": "strong" if price_change >= 0.10 else "moderate",
            })
        elif vol_ratio > 3:  # volume spike 3x+
            movers.append({
                "question": m["question"],
                "id": m["id"],
                "price_before": prev["outcome_yes"],
                "price_after": m["outcome_yes"],
                "change": m["outcome_yes"] - prev["outcome_yes"],
                "volume_24h": m["volume_24h"],
                "signal": "volume_spike",
            })
    
    movers.sort(key=lambda x: abs(x["change"]), reverse=True)
    return movers

def fetch_headline(url, timeout=10):
    """Fetch headlines from a news source."""
    try:
        resp = httpx.get(url, timeout=timeout, follow_redirects=True,
                        headers={"User-Agent": "Mozilla/5.0"})
        # Extract title tags as rough headlines
        titles = re.findall(r'<title[^>]*>(.*?)</title>', resp.text, re.IGNORECASE)
        # Extract h2/h3 headlines
        headlines = re.findall(r'<h[23][^>]*>(.*?)</h[23]>', resp.text, re.IGNORECASE | re.DOTALL)
        # Clean HTML tags
        clean = lambda s: re.sub(r'<[^>]+>', '', s).strip()
        return [clean(h) for h in (titles + headlines)[:10] if len(clean(h)) > 10]
    except:
        return []

SNAPSHOT_FILE = __import__('os').path.join(__import__('os').path.dirname(__file__), "market_snapshot.json")

def save_snapshot(markets):
    with open(SNAPSHOT_FILE, "w") as f:
        json.dump({"time": datetime.now().isoformat(), "markets": markets}, f)

def load_snapshot():
    try:
        with open(SNAPSHOT_FILE) as f:
            return json.load(f)["markets"]
    except:
        return []

if __name__ == "__main__":
    for src in NEWS_SOURCES:
        headlines = fetch_headline(src["url"])
        print(f"\n📰 {src['name']}:")
        for h in headlines[:5]:
            print(f"  • {h}")
