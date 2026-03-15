"""
AllSports API - Fiktur + Takim Gecmis Mac Verileri
"""
import requests
import datetime
import os
from typing import Optional

BASE = "https://apiv2.allsportsapi.com/football/"

API_KEY = os.environ.get("ALLSPORTS_KEY", "043a0ecb1606761afe8f035a5391fb80581767a64eb3c6e5762966c0d57f9905")

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
            match_time  = ev.get("event_time", "00:00")[:5]
            match_date  = ev.get("event_date", date_str)

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
        result_str = ev.get("event_final_result", "")
        if not result_str or "-" not in result_str:
            return None

        parts = result_str.strip().split(" - ")
        if len(parts) != 2:
            return None

        home_score = int(parts[0].strip())
        away_score = int(parts[1].strip())

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


def _get_team_matches(team_id):
    """Takimin son 3 aylik maclarini getirir."""
    today = datetime.date.today()
    from_date = (today - datetime.timedelta(days=90)).strftime("%Y-%m-%d")
    to_date   = today.strftime("%Y-%m-%d")

    result = _get({
        "met":    "Fixtures",
        "teamId": team_id,
        "from":   from_date,
        "to":     to_date,
    })

    if not result:
        # 6 aylik dene
        from_date = (today - datetime.timedelta(days=180)).strftime("%Y-%m-%d")
        result = _get({
            "met":    "Fixtures",
            "teamId": team_id,
            "from":   from_date,
            "to":     to_date,
        })

    if not result:
        return []

    parsed = []
    for ev in result:
        status = ev.get("event_status", "")
        if status not in ("Finished", "FT", "AET", "Pen.", "finished"):
            continue
        p = _parse_match(ev, team_id)
        if p:
            parsed.append(p)

    return parsed


def get_team_last_matches(team_id, limit=6):
    matches = _get_team_matches(team_id)
    return matches[-limit:]


def get_team_home_matches(team_id, limit=6):
    matches = _get_team_matches(team_id)
    home = [m for m in matches if m.get("is_home")]
    return home[-limit:]


def get_team_away_matches(team_id, limit=6):
    matches = _get_team_matches(team_id)
    away = [m for m in matches if not m.get("is_home")]
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
