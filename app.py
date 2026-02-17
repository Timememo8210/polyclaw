"""PolyClaw Web Dashboard"""
from flask import Flask, render_template, request, jsonify
import json, os, sys

sys.path.insert(0, os.path.dirname(__file__))
from market_data import get_trending_markets
from paper_trading import buy, sell, get_portfolio, get_pnl, reset

app = Flask(__name__, template_folder=os.path.dirname(__file__))

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/markets")
def api_markets():
    try:
        markets = get_trending_markets(30)
        return jsonify(markets)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/portfolio")
def api_portfolio():
    return jsonify(get_pnl())

@app.route("/api/buy", methods=["POST"])
def api_buy():
    d = request.json
    result = buy(d["market_id"], d["question"], d["side"], d["price"], d["amount"])
    return jsonify(result)

@app.route("/api/sell", methods=["POST"])
def api_sell():
    d = request.json
    result = sell(d["market_id"], d["side"], d["price"], d.get("shares"))
    return jsonify(result)

@app.route("/api/reset", methods=["POST"])
def api_reset():
    return jsonify(reset())

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8877, debug=False)
