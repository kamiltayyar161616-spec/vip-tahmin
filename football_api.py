"""
AllSports API - Fiktur + Takim Istatistik Cekici
API saati UTC+1, Turkiye UTC+3 = +2 saat fark
"""
import requests
import datetime
import os

BASE    = "https://apiv2.allsportsapi.com/football/"
API_KEY = os.environ.get("ALLSPORTS_KEY", "043a0ecb1606761afe8f035a5391fb80581767a64eb3c6e5762966c0d57f9905")
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
TIMEOUT = 15
TZ_OFFSET = 2  # API UTC+1, Turkiye UTC+3 = +2 saat


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
# FIKTUR
# ─────────────────────────────────────────────

def get_fixtures_by_date(date_str):
    """
    Verilen Turkiye tarihine gore maclari getirir.
    API saatine +2 ekleyerek TR saatine cevirir.
    """
    try:
        tr_day = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        # API UTC+1 oldugu icin bir onceki gun de cekebilir
        prev_date = (tr_day - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        next_date = (tr_day + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    except Exception:
        prev_date = date_str
        next_date = date_str

    # 3 gunden cek, sonra TR saatine gore filtrele
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

            api_dt = datetime.datetime.strptime(f"{raw_date} {raw_time}", "%Y-%m-%d %H:%M")
            tr_dt  = api_dt + datetime.timedelta(hours=TZ_OFFSET)

            # Sadece o Turkiye gunune ait maclari al
            if not (tr_day_start <= tr_dt < tr_day_end):
                continue

            seen_ids.add(match_id)
            match_time = tr_dt.strftime("%H:%M")
            timestamp  = int(tr_dt.timestamp())

            home_id     = int(ev["home_team_key"])
            away_id     = int(ev["away_team_key"])
            home_name   = ev["event_home_team"]
            away_name   = ev["event_away_team"]
            league      = ev.get("league_name", "")
            country     = ev.get("country_name", "")
            league_full = f"{country} - {league}" if country else league

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
    today     = datetime.date.today()
    from_date = (today - datetime.timedelta(days=180)).strftime("%Y-%m-%d")
    to_date   = today.strftime("%Y-%m-%d")

    result = _get({
        "met":    "Fixtures",
        "teamId": team_id,
        "from":   from_date,
        "to":     to_date,
    })

    if not result:
        return []

    finished = {"Finished", "FT", "AET", "Pen.", "finished", "After ET", "After Pen."}
    parsed = []
    for ev in result:
        if ev.get("event_status", "") not in finished:
            continue
        p = _parse_match(ev, team_id)
        if p:
            parsed.append(p)
    return parsed


def get_team_last_matches(team_id, limit=6):
    return _get_team_matches(team_id)[-limit:]


def get_team_home_matches(team_id, limit=6):
    all_m = _get_team_matches(team_id)
    return [m for m in all_m if m.get("is_home")][-limit:]


def get_team_away_matches(team_id, limit=6):
    all_m = _get_team_matches(team_id)
    return [m for m in all_m if not m.get("is_home")][-limit:]


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
