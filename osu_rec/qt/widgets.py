import os
import sys
import time
from PySide6.QtCore import Qt, Signal, QRectF, QPoint, QUrl
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPixmap, QDesktopServices
from PySide6.QtWidgets import (QAbstractButton, QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton,
                               QSizePolicy, QVBoxLayout, QWidget)
from . import theme as T
from ..ui.options import TAG_COLORS, tag_label


def repolish(w):
    w.style().unpolish(w)
    w.style().polish(w)


def rounded_pixmap(src, size, radius):
    """Recorta el centro de `src` a un cuadrado de `size` con esquinas redondeadas."""
    out = QPixmap(size, size)
    out.fill(Qt.transparent)
    if src is None or src.isNull():
        return out
    scaled = src.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), radius, radius)
    p.setClipPath(path)
    p.drawPixmap((size - scaled.width()) // 2, (size - scaled.height()) // 2, scaled)
    p.end()
    return out


def placeholder_pixmap(size, radius, color="#2a2a38"):
    out = QPixmap(size, size)
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    p.drawRoundedRect(QRectF(0, 0, size, size), radius, radius)
    p.end()
    return out


class Tabs(QWidget):
    """Pestañas de texto con línea de acento bajo la activa."""
    changed = Signal(str)

    def __init__(self, values):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(22)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.btns = {}
        for v in values:
            b = QPushButton(v)
            b.setObjectName("tab")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            self.group.addButton(b)
            lay.addWidget(b)
            b.clicked.connect(lambda _checked=False, x=v: self._clicked(x))
            self.btns[v] = b
        self.value = list(values)[0]
        self.btns[self.value].setChecked(True)

    def _clicked(self, v):
        if v != self.value:
            self.value = v
            self.changed.emit(v)

    def get(self):
        return self.value


class PopupList(QFrame):
    """Lista emergente propia: fondo del programa, filas planas con hover y la opción actual en rosa."""
    picked = Signal(str)
    closed = Signal()

    def __init__(self, options, current, min_width=190):
        super().__init__(None, Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        inner = QFrame()
        inner.setObjectName("popupInner")
        outer.addWidget(inner)
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(2)
        for opt in options:
            b = QPushButton(("●  " if opt == current else "     ") + opt)
            b.setObjectName("popupRow")
            b.setProperty("current", opt == current)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _checked=False, o=opt: self._pick(o))
            lay.addWidget(b)
        self.setMinimumWidth(min_width)

    def _pick(self, opt):
        self.picked.emit(opt)
        self.close()

    def hideEvent(self, e):
        self.closed.emit()
        super().hideEvent(e)

    def show_below(self, anchor):
        self.setMinimumWidth(max(self.minimumWidth(), anchor.width()))
        self.adjustSize()
        pos = anchor.mapToGlobal(QPoint(0, anchor.height() + 6))
        screen = anchor.screen().availableGeometry() if anchor.screen() else None
        if screen is not None:
            if pos.y() + self.height() > screen.bottom():
                pos = anchor.mapToGlobal(QPoint(0, -self.height() - 6))
            pos.setX(max(screen.left(), min(pos.x(), screen.right() - self.width())))
        self.move(pos)
        self.show()


class Pill(QPushButton):
    """Filtro plano tipo etiqueta; al hacer clic abre una lista emergente. Borde rosado si no es el valor por defecto."""
    changed = Signal(str)

    def __init__(self, label, options, default):
        super().__init__()
        self.setObjectName("pill")
        self.setCursor(Qt.PointingHandCursor)
        self.label, self.opts, self.default, self.value = label, list(options), default, default
        self._closed_at = 0.0
        self.clicked.connect(self._open)
        self._refresh()

    def _refresh(self):
        self.setText(f"{self.label}:  {self.value}  ▾" if self.label else f"{self.value}  ▾")
        self.setProperty("active", self.value != self.default)
        repolish(self)

    def get(self):
        return self.value

    def set(self, v):
        self.value = v
        self._refresh()

    def set_options(self, options, default):
        self.opts, self.default = list(options), default
        self.set(default)

    def _mark_closed(self):
        self._closed_at = time.time()

    def _open(self):
        if time.time() - self._closed_at < 0.25:
            return
        pop = PopupList(self.opts, self.value)
        pop.picked.connect(self._picked)
        pop.closed.connect(self._mark_closed)
        self._popup = pop
        pop.show_below(self)

    def _picked(self, v):
        changed = v != self.value
        self.set(v)
        if changed:
            self.changed.emit(v)


class ChipGroup(QWidget):
    """Botones pequeños exclusivos con borde rosado en el activo."""
    changed = Signal(object)

    def __init__(self, options, default):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.btns = {}
        for label, val in options:
            b = QPushButton(label)
            b.setObjectName("chip")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            self.group.addButton(b)
            lay.addWidget(b)
            b.clicked.connect(lambda _checked=False, v=val: self._clicked(v))
            self.btns[val] = b
        self.value = default
        self.btns[default].setChecked(True)

    def _clicked(self, v):
        if v != self.value:
            self.value = v
            self.changed.emit(v)

    def get(self):
        return self.value


class ModChips(QWidget):
    """Interruptores NM / HD / DT (multi-selección, siempre al menos uno activo)."""
    changed = Signal(object)
    ORDER = ("NM", "HD", "DT")

    def __init__(self, default=("NM",)):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.btns = {}
        for v in self.ORDER:
            b = QPushButton(v)
            b.setObjectName("chip")
            b.setCheckable(True)
            b.setChecked(v in default)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _checked=False, x=v: self._toggled(x))
            lay.addWidget(b)
            self.btns[v] = b

    def _toggled(self, v):
        if not self.get():
            self.btns[v].setChecked(True)
            return
        self.changed.emit(self.get())

    def get(self):
        return {v for v, b in self.btns.items() if b.isChecked()}


