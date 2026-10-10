import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from osu_rec import config as C
from osu_rec import patterns as P


def get_osu(bid):
    p = C.MAPS_DIR / f"{bid}.osu"
    if not p.exists():
        r = requests.get(f"https://osu.ppy.sh/osu/{bid}", timeout=C.TIMEOUT)
        r.raise_for_status()
        p.write_bytes(r.content)
    return p


def main():
    if len(sys.argv) < 2:
        sys.exit("Uso: python scripts/inspect_map.py ID [ID ...]   (el número de osu.ppy.sh/b/ID)")
    for arg in sys.argv[1:]:
        bid = int(arg)
        p = get_osu(bid)
        bpm, cs = P.main_bpm(p), P.parse_cs(p)
        f = P.features(P.parse_hitobjects(p), bpm, cs)
        print(f"\n=== Mapa {bid} | BPM principal {bpm:.0f} | CS {cs} ===")
        if not f:
            print("No se pudo analizar.")
            continue
        print("Etiquetas:", ", ".join(P.tags(f)))
        print(f"Secciones de jumps: {f['jump_sec']*100:.1f}% de las notas (mínimo {P.JUMP_SEC_MIN*100:.0f}%)")
        print(f"Secciones de finger control: {f['finger_sec']*100:.1f}% (mínimo {P.FINGER_SEC_MIN*100:.0f}%)")
        print(f"Streams: {f['stream']*100:.1f}% | Tech score: {f['tech']:.2f} (mínimo {P.TECH_MIN})")
        print("Tech componentes:", {k: round(v, 2) for k, v in P.tech_breakdown(f).items()})


if __name__ == "__main__":
    main()
