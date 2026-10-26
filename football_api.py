"""
BetOracle veri katmani - NowGoal (SAHA veritabani)
AllSports API kaldirildi. Ayni sunucudaki SAHA (Volkano-Sinyal) sistemi NowGoal'dan
maclari ve her takimin son maclarini zaten cekip data/nowgoal.db'ye yaziyor; burada sadece okunur.
Fonksiyon imzalari eskisiyle ayni (app.py / value_hunting.py degismeden calisir).
"""
import os
import json
import sqlite3
import datetime
import time
import urllib.request
from collections import Counter
from zoneinfo import ZoneInfo

DB_FILE = os.environ.get("NOWGOAL_DB", "/root/Volkano-Sinyal/data/nowgoal.db")
TZ = ZoneInfo(os.environ.get("ORACLE_TZ", "Europe/Podgorica"))
LIVE_MAX_MIN = 180   # baslama + bu kadar dk icinde sonucu gelmemisse canli skor sorulur
FLASH_SITES = ["https://www.nowgoal.net", "https://www.nowgoal.world"]
FLASH_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "identity",
}
FLASH_TTL = 60          # canli skor onbellek (sn)
MAX_FLASH_PER_CALL = 40 # tek fikstur isteginde en fazla bu kadar NowGoal sorgusu
_flash_cache = {}       # mid -> (zaman, veri)
_ht_cache = {}          # mid -> (ht_h, ht_a)  bitmis maclarin ilk yarisi (kalici)

# NowGoal lig kodlari (ornek: "ENG PR", "SPA D1", "TFF 1. Lig"). Eski AllSports beyaz listesinin karsiligi.
ALLOWED_CODES = {
    # Ingiltere 4 lig
    "ENG PR", "ENG LCH", "ENG L1", "ENG L2",
    # 1. ve 2. lig istenenler
    "GER D1", "GER D2", "SPA D1", "SPA D2", "ITA D1", "ITA D2", "FRA D1", "FRA D2",
    "SCO PR", "SCO CH", "SWE D1", "SWE D2", "NOR D1", "NOR AL", "TUR D1", "TFF 1. Lig",
    "POL PR", "POL D1",
    "HOL D1", "HOL D2", "POR D1", "POR D2", "BEL D1", "BEL D2", "SUI D1", "SUI D2", "SWI D1", "SWI D2",
    "DEN SASL", "DEN D1", "CZE D1", "CZE D2", "CRO D1", "CRO D2", "IRE PR", "IRE D1",
    # sadece 1. lig
    "RUS PR", "GRE D1", "AUT D1", "SVK D1", "ROM D1", "HUN D1", "SER D1", "UKR D1", "BUL FL",
    "CYP D1", "WAL D1", "NIR D1", "FIN D1", "ICE PR", "LUX D1", "ALB D1", "MNE D1", "MKD D1",
    "GEO D1", "ARM D1", "AZE D1", "MOL D1", "KOS D1", "EST D1", "LAT D1", "TOPLYGA", "BLR D1", "KAZ PR",
    # Amerika
    "BRA D1", "ARG D1", "MEX D1", "COL D1", "CHI D1", "URU D1", "PER D1", "ECU LPSA", "VEN D1", "MLS",
    # Asya / Okyanusya / Afrika
    "JPN D1", "KOR D1", "CHA CSL", "AUS D1", "RSA PR", "NGA PR", "GHA D1", "CMR D1", "CIV D1",
    # Uluslararasi kulup turnuvalari
    "UEFA CL", "UEFA EL", "UEFA ECL", "CON CLA",
}
# Kod listede olmasa bile: bilinen ulke + ust lig son eki ise kabul et (kod adlari zamanla degisebilir)
TOP_SUFFIX = ("D1", "PR", "PL")
NOT_ALLOWED_PART = ("W", "U19", "U20", "U21", "U23", "Y", "YL", "RES", "CUP", "Cup", "LC", "CF")

_COUNTRIES = {c.split()[0] for c in ALLOWED_CODES if " " in c}
_league_cache = {}   # eski /api/debug ve /api/clear-cache uyumlulugu icin (artik kullanilmiyor)


def _conn():
    c = sqlite3.connect(f"file:{DB_FILE}?mode=ro", uri=True, timeout=20)
    c.row_factory = sqlite3.Row
    return c


def _team_name(rows):
    c = Counter()
    for r in rows:
        c[r.get("home")] += 1
        c[r.get("away")] += 1
    c.pop(None, None)
    return c.most_common(1)[0][0] if c else None


def _league_code(st):
    """Iki takimin son maclarinda ortak gecen (kupa/hazirlik olmayan) en sik lig kodu."""
    hc = Counter(r["lg"] for r in st.get("home_last", []) if r.get("lg"))
    ac = Counter(r["lg"] for r in st.get("away_last", []) if r.get("lg"))
    common = [k for k, _ in (hc + ac).most_common() if k in hc and k in ac]
    for k in common:
        if not _is_cup_code(k):
            return k
    return common[0] if common else None


