"""
AllSports API - Fiktur + Canli Skor + Takim Istatistik
Takim gecmisi: aylik parcali isteklerle tam veri cekilir
"""
import requests
import datetime
import time
import os

BASE    = "https://apiv2.allsportsapi.com/football/"
API_KEY = os.environ.get("ALLSPORTS_KEY", "043a0ecb1606761afe8f035a5391fb80581767a64eb3c6e5762966c0d57f9905")
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Accept": "application/json"}
TIMEOUT  = 15
TZ_OFFSET = 2


def _get(params, retries=2):
    params["APIkey"] = API_KEY
    for attempt in range(retries):
        try:
            r = requests.get(BASE, headers=HEADERS, params=params, timeout=TIMEOUT)
            if r.status_code == 200:
                data = r.json()
                if data.get("success") == 1:
                    return data.get("result", [])
                return None
            elif r.status_code == 429:
                time.sleep(2 * (attempt + 1))
            else:
                return None
        except Exception as e:
            print(f"[AllSports] Hata: {e}")
            if attempt < retries - 1:
                time.sleep(1)
    return None


def _parse_score(score_str):
    if not score_str or str(score_str).strip() in ("-", "", "- -"):
        return None, None
    try:
        s = str(score_str).strip()
        sep = " - " if " - " in s else "-"
        parts = s.split(sep)
        if len(parts) == 2:
            return int(parts[0].strip()), int(parts[1].strip())
    except Exception:
        pass
    return None, None


def _extract_scores(ev):
    h, a = _parse_score(ev.get("event_final_result", ""))
    if h is not None:
        return h, a
    try:
        hf = ev.get("event_home_final_score")
        af = ev.get("event_away_final_score")
        if hf is not None and af is not None and str(hf) != "" and str(af) != "":
            return int(hf), int(af)
    except Exception:
        pass
    return None, None


def _extract_ht_scores(ev):
    h, a = _parse_score(ev.get("event_halftime_result", ""))
    return (h, a) if h is not None else (None, None)


def _get_match_status(ev):
    event_live   = str(ev.get("event_live", "0")).strip()
    event_status = str(ev.get("event_status", "")).strip()
    if event_live == "1":
        return "live"
    finished = {"Finished", "FT", "AET", "Pen.", "finished", "After ET", "After Pen.", "Awarded"}
    if event_status in finished:
        return "finished"
    h, a = _extract_scores(ev)
    if h is not None and event_live != "1" and event_status != "":
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

    live = _get({"met": "Livescore"})
    if live:
        all_results.extend(live)

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
            status       = _get_match_status(ev)
            event_status = str(ev.get("event_status", "")).strip()
            live_min = ""
            if status == "live":
                if event_status and event_status not in ("", "HT"):
                    live_min = f"{event_status}'"
                elif event_status == "HT":
                    live_min = "HT"
                else:
                    live_min = "CANLI"
            home_score, away_score = _extract_scores(ev)
            home_ht,    away_ht    = _extract_ht_scores(ev)
            league      = ev.get("league_name", "")
            country     = ev.get("country_name", "")
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
# TAKIM SON MACLARI — Aylik parcali cekme
# ─────────────────────────────────────────────

def _parse_match(ev, team_id):
    try:
        home_id              = int(ev["home_team_key"])
        home_score, away_score = _extract_scores(ev)
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


def _get_team_matches_in_range(team_id, from_date, to_date):
    """Belirli tarih araliginda takim maclarini getirir."""
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
        if _get_match_status(ev) != "finished":
            continue
        p = _parse_match(ev, team_id)
        if p:
            parsed.append(p)
    return parsed


def _get_team_matches(team_id, needed=12):
    """
    Takimin bitmis maclarini aylik parcali isteklerle getirir.
    En az 'needed' mac bulana kadar geriye gider.
    """
    today     = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)
    all_matches = []

    # Aylik araliklar halinde geri git (en fazla 6 ay)
    months_back = 0
    while len(all_matches) < needed and months_back < 6:
        # Bu aylik aralik
        period_end   = yesterday - datetime.timedelta(days=months_back * 30)
        period_start = period_end - datetime.timedelta(days=30)

        from_str = period_start.strftime("%Y-%m-%d")
        to_str   = period_end.strftime("%Y-%m-%d")

        chunk = _get_team_matches_in_range(team_id, from_str, to_str)
        all_matches = chunk + all_matches  # Eskiler başa
        months_back += 1

        # Yeterli maç varsa dur
        if len(all_matches) >= needed:
            break

    return all_matches


def get_team_last_matches(team_id, limit=6):
    """Son N genel mac."""
    matches = _get_team_matches(team_id, needed=limit * 2)
    return matches[-limit:]


def get_team_home_matches(team_id, limit=6):
    """Son N ic saha mac."""
    matches = _get_team_matches(team_id, needed=limit * 4)
    home = [m for m in matches if m.get("is_home") == True]
    return home[-limit:]


def get_team_away_matches(team_id, limit=6):
    """Son N dis saha mac."""
    matches = _get_team_matches(team_id, needed=limit * 4)
    away = [m for m in matches if m.get("is_home") == False]
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
