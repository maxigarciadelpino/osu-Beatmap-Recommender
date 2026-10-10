import time
from concurrent.futures import ThreadPoolExecutor
import requests
import rosu_pp_py as rosu
from . import config as C


def download(bid, tries=3):
    p = C.MAPS_DIR / f"{bid}.osu"
    if p.exists():
        return True
    for i in range(tries):
        try:
            r = requests.get(f"https://osu.ppy.sh/osu/{bid}", timeout=C.TIMEOUT)
            if r.status_code == 200 and r.content.startswith(b"osu file format"):
                p.write_bytes(r.content)
                time.sleep(0.3)
                return True
            time.sleep(2)
        except requests.exceptions.RequestException:
            time.sleep(2 * (i + 1))
    return False


def prefetch(ids, progress=print):
    todo = [i for i in ids if not (C.MAPS_DIR / f"{i}.osu").exists()]
    progress(f"Descargando {len(todo)} mapas nuevos ({len(ids) - len(todo)} en caché)...")
    if todo:
        with ThreadPoolExecutor(C.DL_WORKERS) as ex:
            list(ex.map(download, todo))


def load_map(bid):
    p = C.MAPS_DIR / f"{bid}.osu"
    if not p.exists():
        return None
    try:
        return rosu.Beatmap(path=str(p))
    except Exception:
        p.unlink(missing_ok=True)
        return None
