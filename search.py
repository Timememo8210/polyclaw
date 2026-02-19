"""Serper Google Search — 免费2500次/月"""
import os, json, httpx

SERPER_KEY = os.environ.get("SERPER_API_KEY", "")

def search(query, num=5):
    """Google search via Serper API. Returns list of {title, link, snippet, date}."""
    if not SERPER_KEY:
        return {"error": "SERPER_API_KEY not set"}
    resp = httpx.post("https://google.serper.dev/search",
        headers={"X-API-KEY": SERPER_KEY, "Content-Type": "application/json"},
        json={"q": query, "num": num},
        timeout=10)
    resp.raise_for_status()
    data = resp.json()
    results = []
    for r in data.get("organic", []):
        results.append({
            "title": r.get("title", ""),
            "link": r.get("link", ""),
            "snippet": r.get("snippet", ""),
            "date": r.get("date", ""),
        })
    return results

def news_search(query, num=5):
    """Google News search via Serper."""
    if not SERPER_KEY:
        return {"error": "SERPER_API_KEY not set"}
    resp = httpx.post("https://google.serper.dev/news",
        headers={"X-API-KEY": SERPER_KEY, "Content-Type": "application/json"},
        json={"q": query, "num": num},
        timeout=10)
    resp.raise_for_status()
    data = resp.json()
    results = []
    for r in data.get("news", []):
        results.append({
            "title": r.get("title", ""),
            "link": r.get("link", ""),
            "snippet": r.get("snippet", ""),
            "date": r.get("date", ""),
            "source": r.get("source", ""),
        })
    return results

if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "Polymarket prediction market news"
    results = news_search(q)
    for r in results:
        print(f"📰 [{r.get('date','')}] {r['title']}")
        print(f"   {r['snippet'][:100]}")
        print(f"   {r['source']} — {r['link']}")
        print()
