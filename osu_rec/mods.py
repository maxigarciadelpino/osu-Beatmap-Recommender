ORDER = ["EZ", "HD", "HT", "DT", "NC", "HR", "FL"]
IGNORE = {"CL"}


def mods_str(score):
    ms = {m["acronym"] for m in score["mods"]} - IGNORE
    return "".join(sorted(ms, key=lambda x: ORDER.index(x) if x in ORDER else 99))


def family(mods):
    return mods.replace("NC", "DT") or "NM"


def chunks(mods):
    return {mods[i:i + 2] for i in range(0, len(mods), 2)}


def target_set(mods):
    return {"DT" if a == "NC" else a for a in chunks(mods)} - {"HD", "NM"}


def mod_set(score_mods):
    acr = {m["acronym"] if isinstance(m, dict) else m for m in score_mods}
    return {"DT" if a == "NC" else a for a in acr} - {"CL", "HD"}


def stored_set(mods_text):
    return {"DT" if a == "NC" else a for a in chunks(mods_text or "")} - {"CL", "HD"}
