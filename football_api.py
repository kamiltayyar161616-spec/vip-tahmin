"""
AllSports API - leagueId ile takim gecmisi
Fiktur: gunluk maclar
Takim gecmisi: ligden cekilip takim filtrelenir
"""
import requests
import datetime
import os

BASE    = "https://apiv2.allsportsapi.com/football/"
API_KEY = os.environ.get("ALLSPORTS_KEY", "043a0ecb1606761afe8f035a5391fb80581767a64eb3c6e5762966c0d57f9905")
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
TIMEOUT   = 15
TZ_OFFSET = 2

CUP_KW = [
    "cup","kupa","copa","coupe","pokal","supercup","super cup",
    "fa cup","league cup","carabao","trophy","shield",
    "playoff","play-off","friendly","world cup","nations league",
    "champions league","europa league","conference league",
    "turkiye kupasi","ziraat","super kupa",
]

# Lig maclari cache: {league_id: [maclar]}
_league_cache = {}


def _get(params):
    params["APIkey"] = API_KEY
    try:
        r = requests.get(BASE, headers=HEADERS, params=params, timeout=TIMEOUT)
        if r.status_code == 200:
            d = r.json()
            if d.get("success") == 1:
                return d.get("result", [])
    except Exception as e:
        print(f"[AllSports] Hata: {e}")
    return None


def _parse_score(s):
    if not s or str(s).strip() in ("-", "", "- -"):
        return None, None
    try:
        s   = str(s).strip()
        sep = " - " if " - " in s else "-"
        p   = s.split(sep)
        if len(p) == 2:
            return int(p[0].strip()), int(p[1].strip())
    except Exception:
        pass
    return None, None


def _status(ev):
    live   = str(ev.get("event_live", "0")).strip()
    status = str(ev.get("event_status", "")).strip()
    if live == "1":
        return "live"
    finished = {"Finished","FT","AET","Pen.","finished","After ET","After Pen.","Awarded"}
    if status in finished:
        return "finished"
    h, a = _parse_score(ev.get("event_final_result",""))
    if h is not None and live != "1" and status != "":
        return "finished"
    return "upcoming"


def _is_cup(league_name):
    ln = (league_name or "").lower()
    return any(k in ln for k in CUP_KW)


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

    tr_start = datetime.datetime.strptime(date_str, "%Y-%m-%d")
    tr_end   = tr_start + datetime.timedelta(hours=24)
    matches  = []
    seen     = set()

    for ev in all_results:
        try:
            mid = str(ev.get("event_key", ""))
            if mid in seen:
                continue
            raw_time = ev.get("event_time", "00:00")[:5]
            raw_date = ev.get("event_date", date_str)
            api_dt   = datetime.datetime.strptime(f"{raw_date} {raw_time}", "%Y-%m-%d %H:%M")
            tr_dt    = api_dt + datetime.timedelta(hours=TZ_OFFSET)
            if not (tr_start <= tr_dt < tr_end):
                continue
            seen.add(mid)

            st  = _status(ev)
            es  = str(ev.get("event_status","")).strip()
            lm  = ""
            if st == "live":
                lm = f"{es}'" if es and es != "HT" else ("HT" if es == "HT" else "CANLI")

            h,  a   = _parse_score(ev.get("event_final_result",""))
            hh, ah  = _parse_score(ev.get("event_halftime_result",""))
            league  = ev.get("league_name","")
            country = ev.get("country_name","")
            league_key = ev.get("league_key")

            matches.append({
                "match_id":      mid,
                "home_team":     ev["event_home_team"],
                "away_team":     ev["event_away_team"],
                "home_id":       int(ev["home_team_key"]),
                "away_id":       int(ev["away_team_key"]),
                "league":        f"{country} - {league}" if country else league,
                "league_name":   league,
                "league_key":    league_key,
                "time":          tr_dt.strftime("%H:%M"),
                "timestamp":     int(tr_dt.timestamp()),
                "status":        st,
                "live_min":      lm,
                "home_score":    h,
                "away_score":    a,
                "home_ht_score": hh,
                "away_ht_score": ah,
            })
        except Exception:
            continue

    matches.sort(key=lambda x: x["timestamp"])
    return matches


# ─────────────────────────────────────────────
# LIG MACLARI — leagueId ile sezonu cek
# ─────────────────────────────────────────────

def _get_league_matches(league_id):
    """Ligin tum sezon maclarini ceker, cache'ler."""
    if league_id in _league_cache:
        return _league_cache[league_id]

    today     = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)

    # Sezon baslangici
    if today.month >= 7:
        season_start = datetime.date(today.year, 7, 1)
    else:
        season_start = datetime.date(today.year - 1, 7, 1)

    from_str = season_start.strftime("%Y-%m-%d")
    to_str   = yesterday.strftime("%Y-%m-%d")

    result = _get({
        "met":      "Fixtures",
        "leagueId": league_id,
        "from":     from_str,
        "to":       to_str,
    })

    matches = result or []
    _league_cache[league_id] = matches
    return matches


def _parse_team_match(ev, team_id):
    """Bir mac eventinden takim perspektifinden gol bilgisi."""
    try:
        home_id = int(ev["home_team_key"])
        away_id = int(ev["away_team_key"])
        if team_id != home_id and team_id != away_id:
            return None
        if _status(ev) != "finished":
            return None
        if _is_cup(ev.get("league_name","")):
            return None
        h, a = _parse_score(ev.get("event_final_result",""))
        if h is None:
            return None
        is_home  = (team_id == home_id)
        scored   = h if is_home else a
        conceded = a if is_home else h
        result   = "W" if scored > conceded else ("D" if scored == conceded else "L")
        return {
            "goals_scored":   scored,
            "goals_conceded": conceded,
            "is_home":        is_home,
            "result":         result,
        }
    except Exception:
        return None


def get_team_matches_from_league(team_id, league_id, limit=12):
    """Lig maclarindan takim verisi ceker."""
    league_matches = _get_league_matches(league_id)
    parsed = []
    seen   = set()
    for ev in league_matches:
        key = str(ev.get("event_key",""))
        if key in seen:
            continue
        seen.add(key)
        p = _parse_team_match(ev, team_id)
        if p:
            parsed.append(p)
    return parsed[-limit:]


def get_match_data(home_id, away_id, league_key=None):
    """
    Ev sahibi ve deplasman icin 4 veri seti.
    Lig ID'si varsa o ligden ceker, yoksa bos doner.
    """
    if not league_key:
        return {"home_general":[],"home_venue":[],"away_general":[],"away_venue":[]}

    home_all = get_team_matches_from_league(home_id, league_key, 12)
    away_all = get_team_matches_from_league(away_id, league_key, 12)

    return {
        "home_general": home_all[-6:],
        "home_venue":   [m for m in home_all if m["is_home"]][-6:],
        "away_general": away_all[-6:],
        "away_venue":   [m for m in away_all if not m["is_home"]][-6:],
    }
