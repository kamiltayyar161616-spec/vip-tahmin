"""
BetOracle - Flask Backend
Sofascore proxy + analiz motoru
"""
import os
import datetime
import random
import requests
from flask import Flask, render_template, jsonify, request, Response
from flask_caching import Cache

import football_api as fapi
import value_hunting as vh

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "betoraclev2-secret")
cache = Cache(app, config={"CACHE_TYPE": "SimpleCache", "CACHE_DEFAULT_TIMEOUT": 3600})

# ── Rotating User-Agents ────────────────────────────────────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Android 14; Mobile; rv:124.0) Gecko/124.0 Firefox/124.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
]

def sofa_headers():
    return {
        "User-Agent":      random.choice(USER_AGENTS),
        "Accept":          "application/json, text/plain, */*",
        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer":         "https://www.sofascore.com/",
        "Origin":          "https://www.sofascore.com",
        "DNT":             "1",
        "Connection":      "keep-alive",
        "Sec-Fetch-Dest":  "empty",
        "Sec-Fetch-Mode":  "cors",
        "Sec-Fetch-Site":  "same-site",
        "Cache-Control":   "no-cache",
        "Pragma":          "no-cache",
    }

# ── Yardımcı ────────────────────────────────────────────────────────────────
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

# ── Routes ───────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/proxy/sofa")
def proxy_sofa():
    """
    Sofascore API proxy - bot tespitini atlatmak icin gercek tarayici gibi davranir.
    Kullanim: /proxy/sofa?path=/sport/football/scheduled-events/2025-06-15
    """
    path = request.args.get("path", "")
    if not path or not path.startswith("/"):
        return jsonify({"error": "Gecersiz path"}), 400

    # Guvenlik: sadece sofascore API path'lerine izin ver
    allowed_prefixes = [
        "/sport/football/scheduled-events/",
        "/team/",
        "/event/",
        "/tournament/",
    ]
    if not any(path.startswith(p) for p in allowed_prefixes):
        return jsonify({"error": "Izin verilmeyen path"}), 403

    cache_key = f"proxy_{path}"
    cached = cache.get(cache_key)
    if cached:
        return Response(cached, mimetype="application/json")

    url = f"https://api.sofascore.com/api/v1{path}"
    try:
        resp = requests.get(url, headers=sofa_headers(), timeout=15)
        if resp.status_code == 200:
            cache.set(cache_key, resp.text, timeout=300)
            return Response(resp.text, mimetype="application/json")
        print(f"[proxy] Sofascore {resp.status_code} — {path}")
        return jsonify({"error": f"Upstream {resp.status_code}"}), resp.status_code
    except Exception as e:
        print(f"[proxy] Hata: {e}")
        return jsonify({"error": str(e)}), 502


@app.route("/api/fixtures")
def api_fixtures():
    date      = request.args.get("date", today_str())
    cache_key = f"fix_{date}"
    cached    = cache.get(cache_key)
    if cached:
        return jsonify({"success": True, "matches": cached, "date": date})
    try:
        matches = fapi.get_fixtures_by_date(date)
        cache.set(cache_key, matches, timeout=300)
        return jsonify({"success": True, "matches": matches, "date": date})
    except Exception as e:
        print(f"[fixtures] hata: {e}")
        return jsonify({"success": False, "matches": [], "error": str(e)})


@app.route("/api/analyze/<int:home_id>/<int:away_id>")
def api_analyze(home_id, away_id):
    cache_key = f"ana_{home_id}_{away_id}"
    cached    = cache.get(cache_key)
    if cached:
        return jsonify({"success": True, "analysis": cached})
    try:
        data = fapi.get_match_data(home_id, away_id)
        if not data["home_general"] and not data["away_general"]:
            return jsonify({"success": True, "analysis": vh.fallback_result()})
        result  = vh.run_value_hunting(
            data["home_general"], data["home_venue"],
            data["away_general"], data["away_venue"]
        )
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
