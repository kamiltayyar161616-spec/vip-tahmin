"""
BetOracle - Football API
AllSports API - ucretsiz, limitsiz, Railway'de calisir
"""
import requests
import datetime
import os

BASE    = "https://apiv2.allsportsapi.com/football"
API_KEY = os.environ.get("ALLSPORTS_KEY", "043a0ecb1606761afe8f035a5391fb80581767a64eb3c6e5762966c0d57f9905")
TIMEOUT = 15

CUP_KW = [
    'cup', 'kupa', 'copa', 'coupe', 'pokal', 'friendly', 'supercup',
    'super cup', 'champions league', 'europa league',
    'conference league', 'nations league', 'world cup',
    'friendlies', 'amical', 'international'
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
}


def _get(params):
    try:
        params["APIkey"] = API_KEY
        r = requests.get(BASE, params=params, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code == 200:
            data = r.json()
            if data.get("success") == 1:
                return data.get("result", [])
            print(f"[AllSports] success=0: {data}")
        else:
            print(f"[AllSports] HTTP {r.status_code}")
    except Exception as e:
        print(f"[AllSports] Hata: {e}")
    return []


def get_fixtures_by_date(date_str):
    results = _get({"met": "Fixtures", "from": date_str, "to": date_str})
    if not results:
        return []

    matches = []
    for ev in results:
        try:
            league = ev.get("league_name", "")
            country = ev.get("country_name", "")

            # Kupa filtresi
            if any(k in league.lower() for k in CUP_KW):
                continue

            # Durum
            status_raw = (ev.get("event_status") or ev.get("event_final_result") or "").lower()
            if "finished" in status_raw or ev.get("event_final_result") not in (None, ""):
                status = "finished"
            elif "inprogress" in status_raw or "live" in status_raw:
                status = "live"
            else:
                status = "upcoming"

            # Skor
            home_score = None
            away_score = None
            final = ev.get("event_final_result", "")
            ht    = ev.get("event_halftime_result", "")
            home_ht = None
            away_ht = None

            if final and " - " in str(final):
                parts = str(final).split(" - ")
                try:
                    home_score = int(parts[0].strip())
                    away_score = int(parts[1].strip())
                except Exception:
                    pass

            if ht and " - " in str(ht):
                parts = str(ht).split(" - ")
                try:
                    home_ht = int(parts[0].strip())
                    away_ht = int(parts[1].strip())
                except Exception:
                    pass

            # Saat (UTC+3)
            time_raw = ev.get("event_time", "00:00")
            try:
                h, m = int(time_raw[:2]), int(time_raw[3:5])
                h = (h + 3) % 24
                time_str = f"{h:02d}:{m:02d}"
            except Exception:
                time_str = time_raw

            live_min = ""
            if status == "live":
                live_min = ev.get("event_status", "CANLI")

            matches.append({
                "match_id":      str(ev.get("event_key", "")),
                "sofa_id":       ev.get("event_key", ""),
                "home_team":     ev.get("event_home_team", ""),
                "away_team":     ev.get("event_away_team", ""),
                "home_id":       int(ev.get("home_team_key", 0) or 0),
                "away_id":       int(ev.get("away_team_key", 0) or 0),
                "league":        f"{country} - {league}" if country else league,
                "time":          time_str,
                "timestamp":     0,
                "status":        status,
                "live_min":      live_min,
                "home_score":    home_score,
                "away_score":    away_score,
                "home_ht_score": home_ht,
                "away_ht_score": away_ht,
            })
        except Exception as ex:
            print(f"[fixtures] parse hatasi: {ex}")
            continue

    matches.sort(key=lambda x: x["time"])
    return matches


def _parse_event(ev, team_id):
    try:
        home_id  = int(ev.get("home_team_key", 0) or 0)
        final    = ev.get("event_final_result", "")
        if not final or " - " not in str(final):
            return None
        parts    = str(final).split(" - ")
        hs       = int(parts[0].strip())
        as_      = int(parts[1].strip())
        is_home  = (team_id == home_id)
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


def get_team_matches(team_id):
    """Takimin H2H/gecmis maclarini cekmek icin son 2 haftayi kullan"""
    # AllSports H2H endpoint - takim ID'si ile son maclar
    results = _get({"met": "Fixtures", "teamId": team_id})
    if not results:
        return []

    parsed = []
    for ev in results:
        league = (ev.get("league_name") or "").lower()
        if any(k in league for k in CUP_KW):
            continue
        # Sadece bitmis maclar
        final = ev.get("event_final_result", "")
        if not final or " - " not in str(final):
            continue
        p = _parse_event(ev, team_id)
        if p:
            parsed.append(p)

    return parsed


def get_match_data(home_id, away_id):
    home_all = get_team_matches(home_id)
    away_all = get_team_matches(away_id)
    return {
        "home_general": home_all[-6:],
        "home_venue":   [m for m in home_all if m["is_home"]][-6:],
        "away_general": away_all[-6:],
        "away_venue":   [m for m in away_all if not m["is_home"]][-6:],
    }