def _is_cup_code(code):
    code = code or ""
    return code == "INT CF" or any(p in code.split() for p in ("CUP", "Cup", "FAC", "FAT", "LC", "C", "SC", "YCup"))


EXCLUDED_CODES = {"CHA D1", "RUS D1", "CHA D2"}   # NowGoal'da bu D1'ler ikinci lig


def _allowed(code):
    if not code or code in EXCLUDED_CODES:
        return False
    if code in ALLOWED_CODES:
        return True
    parts = code.split()
    if any(p in NOT_ALLOWED_PART for p in parts) or (len(parts[0]) > 3 and parts[0].endswith("W")):
        return False   # kadin / genc / kupa
    return len(parts) == 2 and parts[1] in TOP_SUFFIX and parts[0] in _COUNTRIES


def _tarih(alan):
    p = (alan or "").split(",")
    if len(p) != 6 or not all(x.isdigit() for x in p):
        return None
    y, ay0, g, sa, dk, sn = map(int, p)   # GMT+8, JS ayi (0 = Ocak)
    try:
        return datetime.datetime(y, ay0 + 1, g, sa, dk, sn,
                                 tzinfo=datetime.timezone(datetime.timedelta(hours=8))).astimezone(datetime.timezone.utc)
    except ValueError:
        return None


def _flash(mid):
    """NowGoal flashdata: 6/7 skor, 8 durum (0 baslamadi, 1 ilk yari, 2 devre, 3 ikinci yari, 4 uzatma,
    -1 bitti, negatif digerleri iptal/ertelendi), 10 icinde bulunulan yarinin baslama saati, 15/16 ilk yari."""
    hit = _flash_cache.get(mid)
    if hit and time.time() - hit[0] < FLASH_TTL:
        return hit[1]
    for site in FLASH_SITES:
        try:
            req = urllib.request.Request(f"{site}/flashdata/get?id={mid}&t={int(time.time() * 1000)}",
                                         headers=dict(FLASH_HEADERS, Referer=site + "/"))
            with urllib.request.urlopen(req, timeout=10) as r:
                bas = r.read().decode("utf-8", errors="replace").split("!")[0].split("^")
            if len(bas) < 17 or bas[0] != str(mid):
                continue
            num = lambda i: int(bas[i]) if bas[i].lstrip("-").isdigit() else None
            d = {"h": num(6), "a": num(7), "state": num(8), "half_start": _tarih(bas[10]),
                 "hth": num(15), "hta": num(16)}
            _flash_cache[mid] = (time.time(), d)
            if d["state"] == -1 and d["hth"] is not None:
                _ht_cache[mid] = (d["hth"], d["hta"])
            return d
        except Exception:
            continue
    return None


def _live_info(f, now):
    st = f.get("state")
    if st == -1:
        return "finished", ""
    if st in (1, 2, 3, 4, 5):
        if st == 2:
            return "live", "HT"
        hs = f.get("half_start")
        dk = int((now - hs).total_seconds() / 60) + 1 if hs else None
        if dk is None:
            return "live", "CANLI"
        dk = min(dk, 45) if st == 1 else min(45 + dk, 90) if st == 3 else 90 + min(dk, 30)
        return "live", f"{max(dk, 1)}'"
    return "upcoming", ""


# ─────────────────────────────────────────────
# FIKSTUR
# ─────────────────────────────────────────────

