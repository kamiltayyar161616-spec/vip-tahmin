"""
BetOracle - Flask Backend
AllSports leagueId ile takim gecmisi
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
    last     = matches[:limit]
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


@app.route("/ping")
def ping():
    """Keep-alive endpoint - UptimeRobot veya benzeri servisler icin."""
    return jsonify({"status": "ok"}), 200


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
    league_key = request.args.get("lk", type=int)
    no_cache   = request.args.get("nc", "0")
    cache_key  = f"ana_{home_id}_{away_id}"

    if no_cache == "0":
        cached = cache.get(cache_key)
        if cached:
            return jsonify({"success": True, "analysis": cached})

    try:
        data = fapi.get_match_data(home_id, away_id, league_key)
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


@app.route("/api/debug/<int:team_id>/<int:league_id>")
def api_debug(team_id, league_id):
    """Cache bypass ederek takim maclarini goster."""
    # League cache'i temizle
    fapi._league_cache.pop(league_id, None)

    # Yeniden cek
    all_matches = fapi.get_team_matches_from_league(team_id, league_id, 20)

    # Tarih bilgisi icin ham veriyi tekrar al
    raw = fapi._league_cache.get(league_id, [])
    team_raw = [ev for ev in raw if
                int(ev.get("home_team_key", 0)) == team_id or
                int(ev.get("away_team_key", 0)) == team_id]

    detailed = []
    for ev in team_raw[:10]:
        p = fapi._parse_team_match(ev, team_id)
        if p:
            p["date"]  = ev.get("event_date", "")
            p["score"] = ev.get("event_final_result", "")
            detailed.append(p)

    return jsonify({
        "total_league": len(fapi._league_cache.get(league_id, [])),
        "team_matches":  len(team_raw),
        "parsed":        len(all_matches),
        "first3_dates":  [ev.get("event_date") for ev in team_raw[:3]],
        "last3_dates":   [ev.get("event_date") for ev in team_raw[-3:]],
        "last6_detailed": detailed[:6],
    })


@app.route("/api/clear-cache")
def api_clear_cache():
    cache.clear()
    fapi._league_cache.clear()
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
