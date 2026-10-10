from datetime import datetime
from . import config as C
from .mods import target_set, stored_set


def _t(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _wmean(vals, ws):
    tw = sum(ws)
    return sum(v * w for v, w in zip(vals, ws)) / tw if tw else 0.0


def session_adjust(prof, plays):
    mods = prof["main_mod"]
    m = prof["by_mod"][mods]
    want = target_set(mods)
    sel = [p for p in plays if stored_set(p["mods"]) == want]
    n = len(sel)
    if n < C.SESSION_MIN_PLAYS:
        return None
    ws = [C.SESSION_DECAY ** (n - 1 - k) for k in range(n)]
    passes = [(p, w) for p, w in zip(sel, ws) if p["passed"]]
    fail_rate = sum(w for p, w in zip(sel, ws) if not p["passed"]) / sum(ws)
    minutes = (_t(sel[-1]["ended_at"]) - _t(sel[0]["ended_at"])).total_seconds() / 60

    acc_delta = miss_mean = 0.0
    if passes:
        pw = [w for _, w in passes]
        acc_delta = _wmean([p["accuracy"] for p, _ in passes], pw) - m["acc_p50"]
        miss_mean = _wmean([p["misses"] or 0 for p, _ in passes], pw)

    shrink = n / (n + 8)
    shift = max(-0.5, min(0.4, acc_delta * 25 - 0.6 * max(0, fail_rate - 0.35)))
    shift -= 0.15 * min(max(0, (minutes - 90) / 60), 2)
    shift *= shrink

    good = [(p, w) for p, w in passes if p["bpm"] and p["accuracy"] >= m["acc_p50"] - 0.01]
    bpm_shift = 0.0
    if len(good) >= 3:
        k = 1.5 if ("DT" in mods or "NC" in mods) else 1.0
        mean_bpm = _wmean([p["bpm"] * k for p, _ in good], [w for _, w in good])
        bpm_shift = max(-25, min(25, shrink * (mean_bpm - prof["bpm_range"][1])))

    return {
        "n": n, "minutes": minutes, "fail_rate": fail_rate, "acc_delta": acc_delta,
        "star_shift": shift,
        "acc_adj": shrink * max(-0.03, min(0.02, acc_delta)),
        "misses": int(round(max(0, min(4, shrink * miss_mean + (1 - shrink) * C.ASSUMED_MISSES)))),
        "bpm_shift": bpm_shift,
    }


def describe(adj):
    if not adj:
        return "Sin jugadas suficientes en esta sesión: se usa tu perfil histórico."
    return (f"Ajuste activo: {adj['star_shift']:+.2f}★ | acc {adj['acc_delta']*100:+.2f}% | "
            f"misses supuestos {adj['misses']} | BPM {adj['bpm_shift']:+.0f}")


def basic_stats(plays):
    n = len(plays)
    if not n:
        return {"n": 0, "acc": None, "fail": None, "minutes": 0.0}
    passes = [p for p in plays if p["passed"]]
    acc = sum(p["accuracy"] for p in passes) / len(passes) if passes else None
    minutes = (_t(plays[-1]["ended_at"]) - _t(plays[0]["ended_at"])).total_seconds() / 60
    return {"n": n, "acc": acc, "fail": 1 - len(passes) / n, "minutes": minutes}
