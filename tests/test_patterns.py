import math, random, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from osu_rec.patterns import (parse_hitobjects, features, tags, preference, similarity,
                              main_bpm, parse_cs)

BPM = 180
BEAT = 60000 / BPM


def write_map(path, objs, bpm=BPM, cs=4):
    lines = ["osu file format v14", "", "[Difficulty]", f"CircleSize:{cs}", "", "[TimingPoints]",
             f"0,{60000 / bpm},4,2,0,100,1,0", "", "[HitObjects]"]
    lines += [f"{int(x)},{int(y)},{int(t)},1,0,0:0:0:0:" for x, y, t in objs]
    Path(path).write_text("\n".join(lines))


def clamp(x, y):
    return min(500, max(10, x)), min(370, max(10, y))


def make(kind):
    random.seed(1)
    t, x, y, objs = 0.0, 256.0, 192.0, []
    if kind == "stream":
        for i in range(400):
            a = random.uniform(0, 2 * math.pi)
            x, y = clamp(x + 25 * math.cos(a), y + 25 * math.sin(a))
            objs.append((x, y, t))
            t += BEAT / 4 if i % 100 != 99 else BEAT * 2
    elif kind == "few_jumps":
        sections = [(60, 66), (180, 186), (300, 306)]
        for i in range(400):
            in_jump = any(a <= i < b for a, b in sections)
            if in_jump:
                x, y = (60, 100) if i % 2 == 0 else (450, 300)
                objs.append((x, y, t))
                t += BEAT / 2
            else:
                a = random.uniform(0, 2 * math.pi)
                x, y = clamp(x + 25 * math.cos(a), y + 25 * math.sin(a))
                objs.append((x, y, t))
                t += BEAT / 4
    elif kind == "jump":
        for i in range(300):
            objs.append((80 if i % 2 == 0 else 430, 100 + (i * 37) % 200, t))
            t += BEAT / 2
    elif kind == "finger":
        for g in range(100):
            for k in range(4):
                a = random.uniform(0, 2 * math.pi)
                step = 160 if k == 0 else 110
                x, y = clamp(x + step * math.cos(a), y + step * math.sin(a))
                objs.append((x, y, t))
                t += BEAT / 4 if k < 3 else BEAT / 2
    elif kind == "normal":
        for i in range(300):
            a = random.uniform(0, 2 * math.pi)
            r = random.choice([60, 90, 120, 150])
            x, y = clamp(x + r * math.cos(a), y + r * math.sin(a))
            objs.append((x, y, t))
            t += BEAT * random.choice([0.25, 0.25, 0.5, 0.5, 0.5, 1.0])
    else:
        for i in range(300):
            objs.append((256 + random.uniform(-150, 150), 192 + random.uniform(-120, 120), t))
            t += BEAT * random.choice([0.25, 1 / 3, 0.5, 2 / 3, 1.0, 0.75])
    return objs


def feats(kind):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / f"{kind}.osu"
        write_map(p, make(kind))
        return features(parse_hitobjects(p), BPM, parse_cs(p))


def test_basic_tags():
    assert "streams" in tags(feats("stream"))
    assert tags(feats("jump")) == ["jumps"]
    assert "tech" in tags(feats("tech"))


def test_few_jump_sections_do_not_count():
    f = feats("few_jumps")
    assert f["jump_sec"] < 0.10
    assert "jumps" not in tags(f)
    assert "streams" in tags(f)


def test_finger_control():
    t = tags(feats("finger"))
    assert "fingercontrol" in t and "jumps" not in t


def test_tech_is_strict():
    for kind in ("stream", "jump", "normal", "finger", "few_jumps"):
        assert "tech" not in tags(feats(kind)), kind


def test_similarity_orders_maps():
    fs = {k: feats(k) for k in ("stream", "jump", "tech")}
    pref = preference([fs["stream"]], [1.0])
    assert similarity(fs["stream"], pref) > similarity(fs["tech"], pref) > 0
    assert similarity(fs["stream"], pref) > similarity(fs["jump"], pref)


def test_main_bpm_and_cs():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "m.osu"
        write_map(p, make("jump"), bpm=200, cs=5)
        assert abs(main_bpm(p) - 200) < 0.5 and parse_cs(p) == 5.0


if __name__ == "__main__":
    test_basic_tags(); test_few_jump_sections_do_not_count(); test_finger_control()
    test_tech_is_strict(); test_similarity_orders_maps(); test_main_bpm_and_cs()
    for k in ("stream", "few_jumps", "jump", "finger", "normal", "tech"):
        f = feats(k)
        print(f"{k:10s} jump_sec={f['jump_sec']:.2f} finger_sec={f['finger_sec']:.2f} -> {tags(f)}")
    print("OK patterns")
