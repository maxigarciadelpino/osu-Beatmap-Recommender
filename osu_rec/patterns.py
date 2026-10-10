import json, math
from pathlib import Path

STYLE_VER = 3
TAG_NAMES = ("streams", "jumps", "stamina", "tech", "fingercontrol")

TECH_MIN = 0.60
TECH_MAX_STREAM = 0.50
JUMP_SEC_MIN = 0.30
JUMP_RUN_MIN = 4
FINGER_SEC_MIN = 0.20
FINGER_RUN_MIN = 3

KEYS = ["nps", "stream", "longest", "jump", "finger", "vel", "sharp", "flow", "slider", "rhythm", "burst"]
WEIGHTS = {"nps": 1.0, "stream": 1.5, "longest": 1.2, "jump": 1.5, "finger": 1.3, "vel": 1.2,
           "sharp": 0.8, "flow": 0.8, "slider": 0.8, "rhythm": 0.8, "burst": 0.6}
RHYTHM_BUCKETS = [0.25, 1 / 3, 0.5, 2 / 3, 0.75, 1.0, 1.5, 2.0]
ODD_BUCKETS = (1, 3, 4)


def parse_hitobjects(path):
    objs, on = [], False
    for line in Path(path).read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if line.startswith("["):
            on = line == "[HitObjects]"
            continue
        if not on or not line:
            continue
        p = line.split(",")
        if len(p) < 4:
            continue
        try:
            x, y, t, ty = float(p[0]), float(p[1]), int(p[2]), int(p[3])
        except ValueError:
            continue
        if ty & 8:
            continue
        objs.append((x, y, t, "slider" if ty & 2 else "circle"))
    return objs


def parse_cs(path, default=4.0):
    sec = None
    for line in Path(path).read_text(encoding="utf-8", errors="ignore").splitlines():
        s = line.strip()
        if s.startswith("["):
            sec = s
        elif sec == "[Difficulty]" and s.startswith("CircleSize"):
            try:
                return float(s.split(":", 1)[1])
            except ValueError:
                return default
    return default


def main_bpm(path):
    pts, last, sec = [], 0.0, None
    for line in Path(path).read_text(encoding="utf-8", errors="ignore").splitlines():
        s = line.strip()
        if s.startswith("["):
            sec = s
            continue
        if not s:
            continue
        p = s.split(",")
        try:
            if sec == "[TimingPoints]" and len(p) >= 2:
                t, bl = float(p[0]), float(p[1])
                uninherited = int(p[6]) if len(p) > 6 else 1
                if uninherited == 1 and bl > 0:
                    pts.append((t, bl))
            elif sec == "[HitObjects]" and len(p) >= 3:
                last = max(last, float(p[2]))
        except ValueError:
            continue
    if not pts:
        return 0.0
    pts.sort()
    dur = {}
    for i, (t, bl) in enumerate(pts):
        end = pts[i + 1][0] if i + 1 < len(pts) else max(last, t)
        dur[bl] = dur.get(bl, 0.0) + max(end - t, 0.0)
    bl = max(dur, key=dur.get)
    return 60000.0 / bl


def _angle(a, b, c):
    v1 = (a[0] - b[0], a[1] - b[1])
    v2 = (c[0] - b[0], c[1] - b[1])
    n1, n2 = math.hypot(*v1), math.hypot(*v2)
    if n1 < 1e-6 or n2 < 1e-6:
        return None
    cos = (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)
    return math.degrees(math.acos(max(-1.0, min(1.0, cos))))


def _section_notes(flags, min_run):
    total, run = 0, 0
    for fl in flags + [False]:
        if fl:
            run += 1
        else:
            if run >= min_run:
                total += run + 1
            run = 0
    return total


def tech_breakdown(f):
    var = min(max(f.get("variety", 0) - 3, 0) / 3, 1.0)
    odd = min(f.get("odd", 0.0) / 0.25, 1.0)
    vcv = f.get("vcv", 0.0)
    ang = min(f.get("sharp", 0.0) / 0.35, 1.0)
    score = 0.35 * var + 0.30 * odd + 0.20 * vcv + 0.15 * ang
    return {"variedad_ritmica": var, "ritmos_impares": odd, "irregularidad": vcv,
            "angulos": ang, "score": score}


