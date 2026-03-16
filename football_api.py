"""
Sofascore API - Railway backend uzerinden
Fiktur + Takim gecmisi
"""
import requests
import datetime
import os

SOFA    = "https://api.sofascore.com/api/v1"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Android 14; Mobile; rv:124.0) Gecko/124.0 Firefox/124.0",
    "Referer":    "https://www.sofascore.com/",
    "Accept":     "application/json",
    "Origin":     "https://www.sofascore.com",
}
TIMEOUT  = 15
TZ_OFFSET = 3  # Sofascore UTC, TR = UTC+3

CUP_KW = [
    'cup','kupa','copa','coupe','pokal','friendly','supercup',
    'super cup','champions league','europa league',
    'conference league','nations league','world cup'
]


def _get(path):
    try:
        r = requests.get(f"{SOFA}{path}", headers=HEADERS, timeout=TIMEOUT)
        if r.status_code == 200:
            return r.json()
        print(f"[Sofa] {r.status_code} {path}")
    except Exception as e:
        print(f"[Sofa] Hata: {e}")
    return None


def get_fixtures_by_date(date_str):
    data = _get(f"/sport/football/scheduled-events/{date_str}")
    if not data or "events" not in data:
        return []

    matches  = []
    for ev in data["events"]:
        try:
            status_type = ev.get("status", {}).get("type", "")
            status_code = ev.get("status", {}).get("code", 0)

            if status_type == "finished":
                status = "finished"
            elif status_type == "inprogress":
                status = "live"
            else:
                status = "upcoming"

            ts     = ev.get("startTimestamp", 0)
            dt     = datetime.datetime.utcfromtimestamp(ts)
            tr_dt  = dt + datetime.timedelta(hours=TZ_OFFSET)
            time_str = tr_dt.strftime("%H:%M")

            # Sadece bugune ait maclar
            date_of_match = tr_dt.strftime("%Y-%m-%d")
            if date_of_match != date_str:
                continue

            league  = ev.get("tournament", {}).get("name", "")
            country = ev.get("tournament", {}).get("category", {}).get("name", "")

            live_min = ""
            if status == "live":
                live_min = ev.get("status", {}).get("description", "CANLI")

            matches.append({
                "match_id":      str(ev["id"]),
                "sofa_id":       ev["id"],
                "home_team":     ev["homeTeam"]["name"],
                "away_team":     ev["awayTeam"]["name"],
                "home_id":       ev["homeTeam"]["id"],
                "away_id":       ev["awayTeam"]["id"],
                "league":        f"{country} - {league}" if country else league,
                "time":          time_str,
                "timestamp":     ts,
                "status":        status,
                "live_min":      live_min,
                "home_score":    ev.get("homeScore", {}).get("current"),
                "away_score":    ev.get("awayScore", {}).get("current"),
                "home_ht_score": ev.get("homeScore", {}).get("period1"),
                "away_ht_score": ev.get("awayScore", {}).get("period1"),
            })
        except Exception:
            continue

    matches.sort(key=lambda x: x["timestamp"])
    return matches


def _parse_event(ev, team_id):
    try:
        home_id = ev["homeTeam"]["id"]
        hs      = int(ev.get("homeScore", {}).get("current", 0) or 0)
        as_     = int(ev.get("awayScore", {}).get("current", 0) or 0)
        is_home = (team_id == home_id)
        scored   = hs if is_home else as_
        conceded = as_ if is_home else hs
        result   = "W" if scored > conceded else ("D" if scored == conceded else "L")
        return {
            "goals_scored":   scored,
            "goals_conceded": conceded,
            "is_home":        is_home,
            "result":         result,
        }
    except Exception:
        return None


def get_team_matches(team_id, pages=2):
    all_matches = []
    for page in range(pages):
        data = _get(f"/team/{team_id}/events/last/{page}")
        if not data or "events" not in data:
            break
        for ev in data["events"]:
            # Kupa maclari atla
            tname = (ev.get("tournament", {}).get("name", "") or "").lower()
            if any(k in tname for k in CUP_KW):
                continue
            # Sadece biten maclar
            if ev.get("status", {}).get("type") != "finished":
                continue
            p = _parse_event(ev, team_id)
            if p:
                all_matches.append(p)
        if not data.get("hasNextPage", False):
            break
    return all_matches


def get_match_data(home_id, away_id):
    home_all = get_team_matches(home_id)
    away_all = get_team_matches(away_id)
    return {
        "home_general": home_all[-6:],
        "home_venue":   [m for m in home_all if m["is_home"]][-6:],
        "away_general": away_all[-6:],
        "away_venue":   [m for m in away_all if not m["is_home"]][-6:],
    }
