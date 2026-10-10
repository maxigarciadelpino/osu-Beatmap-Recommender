import argparse, json, os, sys
from osu_rec import config as C
from osu_rec.api import TokenManager, get_user, fetch_best, fetch_recent
from osu_rec.patterns import TAG_NAMES
from osu_rec.profile import build_profile, save_profile, load_profile
from osu_rec.recommend import evaluate, format_rec
from osu_rec.session import session_adjust, describe
from osu_rec.storage import Store

STYLES = ["profile", "similar", "any", "speed", "aim", "hybrid"] + list(TAG_NAMES)


def main():
    ap = argparse.ArgumentParser(description="osu! beatmap recommender (consola)")
    ap.add_argument("--user", help="Username (por defecto OSU_USERNAME del credentials.env)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fetch", help="Descarga best/recent scores")
    sub.add_parser("profile", help="Construye el perfil desde tus best scores")
    r = sub.add_parser("recommend", help="Recomienda mapas")
    r.add_argument("goal", choices=["pp", "skillcap"], default="pp", nargs="?")
    r.add_argument("--style", choices=STYLES, default="profile")
    r.add_argument("--mods", default="NM", help="Mods a buscar, separados por coma: NM,HD,DT (por defecto NM)")
    r.add_argument("--sort", choices=["prob", "pp", "balanced", "skill", "stars"], default=None,
                   help="Orden. pp: prob (defecto), pp, balanced. skillcap: skill (defecto), prob, stars")
    r.add_argument("--no-session", action="store_true")
    r.add_argument("--require-refs", action="store_true",
                   help="Oculta mapas sin >=8 scores del mismo mod ni FCs de referencia")
    r.add_argument("--maps", type=int, default=C.TARGET_MAPS, help="Mapas a analizar (por defecto 1000)")
    r.add_argument("--results", type=int, default=10, help="Recomendaciones a mostrar (por defecto 10)")
    r.add_argument("--all", action="store_true", help="Mostrar todas las recomendaciones")
    r.add_argument("--pp-low", type=float, default=0.8, help="(goal pp) mínimo de pp como múltiplo de tu top play")
    r.add_argument("--pp-high", type=float, default=1.3, help="(goal pp) máximo de pp como múltiplo de tu top play")
    a = ap.parse_args()

    if not C.have_credentials():
        sys.exit(f"Faltan credenciales en {C.ENV_FILE} (ver .env.example)")
    tm = TokenManager()
    user = get_user(tm, a.user or os.environ.get("OSU_USERNAME", ""))
    if not user:
        sys.exit("Usuario no encontrado")
    uid = user["id"]

    if a.cmd == "fetch":
        json.dump(fetch_best(tm, uid), open(C.best_file(uid), "w"), indent=2)
        json.dump(fetch_recent(tm, uid), open(C.DATA_DIR / f"recent_scores_{uid}.json", "w"), indent=2)
        print("Listo:", uid)
    elif a.cmd == "profile":
        prof = build_profile(json.load(open(C.best_file(uid))))
        save_profile(prof)
        print(json.dumps(prof, indent=2))
    else:
        prof = load_profile(uid)
        if not prof:
            sys.exit("Falta el perfil: ejecuta 'fetch' y 'profile' primero")
        adj, recent = None, None
        if not a.no_session:
            store = Store()
            sid = store.last_session(uid)
            plays = store.session_plays(sid) if sid else []
            adj = session_adjust(prof, plays) if sid else None
            recent = [p for p in plays if isinstance(p, dict) and p.get("beatmap_id")]
            print("Sesión:", describe(adj))
        sort = a.sort or ("skill" if a.goal == "skillcap" else "prob")
        mods = {m.strip().upper() for m in a.mods.split(",") if m.strip()}
        for c in evaluate(prof, a.goal, tm, adj=adj, style=a.style, require_refs=a.require_refs,
                          max_maps=a.maps, n_results=None if a.all else a.results, sort_by=sort,
                          pp_range=(a.pp_low, a.pp_high), recent=recent, mods=mods):
            print(format_rec(c))


if __name__ == "__main__":
    main()
