"""Ajustes de la interfaz Qt que se aplican al arrancar (antes de crear la ventana):
interruptor HR junto a NM / HD / DT y etiquetas de mods con color y tamaño de letra según la combinación."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout
from . import theme as T
from . import widgets as W

MODS = ("NM", "HD", "HR", "DT")

COLORS = {
    "NM": "#4b5563",
    "HD": "#d97706", "HR": "#dc2626", "HDHR": "#c2410c",
    "DT": "#db2777", "DTHD": "#7c3aed", "DTHR": "#be123c", "DTHDHR": "#5b21b6",
}


class ModChips(W.ModChips):
    ORDER = MODS


def make_badge(combo):
    """Columna de color con los mods con los que se debe jugar (la letra se achica si la combinación es larga)."""
    box = QFrame()
    box.setFixedWidth(64)
    box.setStyleSheet(f"background: {COLORS.get(combo, '#4b5563')}; border-radius: 14px;")
    lay = QVBoxLayout(box)
    lay.setAlignment(Qt.AlignCenter)
    lay.setSpacing(4)
    top = QLabel("MODS")
    top.setStyleSheet("font-size: 9px; font-weight: bold; color: #f3f4f6; background: transparent;")
    size = 16 if len(combo) <= 4 else 12
    name = QLabel(combo)
    name.setStyleSheet(f"font-size: {size}px; font-weight: bold; color: white; background: transparent;")
    for lab in (top, name):
        lab.setAlignment(Qt.AlignCenter)
        lay.addWidget(lab)
    return box


def apply():
    T.MOD_COLORS.update(COLORS)
    W.ModChips = ModChips
    W.make_badge = make_badge
    from . import main_window as MW
    MW.MOD_ORDER = MODS
