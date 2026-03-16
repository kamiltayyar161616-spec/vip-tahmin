"""
AllSports API - Sadece fiktur + canli skor
Takim gecmisi tarayicidan Sofascore ile cekilir
"""
import requests
import datetime
import os

BASE    = "https://apiv2.allsportsapi.com/football/"
API_KEY = os.environ.get("ALLSPORTS_KEY", "043a0ecb1606761afe8f035a5391fb80581767a64eb3c6e5762966c0d57f9905")
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
TIMEOUT   = 15
TZ_OFFSET = 2


def _get(params):
    params["APIkey"] = API_KEY
    try:
        r = requests.get(BASE, headers=HEADERS, params=params, timeout=TIMEOUT)
        if r.status_code == 200:
            data = r.json()
            if data.get("success") == 1:
                return data.get("result", [])
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
    finished = {"Finished", "FT", "AET", "Pen.", "finished", "After ET", "After Pen.", "Awarded"}
    if status in finished:
        return "finished"
    h, a = _parse_score(ev.get("event_final_result", ""))
    if h is not None and live != "1" and status != "":
        return "finished"
    return "upcoming"


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

            st = _status(ev)
            es = str(ev.get("event_status", "")).strip()
            lm = ""
            if st == "live":
                if es and es != "HT":
                    lm = f"{es}'"
                elif es == "HT":
                    lm = "HT"
                else:
                    lm = "CANLI"

            h,  a  = _parse_score(ev.get("event_final_result", ""))
            hh, ah = _parse_score(ev.get("event_halftime_result", ""))
            league  = ev.get("league_name", "")
            country = ev.get("country_name", "")

            matches.append({
                "match_id":      mid,
                "home_team":     ev["event_home_team"],
                "away_team":     ev["event_away_team"],
                "home_id":       int(ev["home_team_key"]),
                "away_id":       int(ev["away_team_key"]),
                "league":        f"{country} - {league}" if country else league,
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
