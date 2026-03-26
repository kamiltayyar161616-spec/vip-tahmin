"""
AllSports API - leagueId ile takim gecmisi
Fiktur + Takim gecmisi (yeniden eskiye sirali)
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

# Fikstürden filtrelenecek anahtar kelimeler
EXCLUDE_KW = [
    # Genc / alt yas ligleri
    "u16","u17","u18","u19","u20","u21","u22","u23",
    " u16"," u17"," u18"," u19"," u20"," u21"," u22"," u23",
    "under-16","under-17","under-18","under-19","under-20","under-21","under-23",
    "under 16","under 17","under 18","under 19","under 20","under 21","under 23",
    "youth","yth","junioren","juniors","juvenil","juveniles",
    "primavera","ospiti","reserves","reserve","b team",
    "development","academy","satelite","sub-20","sub-23",
    # Bayan ligleri
    " w ","women","femeni","femenina","feminine","frauen","dames",
    "ladies","mujer","mujeres","feminino","naiset","womens",
    "a-league women","super league women","liga f",
    "nwsl","wsl","division 1 feminine","d1 feminine",
    # Alt ligler / bölgesel
    "regional","oberliga","verbandsliga","landesliga",
    "amateur","amatör","amateure",
    "3. liga","4. liga","5. liga","6. liga",
    "ii liga","iii liga","iv liga",
    "3rd division","4th division","5th division",
    "division 3","division 4","division 5","division 6",
    "serie c","serie d","serie e",
    "3rd division","4th division","5th division",
    "league three",
    "tercera","segunda b","terceira",
    "national league n","national league s",
    "non league","isthmian","npl premier",
    "northern premier",
    # Diğer istenmeyen
    "futsal","beach","indoor","sala",
    "viareggio","highland","lowland",
    "nasjonal u","revelacao","pro development",
]

# Her ülke için izin verilen lig anahtar kelimeleri
COUNTRY_LEAGUES = {
    # İngiltere - 4 lig
    "england": ["premier league","championship","league one","league two"],
    # Almanya
    "germany": ["bundesliga","2. bundesliga","bundesliga 2","2.bundesliga"],
    # İspanya
    "spain": ["la liga","laliga","segunda","segunda division","2. division"],
    # İtalya
    "italy": ["serie a","serie b"],
    # Fransa
    "france": ["ligue 1","ligue 2"],
    # Hollanda
    "netherlands": ["eredivisie","eerste divisie","keuken kampioen"],
    # Portekiz
    "portugal": ["primeira liga","liga portugal","segunda liga","liga nos"],
    # Belçika
    "belgium": ["first division","pro league","1a","1b","jupiler"],
    # Türkiye
    "turkey": ["süper lig","super lig","1. lig","tff 1"],
    # Rusya
    "russia": ["premier league","first league","1. division"],
    # İskoçya
    "scotland": ["premiership","championship","premier league"],
    # Yunanistan
    "greece": ["super league","super league 2"],
    # İsviçre
    "switzerland": ["super league","challenge league"],
    # Avusturya
    "austria": ["bundesliga","2. liga","erste liga"],
    # Danimarka
    "denmark": ["superliga","1. division","first division"],
    # Norveç
    "norway": ["eliteserien","1. divisjon","first division"],
    # İsveç
    "sweden": ["allsvenskan","superettan"],
    # Polonya - sadece Ekstraklasa
    "poland": ["ekstraklasa"],
    # Not: II Liga, III Liga vs. EXCLUDE_KW ile zaten filtreleniyor
    # Çek Cumhuriyeti
    "czech republic": ["první liga","fortuna liga","fnl","druhá liga","2. liga"],
    # Slovakya
    "slovakia": ["super liga","fortuna liga","2. liga"],
    # Romanya
    "romania": ["superliga","liga 1","liga 2"],
    # Macaristan
    "hungary": ["otp bank liga","nb i","nb ii","nemzeti bajnokság"],
    # Hırvatistan
    "croatia": ["hnl","1. hnl","superkup","prva hnl"],
    # Sırbistan
    "serbia": ["superliga","prva liga"],
    # Ukrayna
    "ukraine": ["premier league","persha liha","1. liha"],
    # Bulgaristan
    "bulgaria": ["first league","first professional league","segunda"],
    # İsrail - istenmiyor
    # "israel": [],
    # Kıbrıs
    "cyprus": ["1st division","first division"],
    # Galler
    "wales": ["cymru premier","premier league"],
    # Kuzey İrlanda
    "northern ireland": ["premiership","championship"],
    # İrlanda
    "ireland": ["premier division","first division"],
    # Finlandiya
    "finland": ["veikkausliiga","ykkönen"],
    # İzlanda
    "iceland": ["urvalsdeild","1. deild"],
    # Lüksemburg
    "luxembourg": ["bgl ligue","national division"],
    # Bosna
    "bosnia and herzegovina": ["premier league","prva liga"],
    # Arnavutluk
    "albania": ["superliga","kategoria superiore"],
    # Karadağ
    "montenegro": ["first league","prva liga"],
    # Kuzey Makedonya
    "north macedonia": ["first league","prva liga"],
    # Gürcistan
    "georgia": ["erovnuli liga","umaglesi liga"],
    # Ermenistan
    "armenia": ["premier league","arakel liga"],
    # Azerbaycan
    "azerbaijan": ["premier league"],
    # Moldova
    "moldova": ["super liga","national division"],
    # Kosova
    "kosovo": ["superliga","first league"],
    # Estonya
    "estonia": ["premium liiga","meistriliiga"],
    # Letonya
    "latvia": ["optibet virsliga","virsliga"],
    # Litvanya
    "lithuania": ["a lyga","1 lyga"],
    # Belarus
    "belarus": ["premier league","vysshaya liga"],
    # Kazakistan
    "kazakhstan": ["premier league","first league"],
    # Brezilya
    "brazil": ["série a","serie a","série b","serie b","brasileirao"],
    # Arjantin
    "argentina": ["liga profesional","primera division","primera nacional","torneo"],
    # Meksika
    "mexico": ["liga mx","ascenso mx","liga de expansion"],
    # Kolombiya
    "colombia": ["primera a","categoria primera","liga betplay"],
    # Şili
    "chile": ["primera division","primera b"],
    # Uruguay
    "uruguay": ["liga auf","primera division"],
    # Peru
    "peru": ["liga 1"],
    # Ekvator
    "ecuador": ["liga pro","serie a","serie b"],
    # Venezuela
    "venezuela": ["primera division"],
    # ABD - sadece MLS
    "usa": ["mls"],
    # Kanada
    "canada": ["canadian premier","cpl"],
    # Japonya
    "japan": ["j1 league","j2 league","j.league"],
    # Güney Kore
    "korea republic": ["k league 1","k league 2"],
    # Çin
    "china": ["super league","chinese super"],
    # Avustralya - SADECE A-League Men
    "australia": ["a-league men"],
    # Suudi Arabistan
    "saudi arabia": ["saudi pro league","roshn saudi league"],
    # BAE
    "united arab emirates": ["pro league","uae pro league"],
    # Katar
    "qatar": ["stars league","qatar stars"],
    # Güney Afrika
    "south africa": ["premier soccer league","psl"],
    # Mısır
    "egypt": ["premier league","egy premier"],
    # Nijerya
    "nigeria": ["npfl","premier league"],
    # Fas
    "morocco": ["botola pro","ligue 1"],
    # Tunus
    "tunisia": ["ligue professionnelle 1"],
    # Fildişi Sahili
    "ivory coast": ["ligue 1"],
    # Gana
    "ghana": ["premier league","ghana premier"],
    # Kamerun
    "cameroon": ["elite one"],
    # Uluslararası
    "intl": ["champions league","europa league","conference league","nations league","world cup","copa america","euro"],
    "eurocups": ["champions league","europa league","conference league","youth league"],
}

def _is_excluded(league_name, country_name):
    """Sadece tanımlı ligleri geçir, diğerlerini filtrele."""
    ln = (league_name or "").lower()
    cn = (country_name or "").lower()
    full = f"{cn} {ln}"

    # Anahtar kelime filtresi - lig adı kontrolü
    kw_hit = next((k for k in EXCLUDE_KW if k in full), None)
    if kw_hit:
        return True

    # Ülke whitelist'te yoksa çıkar
    matched_country = None
    for c in COUNTRY_LEAGUES:
        if c in cn:
            matched_country = c
            break

    if not matched_country:
        return True  # Bilinmeyen ülke = çıkar

    # Ülke için izin verilen ligler
    allowed = COUNTRY_LEAGUES[matched_country]
    if not any(a in ln for a in allowed):
        return True  # İzin verilmeyen lig = çıkar

    return False

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

            # Alt lig / genc / bayan filtresi
            home_t = ev.get("event_home_team","").lower()
            away_t = ev.get("event_away_team","").lower()
            team_str = f"{home_t} {away_t}"
            youth_kw = ["u16","u17","u18","u19","u20","u21","u22","u23",
                       "under-16","under-17","under-18","under-19","under-20","under-21","under-23",
                       "reserves","reserve","youth","b team","ii ","' ii","(b)","sub-20","sub-23"]
            if any(k in team_str for k in youth_kw):
                continue
            if _is_excluded(league, country):
                continue

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
# LIG MACLARI
# ─────────────────────────────────────────────

def _get_league_matches(league_id):
    """Ligin tum sezon maclarini ceker. Yeniden eskiye sirali."""
    if league_id in _league_cache:
        return _league_cache[league_id]

    today     = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)

    if today.month >= 7:
        season_start = datetime.date(today.year, 7, 1)
    else:
        season_start = datetime.date(today.year - 1, 7, 1)

    from_str = season_start.strftime("%Y-%m-%d")
    to_str   = yesterday.strftime("%Y-%m-%d")

    print(f"[AllSports] League {league_id} cekiliyor: {from_str} -> {to_str}")

    result = _get({
        "met":             "Fixtures",
        "leagueId":        league_id,
        "from":            from_str,
        "to":              to_str,
        "withPlayerStats": 0,
    })

    if not result:
        print(f"[AllSports] League {league_id} bos dondu!")
        _league_cache[league_id] = []
        return []

    print(f"[AllSports] League {league_id}: {len(result)} mac geldi")

    # Sadece gerekli alanları tut
    slim = []
    for ev in result:
        try:
            slim.append({
                "event_key":             str(ev.get("event_key", "")),
                "event_date":            ev.get("event_date", ""),
                "home_team_key":         ev.get("home_team_key"),
                "away_team_key":         ev.get("away_team_key"),
                "event_final_result":    ev.get("event_final_result", ""),
                "event_halftime_result": ev.get("event_halftime_result", ""),
                "event_status":          ev.get("event_status", ""),
                "event_live":            ev.get("event_live", "0"),
                "league_name":           ev.get("league_name", ""),
            })
        except Exception:
            continue

    # YENİDEN ESKİYE sirala (en son mac basta)
    slim.sort(key=lambda x: x.get("event_date", ""), reverse=True)
    print(f"[AllSports] League {league_id}: ilk mac {slim[0]['event_date'] if slim else 'yok'}, son mac {slim[-1]['event_date'] if slim else 'yok'}")

    _league_cache[league_id] = slim
    return slim


def _parse_team_match(ev, team_id):
    try:
        home_id = int(ev["home_team_key"])
        away_id = int(ev["away_team_key"])
        if team_id != home_id and team_id != away_id:
            return None
        if _status(ev) != "finished":
            return None
        if _is_cup(ev.get("league_name", "")):
            return None
        h, a = _parse_score(ev.get("event_final_result", ""))
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


def get_team_matches_from_league(team_id, league_id, limit=20):
    """Lig maclarindan takim verisi. Yeniden eskiye sirali, ilk limit = en son maclar."""
    league_matches = _get_league_matches(league_id)
    parsed = []
    seen   = set()
    for ev in league_matches:
        key = ev.get("event_key", "")
        if key in seen:
            continue
        seen.add(key)
        p = _parse_team_match(ev, team_id)
        if p:
            parsed.append(p)
    # Yeniden eskiye sirali, [:limit] = en son maclar
    return parsed[:limit]


def get_match_data(home_id, away_id, league_key=None):
    if not league_key:
        return {"home_general":[],"home_venue":[],"away_general":[],"away_venue":[]}

    # Genel: ligden son 6
    home_all = get_team_matches_from_league(home_id, league_key, 20)
    away_all = get_team_matches_from_league(away_id, league_key, 20)

    # Ic/dis saha: genel listeden filtrele (eksik olmamasi icin)
    home_venue = [m for m in home_all if m["is_home"]]
    away_venue = [m for m in away_all if not m["is_home"]]

    # 6 mac yoksa genel listeden tamamla
    if len(home_venue) < 6:
        home_venue = home_all[:6]
    if len(away_venue) < 6:
        away_venue = away_all[:6]

    return {
        "home_general": home_all[:6],
        "home_venue":   home_venue[:6],
        "away_general": away_all[:6],
        "away_venue":   away_venue[:6],
    }
