import json, math, time
from collections import Counter, defaultdict
import rosu_pp_py as rosu
from . import config as C
from .api import api_get, candidates
from .maps import prefetch, load_map
from .mods import mod_set, target_set
from .patterns import FeatureCache, similarity, tags as pattern_tags, TAG_NAMES

STYLE_RANGES = {"speed": (1.05, 99.0), "aim": (0.0, 0.95), "hybrid": (0.95, 1.05)}
TAG_STYLES = set(TAG_NAMES)
STARS_PER_PP_RATIO = 4.0

SKILLCAP_BELOW = 0.5
SKILLCAP_ABOVE = 0.4
SKILLCAP_TARGET_OVER = 0.1
SESSION_WINDOW = 30
MIN_SKILLCAP_AFFINITY = 0.25

DT_RATIO = 1.45
DT_BPM = 1.5
HR_PAD = 0.5
MIN_MOD_SCORES = 5
MOD_ORDER = ("NM", "HD", "HR", "DT")
ADDON_ORDER = ("HD", "HR")

PP_SOFT = 0.08
PP_SEARCH_BELOW = 2.0
PP_SEARCH_ABOVE = 1.2


def norm_mods(s):
    s = (s or "").upper()
    parts = {s[i:i + 2] for i in range(0, len(s), 2)}
    return frozenset({"DT" if p == "NC" else p for p in parts} - {"NM", "CL", ""})


def _addon_variants(addons):
    """Todos los subconjuntos no vacíos de los complementos (HD, HR), de menor a mayor tamaño."""
    out = []
    for mask in range(1, 1 << len(addons)):
        out.append([a for i, a in enumerate(addons) if mask >> i & 1])
    out.sort(key=len)
    return out


def combo_list(selected):
    """Combinaciones de mods a buscar según los interruptores NM / HD / HR / DT.
    HD y HR son complementos: producen variantes (HD, HR, HDHR). Con DT sin NM solo salen combinaciones con DT.
      NM -> NM | HD -> HD | HR -> HR | NM+HD -> NM, HD | NM+HR -> NM, HR | HD+HR -> HD, HR, HDHR
      NM+HD+HR -> NM, HD, HR, HDHR | DT -> DT | DT+HD -> DTHD | DT+HR -> DTHR | DT+HD+HR -> DTHD, DTHR, DTHDHR
      NM+DT -> NM, DT | NM+DT+HD -> NM, HD, DT, DTHD"""
    sel = set(selected or ()) & set(MOD_ORDER) or {"NM"}
    nm, dt = "NM" in sel, "DT" in sel
    variants = _addon_variants([a for a in ADDON_ORDER if a in sel])
    out = []
    if nm:
        out.append("NM")
    if variants and (nm or not dt):
        out += ["".join(v) for v in variants]
    if dt and (nm or not variants):
        out.append("DT")
    if dt and variants:
        out += ["DT" + "".join(v) for v in variants]
    return out


def top_n_mean(scores, n=10):
    """Promedio de pp de tus n mejores scores (lista de scores de la API con la clave 'pp')."""
    pps = sorted((s.get("pp") or 0 for s in scores), reverse=True)[:n]
    pps = [p for p in pps if p > 0]
    return sum(pps) / len(pps) if pps else None


def pp_fit(pp, lo, hi, soft=PP_SOFT):
    """1.0 dentro del rango; baja hasta 0.5 en el borde de la tolerancia blanda; None fuera de ella."""
    if lo <= pp <= hi:
        return 1.0
    d, edge = (lo - pp, lo * soft) if pp < lo else (pp - hi, hi * soft)
    if d > edge:
        return None
    return 1.0 - 0.5 * d / edge


def _leaderboard(tm, bid, extra=None):
    params = {"mode": "osu", "type": "global"}
    if extra:
        params.update(extra)
    data = api_get(f"{C.BASE}/beatmaps/{bid}/scores", tm, params)
    return (data or {}).get("scores", [])


