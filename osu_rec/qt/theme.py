from pathlib import Path
from PySide6.QtGui import QFont, QFontDatabase
from .. import config as C

BG = "#14141c"
SIDE = "#101017"
CARD = "#1c1c26"
CARD_HOVER = "#212130"
PILL = "#22222e"
PILL_HOVER = "#2b2b39"
BORDER = "#33333f"
BTN = "#2a2a35"
ACCENT = "#ff66aa"
ACCENT_H = "#ff4d9d"
MUTED = "#8a8a98"
TXT = "#f2f2f5"
GOOD = "#4ade80"
BAD = "#f87171"
WARN = "#fbbf24"
SCROLL = "#3a3a48"
OFF_TRACK = "#2f2f3c"
OFF_KNOB = "#8a8a98"

MOD_COLORS = {"NM": "#4b5563", "HD": "#d97706", "DT": "#db2777", "HDDT": "#7c3aed"}

PREFERRED_FONTS = ("Rajdhani", "Exo 2", "Bai Jamjuree", "Segoe UI Variable", "Segoe UI")

QSS = """
* { font-family: "@FONT@"; color: @TXT@; }
QMainWindow, QWidget#root { background: @BG@; }
QLabel { background: transparent; }
QLabel#muted { color: @MUTED@; }
QLabel#h1 { font-size: 26px; font-weight: bold; }
QFrame#sidebar { background: @SIDE@; }
QFrame#card, QFrame#bar { background: @CARD@; border-radius: 16px; }
QFrame#divider { background: @BORDER@; max-height: 1px; min-height: 1px; border: none; }
QFrame#recCard { background: @CARD@; border-radius: 16px; }
QFrame#recCard:hover { background: @CARD_HOVER@; }
QFrame#popupInner { background: @CARD@; border: 1px solid @BORDER@; border-radius: 12px; }

QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget, QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: @SCROLL@; border-radius: 4px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: @ACCENT@; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }

QPushButton { border: none; background: transparent; }
QPushButton#primary { background: @ACCENT@; color: white; border-radius: 12px; font-weight: bold; padding: 0 18px; }
QPushButton#primary:hover { background: @ACCENT_H@; }
QPushButton#primary:disabled { background: #7a3a58; color: #ffe3f0; }
QPushButton#secondary { background: @BTN@; color: white; border-radius: 12px; font-weight: bold; padding: 0 16px; }
QPushButton#secondary:hover { background: @BAD@; }
QPushButton#more { background: @BTN@; color: white; border-radius: 12px; font-weight: bold; }
QPushButton#more:hover { background: @ACCENT_H@; }
QPushButton#ghost { color: @MUTED@; font-size: 12px; padding: 4px 10px; border-radius: 8px; }
QPushButton#ghost:hover { background: @BTN@; }
QPushButton#link { color: @ACCENT@; font-size: 12px; }
QPushButton#nav { text-align: left; padding: 11px 16px; border-radius: 12px; font-weight: bold; font-size: 15px; }
QPushButton#nav:hover, QPushButton#nav:checked { background: @CARD@; }
QPushButton#tab { color: @MUTED@; font-size: 16px; font-weight: bold; padding: 6px 6px 4px 6px;
                  border-bottom: 3px solid transparent; }
QPushButton#tab:checked { color: @ACCENT@; border-bottom: 3px solid @ACCENT@; }
QPushButton#pill { background: @PILL@; border: 1px solid @BORDER@; border-radius: 17px; padding: 0 16px;
                   min-height: 34px; font-size: 12px; font-weight: bold; }
QPushButton#pill:hover { background: @PILL_HOVER@; }
QPushButton#pill[active="true"] { border: 1px solid @ACCENT@; }
QPushButton#chip { border: 1px solid @BORDER@; border-radius: 15px; color: @MUTED@; padding: 0 14px;
                   min-height: 30px; font-size: 12px; font-weight: bold; }
QPushButton#chip:hover { background: @PILL_HOVER@; }
QPushButton#chip:checked { background: @PILL@; border: 1px solid @ACCENT@; color: @TXT@; }
QPushButton#popupRow { text-align: left; padding: 7px 14px; border-radius: 8px; font-size: 13px; }
QPushButton#popupRow:hover { background: @PILL_HOVER@; }
QPushButton#popupRow[current="true"] { color: @ACCENT@; font-weight: bold; }
QPushButton#direct { background: @CARD@; border-radius: 14px; font-weight: bold; font-size: 12px; }
QPushButton#direct:hover { background: @ACCENT@; color: white; }
QPushButton#avatar { border-radius: 48px; }
QPushButton#avatar:hover { background: @CARD@; }

QLineEdit { background: @PILL@; border: 1px solid @BORDER@; border-radius: 10px; padding: 6px 10px;
            selection-background-color: @ACCENT@; }
QLineEdit#login { background: @CARD@; border: 1px solid #2c2c38; padding: 0 12px; min-height: 44px; }
QCheckBox { spacing: 8px; font-size: 13px; }
QCheckBox::indicator { width: 16px; height: 16px; border-radius: 5px; border: 2px solid @BORDER@; }
QCheckBox::indicator:checked { background: @ACCENT@; border: 2px solid @ACCENT@; }
QProgressBar { background: transparent; border: none; min-height: 4px; max-height: 4px; }
QProgressBar::chunk { background: @ACCENT@; border-radius: 2px; }

QTableWidget { background: @CARD@; border: none; border-radius: 12px; gridline-color: transparent;
               alternate-background-color: #20202b; selection-background-color: @PILL_HOVER@; outline: 0; }
QTableWidget::item { padding: 6px; }
QHeaderView::section { background: @CARD@; color: @MUTED@; border: none; padding: 8px; font-weight: bold; }
QTableCornerButton::section { background: @CARD@; border: none; }

QMenu { background: @CARD@; border: 1px solid @BORDER@; padding: 6px; }
QMenu::item { padding: 8px 22px; border-radius: 6px; }
QMenu::item:selected { background: @ACCENT@; color: white; }
QMenu::item:disabled { color: @MUTED@; }
QMenu::separator { height: 1px; background: @BORDER@; margin: 4px 8px; }
"""


def setup_fonts(app):
    """Registra fuentes de assets/ (si hay) y elige la familia; devuelve su nombre."""
    root = Path(C.resource_path("assets"))
    if root.exists():
        for p in sorted(root.rglob("*")):
            if p.suffix.lower() in (".ttf", ".otf"):
                QFontDatabase.addApplicationFont(str(p))
    families = set(QFontDatabase.families())
    fam = next((f for f in PREFERRED_FONTS if f in families), None) or app.font().family()
    app.setFont(QFont(fam, 10))
    return fam


def stylesheet(font_family):
    values = {"FONT": font_family, "BG": BG, "SIDE": SIDE, "CARD": CARD, "CARD_HOVER": CARD_HOVER, "PILL": PILL,
              "PILL_HOVER": PILL_HOVER, "BORDER": BORDER, "BTN": BTN, "ACCENT": ACCENT, "ACCENT_H": ACCENT_H,
              "MUTED": MUTED, "TXT": TXT, "BAD": BAD, "SCROLL": SCROLL}
    out = QSS
    for k, v in values.items():
        out = out.replace(f"@{k}@", v)
    return out
