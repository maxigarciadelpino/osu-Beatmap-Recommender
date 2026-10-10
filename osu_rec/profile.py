import json, statistics
from collections import defaultdict
from . import config as C
from .maps import prefetch, load_map
from .mods import mods_str, family
from .patterns import FeatureCache, preference, similarity, tags, STYLE_VER
import rosu_pp_py as rosu

MIN_SAMPLES = 5
PROFILE_VER = 4


def analyze(s):
    bm = load_map(s["beatmap_id"])
    if bm is None:
        return None
    mods = mods_str(s)
    d = rosu.Difficulty(mods=mods).calculate(bm)
    ss = rosu.Performance(mods=mods, accuracy=100.0).calculate(bm)
    pp = s.get("pp") or 0
    fam = family(mods)
    return {
        "mods": fam, "pp": pp, "stars": d.stars, "aim": d.aim, "speed": d.speed,
        "speed_ratio": d.speed / d.aim if d.aim else 0,
        "efficiency": pp / ss.pp if ss.pp else 0,
        "bpm": s["beatmap"]["bpm"] * (1.5 if "DT" in fam else 1),
        "length": s["beatmap"]["total_length"], "acc": s["accuracy"], "passed": s["passed"],
    }


def classify(ratio):
    return "speed" if ratio > 1.05 else "aim" if ratio < 0.95 else "hibrido"


def summarize(rows):
    med = statistics.median
    return {
        "n": len(rows),
        "skill": classify(med(r["speed_ratio"] for r in rows)),
        "speed_ratio": round(med(r["speed_ratio"] for r in rows), 3),
        "stars_p50": round(med(r["stars"] for r in rows), 2),
        "stars_max": round(max(r["stars"] for r in rows), 2),
        "pp_p50": round(med(r["pp"] for r in rows), 1),
        "pp_max": round(max(r["pp"] for r in rows), 1),
        "efficiency_p50": round(med(r["efficiency"] for r in rows), 3),
        "bpm_p50": round(med(r["bpm"] for r in rows)),
        "length_p50": round(med(r["length"] for r in rows)),
        "acc_p50": round(med(r["acc"] for r in rows), 4),
    }


def bpm_range(scores):
    vals = []
    for s in scores:
        acr = {m["acronym"] for m in s["mods"]}
        k = 1.5 if acr & {"DT", "NC"} else 0.75 if "HT" in acr else 1.0
        vals.append(s["beatmap"]["bpm"] * k)
    vals.sort()
    n = len(vals)
    return [vals[int(n * 0.10)], vals[int(n * 0.50)], vals[min(n - 1, int(n * 0.90))]]


def style_profile(scores):
    fc = FeatureCache(C.FEATURES_FILE, C.MAPS_DIR)
    vecs, ws, counts = [], [], defaultdict(int)
    for s in scores:
        f = fc.get(s["beatmap_id"], s["beatmap"]["bpm"])
        if not f:
            continue
        vecs.append(f)
        ws.append(((s.get("pp") or 1.0)) ** 2)
        for t in tags(f):
            counts[t] += 1
    fc.save()
    if not vecs:
        return None, {}, 0.5
    pref = preference(vecs, ws)
    sims = sorted(similarity(f, pref) for f in vecs)
    ref = max(sims[len(sims) // 2], 0.2)
    shares = {t: round(c / len(vecs), 3) for t, c in sorted(counts.items(), key=lambda kv: -kv[1])}
    return pref, shares, ref


def build_profile(scores, progress=print):
    prefetch([s["beatmap_id"] for s in scores], progress)
    progress("Calculando perfil de skills...")
    rows = [r for r in (analyze(s) for s in scores) if r]
    by_mod = defaultdict(list)
    for r in rows:
        by_mod[r["mods"]].append(r)
    main = max(by_mod, key=lambda k: len(by_mod[k]))
    progress("Analizando patrones de tus mejores mapas...")
    vec, tag_share, ref = style_profile(scores)
    return {
        "user_id": scores[0]["user_id"],
        "main_mod": main,
        "played_ids": [s["beatmap_id"] for s in scores],
        "bpm_range": bpm_range(scores),
        "style_ver": STYLE_VER,
        "profile_ver": PROFILE_VER,
        "style_vector": vec,
        "style_ref": ref,
        "style_tags": tag_share,
        "overall": summarize(rows),
        "by_mod": {k: summarize(v) | {"low_sample": len(v) < MIN_SAMPLES}
                   for k, v in sorted(by_mod.items(), key=lambda kv: -len(kv[1]))},
    }


def save_profile(prof):
    json.dump(prof, open(C.profile_file(prof["user_id"]), "w"), indent=2)


def load_profile(uid):
    p = C.profile_file(uid)
    if p.exists():
        prof = json.load(open(p))
        if (prof.get("style_ver") == STYLE_VER and prof.get("profile_ver") == PROFILE_VER
                and all(k in prof for k in ("bpm_range", "played_ids", "style_vector", "style_tags"))):
            return prof
    return None
