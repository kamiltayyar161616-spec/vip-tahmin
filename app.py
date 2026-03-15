"""
BetOracle - Flask Backend
Railway deploy icin hazir
"""
import os
import datetime
import concurrent.futures
from flask import Flask, render_template, jsonify, request
from flask_caching import Cache

import football_api as fapi
import value_hunting as vh

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "betoraclev2-secret")

cache_config = {
    "CACHE_TYPE": "SimpleCache",
    "CACHE_DEFAULT_TIMEOUT": 1800,
}
cache = Cache(app, config=cache_config)


def today_str():
    return datetime.datetime.utcnow().strftime("%Y-%m-%d")


def analyze_match(match):
    cache_key = f"analysis_{match['home_id']}_{match['away_id']}"
    cached = cache.get(cache_key)
    if cached:
        match["analysis"] = cached
        return match

    try:
        # 25 saniye timeout ile veri cek
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(fapi.get_match_data, match["home_id"], match["away_id"])
            try:
                data = future.result(timeout=25)
            except concurrent.futures.TimeoutError:
                print(f"[analyze_match] timeout: {match['home_id']} vs {match['away_id']}")
                match["analysis"] = vh.fallback_result()
                return match

        if not data["home_general"] and not data["away_general"]:
            match["analysis"] = vh.fallback_result()
        else:
            result = vh.run_value_hunting(
                data["home_general"],
                data["home_venue"],
                data["away_general"],
                data["away_venue"],
            )
            cache.set(cache_key, result)
            match["analysis"] = result
    except Exception as e:
        print(f"[analyze_match] hata: {e}")
        match["analysis"] = vh.fallback_result()

    return match


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/fixtures")
def api_fixtures():
    date = request.args.get("date", today_str())
    cache_key = f"fixtures_{date}"
    cached = cache.get(cache_key)
    if cached:
        return jsonify({"success": True, "matches": cached, "date": date})
    matches = fapi.get_fixtures_by_date(date)
    cache.set(cache_key, matches, timeout=600)
    return jsonify({"success": True, "matches": matches, "date": date})


@app.route("/api/analyze/<int:home_id>/<int:away_id>")
def api_analyze(home_id, away_id):
    cache_key = f"analysis_{home_id}_{away_id}"
    cached = cache.get(cache_key)
    if cached:
        return jsonify({"success": True, "analysis": cached})

    try:
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(fapi.get_match_data, home_id, away_id)
            try:
                data = future.result(timeout=25)
            except concurrent.futures.TimeoutError:
                return jsonify({"success": True, "analysis": vh.fallback_result()})

        if not data["home_general"] and not data["away_general"]:
            return jsonify({"success": True, "analysis": vh.fallback_result()})

        result = vh.run_value_hunting(
            data["home_general"],
            data["home_venue"],
            data["away_general"],
            data["away_venue"],
        )
        cache.set(cache_key, result)
        return jsonify({"success": True, "analysis": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e),
                        "analysis": vh.fallback_result()})


@app.route("/api/analyze-all")
def api_analyze_all():
    date = request.args.get("date", today_str())
    cache_key = f"analyzed_all_{date}"
    cached = cache.get(cache_key)
    if cached:
        return jsonify({"success": True, "matches": cached, "date": date, "cached": True})
    matches = fapi.get_fixtures_by_date(date)
    analyzed = [analyze_match(m) for m in matches]
    cache.set(cache_key, analyzed, timeout=1800)
    return jsonify({"success": True, "matches": analyzed, "date": date, "cached": False})


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