class Switch(QAbstractButton):
    """Interruptor: riel oscuro con perilla gris apagado; riel rosa con perilla blanca encendido."""

    def __init__(self):
        super().__init__()
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(46, 26)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        on = self.isChecked()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(T.ACCENT if on else T.OFF_TRACK))
        p.drawRoundedRect(QRectF(1, 1, 44, 24), 12, 12)
        p.setBrush(QColor("white" if on else T.OFF_KNOB))
        x = 25 if on else 5
        p.drawEllipse(QRectF(x, 5, 16, 16))


class Toggle(QWidget):
    """Fila de ajuste: título y descripción a la izquierda, interruptor a la derecha."""
    changed = Signal()

    def __init__(self, title, desc, default=False):
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        text = QVBoxLayout()
        text.setSpacing(1)
        t = QLabel(title)
        t.setStyleSheet("font-weight: bold; font-size: 13px;")
        d = QLabel(desc)
        d.setObjectName("muted")
        d.setStyleSheet("font-size: 11px;")
        d.setWordWrap(True)
        text.addWidget(t)
        text.addWidget(d)
        row.addLayout(text, 1)
        self.switch = Switch()
        self.switch.setChecked(default)
        self.switch.toggled.connect(lambda _on: self.changed.emit())
        row.addWidget(self.switch, 0, Qt.AlignVCenter)

    def get(self):
        return int(self.switch.isChecked())

    def select(self):
        self.switch.setChecked(True)

    def deselect(self):
        self.switch.setChecked(False)


