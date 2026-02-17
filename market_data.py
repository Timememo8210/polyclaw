"""Polymarket data fetcher - no auth needed for read-only"""
import json
import httpx
from datetime import datetime

GAMMA_API = "https://gamma-api.polymarket.com"

def _parse_price(raw, idx):
    try:
        prices = json.loads(raw) if raw else [0, 0]
        return float(prices[idx]) if idx < len(prices) else 0
    except:
        return 0

def get_trending_markets(limit=20):
    """Fetch trending/popular markets"""
    resp = httpx.get(f"{GAMMA_API}/markets", params={
        "limit": limit,
        "active": True,
        "closed": False,
        "order": "volume24hr",
        "ascending": False,
    }, timeout=15)
    resp.raise_for_status()
    markets = resp.json()
    results = []
    for m in markets:
        results.append({
            "id": m.get("id"),
            "condition_id": m.get("conditionId"),
            "question": m.get("question", ""),
            "description": m.get("description", "")[:200],
            "outcome_yes": _parse_price(m.get("outcomePrices", ""), 0),
            "outcome_no": _parse_price(m.get("outcomePrices", ""), 1),
            "volume_24h": float(m.get("volume24hr", 0)),
            "volume_total": float(m.get("volumeNum", 0)),
            "liquidity": float(m.get("liquidityNum", 0)),
            "end_date": m.get("endDate", ""),
            "category": m.get("groupSlug", ""),
        })
    return results

def get_market_detail(market_id):
    """Fetch single market details"""
    resp = httpx.get(f"{GAMMA_API}/markets/{market_id}", timeout=15)
    resp.raise_for_status()
    return resp.json()

def search_markets(query, limit=10):
    """Search markets by keyword"""
    resp = httpx.get(f"{GAMMA_API}/markets", params={
        "limit": limit,
        "active": True,
        "closed": False,
        "tag_slug": query,
    }, timeout=15)
    # Also try text search
    resp2 = httpx.get(f"{GAMMA_API}/markets", params={
        "limit": limit,
        "active": True,
        "closed": False,
    }, timeout=15)
    resp.raise_for_status()
    return resp.json()

if __name__ == "__main__":
    markets = get_trending_markets(10)
    for m in markets:
        print(f"  {m['question']}")
        print(f"    YES: {m['outcome_yes']:.0%}  |  24h Vol: ${m['volume_24h']:,.0f}")
        print()
