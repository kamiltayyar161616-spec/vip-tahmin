"""
AllSports API - Fiktur + Takim Istatistik Cekici
"""
import requests
import datetime
import os
from typing import Optional

BASE = "https://apiv2.allsportsapi.com/football/"

API_KEY = os.environ.get("ALLSPORTS_KEY", "2cdd0ee14f286d9497f882f35b392927d73aa35a25ad92c8b285278c041eac78")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "application/json",
}
TIMEOUT = 15


def _get(params):
    params["APIkey"] = API_KEY
    try:
        r = requests.get(BASE, headers=HEADERS, params=params, timeout=TIMEOUT)
        if r.status_code == 200:
            data = r.json()
            if data.get("success") == 1:
                return data.get("result", [])
            else:
                print(f"[AllSports] Hata: {data}")
        else:
            print(f"[AllSports] HTTP {r.status_code}")
    except Exception as e:
        print(f"[AllSports] Istek hatasi: {e}")
    return None


# ─────────────────────────────────────────────
# FIKTUR
# ─────────────────────────────────────────────

def get_fixtures_by_date(date_str):
    """
    Verilen tarihteki tum futbol maclarini dondurur.
    date_str: 'YYYY-MM-DD'
    """
    result = _get({"met": "Fixtures", "from": date_str, "to": date_str})
    if not result:
        return []

    matches = []
    for ev in result:
        try:
            home_id   = int(ev["home_team_key"])
            away_id   = int(ev["away_team_key"])
            match_id  = str(ev.get("event_key", ""))
            home_name = ev["event_home_team"]
            away_name = ev["event_away_team"]
            league    = ev.get("league_name", "")
            country   = ev.get("country_name", "")
            league_full = f"{country} - {league}" if country else league

            match_time = ev.get("event_time", "00:00")[:5]
            match_date = ev.get("event_date", date_str)

            try:
                dt = datetime.datetime.strptime(f"{match_date} {match_time}", "%Y-%m-%d %H:%M")
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


# ─────────────────────────────────────────────
# TAKIM SON MACLARI
# ─────────────────────────────────────────────

def _parse_match(ev, team_id):
    try:
        home_id    = int(ev["home_team_key"])
        home_score = int(ev.get("event_final_result", "0 - 0").split(" - ")[0])
        away_score = int(ev.get("event_final_result", "0 - 0").split(" - ")[1])

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
    except (KeyError, TypeError, IndexError, ValueError):
        return None


def get_team_last_matches(team_id, limit=6):
    """Son N genel mac."""
    result = _get({"met": "Fixtures", "teamId": team_id})
    if not result:
        return []

    parsed = []
    for ev in result:
        # Sadece bitmis maclari al
        status = ev.get("event_status", "")
        if status not in ("Finished", "FT", "AET", "Pen."):
            continue
        p = _parse_match(ev, team_id)
        if p:
            parsed.append(p)

    return parsed[-limit:]


def get_team_home_matches(team_id, limit=6):
    """Son N ic saha mac."""
    all_matches = get_team_last_matches(team_id, limit * 3)
    home = [m for m in all_matches if m.get("is_home")]
    return home[-limit:]


def get_team_away_matches(team_id, limit=6):
    """Son N deplasman mac."""
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
