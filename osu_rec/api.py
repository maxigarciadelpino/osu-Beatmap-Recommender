import os, time, threading
import requests
from . import config as C

_lock = threading.Lock()
_last_call = [0.0]


class TokenManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._headers, self._exp = None, 0.0

    def headers(self):
        with self._lock:
            if not self._headers or time.time() > self._exp - 60:
                r = requests.post("https://osu.ppy.sh/oauth/token", timeout=C.TIMEOUT, data={
                    "client_id": os.environ["OSU_CLIENT_ID"],
                    "client_secret": os.environ["OSU_CLIENT_SECRET"],
                    "grant_type": "client_credentials", "scope": "public"})
                r.raise_for_status()
                j = r.json()
                self._headers = {"Authorization": f"Bearer {j['access_token']}",
                                 "Accept": "application/json", "x-api-version": "20220705"}
                self._exp = time.time() + j.get("expires_in", 3600)
            return self._headers


def api_get(url, tm, params=None, tries=3):
    for i in range(tries):
        with _lock:
            wait = C.API_INTERVAL - (time.time() - _last_call[0])
            if wait > 0:
                time.sleep(wait)
            _last_call[0] = time.time()
        try:
            r = requests.get(url, headers=tm.headers(), params=params, timeout=C.TIMEOUT)
            if r.status_code == 429:
                time.sleep(5 * (i + 1))
                continue
            if 400 <= r.status_code < 500:
                return None
            r.raise_for_status()
            return r.json()
        except requests.exceptions.RequestException:
            time.sleep(2 * (i + 1))
    return None


def get_user(tm, username):
    return api_get(f"{C.BASE}/users/{username}/osu", tm, {"key": "username"})


def fetch_scores(tm, uid, kind, total=100, **params):
    out, offset = [], 0
    while len(out) < total:
        p = {"mode": "osu", "limit": 50, "offset": offset, **params}
        page = api_get(f"{C.BASE}/users/{uid}/scores/{kind}", tm, p)
        if not page:
            break
        out += page
        if len(page) < 50:
            break
        offset += 50
    return out[:total]


def fetch_recent(tm, uid, total=50):
    return fetch_scores(tm, uid, "recent", total=total, include_fails=1)


def fetch_best(tm, uid, total=100):
    return fetch_scores(tm, uid, "best", total=total)


def candidates(tm, lo, hi, played, progress=print, stop=None, target=None):
    per_band = -(-(target or C.TARGET_MAPS) // C.BANDS)
    seen, reqs = {}, 0
    step = (hi - lo) / C.BANDS
    for b in range(C.BANDS):
        blo, bhi = round(lo + b * step, 2), round(lo + (b + 1) * step, 2)
        got = {}
        for sort in C.SORTS:
            cursor = None
            for _ in range(C.PAGES_MAX):
                if len(got) >= per_band or (stop and stop.is_set()):
                    break
                params = {"m": 0, "s": "ranked", "sort": sort,
                          "q": f"stars>={blo} stars<={bhi}"}
                if cursor:
                    params["cursor_string"] = cursor
                data = api_get(f"{C.BASE}/beatmapsets/search", tm, params)
                reqs += 1
                if not data:
                    break
                for s in data["beatmapsets"]:
                    for bm in s["beatmaps"]:
                        if (bm["mode"] == "osu" and blo <= bm["difficulty_rating"] <= bhi
                                and bm["id"] not in played):
                            got[bm["id"]] = {
                                "id": bm["id"], "set_id": s["id"],
                                "name": f"{s['artist']} - {s['title']} [{bm['version']}]",
                                "pass": bm.get("passcount", 0), "play": bm.get("playcount", 0),
                                "length": bm.get("total_length", 0), "bpm": bm.get("bpm", 0)}
                cursor = data.get("cursor_string")
                if not cursor:
                    break
            if len(got) >= per_band:
                break
        seen.update(dict(list(got.items())[:per_band]))
        progress(f"Banda {b + 1}/{C.BANDS} ({blo}-{bhi}): {len(got)} mapas | total {len(seen)} | {reqs} peticiones")
    return list(seen.values())