class StatCard(QFrame):
    def __init__(self, title):
        super().__init__()
        self.setObjectName("card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(4)
        self.title = QLabel(title)
        self.title.setObjectName("muted")
        self.title.setStyleSheet("font-size: 12px;")
        self.value = QLabel("—")
        self.value.setStyleSheet("font-size: 22px; font-weight: bold;")
        lay.addWidget(self.title)
        lay.addWidget(self.value)

    def set(self, text, color=None):
        self.value.setText(str(text))
        self.value.setStyleSheet(f"font-size: 22px; font-weight: bold; color: {color or T.TXT};")


def cards_row(items):
    """items: [(clave, título)] -> (widget con la fila, {clave: StatCard})"""
    box = QWidget()
    lay = QHBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(12)
    cards = {}
    for key, title in items:
        c = StatCard(title)
        lay.addWidget(c, 1)
        cards[key] = c
    return box, cards


def direct_url(beatmap_id):
    return f"osu://b/{beatmap_id}"


def open_direct(beatmap_id):
    """Abre el mapa en osu! (osu!direct / navegador de mapas de lazer). False si falla."""
    url = direct_url(beatmap_id)
    try:
        if sys.platform.startswith("win"):
            os.startfile(url)
            return True
    except Exception:
        pass
    return bool(QDesktopServices.openUrl(QUrl(url)))


def _tag_pill(tag):
    lab = QLabel(tag_label(tag))
    color = TAG_COLORS.get(tag, "#6b7280")
    lab.setStyleSheet(f"background: {color}; color: white; border-radius: 6px; padding: 4px 14px; "
                      "font-size: 11px; font-weight: bold;")
    return lab


def _fmt_len(seconds):
    s = int(seconds or 0)
    return f"{s // 60}:{s % 60:02d}"


def _success_color(p):
    return T.GOOD if p >= 0.45 else (T.WARN if p >= 0.25 else T.BAD)


class RecCard(QFrame):
    """Tarjeta de recomendación; un clic en cualquier parte abre la web del mapa."""
    clicked = Signal()
    THUMB = 84

    def __init__(self, rec, thumb=None):
        super().__init__()
        self.rec = rec
        self.setObjectName("recCard")
        self.setCursor(Qt.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 12, 20, 12)
        lay.setSpacing(16)

        self.thumb = QLabel()
        self.thumb.setFixedSize(self.THUMB, self.THUMB)
        self.thumb.setPixmap(thumb if thumb is not None else placeholder_pixmap(self.THUMB, 14))
        lay.addWidget(self.thumb, 0, Qt.AlignVCenter)

        mid = QVBoxLayout()
        mid.setSpacing(7)
        title = QLabel(rec.get("name", "?"))
        title.setWordWrap(True)
        title.setStyleSheet("font-size: 15px; font-weight: bold;")
        length = rec.get("length_eff") or rec.get("length") or 0
        meta = QLabel(f"{rec['stars']:.2f}★   ·   {rec['bpm_eff']:.0f} BPM   ·   {_fmt_len(length)}   ·   "
                      f"ratio {rec['sr']:.2f}")
        meta.setObjectName("muted")
        meta.setStyleSheet("font-size: 13px;")
        mid.addWidget(title)
        mid.addWidget(meta)
        tags = QHBoxLayout()
        tags.setSpacing(8)
        for t in rec.get("tags", []):
            tags.addWidget(_tag_pill(t))
        tags.addStretch(1)
        mid.addLayout(tags)
        lay.addLayout(mid, 1)

        right = QVBoxLayout()
        right.setSpacing(3)
        right.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        pp = QLabel(f"{rec['pp']:.0f} pp")
        pp.setStyleSheet(f"font-size: 24px; font-weight: bold; color: {T.ACCENT};")
        pp.setAlignment(Qt.AlignRight)
        p, known = rec.get("p", 0.0), rec.get("p_known", False)
        ok = QLabel(f"Éxito {p * 100:.0f}%" if known else "Éxito n/d")
        ok.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {_success_color(p) if known else T.MUTED};")
        ok.setAlignment(Qt.AlignRight)
        aff = QLabel(f"Afinidad con tu estilo {rec['skill'] * 100:.0f}%")
        aff.setStyleSheet(f"font-size: 12px; color: {T.WARN};")
        aff.setAlignment(Qt.AlignRight)
        ref = QLabel(self._ref_text(rec))
        ref.setObjectName("muted")
        ref.setStyleSheet("font-size: 12px;")
        ref.setAlignment(Qt.AlignRight)
        for lab in (pp, ok, aff, ref):
            right.addWidget(lab)
        lay.addLayout(right, 0)

        for lab in self.findChildren(QLabel):
            lab.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    @staticmethod
    def _ref_text(rec):
        cr = rec.get("cr")
        if cr is not None:
            return f"{cr * 100:.0f}% clears · FC {rec.get('n_fc', 0)}/{rec.get('n_lb', 0)}"
        if rec.get("p_known"):
            return "Éxito solo con tu perfil"
        return f"Sin referencia ({rec.get('n_lb', 0)}/{rec.get('min_sample', 8)} scores)"

    def set_thumb(self, pix):
        self.thumb.setPixmap(pix)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(e)


def make_badge(combo):
    """Columna de color con los mods con los que se debe jugar."""
    box = QFrame()
    box.setFixedWidth(64)
    box.setStyleSheet(f"background: {T.MOD_COLORS.get(combo, '#4b5563')}; border-radius: 14px;")
    lay = QVBoxLayout(box)
    lay.setAlignment(Qt.AlignCenter)
    lay.setSpacing(4)
    a = QLabel("MODS")
    a.setStyleSheet("font-size: 9px; font-weight: bold; color: #f3f4f6; background: transparent;")
    b = QLabel(combo)
    b.setStyleSheet("font-size: 16px; font-weight: bold; color: white; background: transparent;")
    for lab in (a, b):
        lab.setAlignment(Qt.AlignCenter)
        lay.addWidget(lab)
    return box


class RecRow(QWidget):
    """[mods] [tarjeta] [osu!direct] — el botón directo avisa si no pudo abrir osu!."""
    direct_failed = Signal(int)

    def __init__(self, rec, thumb=None):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 8, 0)
        lay.setSpacing(10)
        lay.addWidget(make_badge(rec.get("mods", "NM")))
        self.card = RecCard(rec, thumb)
        lay.addWidget(self.card, 1)
        btn = QPushButton("osu!\ndirect")
        btn.setObjectName("direct")
        btn.setFixedWidth(72)
        btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        btn.setCursor(Qt.PointingHandCursor)
        bid = rec["id"]
        btn.clicked.connect(lambda _c=False: None if open_direct(bid) else self.direct_failed.emit(bid))
        lay.addWidget(btn)