def clear_rate(tm, bid, mods, lb):
    """Devuelve (tasa de <=3 misses, n scores, n FCs, vino_de_cache)."""
    key = f"{bid}:{mods}:{C.MAX_MISSES}:v2"
    now = time.time()
    hit = lb.get(key)
    if hit:
        ttl = C.LB_TTL_KNOWN if hit["cr"] is not None else C.LB_TTL_UNKNOWN
        if now - hit["t"] < ttl:
            return hit["cr"], hit["n"], hit["fc"], True

    want = target_set(mods)
    seen, same = set(), []

    def add(scores):
        for s in scores:
            sid = s.get("id")
            if sid in seen:
                continue
            seen.add(sid)
            if mod_set(s.get("mods", [])) == want:
                same.append(s)

    if C.LB_MODS_FILTER and want:
        add(_leaderboard(tm, bid, {"mods[]": sorted(want)}))
    if len(same) < C.MIN_LB_SAMPLE:
        add(_leaderboard(tm, bid))

    n = len(same)
    if n < C.MIN_LB_SAMPLE:
        lb[key] = {"cr": None, "n": n, "fc": 0, "t": now}
        return None, n, 0, False
    miss = [s.get("statistics", {}).get("miss", 0) for s in same]
    cr = sum(1 for m in miss if m <= C.MAX_MISSES) / n
    fc = sum(1 for m in miss if m == 0)
    lb[key] = {"cr": cr, "n": n, "fc": fc, "t": now}
    return cr, n, fc, False


def bpm_factor(bpm, lo, mid, hi):
    dist = max(lo - bpm, bpm - hi, 0)
    return max(0.4, 1 - dist / (0.25 * mid))


def skill_match(sr, player_ratio, feats, style_vec, style_ref):
    ratio_m = max(0.0, 1 - abs(sr - player_ratio) / 0.4)
    if feats and style_vec:
        rel = min(similarity(feats, style_vec) / max(style_ref, 0.2), 1.0)
    else:
        rel = 0.5
    return 0.5 * ratio_m + 0.5 * rel


def current_skills(prof, m, recent, fcache, progress):
    """Skills que juegas ahora: ratio speed/aim y patrones de tus últimas jugadas aprobadas
    (más peso a las recientes), mezclado con tu perfil si hay pocas jugadas."""
    plays = [s for s in (recent or []) if s.get("passed") and s.get("beatmap_id")][-SESSION_WINDOW:]
    if plays:
        prefetch(list({s["beatmap_id"] for s in plays}), progress)
    ratio_sum = ratio_w = 0.0
    tag_w = defaultdict(float)
    used = 0
    for k, s in enumerate(reversed(plays)):
        wgt = 0.9 ** k
        bid = s["beatmap_id"]
        try:
            bm = load_map(bid)
            if bm is None:
                continue
            pm = "".join(x["acronym"] for x in s.get("mods", []) if x["acronym"] != "CL")
            d = (rosu.Difficulty(mods=pm) if pm else rosu.Difficulty()).calculate(bm)
            if not d.aim:
                continue
            ratio_sum += wgt * d.speed / d.aim
            ratio_w += wgt
            bpm = getattr(bm, "bpm", 0)
            feats = fcache.get(bid, bpm) if bpm else None
            for t in pattern_tags(feats):
                tag_w[t] += wgt
            used += 1
        except Exception:
            continue

    w_s = min(used, 10) / 10 * 0.7
    prof_ratio = m["speed_ratio"]
    ratio = (w_s * ratio_sum / ratio_w + (1 - w_s) * prof_ratio) if ratio_w else prof_ratio
    prof_tags = prof.get("style_tags") or {}
    tot = sum(tag_w.values()) or 1.0
    dist = defaultdict(float)
    for t, v in tag_w.items():
        dist[t] += w_s * v / tot
    for t, v in prof_tags.items():
        dist[t] += (1 - w_s) * v
    top = sorted(dist.items(), key=lambda kv: -kv[1])[:3]
    text = (f"{used} jugadas recientes + perfil" if used else "solo tu perfil (sin jugadas aprobadas en la sesión)")
    text += f" | ratio speed/aim {ratio:.2f} | " + ", ".join(f"{t} {v*100:.0f}%" for t, v in top)
    return {"ratio": ratio, "dist": dict(dist), "used": used, "text": text}


def current_affinity(cur, sr, ptags):
    ratio_m = max(0.0, 1 - abs(sr - cur["ratio"]) / 0.4)
    dist = cur["dist"]
    top = max(dist.values()) if dist else 0
    if top and ptags:
        tag_m = max(dist.get(t, 0.0) for t in ptags) / top
    else:
        tag_m = 0.5
    return 0.5 * ratio_m + 0.5 * tag_m


