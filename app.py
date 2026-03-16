"""
BetOracle - Flask Backend
Hibrit API: Bzzoiro + AllSports
"""
import os
import datetime
from flask import Flask, render_template, jsonify, request
from flask_caching import Cache

import football_api as fapi
import value_hunting as vh

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "betoraclev2-secret")

cache_config = {
    "CACHE_TYPE": "SimpleCache",
    "CACHE_DEFAULT_TIMEOUT": 3600,
}
cache = Cache(app, config=cache_config)


def today_str():
    return datetime.datetime.utcnow().strftime("%Y-%m-%d")


def compute_rating(matches, limit=6):
    last     = matches[-limit:] if len(matches) > limit else matches
    scored   = sum(m.get("goals_scored",   0) for m in last)
    conceded = sum(m.get("goals_conceded", 0) for m in last)
    return scored - conceded


def compute_match_ratings(data):
    home_g  = compute_rating(data.get("home_general", []), 6)
    away_g  = compute_rating(data.get("away_general", []), 6)
    home_id = compute_rating(data.get("home_venue",   []), 6)
    away_id = compute_rating(data.get("away_venue",   []), 6)
    return {
        "g_rating":       home_g - away_g,
        "id_rating":      home_id - away_id,
        "home_g_rating":  home_g,
        "away_g_rating":  away_g,
        "home_id_rating": home_id,
        "away_id_rating": away_id,
    }


def run_analysis(home_id, away_id, home_name="", away_name="", league_name=""):
    try:
        data = fapi.get_match_data(home_id, away_id, home_name, away_name, league_name)
        if not data["home_general"] and not data["away_general"]:
            return vh.fallback_result()
        result  = vh.run_value_hunting(
            data["home_general"],
            data["home_venue"],
            data["away_general"],
            data["away_venue"],
        )
        ratings = compute_match_ratings(data)
        result.update(ratings)
        return result
    except Exception as e:
        print(f"[run_analysis] hata: {e}")
        return vh.fallback_result()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/fixtures")
def api_fixtures():
    date      = request.args.get("date", today_str())
    cache_key = f"fixtures_v4_{date}"
    cached    = cache.get(cache_key)
    if cached:
        return jsonify({"success": True, "matches": cached, "date": date})
    try:
        matches = fapi.get_fixtures_by_date(date)
        cache.set(cache_key, matches, timeout=600)
        return jsonify({"success": True, "matches": matches, "date": date})
    except Exception as e:
        return jsonify({"success": False, "matches": [], "date": date, "error": str(e)})


@app.route("/api/analyze/<int:home_id>/<int:away_id>")
def api_analyze(home_id, away_id):
    # Takım isimleri ve lig ismi query param olarak alınabilir
    home_name   = request.args.get("hn", "")
    away_name   = request.args.get("an", "")
    league_name = request.args.get("ln", "")

    cache_key = f"analysis_v4_{home_id}_{away_id}"
    cached    = cache.get(cache_key)
    if cached:
        return jsonify({"success": True, "analysis": cached})
    try:
        result = run_analysis(home_id, away_id, home_name, away_name, league_name)
        cache.set(cache_key, result)
        return jsonify({"success": True, "analysis": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e),
                        "analysis": vh.fallback_result()})


@app.route("/api/clear-cache")
def api_clear_cache():
    cache.clear()
    return jsonify({"success": True, "message": "Cache temizlendi"})


@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Sayfa bulunamadi"}), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Sunucu hatasi"}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
