"""
BetOracle - Flask Backend
Takim gecmisi tarayicidan gelir (Sofascore JS)
"""
import os
import datetime
from flask import Flask, render_template, jsonify, request
from flask_caching import Cache

import football_api as fapi
import value_hunting as vh

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "betoraclev2-secret")
cache = Cache(app, config={"CACHE_TYPE": "SimpleCache", "CACHE_DEFAULT_TIMEOUT": 3600})


def today_str():
    return datetime.datetime.utcnow().strftime("%Y-%m-%d")


def compute_rating(matches, limit=6):
    last     = matches[-limit:] if len(matches) > limit else matches
    scored   = sum(m.get("goals_scored",   0) for m in last)
    conceded = sum(m.get("goals_conceded", 0) for m in last)
    return scored - conceded


def compute_ratings(data):
    hg = compute_rating(data.get("home_general", []), 6)
    ag = compute_rating(data.get("away_general", []), 6)
    hi = compute_rating(data.get("home_venue",   []), 6)
    ai = compute_rating(data.get("away_venue",   []), 6)
    return {
        "g_rating":       hg - ag,
        "id_rating":      hi - ai,
        "home_g_rating":  hg,
        "away_g_rating":  ag,
        "home_id_rating": hi,
        "away_id_rating": ai,
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/fixtures")
def api_fixtures():
    date      = request.args.get("date", today_str())
    cache_key = f"fix_{date}"
    cached    = cache.get(cache_key)
    if cached:
        return jsonify({"success": True, "matches": cached, "date": date})
    try:
        matches = fapi.get_fixtures_by_date(date)
        cache.set(cache_key, matches, timeout=600)
        return jsonify({"success": True, "matches": matches, "date": date})
    except Exception as e:
        return jsonify({"success": False, "matches": [], "error": str(e)})


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    try:
        data    = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Veri yok"})

        home_id = data.get("home_id", 0)
        away_id = data.get("away_id", 0)

        cache_key = f"ana_{home_id}_{away_id}"
        cached    = cache.get(cache_key)
        if cached:
            return jsonify({"success": True, "analysis": cached})

        home_general = data.get("home_general", [])
        home_venue   = data.get("home_venue",   [])
        away_general = data.get("away_general", [])
        away_venue   = data.get("away_venue",   [])

        if not home_general and not away_general:
            return jsonify({"success": True, "analysis": vh.fallback_result()})

        result  = vh.run_value_hunting(home_general, home_venue, away_general, away_venue)
        ratings = compute_ratings(data)
        result.update(ratings)

        cache.set(cache_key, result)
        return jsonify({"success": True, "analysis": result})

    except Exception as e:
        print(f"[analyze] hata: {e}")
        return jsonify({"success": False, "error": str(e), "analysis": vh.fallback_result()})


@app.route("/api/clear-cache")
def api_clear_cache():
    cache.clear()
    return jsonify({"success": True, "message": "Cache temizlendi"})


@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Bulunamadi"}), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Sunucu hatasi"}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
