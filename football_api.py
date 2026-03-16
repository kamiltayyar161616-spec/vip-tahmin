"""
Hibrit API:
- Bzzoiro: 22 buyuk lig icin fiktur + takim gecmisi
- AllSports: Diger ligler icin fiktur
"""
import requests
import datetime
import os

# ─── ALLSPORTS ───────────────────────────────
ALLSPORTS_BASE = "https://apiv2.allsportsapi.com/football/"
ALLSPORTS_KEY  = os.environ.get("ALLSPORTS_KEY", "043a0ecb1606761afe8f035a5391fb80581767a64eb3c6e5762966c0d57f9905")

# ─── BZZOIRO ─────────────────────────────────
BZZ_BASE    = "https://sports.bzzoiro.com/api"
BZZ_KEY     = os.environ.get("BZZ_KEY", "9c3aaeab5cb973a0a5db5bfbc455606d6a8f0337")
BZZ_HEADERS = {"Authorization": f"Token {BZZ_KEY}", "Accept": "application/json"}

TIMEOUT   = 15
TZ_OFFSET = 2

CUP_KEYWORDS = [
    "cup", "kupa", "copa", "coupe", "pokal", "supercup", "super cup",
    "fa cup", "league cup", "carabao", "trophy", "shield", "charity",
    "playoff", "play-off", "friendly", "friendlies",
    "world cup", "nations league", "champions league", "europa league",
    "conference league", "turkiye kupasi", "ziraat", "super kupa",
]

# Bzzoiro'nun destekledigi lig isimleri (kucuk harf)
BZZ_LEAGUES = {
    "premier league", "la liga", "serie a", "bundesliga", "ligue 1",
    "eredivisie", "liga portugal betclic", "championship", "pro league",
    "brasileirao serie a", "mls", "liga mx clausura", "liga mx apertura",
    "trendyol super lig", "superliga", "parva liga", "stoiximan super league",
    "saudi pro league", "scottish premiership", "super league",
    "champions league", "europa league",
}


def _is_cup_match(ev) -> bool:
    league = str(ev.get("league_name", "")).lower()
    for kw in CUP_KEYWORDS:
        if kw in league:
            return True
    return False


# ─────────────────────────────────────────────
# ALLSPORTS ISTEKLERI
# ─────────────────────────────────────────────

def _allsports_get(params):
    params["APIkey"] = ALLSPORTS_KEY
    try:
        r = requests.get(ALLSPORTS_BASE, params=params, timeout=TIMEOUT,
                         headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        if r.status_code == 200:
            data = r.json()
            if data.get("success") == 1:
                return data.get("result", [])
    except Exception as e:
        print(f"[AllSports] Hata: {e}")
    return None


def _parse_allsports_score(score_str):
    if not score_str or str(score_str).strip() in ("-", "", "- -"):
        return None, None
    try:
        s     = str(score_str).strip()
        sep   = " - " if " - " in s else "-"
        parts = s.split(sep)
        if len(parts) == 2:
            return int(parts[0].strip()), int(parts[1].strip())
    except Exception:
        pass
    return None, None


def _allsports_match_status(ev):
    live   = str(ev.get("event_live", "0")).strip()
    status = str(ev.get("event_status", "")).strip()
    if live == "1":
        return "live"
    finished = {"Finished", "FT", "AET", "Pen.", "finished", "After ET", "After Pen.", "Awarded"}
    if status in finished:
        return "finished"
    h, a = _parse_allsports_score(ev.get("event_final_result", ""))
    if h is not None and live != "1" and status != "":
        return "finished"
    return "upcoming"


# ─────────────────────────────────────────────
# BZZOIRO ISTEKLERI
# ─────────────────────────────────────────────

def _bzz_get(endpoint, params=None):
    try:
        url = f"{BZZ_BASE}/{endpoint}/"
        r   = requests.get(url, headers=BZZ_HEADERS, params=params, timeout=TIMEOUT)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"[Bzzoiro] Hata: {e}")
    return None


# ─────────────────────────────────────────────
# FIKTUR — AllSports'tan cek, TR saatine cevir
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
        r = _allsports_get({"met": "Fixtures", "from": d, "to": d})
        if r:
            all_results.extend(r)

    live = _allsports_get({"met": "Livescore"})
    if live:
        all_results.extend(live)

    if not all_results:
        return []

    tr_day_start = datetime.datetime.strptime(date_str, "%Y-%m-%d")
    tr_day_end   = tr_day_start + datetime.timedelta(hours=24)
    matches      = []
    seen_ids     = set()

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

            status       = _allsports_match_status(ev)
            event_status = str(ev.get("event_status", "")).strip()
            live_min = ""
            if status == "live":
                if event_status and event_status not in ("", "HT"):
                    live_min = f"{event_status}'"
                elif event_status == "HT":
                    live_min = "HT"
                else:
                    live_min = "CANLI"

            h, a   = _parse_allsports_score(ev.get("event_final_result", ""))
            hht, aht = _parse_allsports_score(ev.get("event_halftime_result", ""))
            league   = ev.get("league_name", "")
            country  = ev.get("country_name", "")
            league_full = f"{country} - {league}" if country else league

            matches.append({
                "match_id":      match_id,
                "home_team":     ev["event_home_team"],
                "away_team":     ev["event_away_team"],
                "home_id":       int(ev["home_team_key"]),
                "away_id":       int(ev["away_team_key"]),
                "league":        league_full,
                "league_name":   league.lower(),
                "time":          tr_dt.strftime("%H:%M"),
                "timestamp":     int(tr_dt.timestamp()),
                "status":        status,
                "live_min":      live_min,
                "home_score":    h,
                "away_score":    a,
                "home_ht_score": hht,
                "away_ht_score": aht,
            })
        except (KeyError, TypeError, ValueError):
            continue

    matches.sort(key=lambda x: x["timestamp"])
    return matches


