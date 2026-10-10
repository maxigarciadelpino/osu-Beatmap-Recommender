"""Desglose del perfil: agrupa tus mejores plays por combinación de mods y por tipo (Aim / Mixto / Speed)."""
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

import rosu_pp_py as rosu

from . import config as C
from .maps import prefetch, load_map
from .patterns import FeatureCache, tags as pattern_tags

AIM_MAX = 0.95
SPEED_MIN = 1.05
CATS = (("aim", "Aim"), ("mixto", "Mixto"), ("speed", "Speed"))
CAT_LABELS = dict(CATS, sin="Sin datos")
CAT_NOTE = (f"Tipo: Aim si speed/aim < {AIM_MAX} · Mixto entre {AIM_MAX} y {SPEED_MIN} · Speed si ≥ {SPEED_MIN} "
            "(con los mods de cada play). Patrón: el más frecuente en esas plays; «Variado» = sin patrón dominante.")
TAG_LABELS = {"streams": "Streams", "jumps": "Jumps", "stamina": "Stamina", "tech": "Tech",
              "fingercontrol": "Finger control", "mixto": "Variado"}


def mods_label(acronyms):
    """['NC','HD','CL'] -> 'DTHD'. Sin mods: 'NM'. DT va primero; luego HD, HR y el resto."""
    mods = {"DT" if a == "NC" else a for a in acronyms if a not in ("CL", "NM")}
    if not mods:
        return "NM"
    order = [m for m in ("HD", "HR") if m in mods]
    rest = sorted(mods - {"DT", "HD", "HR"})
    return ("DT" if "DT" in mods else "") + "".join(order) + "".join(rest)


def category(sr):
    if sr is None:
        return "sin"
    if sr < AIM_MAX:
        return "aim"
    return "speed" if sr >= SPEED_MIN else "mixto"


def _acronyms(score):
    return [m["acronym"] if isinstance(m, dict) else str(m) for m in score.get("mods", [])]


def _record(score, fcache):
    acr = _acronyms(score)
    rec = {"id": score["id"], "mod": mods_label(acr), "pp": score.get("pp"), "acc": score.get("accuracy"),
           "sr": None, "stars": None, "tags": []}
    try:
        bm = load_map(score["beatmap_id"])
        if bm is not None:
            pm = "".join(a for a in acr if a != "CL")
            d = (rosu.Difficulty(mods=pm) if pm else rosu.Difficulty()).calculate(bm)
            rec["stars"] = d.stars
            rec["sr"] = d.speed / d.aim if d.aim else None
            bpm = (score.get("beatmap") or {}).get("bpm") or getattr(bm, "bpm", 0)
            if bpm:
                rec["tags"] = list(pattern_tags(fcache.get(score["beatmap_id"], bpm)))
    except Exception:
        pass
    rec["cat"] = category(rec["sr"])
    return rec


def _med(values):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def _main_pattern(items):
    tags = Counter(t for r in items for t in r["tags"])
    if not tags:
        return "—"
    top = tags.most_common(1)[0][0]
    return TAG_LABELS.get(top, top.capitalize())


def _row(mod, label, items, total, is_total):
    stars = [r["stars"] for r in items if r["stars"] is not None]
    pps = [r["pp"] for r in items if r["pp"] is not None]
    return {"mod": mod, "cat": label, "n": len(items), "share": len(items) / total if total else 0.0,
            "stars_p50": _med(stars), "stars_max": max(stars) if stars else None,
            "pp_p50": _med(pps), "pp_max": max(pps) if pps else None,
            "acc_p50": _med([r["acc"] for r in items]), "tags": _main_pattern(items), "total": is_total}


def _main_category(items):
    """Tipo más frecuente de la combinación (ignora «sin datos» salvo que no haya otro)."""
    cnt = Counter(r["cat"] for r in items if r["cat"] != "sin") or Counter(r["cat"] for r in items)
    return CAT_LABELS[cnt.most_common(1)[0][0]]


def summarize(records):
    """Por cada combinación de mods: una fila resumen (con su tipo principal) y una fila por tipo."""
    groups = defaultdict(list)
    for r in records:
        groups[r["mod"]].append(r)
    rows = []
    for mod, items in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        rows.append(_row(mod, _main_category(items), items, len(items), True))
        for key, label in CATS + (("sin", "Sin datos"),):
            sub = [r for r in items if r["cat"] == key]
            if sub:
                rows.append(_row(mod, label, sub, len(items), False))
    return rows


def analyze(scores, cache_file, progress=print):
    """Devuelve (filas, nº de plays). Guarda en caché lo ya calculado para no repetirlo en cada apertura."""
    cache_file = Path(cache_file)
    try:
        cache = json.loads(cache_file.read_text(encoding="utf-8"))
    except Exception:
        cache = {}
    todo = [s for s in scores if str(s["id"]) not in cache]
    if todo:
        progress(f"Analizando {len(todo)} plays de tu perfil (tipo y patrones)...")
        prefetch(list({s["beatmap_id"] for s in todo}), progress)
        fcache = FeatureCache(C.FEATURES_FILE, C.MAPS_DIR)
        for i, s in enumerate(todo, 1):
            cache[str(s["id"])] = _record(s, fcache)
            if i % 10 == 0:
                progress(f"Analizando plays del perfil {i}/{len(todo)}")
        try:
            fcache.save()
            cache_file.write_text(json.dumps(cache), encoding="utf-8")
        except Exception:
            pass
    records = [cache[str(s["id"])] for s in scores if str(s["id"]) in cache]
    return summarize(records), len(records)
