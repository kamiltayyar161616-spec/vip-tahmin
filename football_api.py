import requests
import datetime
import os

BASE    = "https://apiv2.allsportsapi.com/football/"
API_KEY = os.environ.get("ALLSPORTS_KEY")

_league_cache = {}


def _get(params):
    params["APIkey"] = API_KEY
    r = requests.get(BASE, params=params, timeout=15)
    return r.json().get("result", [])


def _parse_score(s):
    if not s or "-" not in s:
        return None, None
    h, a = s.split("-")
    return int(h.strip()), int(a.strip())


def _get_league_matches(league_id):

    if league_id in _league_cache:
        return _league_cache[league_id]

    today = datetime.date.today()
    start = today - datetime.timedelta(days=120)

    result = _get({
        "met": "Fixtures",
        "leagueId": league_id,
        "from": start.strftime("%Y-%m-%d"),
        "to": today.strftime("%Y-%m-%d")
    })

    slim = []
    for ev in result:
        slim.append({
            "event_date": ev.get("event_date"),
            "home_team_key": ev.get("home_team_key"),
            "away_team_key": ev.get("away_team_key"),
            "event_final_result": ev.get("event_final_result"),
        })

    # 🔥 EN KRİTİK FIX
    slim.sort(key=lambda x: x["event_date"])

    _league_cache[league_id] = slim
    return slim


def _parse_team_match(ev, team_id):
    h, a = _parse_score(ev["event_final_result"])
    if h is None:
        return None

    is_home = int(ev["home_team_key"]) == team_id

    return {
        "goals_scored": h if is_home else a,
        "goals_conceded": a if is_home else h,
        "is_home": is_home
    }


def get_team_matches_from_league(team_id, league_id, limit=12):

    league_matches = _get_league_matches(league_id)

    parsed = []

    # 🔥 SON MAÇTAN GERİYE DOĞRU
    for ev in reversed(league_matches):
        p = _parse_team_match(ev, team_id)
        if p:
            parsed.append(p)

        # 🔥 LIMIT (PERFORMANS FIX)
        if len(parsed) >= limit:
            break

    return parsed


def get_match_data(home_id, away_id, league_key):

    home_all = get_team_matches_from_league(home_id, league_key, 12)
    away_all = get_team_matches_from_league(away_id, league_key, 12)

    return {
        "home_general": home_all[-6:],
        "home_venue":   [m for m in home_all if m["is_home"]][-6:],
        "away_general": away_all[-6:],
        "away_venue":   [m for m in away_all if not m["is_home"]][-6:]
    }