def success_prob(stars, m, crate, passrate, length_eff, bpm_f, skill=1.0, use_clear=True):
    """Probabilidad estimada de éxito. Con use_clear=False no usa leaderboards: solo tu perfil
    (estrellas vs tu techo, afinidad de skills, BPM, duración y pass rate del mapa)."""
    mid = m["stars_p50"] + 0.5 * (m["stars_max"] - m["stars_p50"])
    p = 1 / (1 + math.exp((stars - mid) / 0.35))
    if use_clear:
        clear_f = 0.8 if crate is None else min(1.0, math.sqrt(crate / 0.6))
    else:
        clear_f = 1.0
    pass_f = 0.7 + 0.3 * min(1.0, passrate / 0.15) if passrate else 0.85
    len_f = max(0.6, 1 - 0.1 * max(0, (length_eff - 180) / 60))
    skill_f = 0.5 + 0.5 * skill
    return p * clear_f * pass_f * len_f * bpm_f * skill_f


def map_url(c):
    if c.get("set_id"):
        return f"https://osu.ppy.sh/beatmapsets/{c['set_id']}#osu/{c['id']}"
    return f"https://osu.ppy.sh/b/{c['id']}"


def _sorter(sort_by):
    if sort_by == "pp":
        return lambda c: (c["pp"], c["p"])
    if sort_by == "balanced":
        return lambda c: (c["pp"] * c["p"], c["p"])
    if sort_by == "skill":
        return lambda c: (c["skill"], c["p"])
    if sort_by == "stars":
        return lambda c: (c["stars"], c["p"])
    return lambda c: (c["p_known"], c["p"], c["pp"])


def star_window(goal, m, pp_low, pp_high):
    if goal == "pp":
        lo = m["stars_p50"] - (0.6 + STARS_PER_PP_RATIO * max(0.9 - pp_low, 0.0))
        hi = m["stars_p50"] + (0.9 + STARS_PER_PP_RATIO * max(pp_high - 1.2, 0.0))
    else:
        lo, hi = m["stars_max"] - SKILLCAP_BELOW, m["stars_max"] + SKILLCAP_ABOVE
    return lo, hi


def build_context(prof, goal, combos, adj, pp_low, pp_high, top_pp, ref_pp=None, pp_target=None):
    """Perfil por combinación de mods (estrellas en la misma escala para todos los mods).
    ref_pp: pp de referencia alternativo a tu top play (p. ej. promedio de tu top 10).
    pp_target=(min, max): rango de pp deseado; ignora estrellas y referencias. Las estrellas solo se usan
    para decidir qué pedir a la API (estimadas a partir del pp objetivo), no para filtrar."""
    main_mod = prof["main_mod"]
    m_main = dict(prof["by_mod"][main_mod])
    main_dt = "DT" in norm_mods(main_mod)
    b_lo, b_mid, b_hi = prof["bpm_range"]
    manual = bool(pp_target)
    ref = ref_pp or top_pp
    star_shift = STARS_PER_PP_RATIO * (ref / top_pp - 1.0) if (ref_pp and not manual) else 0.0
    ctx = {}
    for combo in combos:
        want = norm_mods(combo)
        dt = "DT" in want
        own = [d for k, d in prof["by_mod"].items() if norm_mods(k) == want and d.get("n", 0) >= MIN_MOD_SCORES]
        if own:
            mc, src = dict(max(own, key=lambda d: d["n"])), "perfil"
            pp_ref = (mc.get("pp_max") or top_pp) * ref / top_pp
        else:
            mc, src, pp_ref = dict(m_main), "derivado", ref
        bf = (DT_BPM if dt else 1.0) / (DT_BPM if main_dt else 1.0)
        shift = 0.0
        mc["stars_p50"] += star_shift
        mc["stars_max"] += star_shift
        if adj:
            mc["stars_p50"] += adj["star_shift"]
            mc["stars_max"] += adj["star_shift"]
            mc["acc_p50"] += adj["acc_adj"]
            shift = adj["bpm_shift"]
        if manual:
            t_lo, t_hi = pp_target
            center = mc["stars_max"] + STARS_PER_PP_RATIO * ((t_lo + t_hi) / 2 / top_pp - 1.0)
            lo, hi = center - PP_SEARCH_BELOW, center + PP_SEARCH_ABOVE
            pp_lo, pp_hi = t_lo, t_hi
        else:
            lo, hi = star_window(goal, mc, pp_low, pp_high)
            pp_lo, pp_hi = pp_ref * pp_low, pp_ref * pp_high
        ctx[combo] = {
            "m": mc, "dt": dt, "src": src, "lo": lo, "hi": hi, "pp_lo": pp_lo, "pp_hi": pp_hi,
            "scale": DT_RATIO if dt else 1.0,
            "pad": HR_PAD if "HR" in want else 0.0,
            "bpm": ((b_lo + shift) * bf, (b_mid + shift) * bf, (b_hi + shift) * bf),
            "kw": {} if combo == "NM" else {"mods": combo},
        }
    return m_main, ctx


