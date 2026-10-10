import os, sys
from pathlib import Path
from dotenv import load_dotenv


def resource_path(rel):
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / rel


def _data_dir():
    if getattr(sys, "frozen", False):
        base = Path(os.environ.get("APPDATA", str(Path.home()))) / "osu_rec"
    else:
        base = Path(__file__).resolve().parent.parent / "data"
    base.mkdir(parents=True, exist_ok=True)
    return base


DATA_DIR = _data_dir()
MAPS_DIR = DATA_DIR / "maps"
THUMBS_DIR = DATA_DIR / "thumbs"
MAPS_DIR.mkdir(exist_ok=True)
THUMBS_DIR.mkdir(exist_ok=True)
ENV_FILE = DATA_DIR / "credentials.env"
DB_FILE = DATA_DIR / "osu_history.db"
LB_CACHE_FILE = DATA_DIR / "lb_cache.json"
FEATURES_FILE = DATA_DIR / "features_cache.json"

BASE = "https://osu.ppy.sh/api/v2"
TIMEOUT = 15
API_INTERVAL = 1.0
DL_WORKERS = 5

BANDS = 8
SORTS = ["plays_desc", "favourites_desc"]
PAGES_MAX = 6
TARGET_MAPS = 1000

LB_CHECK = 60
LB_CHECK_REFS = 100
REFS_RESULTS = 15
MIN_LB_SAMPLE = 8
MIN_FC_REFS = 1
LB_MODS_FILTER = True
LB_TTL_KNOWN = 3 * 86400
LB_TTL_UNKNOWN = 6 * 3600

PP_LOW, PP_HIGH = 0.9, 1.2
MAX_MISSES = 3
ASSUMED_MISSES = 2
MIN_CLEAR_RATE = 0.30
FIT_POWER = 2

POLL_INTERVAL = 60
SESSION_MIN_PLAYS = 5
SESSION_DECAY = 0.9
REC_EVERY_PLAYS = 5


def best_file(uid):
    return DATA_DIR / f"best_scores_{uid}.json"


def profile_file(uid):
    return DATA_DIR / f"profile_{uid}.json"


def load_env():
    if ENV_FILE.exists():
        load_dotenv(ENV_FILE, override=True)


def saved_credentials():
    load_env()
    return (os.environ.get("OSU_CLIENT_ID", ""), os.environ.get("OSU_CLIENT_SECRET", ""),
            os.environ.get("OSU_USERNAME", ""))


def have_credentials():
    cid, sec, _ = saved_credentials()
    return bool(cid and sec)


def save_credentials(client_id, client_secret, username, remember=True):
    os.environ["OSU_CLIENT_ID"] = client_id
    os.environ["OSU_CLIENT_SECRET"] = client_secret
    os.environ["OSU_USERNAME"] = username
    if remember:
        ENV_FILE.write_text(
            f"OSU_CLIENT_ID={client_id}\nOSU_CLIENT_SECRET={client_secret}\nOSU_USERNAME={username}\n",
            encoding="utf-8")
    else:
        ENV_FILE.unlink(missing_ok=True)


def clear_credentials():
    ENV_FILE.unlink(missing_ok=True)
    for k in ("OSU_CLIENT_ID", "OSU_CLIENT_SECRET", "OSU_USERNAME"):
        os.environ.pop(k, None)