# ─────────────────────────────────────────────
# TAKIM GECMISI — Bzzoiro'dan cek
# ─────────────────────────────────────────────

def _bzz_team_matches(team_name, limit=18):
    """Bzzoiro'dan takim adi ile bitmis maclari ceker."""
    data = _bzz_get("events", {
        "team":      team_name,
        "status":    "finished",
        "page_size": limit,
    })
    if not data or "results" not in data:
        return []
    return data["results"]


def _bzz_parse_match(ev, team_name):
    """Bzzoiro event'inden gol bilgisi cikarir."""
    try:
        home_team  = ev.get("home_team", "").lower()
        away_team  = ev.get("away_team", "").lower()
        team_lower = team_name.lower()

        is_home  = team_lower in home_team
        h_score  = ev.get("home_score")
        a_score  = ev.get("away_score")

        if h_score is None or a_score is None:
            return None

        scored   = h_score if is_home else a_score
        conceded = a_score if is_home else h_score
        result   = "W" if scored > conceded else ("D" if scored == conceded else "L")

        return {
            "goals_scored":   scored,
            "goals_conceded": conceded,
            "is_home":        is_home,
            "result":         result,
        }
    except Exception:
        return None


def _get_team_matches_bzz(team_name, limit=6):
    """Bzzoiro'dan son N mac."""
    raw     = _bzz_team_matches(team_name, limit * 2)
    parsed  = []
    for ev in raw:
        # Kupa maclari atla
        league = ev.get("league", {}).get("name", "").lower()
        if any(kw in league for kw in CUP_KEYWORDS):
            continue
        p = _bzz_parse_match(ev, team_name)
        if p:
            parsed.append(p)
    return parsed[-limit:]


# ─────────────────────────────────────────────
# TAKIM GECMISI — AllSports fallback
# ─────────────────────────────────────────────

def _get_team_matches_allsports(team_id, limit=6):
    """AllSports'tan son 60 gunluk bitmis lig maclari."""
    today     = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)
    from_date = (yesterday - datetime.timedelta(days=60)).strftime("%Y-%m-%d")
    to_date   = yesterday.strftime("%Y-%m-%d")

    result = _allsports_get({"met": "Fixtures", "from": from_date, "to": to_date})
    if not result:
        return []

    parsed    = []
    seen_keys = set()
    for ev in result:
        key     = str(ev.get("event_key", ""))
        home_id = int(ev.get("home_team_key", 0))
        away_id = int(ev.get("away_team_key", 0))
        if team_id != home_id and team_id != away_id:
            continue
        if key in seen_keys:
            continue
        seen_keys.add(key)
        if _allsports_match_status(ev) != "finished":
            continue
        if _is_cup_match(ev):
            continue
        h, a = _parse_allsports_score(ev.get("event_final_result", ""))
        if h is None:
            continue
        is_home  = (team_id == home_id)
        scored   = h if is_home else a
        conceded = a if is_home else h
        result_s = "W" if scored > conceded else ("D" if scored == conceded else "L")
        parsed.append({
            "goals_scored":   scored,
            "goals_conceded": conceded,
            "is_home":        is_home,
            "result":         result_s,
        })

    return parsed[-limit:]


# ─────────────────────────────────────────────
# TOPLU VERİ CEKME
# ─────────────────────────────────────────────

def get_match_data(home_id, away_id, home_name="", away_name="", league_name=""):
    """
    Ev sahibi ve deplasman icin 4 veri seti.
    Buyuk ligler icin Bzzoiro, diger ligler icin AllSports.
    """
    use_bzz = league_name.lower() in BZZ_LEAGUES

    if use_bzz and home_name and away_name:
        home_all = _get_team_matches_bzz(home_name, 12)
        away_all = _get_team_matches_bzz(away_name, 12)
    else:
        home_all = _get_team_matches_allsports(home_id, 12)
        away_all = _get_team_matches_allsports(away_id, 12)

    home_general = home_all[-6:]
    home_venue   = [m for m in home_all if m.get("is_home")][-6:]
    away_general = away_all[-6:]
    away_venue   = [m for m in away_all if not m.get("is_home")][-6:]

    return {
        "home_general": home_general,
        "home_venue":   home_venue,
        "away_general": away_general,
        "away_venue":   away_venue,
    }
