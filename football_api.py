"""
Live-Score-API.com - Fiktur + Takim Istatistik Cekici
"""
import requests
import datetime
import os
from typing import Optional

BASE = "https://live-score-api.com/api-client"

API_KEY    = os.environ.get("LIVESCORE_KEY",    "ID0xMVIUGwip7fzY")
API_SECRET = os.environ.get("LIVESCORE_SECRET", "C7b6mK3wocmicEDxhD44zqYfWhF3we19")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "application/json",
}
TIMEOUT = 15


def _get(endpoint, params=None):
    if params is None:
        params = {}
    params["key"]    = API_KEY
    params["secret"] = API_SECRET
    url = f"{BASE}/{endpoint}"
    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=TIMEOUT)
        if r.status_code == 200:
            data = r.json()
            if data.get("success"):
                return data.get("data")
            else:
                print(f"[API] Hata: {data}")
        else:
            print(f"[API] HTTP {r.status_code}")
    except Exception as e:
        print(f"[API] Istek hatasi: {e}")
    return None


def get_fixtures_by_date(date_str):
    data = _get("fixtures/matches.json", {"date": date_str})
    if not data or "match" not in data:
        return []

    matches = []
    for ev in data["match"]:
        try:
            home_id   = int(ev["home"]["id"])
            away_id   = int(ev["away"]["id"])
            match_id  = str(ev.get("id", ""))
            home_name = ev["home"]["name"]
            away_name = ev["away"]["name"]

            competition  = ev.get("competition", {})
            country      = ev.get("country", {})
            league_name  = competition.get("name", "")
            country_name = country.get("name", "")
            league_full  = f"{country_name} - {league_name}" if country_name else league_name

            scheduled  = ev.get("scheduled", "00:00")
            match_time = scheduled[:5] if scheduled else "00:00"

            try:
                dt = datetime.datetime.strptime(f"{date_str} {match_time}", "%Y-%m-%d %H:%M")
                timestamp = int(dt.timestamp())
            except Exception:
                timestamp = 0

            matches.append({
                "match_id":  match_id,
                "home_team": home_name,
                "away_team": away_name,
                "home_id":   home_id,
                "away_id":   away_id,
                "league":    league_full,
                "time":      match_time,
                "status":    0,
                "timestamp": timestamp,
            })
        except (KeyError, TypeError, ValueError):
            continue

    matches.sort(key=lambda x: x["timestamp"])
    return matches


def _parse_match(ev, team_id):
    try:
        home_id   = int(ev["home"]["id"])
        scores    = ev.get("scores", {})
        score_str = scores.get("score", "0 - 0") or "0 - 0"
        parts     = score_str.replace(" ", "").split("-")
        home_score = int(parts[0]) if parts[0].isdigit() else 0
        away_score = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0

        is_home  = (team_id == home_id)
        scored   = home_score if is_home else away_score
        conceded = away_score if is_home else home_score
        result   = "W" if scored > conceded else ("D" if scored == conceded else "L")

        return {
            "goals_scored":   scored,
            "goals_conceded": conceded,
            "is_home":        is_home,
            "result":         result,
        }
    except (KeyError, TypeError, IndexError):
        return None


def get_team_last_matches(team_id, limit=6):
    data = _get("teams/matches.json", {"team_id": team_id})
    if not data or "match" not in data:
        return []
    results = []
    for ev in data["match"]:
        parsed = _parse_match(ev, team_id)
        if parsed:
            results.append(parsed)
    return results[-limit:]


def get_team_home_matches(team_id, limit=6):
    all_matches = get_team_last_matches(team_id, limit * 3)
    home = [m for m in all_matches if m.get("is_home")]
    return home[-limit:]


def get_team_away_matches(team_id, limit=6):
    all_matches = get_team_last_matches(team_id, limit * 3)
    away = [m for m in all_matches if not m.get("is_home")]
    return away[-limit:]


def get_match_data(home_id, away_id):
    home_general = get_team_last_matches(home_id, 6)
    home_venue   = get_team_home_matches(home_id, 6)
    away_general = get_team_last_matches(away_id, 6)
    away_venue   = get_team_away_matches(away_id, 6)

    return {
        "home_general": home_general,
        "home_venue":   home_venue,
        "away_general": away_general,
        "away_venue":   away_venue,
    }
