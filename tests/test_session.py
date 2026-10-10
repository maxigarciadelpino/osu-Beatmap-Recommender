import sys, types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if "dotenv" not in sys.modules:
    try:
        import dotenv  # noqa: F401
    except ImportError:
        stub = types.ModuleType("dotenv")
        stub.load_dotenv = lambda *a, **k: None
        sys.modules["dotenv"] = stub
from osu_rec.session import session_adjust, basic_stats

PROF = {"main_mod": "HDDT", "bpm_range": [255, 270, 285],
        "by_mod": {"HDDT": {"acc_p50": 0.98, "stars_p50": 8.9, "stars_max": 10.0}}}


def play(i, acc, passed=True, misses=0):
    return {"ended_at": f"2026-10-09T01:{i:02d}:00Z", "mods": "HDNC", "accuracy": acc,
            "passed": passed, "misses": misses, "bpm": 180}


def test_good_session_positive():
    adj = session_adjust(PROF, [play(i, 0.99) for i in range(12)])
    assert adj and adj["star_shift"] > 0


def test_bad_session_negative():
    plays = [play(i, 0.93, passed=(i % 2 == 0), misses=6) for i in range(12)]
    adj = session_adjust(PROF, plays)
    assert adj and adj["star_shift"] < 0


def test_short_session_none():
    assert session_adjust(PROF, [play(i, 0.99) for i in range(3)]) is None


def test_basic_stats():
    st = basic_stats([play(0, 0.98), play(5, 0.9, passed=False)])
    assert st["n"] == 2 and abs(st["fail"] - 0.5) < 1e-9 and st["minutes"] == 5


if __name__ == "__main__":
    test_good_session_positive(); test_bad_session_negative()
    test_short_session_none(); test_basic_stats()
    print("OK session")
