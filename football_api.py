"""
AllSports API - Fiktur + Canli Skor + Takim Istatistik
"""
import requests
import datetime
import os

BASE    = "https://apiv2.allsportsapi.com/football/"
API_KEY = os.environ.get("ALLSPORTS_KEY", "043a0ecb1606761afe8f035a5391fb80581767a64eb3c6e5762966c0d57f9905")
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
TIMEOUT = 15
TZ_OFFSET = 2  # API UTC+1, Turkiye UTC+3


def _get(params):
    params["APIkey"] = API_KEY
    try:
        r = requests.get(BASE, headers=HEADERS, params=params, timeout=TIMEOUT)
        if r.status_code == 200:
            data = r.json()
            if data.get("success") == 1:
                return data.get("result", [])
            print(f"[AllSports] Basarisiz: {data.get('error','?')}")
        else:
            print(f"[AllSports] HTTP {r.status_code}")
    except Exception as e:
        print(f"[AllSports] Hata: {e}")
    return None


# ─────────────────────────────────────────────
# MAC DURUMU
# ─────────────────────────────────────────────

FINISHED_STATUSES = {
    "Finished", "FT", "AET", "Pen.", "finished",
    "After ET", "After Pen.", "Awarded"
}

LIVE_STATUSES = {
    "1H", "HT", "2H", "ET", "P", "Break",
    "Live", "1st Half", "Half Time", "2nd Half",
    "Extra Time", "Penalty In Progress"
}

def _get_match_status(status_str):
    """mac, canli, bitti, bekliyor"""
    if not status_str:
        return "upcoming"
    s = str(status_str).strip()
    if s in FINISHED_STATUSES:
        return "finished"
    if s in LIVE_STATUSES or s.isdigit():
        return "live"
    return "upcoming"


# ─────────────────────────────────────────────
# FIKTUR
# ─────────────────────────────────────────────

def get_fixtures_by_date(date_str):
    try:
        tr_day    = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        prev_date = (tr_day - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        next_date = (tr_day + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    except Exception:
        prev_date = date_str
        next_date = date_str

    all_results = []
    for d in [prev_date, date_str, next_date]:
        r = _get({"met": "Fixtures", "from": d, "to": d})
        if r:
            all_results.extend(r)

    if not all_results:
        return []

    tr_day_start = datetime.datetime.strptime(date_str, "%Y-%m-%d")
    tr_day_end   = tr_day_start + datetime.timedelta(hours=24)

    matches  = []
    seen_ids = set()

    for ev in all_results:
        try:
            match_id = str(ev.get("event_key", ""))
            if match_id in seen_ids:
                continue

            raw_time = ev.get("event_time", "00:00")[:5]
            raw_date = ev.get("event_date", date_str)
            api_dt   = datetime.datetime.strptime(f"{raw_date} {raw_time}", "%Y-%m-%d %H:%M")
            tr_dt    = api_dt + datetime.timedelta(hours=TZ_OFFSET)

            if not (tr_day_start <= tr_dt < tr_day_end):
                continue

            seen_ids.add(match_id)

            status_raw = ev.get("event_status", "")
            status     = _get_match_status(status_raw)

            # Skorlar
            home_score    = ev.get("event_home_final_score", None)
            away_score    = ev.get("event_away_final_score", None)
            home_ht_score = ev.get("event_home_first_half_score", None)
            away_ht_score = ev.get("event_away_first_half_score", None)

            # Canlı maçta dakika
            live_min = ""
            if status == "live":
                if str(status_raw).isdigit():
                    live_min = f"{status_raw}'"
                elif status_raw == "HT":
                    live_min = "HT"

            matches.append({
                "match_id":       match_id,
                "home_team":      ev["event_home_team"],
                "away_team":      ev["event_away_team"],
                "home_id":        int(ev["home_team_key"]),
                "away_id":        int(ev["away_team_key"]),
                "league":         f"{ev.get('country_name','')} - {ev.get('league_name','')}" if ev.get('country_name') else ev.get('league_name',''),
                "time":           tr_dt.strftime("%H:%M"),
                "timestamp":      int(tr_dt.timestamp()),
                "status":         status,
                "status_raw":     status_raw,
                "live_min":       live_min,
                "home_score":     home_score,
                "away_score":     away_score,
                "home_ht_score":  home_ht_score,
                "away_ht_score":  away_ht_score,
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
    today     = datetime.date.today()
    from_date = (today - datetime.timedelta(days=180)).strftime("%Y-%m-%d")
    to_date   = today.strftime("%Y-%m-%d")
    result    = _get({"met": "Fixtures", "teamId": team_id, "from": from_date, "to": to_date})
    if not result:
        return []
    parsed = []
    for ev in result:
        if _get_match_status(ev.get("event_status","")) != "finished":
            continue
        p = _parse_match(ev, team_id)
        if p:
            parsed.append(p)
    return parsed


def get_team_last_matches(team_id, limit=6):
    return _get_team_matches(team_id)[-limit:]

def get_team_home_matches(team_id, limit=6):
    return [m for m in _get_team_matches(team_id) if m.get("is_home")][-limit:]

def get_team_away_matches(team_id, limit=6):
    return [m for m in _get_team_matches(team_id) if not m.get("is_home")][-limit:]

def get_match_data(home_id, away_id):
    return {
        "home_general": get_team_last_matches(home_id, 6),
        "home_venue":   get_team_home_matches(home_id, 6),
        "away_general": get_team_last_matches(away_id, 6),
        "away_venue":   get_team_away_matches(away_id, 6),
    }
