"""
Sofascore API — Rotating Headers + Retry
"""
import requests
import datetime
import random
from typing import Optional

BASE = "https://api.sofascore.com/api/v1"
TIMEOUT = 15

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3.1 Safari/605.1.15",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3.1 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Android 14; Mobile; rv:124.0) Gecko/124.0 Firefox/124.0",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.6261.119 Mobile Safari/537.36",
]

PROXIES_FREE = [
    None,  # önce proxysiz dene
]

def _make_headers():
    ua = random.choice(USER_AGENTS)
    return {
        "User-Agent": ua,
        "Referer": "https://www.sofascore.com/",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Origin": "https://www.sofascore.com",
        "DNT": "1",
        "Connection": "keep-alive",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }


def _get(url: str, params: dict = None, retries: int = 3) -> Optional[dict]:
    for attempt in range(retries):
        try:
            headers = _make_headers()
            session = requests.Session()
            # Önce ana sayfayı "ziyaret et" (cookie almak için)
            if attempt == 0:
                try:
                    session.get(
                        "https://www.sofascore.com/",
                        headers=headers,
                        timeout=8,
                        allow_redirects=True
                    )
                except Exception:
                    pass

            r = session.get(
                url,
                headers=headers,
                params=params,
                timeout=TIMEOUT,
                allow_redirects=True
            )
            if r.status_code == 200:
                return r.json()
            elif r.status_code == 403:
                print(f"[Sofascore] 403 engel - deneme {attempt+1}/{retries}")
            else:
                print(f"[Sofascore] HTTP {r.status_code} - {url}")
        except Exception as e:
            print(f"[Sofascore] Hata deneme {attempt+1}: {e}")
    return None


# ────────────────────────────────────────────────────────────────────────────
# FİKSTÜR
# ────────────────────────────────────────────────────────────────────────────

def get_fixtures_by_date(date_str: str) -> list[dict]:
    url  = f"{BASE}/sport/football/scheduled-events/{date_str}"
    data = _get(url)
    if not data or "events" not in data:
        return []

    matches = []
    for ev in data["events"]:
        try:
            home = ev["homeTeam"]["name"]
            away = ev["awayTeam"]["name"]
            home_id = ev["homeTeam"]["id"]
            away_id = ev["awayTeam"]["id"]
            match_id = ev["id"]
            tournament = ev.get("tournament", {})
            league_name = tournament.get("name", "")
            category = tournament.get("category", {}).get("name", "")
            league_full = f"{category} — {league_name}" if category else league_name
            timestamp = ev.get("startTimestamp", 0)
            dt = datetime.datetime.utcfromtimestamp(timestamp)
            match_time = dt.strftime("%H:%M")
            status_code = ev.get("status", {}).get("code", 0)
            matches.append({
                "match_id":  match_id,
                "home_team": home,
                "away_team": away,
                "home_id":   home_id,
                "away_id":   away_id,
                "league":    league_full,
                "time":      match_time,
                "status":    status_code,
                "timestamp": timestamp,
            })
        except (KeyError, TypeError):
            continue

    matches.sort(key=lambda x: x["timestamp"])
    return matches


# ────────────────────────────────────────────────────────────────────────────
# TAKIM İSTATİSTİKLERİ
# ────────────────────────────────────────────────────────────────────────────

def _parse_event_stats(event: dict, team_id: int) -> Optional[dict]:
    try:
        home_id    = event["homeTeam"]["id"]
        home_score = event.get("homeScore", {}).get("current", 0) or 0
        away_score = event.get("awayScore", {}).get("current", 0) or 0
        if team_id == home_id:
            return {"goals_scored": home_score, "goals_conceded": away_score,
                    "is_home": True,
                    "result": "W" if home_score > away_score else ("D" if home_score == away_score else "L")}
        else:
            return {"goals_scored": away_score, "goals_conceded": home_score,
                    "is_home": False,
                    "result": "W" if away_score > home_score else ("D" if home_score == away_score else "L")}
    except (KeyError, TypeError):
        return None


def _get_all_last(team_id: int, pages: int = 3) -> list[dict]:
    all_events = []
    for page in range(pages):
        url  = f"{BASE}/team/{team_id}/events/last/{page}"
        data = _get(url)
        if not data or "events" not in data:
            break
        for ev in data["events"]:
            parsed = _parse_event_stats(ev, team_id)
            if parsed:
                all_events.append(parsed)
        if not data.get("hasNextPage", False) and page > 0:
            break
    return all_events


def get_team_last_matches(team_id: int, limit: int = 6) -> list[dict]:
    events = _get_all_last(team_id, pages=2)
    return events[-limit:]


def get_team_home_matches(team_id: int, limit: int = 6) -> list[dict]:
    all_matches = _get_all_last(team_id, pages=3)
    home = [m for m in all_matches if m.get("is_home")]
    return home[-limit:]


def get_team_away_matches(team_id: int, limit: int = 6) -> list[dict]:
    all_matches = _get_all_last(team_id, pages=3)
    away = [m for m in all_matches if not m.get("is_home")]
    return away[-limit:]


def get_match_data(home_id: int, away_id: int) -> dict:
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
