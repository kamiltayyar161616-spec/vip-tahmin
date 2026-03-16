"""
BetOracle - Football API
AllSports API - takim gecmisi duzeltildi
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
                return data.get("result", []) or []
            print(f"[AllSports] success!=1: {data}")
        else:
            print(f"[AllSports] HTTP {r.status_code}")
    except Exception as e:
        print(f"[AllSports] Hata: {e}")
    return []


def _parse_score(raw):
    if not raw:
        return None, None
    raw = str(raw).strip()
    for sep in [" - ", "-", ":"]:
        if sep in raw:
            parts = raw.split(sep)
            if len(parts) == 2:
                try:
                    return int(parts[0].strip()), int(parts[1].strip())
                except Exception:
                    pass
    return None, None


def get_fixtures_by_date(date_str):
    results = _get({"met": "Fixtures", "from": date_str, "to": date_str})
    if not results:
        return []

    matches = []
    for ev in results:
        try:
            league  = ev.get("league_name", "") or ""
            country = ev.get("country_name", "") or ""

            league_low = league.lower()
            if any(k in league_low for k in CUP_KW):
                continue

            status_raw = (ev.get("event_status") or "").strip()
            if status_raw in ("Finished", "FT", "AET", "PEN"):
                status = "finished"
            elif status_raw in ("", "NS", "TBD", "Sched."):
                status = "upcoming"
            else:
                status = "live"

            home_score, away_score = _parse_score(ev.get("event_final_result"))
            home_ht, away_ht       = _parse_score(ev.get("event_halftime_result"))

            # Saat - AllSports UTC donduruyor, TR = UTC+2
            time_raw = ev.get("event_time", "00:00") or "00:00"
            try:
                h, m     = int(time_raw[:2]), int(time_raw[3:5])
                h        = (h + 2) % 24
                time_str = f"{h:02d}:{m:02d}"
            except Exception:
                time_str = time_raw

            live_min = ""
            if status == "live":
                live_min = status_raw or "CANLI"

            matches.append({
                "match_id":      str(ev.get("event_key", "")),
                "sofa_id":       ev.get("event_key", ""),
                "home_team":     ev.get("event_home_team", ""),
                "away_team":     ev.get("event_away_team", ""),
                "home_id":       int(ev.get("home_team_key") or 0),
                "away_id":       int(ev.get("away_team_key") or 0),
                "league":        f"{country} - {league}" if country else league,
                "league_key":    int(ev.get("league_key") or 0),
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


def get_team_matches(team_id):
    """
    Takimin son 9 aylik bitirmis ligmaclarini cek.
    Her ay icin ayri istek at, sonuclari birlestir.
    """
    today     = datetime.date.today()
    from_date = (today - datetime.timedelta(days=270)).strftime("%Y-%m-%d")
    to_date   = (today - datetime.timedelta(days=1)).strftime("%Y-%m-%d")

    results = _get({
        "met":    "Fixtures",
        "teamId": team_id,
        "from":   from_date,
        "to":     to_date,
    })

    if not results:
        print(f"[fapi] Takim {team_id} icin mac bulunamadi")
        return []

    parsed = []
    for ev in results:
        league = (ev.get("league_name") or "").lower()
        if any(k in league for k in CUP_KW):
            continue

        status_raw = (ev.get("event_status") or "").strip()
        if status_raw not in ("Finished", "FT", "AET", "PEN"):
            continue

        hs, as_ = _parse_score(ev.get("event_final_result"))
        if hs is None or as_ is None:
            continue

        home_id = int(ev.get("home_team_key") or 0)
        is_home  = (team_id == home_id)
        scored   = hs if is_home else as_
        conceded = as_ if is_home else hs
        result   = "W" if scored > conceded else ("D" if scored == conceded else "L")

        parsed.append({
            "goals_scored":   scored,
            "goals_conceded": conceded,
            "is_home":        is_home,
            "result":         result,
        })

    print(f"[fapi] Takim {team_id}: {len(parsed)} mac bulundu")
    return parsed


def get_match_data(home_id, away_id):
    home_all = get_team_matches(home_id)
    away_all = get_team_matches(away_id)

    print(f"[fapi] Ev: {len(home_all)} mac, Dep: {len(away_all)} mac")

    return {
        "home_general": home_all[-6:],
        "home_venue":   [m for m in home_all if m["is_home"]][-6:],
        "away_general": away_all[-6:],
        "away_venue":   [m for m in away_all if not m["is_home"]][-6:],
    }