def get_fixtures_by_date(date_str):
    day = datetime.datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=TZ)
    start, end = day.astimezone(datetime.timezone.utc), (day + datetime.timedelta(days=1)).astimezone(datetime.timezone.utc)
    now = datetime.datetime.now(datetime.timezone.utc)
    try:
        c = _conn()
        have = {x[1] for x in c.execute("PRAGMA table_info(ng_match)")}
        htcols = "ht_h, ht_a" if "ht_h" in have else "NULL AS ht_h, NULL AS ht_a"
        rows = c.execute(f"""SELECT mid, home, away, kickoff_utc, status, ft_h, ft_a, {htcols}, league_vk, stats_json
                            FROM ng_match WHERE status IN ('stats','finished') AND kickoff_utc >= ? AND kickoff_utc < ?
                            ORDER BY kickoff_utc""", (start.isoformat(), end.isoformat())).fetchall()
        c.close()
    except Exception as e:
        print(f"[NowGoal] DB okunamadi: {e}")
        return []

    matches = []
    asked = 0
    for r in rows:
        try:
            st = json.loads(r["stats_json"]) if r["stats_json"] else {}
            code = _league_code(st)
            if not (_allowed(code) or r["league_vk"]):   # Volkano'da olan mac lig filtresine takilmaz
                continue
            ko_utc = datetime.datetime.fromisoformat(r["kickoff_utc"])
            mins = (now - ko_utc).total_seconds() / 60
            hs, as_, hth, hta = r["ft_h"], r["ft_a"], r["ht_h"], r["ht_a"]
            status, live_min = ("finished", "") if hs is not None else ("upcoming", "")
            if hth is None and r["mid"] in _ht_cache:
                hth, hta = _ht_cache[r["mid"]]
            need_live = hs is None and 0 <= mins <= LIVE_MAX_MIN
            need_ht = hs is not None and hth is None and mins <= 72 * 60 and r["mid"] not in _ht_cache
            if (need_live or need_ht) and asked < MAX_FLASH_PER_CALL:
                if r["mid"] not in _flash_cache or time.time() - _flash_cache[r["mid"]][0] >= FLASH_TTL:
                    asked += 1
                f = _flash(r["mid"])
                if f:
                    if need_live:
                        status, live_min = _live_info(f, now)
                        if status != "upcoming":
                            hs, as_ = f["h"], f["a"]
                    if f["hth"] is not None and (status == "finished" or f["state"] in (2, 3, 4, 5)):
                        hth, hta = f["hth"], f["hta"]
            ko = ko_utc.astimezone(TZ)
            lg = r["league_vk"] or code
            matches.append({
                "match_id": str(r["mid"]),
                "home_team": r["home"],
                "away_team": r["away"],
                # analiz rotasi /api/analyze/<home_id>/<away_id>?lk= -> hepsi mac id'si (veri mac bazinda)
                "home_id": int(r["mid"]),
                "away_id": int(r["mid"]),
                "league": lg,
                "league_name": code,
                "league_key": int(r["mid"]),
                "time": ko.strftime("%H:%M"),
                "timestamp": int(ko.timestamp()),
                "status": status,
                "live_min": live_min,
                "home_score": hs,
                "away_score": as_,
                "home_ht_score": hth,
                "away_ht_score": hta,
            })
        except Exception as e:
            print(f"[NowGoal] mac atlandi {r['mid']}: {e}")
    return matches


# ─────────────────────────────────────────────
# TAKIM GECMISI
# ─────────────────────────────────────────────

def _parse_rows(rows, team, code):
    """Takimin son maclari -> value_hunting formatı. Once ayni ligdeki maclar; azsa kupa disi tum maclar."""
    out_lg, out_all = [], []
    for r in rows:
        ft = r.get("ft")
        if not ft or team not in (r.get("home"), r.get("away")):
            continue
        is_home = r.get("home") == team
        s, k = (ft[0], ft[1]) if is_home else (ft[1], ft[0])
        m = {"goals_scored": s, "goals_conceded": k, "is_home": is_home,
             "result": "W" if s > k else ("D" if s == k else "L"), "date": r.get("date"), "lg": r.get("lg")}
        ht = r.get("ht")
        if ht and len(ht) == 2:
            m["iy_scored"], m["iy_conceded"] = (ht[0], ht[1]) if is_home else (ht[1], ht[0])
        if r.get("lg") == code:
            out_lg.append(m)
        if not _is_cup_code(r.get("lg")):
            out_all.append(m)
    out_lg.sort(key=lambda x: x.get("date") or "", reverse=True)
    out_all.sort(key=lambda x: x.get("date") or "", reverse=True)
    return out_lg if len(out_lg) >= 4 else out_all


def get_match_data(home_id, away_id, league_key=None):
    empty = {"home_general": [], "home_venue": [], "away_general": [], "away_venue": []}
    mid = league_key or home_id
    try:
        c = _conn()
        r = c.execute("SELECT stats_json FROM ng_match WHERE mid=?", (int(mid),)).fetchone()
        c.close()
    except Exception as e:
        print(f"[NowGoal] DB okunamadi: {e}")
        return empty
    if not r or not r["stats_json"]:
        return empty
    st = json.loads(r["stats_json"])
    code = _league_code(st)
    ht = _team_name(st.get("home_last", [])) or st.get("home_team")
    at = _team_name(st.get("away_last", [])) or st.get("away_team")
    home_all = _parse_rows(st.get("home_last", []), ht, code)
    away_all = _parse_rows(st.get("away_last", []), at, code)
    home_venue = [m for m in home_all if m["is_home"]] or home_all[:6]
    away_venue = [m for m in away_all if not m["is_home"]] or away_all[:6]
    return {
        "home_general": home_all[:6],
        "home_venue": home_venue[:6],
        "away_general": away_all[:6],
        "away_venue": away_venue[:6],
    }


# eski debug rotasi uyumlulugu
def get_team_matches_from_league(team_id, league_id, limit=20):
    d = get_match_data(team_id, team_id, league_id)
    return d["home_general"][:limit]


def _parse_team_match(ev, team_id):
    return None
