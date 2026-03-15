"""
AllSports API - Fiktur + Canli Skor + Takim Istatistik
event_final_result ve event_halftime_result field'lari kullanilir
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


def _parse_score(score_str):
    """'2 - 1' formatini (home, away) tuple'a cevirir."""
    if not score_str or score_str.strip() in ("-", "", "- -", "0 - 0"):
        return None, None
    try:
        parts = score_str.strip().split(" - ")
        if len(parts) == 2:
            return int(parts[0].strip()), int(parts[1].strip())
    except Exception:
        pass
    return None, None


def _get_match_status(ev):
    """mac durumunu dondurur: upcoming, live, finished"""
    event_live   = str(ev.get("event_live", "0"))
    event_status = str(ev.get("event_status", "")).strip()
    final_result = str(ev.get("event_final_result", "")).strip()

    if event_live == "1":
        return "live"

    finished_statuses = {
        "Finished", "FT", "AET", "Pen.", "finished",
        "After ET", "After Pen.", "Awarded"
    }
    if event_status in finished_statuses:
        return "finished"

    # Skoru varsa ve event_live=0 ise bitmiş
    if final_result and final_result not in ("-", "", "- -"):
        h, a = _parse_score(final_result)
        if h is not None:
            return "finished"

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

            status   = _get_match_status(ev)
            event_status = str(ev.get("event_status", "")).strip()

            # Canlı dakika
            live_min = ""
            if status == "live":
                if event_status and event_status not in ("", "HT"):
                    live_min = f"{event_status}'"
                elif event_status == "HT":
                    live_min = "HT"
                else:
                    live_min = "CANLI"

            # Skorlar - event_final_result: "2 - 1"
            final_result = ev.get("event_final_result", "")
            ht_result    = ev.get("event_halftime_result", "")

            home_score, away_score = _parse_score(final_result)
            home_ht,    away_ht    = _parse_score(ht_result)

            # Canlı maçta event_final_result anlık skoru verir
            league    = ev.get("league_name", "")
            country   = ev.get("country_name", "")
            league_full = f"{country} - {league}" if country else league

            matches.append({
                "match_id":      match_id,
                "home_team":     ev["event_home_team"],
                "away_team":     ev["event_away_team"],
                "home_id":       int(ev["home_team_key"]),
                "away_id":       int(ev["away_team_key"]),
                "league":        league_full,
                "time":          tr_dt.strftime("%H:%M"),
                "timestamp":     int(tr_dt.timestamp()),
                "status":        status,
                "live_min":      live_min,
                "home_score":    home_score,
                "away_score":    away_score,
                "home_ht_score": home_ht,
                "away_ht_score": away_ht,
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
        home_id      = int(ev["home_team_key"])
        result_str   = ev.get("event_final_result", "")
        home_score, away_score = _parse_score(result_str)
        if home_score is None or away_score is None:
            return None

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
    except (KeyError, TypeError, ValueError):
        return None


def _get_team_matches(team_id):
    today     = datetime.date.today()
    from_date = (today - datetime.timedelta(days=180)).strftime("%Y-%m-%d")
    to_date   = today.strftime("%Y-%m-%d")

    result = _get({"met": "Fixtures", "teamId": team_id, "from": from_date, "to": to_date})
    if not result:
        return []

    parsed = []
    for ev in result:
        if _get_match_status(ev) != "finished":
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
