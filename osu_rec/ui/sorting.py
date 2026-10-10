_KEYS = {
    "pp": lambda c: (c["pp"], c["p"]),
    "balanced": lambda c: (c["pp"] * c["p"], c["p"]),
    "skill": lambda c: (c["skill"], c["p"]),
    "stars": lambda c: (c["stars"], c["p"]),
}


def sort_recs(recs, sort_by):
    key = _KEYS.get(sort_by, lambda c: (c.get("p_known", False), c["p"], c["pp"]))
    return sorted(recs, key=key, reverse=True)