def features(objs, bpm, cs=4.0):
    n = len(objs)
    if n < 20 or bpm <= 0:
        return None
    beat = 60000.0 / bpm
    q = beat / 4
    diam = max(2 * (54.4 - 4.48 * cs), 30.0)
    dts = [objs[i + 1][2] - objs[i][2] for i in range(n - 1)]
    dist = [math.hypot(objs[i + 1][0] - objs[i][0], objs[i + 1][1] - objs[i][1]) for i in range(n - 1)]

    runs, cur = [], 0
    for d in dts:
        if 0 < d <= q * 1.25:
            cur += 1
        else:
            if cur >= 4:
                runs.append(cur + 1)
            cur = 0
    if cur >= 4:
        runs.append(cur + 1)
    stream_notes, longest = sum(runs), (max(runs) if runs else 0)

    jump_flags = [d >= 1.8 * diam and q * 1.25 < t <= beat * 0.625 for d, t in zip(dist, dts)]
    finger_flags = [0 < t <= q * 1.25 and d >= 1.2 * diam for d, t in zip(dist, dts)]
    jump_sec = _section_notes(jump_flags, JUMP_RUN_MIN) / n
    finger_sec = _section_notes(finger_flags, FINGER_RUN_MIN) / n

    vs = [d / t for d, t in zip(dist, dts) if t > 0]
    vels = sorted(vs)
    p90 = vels[int(len(vels) * 0.9)] if vels else 0.0
    mean_v = sum(vs) / len(vs) if vs else 0.0
    cv = (math.sqrt(sum((v - mean_v) ** 2 for v in vs) / len(vs)) / mean_v) if mean_v > 0 else 0.0

    angs = [a for i in range(1, n - 1) if (a := _angle(objs[i - 1], objs[i], objs[i + 1])) is not None]
    sharp = sum(1 for a in angs if a < 75) / max(len(angs), 1)
    flow = sum(1 for a in angs if a > 135) / max(len(angs), 1)

    counts = [0] * len(RHYTHM_BUCKETS)
    for d in dts:
        if d <= 0:
            continue
        k = min(range(len(RHYTHM_BUCKETS)), key=lambda i: abs(RHYTHM_BUCKETS[i] - d / beat))
        counts[k] += 1
    tot = sum(counts) or 1
    shares = [c / tot for c in counts]
    ent = -sum(s * math.log(s) for s in shares if s > 0) / math.log(len(counts))
    variety = sum(1 for s in shares if s >= 0.04)
    odd = sum(shares[i] for i in ODD_BUCKETS)

    span = max(objs[-1][2] - objs[0][2], 1) / 1000
    win = {}
    for o in objs:
        win[int(o[2] // 10000)] = win.get(int(o[2] // 10000), 0) + 1
    avg_w = sum(win.values()) / len(win)
    burst = (max(win.values()) / avg_w - 1) if avg_w else 0

    f = {
        "nps": min(n / span / 12, 1.0),
        "stream": stream_notes / n,
        "longest": min(longest / 150, 1.0),
        "jump": min(jump_sec / 0.5, 1.0), "jump_sec": jump_sec,
        "finger": min(finger_sec / 0.4, 1.0), "finger_sec": finger_sec,
        "vel": min(p90 / 2.5, 1.0),
        "sharp": sharp, "flow": flow,
        "slider": sum(1 for o in objs if o[3] == "slider") / n,
        "rhythm": ent,
        "burst": min(burst / 2, 1.0),
        "variety": variety, "odd": odd, "vcv": min(cv / 1.5, 1.0),
    }
    f["tech"] = tech_breakdown(f)["score"]
    return f


def tags(f):
    if not f:
        return []
    t = []
    if f["stream"] >= 0.30:
        t.append("streams")
    if f.get("jump_sec", 0.0) >= JUMP_SEC_MIN:
        t.append("jumps")
    if f.get("finger_sec", 0.0) >= FINGER_SEC_MIN:
        t.append("fingercontrol")
    if f["longest"] >= 0.5 or (f["stream"] >= 0.30 and f["burst"] < 0.25):
        t.append("stamina")
    if f.get("tech", 0.0) >= TECH_MIN and f["stream"] < TECH_MAX_STREAM:
        t.append("tech")
    return t or ["mixto"]


def preference(vectors, weights):
    tw = sum(weights) or 1.0
    return {k: sum(v[k] * w for v, w in zip(vectors, weights)) / tw for k in KEYS}


def similarity(f, pref, sigma=0.35):
    d2 = sum(WEIGHTS[k] * (f[k] - pref[k]) ** 2 for k in KEYS) / sum(WEIGHTS.values())
    return math.exp(-d2 / (2 * sigma ** 2))


class FeatureCache:
    def __init__(self, path, maps_dir):
        self.path, self.maps_dir = Path(path), Path(maps_dir)
        self.data = json.load(open(self.path)) if self.path.exists() else {}

    def get(self, bid, bpm):
        key = f"v{STYLE_VER}:{bid}"
        if key not in self.data:
            p = self.maps_dir / f"{bid}.osu"
            if not p.exists():
                return None
            self.data[key] = features(parse_hitobjects(p), bpm, parse_cs(p))
        return self.data[key]

    def save(self):
        json.dump(self.data, open(self.path, "w"))
