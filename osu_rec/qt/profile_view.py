"""Ventana principal con la pestaña «Mi perfil» ampliada: desglose por mods y tipo de play (Aim / Mixto / Speed)."""
import threading
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QLabel, QTableWidgetItem

from .. import config as C
from ..profile_breakdown import analyze, CAT_NOTE
from . import main_window as MW
from . import theme as T

COLS = ["Mod", "Tipo", "Plays", "% del mod", "★ mediana", "★ máx", "pp mediana", "pp máx", "Acc", "Patrón"]
CAT_COLORS = {"Aim": "#60a5fa", "Mixto": "#a78bfa", "Speed": T.ACCENT, "Sin datos": T.MUTED}
TOTAL_BG = "#262634"


def _fmt(v, spec, suffix=""):
    return "—" if v is None else f"{v:{spec}}{suffix}"


class ProfileWindow(MW.MainWindow):
    breakdown_ready = Signal(object, int)

    def _build_profile_page(self):
        page = super()._build_profile_page()
        lay = page.layout()
        idx = lay.indexOf(self.tree_prof)
        lay.takeAt(idx)
        self.tree_prof.setParent(None)
        self.tree_prof.hide()
        self.tree_bd = self._make_table(COLS, stretch=len(COLS) - 1)
        self.tree_bd.setSelectionMode(QAbstractItemView.NoSelection)
        self.tree_bd.setFocusPolicy(Qt.NoFocus)
        self.tree_bd.horizontalHeader().setSectionResizeMode(len(COLS) - 1, QHeaderView.Stretch)
        lay.insertWidget(idx, self.tree_bd, 1)
        self.lbl_bd = QLabel("")
        self.lbl_bd.setObjectName("muted")
        self.lbl_bd.setStyleSheet("font-size: 12px;")
        self.lbl_bd.setWordWrap(True)
        lay.insertWidget(idx + 1, self.lbl_bd)
        self._bd_running = False
        self.breakdown_ready.connect(self._show_breakdown)
        return page

    def _fill_profile(self):
        super()._fill_profile()
        self._start_breakdown()

    def logout(self, forget, switch=False):
        self.tree_bd.setRowCount(0)
        self.lbl_bd.setText("")
        super().logout(forget, switch)

    def _start_breakdown(self):
        if self._bd_running or not self.uid:
            return
        try:
            import json
            with open(C.best_file(self.uid), encoding="utf-8") as f:
                scores = json.load(f)
        except Exception:
            self.lbl_bd.setText("No se encontraron tus best scores para el desglose; pulsa «Actualizar perfil».")
            return
        cache = Path(C.DATA_DIR) / f"profile_breakdown_{self.uid}.json"
        ep = self.epoch
        self._bd_running = True
        self.lbl_bd.setText("Analizando tus plays por tipo y patrón… (la primera vez puede tardar un poco)")

        def work():
            try:
                rows, n = analyze(scores, cache, progress=self._log)
                self.breakdown_ready.emit((rows, n), ep)
            except Exception as e:
                self._log(f"Error al analizar el perfil: {e}")
                self.breakdown_ready.emit(([], 0), ep)
        threading.Thread(target=work, daemon=True).start()

    def _show_breakdown(self, payload, ep):
        self._bd_running = False
        if ep != self.epoch:
            return
        rows, n = payload
        t = self.tree_bd
        t.setRowCount(0)
        for r in rows:
            i = t.rowCount()
            t.insertRow(i)
            vals = [r["mod"] if r["total"] else "", r["cat"], str(r["n"]),
                    "100%" if r["total"] else f"{r['share'] * 100:.0f}%",
                    _fmt(r["stars_p50"], ".2f"), _fmt(r["stars_max"], ".2f"),
                    _fmt(r["pp_p50"], ".0f"), _fmt(r["pp_max"], ".0f"),
                    "—" if r["acc_p50"] is None else f"{r['acc_p50'] * 100:.2f}%", r["tags"]]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                it.setFlags(Qt.ItemIsEnabled)
                if r["total"]:
                    f = it.font()
                    f.setBold(True)
                    it.setFont(f)
                    it.setBackground(QColor(TOTAL_BG))
                if c == 1:
                    it.setForeground(QColor(CAT_COLORS.get(r["cat"], T.TXT)))
                if c in (2, 3, 4, 5, 6, 7, 8):
                    it.setTextAlignment(Qt.AlignCenter)
                t.setItem(i, c, it)
        self.lbl_bd.setText(f"{n} plays analizadas · {CAT_NOTE}" if rows else
                            "No se pudo generar el desglose (revisa que los mapas se hayan descargado).")
