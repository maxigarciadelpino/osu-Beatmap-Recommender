GOAL_LABELS = {"PP": "pp", "Skillcap": "skillcap"}

STYLE_LABELS = {
    "Mi perfil": "profile", "Parecidos a mis tops": "similar", "Todos": "any",
    "Speed": "speed", "Aim": "aim", "Híbrido": "hybrid",
    "Streams": "streams", "Jumps": "jumps", "Finger control": "fingercontrol",
    "Stamina": "stamina", "Tech": "tech",
}

SORT_OPTIONS = {"Éxito": "prob", "pp esperados": "pp", "pp × éxito": "balanced"}
SORT_SKILLCAP = {"Afinidad": "skill", "Éxito": "prob", "Dificultad ★": "stars"}

PP_RANGE_OPTIONS = {"0.8× – 1.3× · amplio": (0.8, 1.3),
                    "0.9× – 1.2× · estrecho": (0.9, 1.2),
                    "0.7× – 1.0× · por debajo de tu top": (0.7, 1.0)}

MAPS_OPTIONS = {"250 · rápido": 250, "500": 500, "1000 · equilibrado": 1000,
                "1500": 1500, "2000 · lento": 2000}

SHOW_OPTIONS = [("10", 10), ("20", 20), ("50", 50), ("Todas", None)]
RESULTS_OPTIONS = {"5": 5, "10": 10, "15": 15, "20": 20, "30": 30, "Todas": None}

TAG_LABELS = {"streams": "Streams", "jumps": "Jumps", "stamina": "Stamina", "tech": "Tech",
              "fingercontrol": "Finger control", "mixto": "Mixto"}
TAG_COLORS = {"streams": "#3b82f6", "jumps": "#f59e0b", "stamina": "#ef4444", "tech": "#a855f7",
              "fingercontrol": "#10b981", "mixto": "#6b7280"}


def tag_label(tag):
    return TAG_LABELS.get(tag, tag[:1].upper() + tag[1:])