def evaluate(prof, goal, tm, adj=None, progress=print, stop=None, mods=None,
             style="profile", require_refs=False, max_maps=None, n_results=10,
             sort_by="prob", pp_range=None, recent=None, ref_pp=None, pp_target=None,
             leaderboards=True):
    show_all = n_results is None or int(n_results) <= 0
    n_results = None if show_all else int(n_results)
    max_maps = int(max_maps or C.TARGET_MAPS)
    pp_low, pp_high = pp_range or (C.PP_LOW, C.PP_HIGH)
    played = set(prof["played_ids"])
    misses = adj["misses"] if adj else C.ASSUMED_MISSES
    combos = combo_list(mods)
    top_pp = max(d["pp_max"] for d in prof["by_mod"].values())
    manual = goal == "pp" and bool(pp_target)
    pp_target = tuple(pp_target) if manual else None
    m_main, ctx = build_context(prof, goal, combos, adj, pp_low, pp_high, top_pp,
                                None if manual else ref_pp, pp_target)
    if manual:
        progress(f"Rango de pp manual: {pp_target[0]:.0f}-{pp_target[1]:.0f} pp (tolerancia blanda ±{PP_SOFT*100:.0f}%: "
                 f"acepta {pp_target[0]*(1-PP_SOFT):.0f}-{pp_target[1]*(1+PP_SOFT):.0f}) · las estrellas no filtran")
    elif ref_pp:
        progress(f"Referencia: promedio de tu top 10 = {ref_pp:.0f} pp (tu mejor play: {top_pp:.0f} pp)")

    # La API filtra por estrellas base (sin mods): una ventana con DT se divide por 1.45 y con HR se amplía
    # un margen, porque HR sube el rating respecto al base.
    wins = sorted((x["lo"] / x["scale"] - x["pad"], x["hi"] / x["scale"]) for x in ctx.values())
    merged = []
    for a, b in wins:
        if merged and a <= merged[-1][1] + 0.05:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    per = max(200, max_maps // len(merged))
    desc = " | ".join(f"{c} {x['lo']:.2f}-{x['hi']:.2f}★ ({x['src']})" for c, x in ctx.items())
    extra = " | pp " + " | ".join(f"{c} {x['pp_lo']:.0f}-{x['pp_hi']:.0f}" for c, x in ctx.items()) if goal == "pp" else ""
    label = "Búsqueda en estrellas (solo para traer candidatos)" if manual else "Mods"
    progress(f"{label} {'+'.join(combos)}: {desc}{extra} | hasta {max_maps} mapas")

    cands = {}
    for a, b in merged:
        for c in candidates(tm, round(a, 2), round(b, 2), played, progress, stop, target=per):
            cands.setdefault(c["id"], c)
        if stop and stop.is_set():
            return []
    progress(f"{len(cands)} candidatos únicos")
    prefetch(list(cands), progress)

    fcache = FeatureCache(C.FEATURES_FILE, C.MAPS_DIR)
    cur = None
    if goal == "skillcap":
        cur = current_skills(prof, m_main, recent, fcache, progress)
        progress("Skills actuales: " + cur["text"])
    style_vec = prof.get("style_vector")
    style_ref = prof.get("style_ref", 0.5)

    progress("Estimando pp de cada mapa con tu precisión y misses típicos...")
    pre, skipped = [], 0
    for c in cands.values():
        if stop and stop.is_set():
            return []
        bm = load_map(c["id"])
        if bm is None:
            skipped += 1
            continue
        base_bpm = c.get("bpm") or getattr(bm, "bpm", 0)
        feats = fcache.get(c["id"], base_bpm) if base_bpm else None
        ptags = pattern_tags(feats)
        for combo, x in ctx.items():
            d = rosu.Difficulty(**x["kw"]).calculate(bm)
            if not manual and not (x["lo"] <= d.stars <= x["hi"]):
                continue
            mc = x["m"]
            acc = max(0.90, mc["acc_p50"] - 0.012 * (d.stars - mc["stars_p50"])) * 100
            pp = rosu.Performance(accuracy=acc, misses=misses, **x["kw"]).calculate(bm).pp
            fit = 1.0
            if goal == "pp":
                fit = pp_fit(pp, x["pp_lo"], x["pp_hi"], PP_SOFT if manual else 0.0)
                if fit is None:
                    continue
            sr = d.speed / d.aim if d.aim else 0
            if style in STYLE_RANGES:
                lo_r, hi_r = STYLE_RANGES[style]
                if not (lo_r <= sr < hi_r):
                    continue
            elif style in TAG_STYLES and style not in ptags:
                continue
            bpm_eff = base_bpm * (DT_BPM if x["dt"] else 1.0)
            bf = bpm_factor(bpm_eff, *x["bpm"]) if bpm_eff else 0.8
            skill = skill_match(sr, m_main["speed_ratio"], feats, style_vec, style_ref)
            if goal == "skillcap":
                skill = 0.7 * current_affinity(cur, sr, ptags) + 0.3 * skill
                if skill < MIN_SKILLCAP_AFFINITY:
                    continue
                target = mc["stars_max"] + SKILLCAP_TARGET_OVER
                closeness = max(0.1, 1 - abs(d.stars - target) / (SKILLCAP_BELOW + SKILLCAP_ABOVE))
                score = skill * closeness * bf
            elif manual:
                score = 1000.0 * fit * bf * (0.5 + 0.5 * skill)
            else:
                score = pp * bf * (0.5 + 0.5 * skill)
            pre.append({**c, "stars": d.stars, "pp": pp, "sr": sr, "score": score, "bpm_eff": bpm_eff,
                        "bf": bf, "tags": ptags, "skill": skill, "url": map_url(c), "mods": combo,
                        "pp_fit": fit, "min_sample": C.MIN_LB_SAMPLE})
    fcache.save()
    cnt = Counter(c["mods"] for c in pre)
    progress(f"{len(pre)} mapas dentro del rango y estilo ("
             + ", ".join(f"{k} {v}" for k, v in cnt.items()) + ")" + (f" · {skipped} omitidos" if skipped else ""))

    pre.sort(key=lambda x: -x["score"])
    total = len(pre)
    if leaderboards:
        lb = json.load(open(C.LB_CACHE_FILE)) if C.LB_CACHE_FILE.exists() else {}
        progress(f"Revisando los leaderboards de los {total} mapas filtrados...")
    else:
        lb = {}
        progress(f"Modo rápido: éxito calculado solo con tu perfil, sin consultar leaderboards ({total} mapas)")
    final, fresh, t0 = [], 0, time.time()
    for i, c in enumerate(pre, 1):
        if stop and stop.is_set():
            progress(f"Detenido tras {i - 1}/{total} mapas: se muestran resultados parciales")
            break
        x = ctx[c["mods"]]
        if leaderboards:
            cr, n_lb, n_fc, cached = clear_rate(tm, c["id"], c["mods"], lb)
            fresh += 0 if cached else 1
            if i % 10 == 0 or i == total:
                eta = (time.time() - t0) / i * (total - i)
                progress(f"Leaderboards {i}/{total} | consultas nuevas: {fresh} | "
                         f"válidos: {len(final)} | restante ≈ {int(eta // 60)}m {int(eta % 60)}s")
            if i % 25 == 0:
                json.dump(lb, open(C.LB_CACHE_FILE, "w"))
            if cr is not None and cr < C.MIN_CLEAR_RATE and (goal == "pp" or require_refs):
                continue
            if require_refs and (cr is None or n_fc < C.MIN_FC_REFS):
                continue
        else:
            cr, n_lb, n_fc = None, 0, 0
        passrate = c["pass"] / c["play"] if c["play"] else 0
        length_eff = c["length"] / DT_BPM if x["dt"] else c["length"]
        p = success_prob(c["stars"], x["m"], cr, passrate, length_eff, c["bf"], c["skill"], use_clear=leaderboards)
        c.update(p=p, p_known=(cr is not None) if leaderboards else True, cr=cr, n_lb=n_lb, n_fc=n_fc,
                 length_eff=length_eff)
        final.append(c)
    if leaderboards:
        json.dump(lb, open(C.LB_CACHE_FILE, "w"))
    final.sort(key=_sorter(sort_by), reverse=True)
    return final if show_all else final[:n_results]


def format_rec(c):
    ok = f"{c['p']*100:.0f}%" if c.get("p_known") else "n/d"
    cl = (f"{c['cr']*100:.0f}% FC {c['n_fc']}/{c['n_lb']}" if c["cr"] is not None
          else (f"sin leaderboard" if c["n_lb"] == 0 else f"n/d ({c['n_lb']}/{C.MIN_LB_SAMPLE} scores)"))
    return (f"[{c['mods']}] {c['stars']:.2f}★ {c['pp']:.0f}pp éxito {ok} afinidad {c['skill']*100:.0f}% "
            f"≤{C.MAX_MISSES} miss {cl} BPM {c['bpm_eff']:.0f} ratio {c['sr']:.2f} "
            f"[{', '.join(c['tags'])}] | {c['name']} | {c['url']}")
