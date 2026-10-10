import json
import queue
import sys
import threading
import webbrowser
from datetime import datetime

import requests
from PySide6.QtCore import QSize, QTimer, Qt
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QButtonGroup, QCheckBox, QFrame, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QMainWindow, QMenu, QProgressBar, QPushButton,
                               QScrollArea, QSizePolicy, QStackedWidget, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from .. import config as C
from ..api import TokenManager, get_user, fetch_best
from ..profile import build_profile, save_profile, load_profile
from ..recommend import evaluate, top_n_mean, SKILLCAP_ABOVE, PP_SOFT
from ..session import session_adjust, describe, basic_stats
from ..storage import Store, now_iso
from ..poller import Poller
from ..ui.options import (GOAL_LABELS, STYLE_LABELS, SORT_OPTIONS, SORT_SKILLCAP, PP_RANGE_OPTIONS,
                          MAPS_OPTIONS, SHOW_OPTIONS, tag_label)
from ..ui.sorting import sort_recs
from . import theme as T
from . import widgets as W

HELP_URL = "https://osu.ppy.sh/home/account/edit#oauth"
BATCH = 30
MOD_ORDER = ("NM", "HD", "DT")


def _divider():
    d = QFrame()
    d.setObjectName("divider")
    d.setFixedHeight(1)
    return d


def _label(text, name=None, style=None):
    lab = QLabel(text)
    if name:
        lab.setObjectName(name)
    if style:
        lab.setStyleSheet(style)
    return lab


class MainWindow(QMainWindow):
    def __init__(self, font_family):
        super().__init__()
        self.font_family = font_family
        self.setWindowTitle("osu! Beatmap Recommender")
        self.resize(1320, 860)
        self.setMinimumSize(1120, 720)
        self._set_icon()

        self.q = queue.Queue()
        self.store = Store()
        self.epoch = 0
        self.tm = self.uid = self.prof = self.info = None
        self.session_id = None
        self.poller = None
        self.stop_rec = threading.Event()
        self.rec_running = False
        self.new_since_rec = 0
        self.rows = []
        self.pending = []
        self.more_btn = None
        self.thumb_pix = {}
        self.session_scores = []
        self.recs_all = []
        self.last_adj = None
        self.top10_pp = None
        self.thumb_ph = W.placeholder_pixmap(W.RecCard.THUMB, 14)

        self.stack = QStackedWidget()
        self.stack.setObjectName("root")
        self.setCentralWidget(self.stack)
        self.stack.addWidget(self._build_login())
        self.stack.addWidget(self._build_main())
        self._show("login")
        self._prefill()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._drain)
        self.timer.start(200)

    # ----------------------------------------------------------------- utils
    def _set_icon(self):
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("osu.beatmap.recommender")
        except Exception:
            pass
        for name in ("assets/icon.ico", "assets/icon.png"):
            p = C.resource_path(name)
            if p.exists():
                self.setWindowIcon(QIcon(str(p)))
                break

    def _show(self, view):
        self.stack.setCurrentIndex(0 if view == "login" else 1)

    def _log(self, text):
        self.q.put(("log", text))

    def _load_top10(self):
        self.top10_pp = None
        try:
            with open(C.best_file(self.uid), encoding="utf-8") as f:
                self.top10_pp = top_n_mean(json.load(f), 10)
        except Exception:
            self.top10_pp = None

    def _direct_failed(self, beatmap_id):
        self.log.setText(f"No se pudo abrir {W.direct_url(beatmap_id)}: ¿está osu! instalado? "
                         "Haz clic en el mapa para abrirlo en la web.")

    def _header(self, title, subtitle=""):
        box = QWidget()
        lay = QHBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 14)
        left = QVBoxLayout()
        left.setSpacing(2)
        left.addWidget(_label(title, "h1"))
        if subtitle:
            left.addWidget(_label(subtitle, "muted"))
        lay.addLayout(left)
        lay.addStretch(1)
        return box, lay

    # ------------------------------------------------------------ login view
    def _build_login(self):
        page = QWidget()
        page.setObjectName("root")
        outer = QVBoxLayout(page)
        outer.setAlignment(Qt.AlignCenter)
        col = QWidget()
        col.setFixedWidth(340)
        lay = QVBoxLayout(col)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        logo = QLabel()
        icon = C.resource_path("assets/icon.png")
        if icon.exists():
            logo.setPixmap(W.rounded_pixmap(QPixmap(str(icon)), 76, 38))
        logo.setAlignment(Qt.AlignCenter)
        lay.addWidget(logo)
        t = _label("osu! Recommender", style="font-size: 26px; font-weight: bold;")
        t.setAlignment(Qt.AlignCenter)
        lay.addWidget(t)
        s = _label("Inicia sesión para continuar", "muted")
        s.setAlignment(Qt.AlignCenter)
        lay.addWidget(s)
        lay.addSpacing(18)

        def field(label, password=False):
            head = QHBoxLayout()
            head.addWidget(_label(label, "muted", "font-size: 12px;"))
            head.addStretch(1)
            lay.addSpacing(8)
            lay.addLayout(head)
            e = QLineEdit()
            e.setObjectName("login")
            if password:
                e.setEchoMode(QLineEdit.Password)
            e.returnPressed.connect(self.login_action)
            lay.addWidget(e)
            return head, e

        _, self.e_user = field("Usuario de osu!")
        _, self.e_id = field("Client ID")
        head, self.e_secret = field("Client Secret", True)
        self.show_btn = QPushButton("Mostrar")
        self.show_btn.setObjectName("link")
        self.show_btn.setCursor(Qt.PointingHandCursor)
        self.show_btn.clicked.connect(self._toggle_secret)
        head.addWidget(self.show_btn)

        self.remember = QCheckBox("Recordarme en este equipo")
        self.remember.setChecked(True)
        lay.addSpacing(14)
        lay.addWidget(self.remember)
        self.b_login = QPushButton("Iniciar sesión")
        self.b_login.setObjectName("primary")
        self.b_login.setFixedHeight(46)
        self.b_login.setCursor(Qt.PointingHandCursor)
        self.b_login.clicked.connect(self.login_action)
        lay.addSpacing(10)
        lay.addWidget(self.b_login)
        self.login_bar = QProgressBar()
        self.login_bar.setTextVisible(False)
        self.login_bar.setRange(0, 1)
        self.login_bar.setValue(0)
        lay.addSpacing(8)
        lay.addWidget(self.login_bar)
        self.login_status = _label("", "muted", "font-size: 12px;")
        self.login_status.setWordWrap(True)
        self.login_status.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.login_status)
        help_btn = QPushButton("¿Cómo obtener Client ID y Secret?")
        help_btn.setObjectName("ghost")
        help_btn.setCursor(Qt.PointingHandCursor)
        help_btn.clicked.connect(lambda: webbrowser.open(HELP_URL))
        lay.addWidget(help_btn)
        outer.addWidget(col)
        return page

    def _toggle_secret(self):
        hidden = self.e_secret.echoMode() == QLineEdit.Password
        self.e_secret.setEchoMode(QLineEdit.Normal if hidden else QLineEdit.Password)
        self.show_btn.setText("Ocultar" if hidden else "Mostrar")

    def _prefill(self):
        cid, sec, user = C.saved_credentials()
        self.e_id.setText(cid or "")
        self.e_secret.setText(sec or "")
        self.e_user.setText(user or "")

    def _login_busy(self, busy, text="", color=None):
        self.b_login.setEnabled(not busy)
        if busy:
            self.login_bar.setRange(0, 0)
        else:
            self.login_bar.setRange(0, 1)
            self.login_bar.setValue(0)
        self.login_status.setStyleSheet(f"font-size: 12px; color: {color or T.MUTED};")
        self.login_status.setText(text)

    def login_action(self):
        cid, sec, user = self.e_id.text().strip(), self.e_secret.text().strip(), self.e_user.text().strip()
        if not (cid and sec and user):
            self._login_busy(False, "Completa usuario, Client ID y Client Secret.", T.BAD)
            return
        self.epoch += 1
        ep = self.epoch
        remember = self.remember.isChecked()
        self._login_busy(True, "Conectando...")
        threading.Thread(target=self._login_worker, args=(cid, sec, user, remember, ep), daemon=True).start()

    def _login_worker(self, cid, sec, user, remember, ep):
        st = lambda t: self.q.put(("login_status", t, ep))
        fail = lambda t: self.q.put(("login_fail", t, ep))
        try:
            C.save_credentials(cid, sec, user, remember)
            tm = TokenManager()
            try:
                tm.headers()
            except requests.exceptions.RequestException:
                return fail("Credenciales inválidas o sin conexión. Revisa Client ID y Secret.")
            st("Buscando usuario...")
            info = get_user(tm, user)
            if not info:
                return fail(f"No se encontró el usuario «{user}».")
            uid = info["id"]
            prof = load_profile(uid)
            if not prof:
                st("Construyendo tu perfil (puede tardar unos minutos la primera vez)...")
                best = fetch_best(tm, uid)
                if not best:
                    return fail("No se pudieron obtener tus best scores.")
                json.dump(best, open(C.best_file(uid), "w"))
                prof = build_profile(best, st)
                save_profile(prof)
            st("Cargando foto de perfil...")
            avatar = None
            try:
                avatar = requests.get(info["avatar_url"], timeout=C.TIMEOUT).content
            except Exception:
                pass
            self.q.put(("logged", (tm, info, prof, avatar, remember), ep))
        except Exception as e:
            fail(f"Error: {e}")

    # ------------------------------------------------------------- main view
    def _build_main(self):
        page = QWidget()
        page.setObjectName("root")
        root = QHBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(270)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(16, 30, 16, 18)
        sl.setSpacing(3)
        self.btn_avatar = QPushButton()
        self.btn_avatar.setObjectName("avatar")
        self.btn_avatar.setFixedSize(96, 96)
        self.btn_avatar.setIconSize(QSize(88, 88))
        self.btn_avatar.setCursor(Qt.PointingHandCursor)
        self.btn_avatar.clicked.connect(self._avatar_menu)
        sl.addWidget(self.btn_avatar, 0, Qt.AlignHCenter)
        self.lbl_name = _label("", style="font-size: 20px; font-weight: bold;")
        self.lbl_rank = _label("", "muted")
        self.lbl_conn = _label("● Conectado", style=f"font-size: 12px; color: {T.GOOD};")
        for lab in (self.lbl_name, self.lbl_rank, self.lbl_conn):
            lab.setAlignment(Qt.AlignCenter)
            sl.addWidget(lab)
        sl.addSpacing(20)

        self.nav_group = QButtonGroup(self)
        self.nav_btns = {}
        for key, text in (("session", "📊   Sesión"), ("recs", "🎯   Recomendaciones"), ("profile", "👤   Mi perfil")):
            b = QPushButton(text)
            b.setObjectName("nav")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _c=False, k=key: self._nav(k))
            self.nav_group.addButton(b)
            sl.addWidget(b)
            self.nav_btns[key] = b
        sl.addStretch(1)
        out = QPushButton("Cerrar sesión")
        out.setObjectName("secondary")
        out.setFixedHeight(42)
        out.setCursor(Qt.PointingHandCursor)
        out.clicked.connect(lambda: self.logout(False))
        sl.addWidget(out)
        root.addWidget(side)

        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(24, 20, 24, 12)
        self.pages = QStackedWidget()
        self.page_idx = {}
        for key, builder in (("session", self._build_session_page), ("recs", self._build_recs_page),
                             ("profile", self._build_profile_page)):
            self.page_idx[key] = self.pages.addWidget(builder())
        cl.addWidget(self.pages, 1)
        self.log = _label("", "muted", "font-size: 12px;")
        cl.addWidget(self.log)
        root.addWidget(content, 1)
        return page

    def _nav(self, key):
        self.pages.setCurrentIndex(self.page_idx[key])
        self.nav_btns[key].setChecked(True)

    # ---- sesión
    def _build_session_page(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        head, hl = self._header("Sesión actual",
                                "Se registra cada jugada mientras tienes la app abierta · doble clic abre el mapa")
        b = QPushButton("Nueva sesión")
        b.setObjectName("primary")
        b.setFixedSize(150, 40)
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(self.new_session)
        hl.addWidget(b)
        lay.addWidget(head)
        row, self.sc = W.cards_row([("n", "Jugadas"), ("acc", "Precisión (pases)"), ("fail", "Fallos"),
                                    ("time", "Duración"), ("adj", "Ajuste de dificultad")])
        lay.addWidget(row)
        self.lbl_adj = _label("", "muted")
        self.lbl_adj.setContentsMargins(0, 10, 0, 10)
        lay.addWidget(self.lbl_adj)
        self.tree_plays = self._make_table(["Hora", "Mapa", "Mods", "Acc", "Miss", "pp", "Resultado"], stretch=1)
        self.tree_plays.cellDoubleClicked.connect(self._open_play)
        lay.addWidget(self.tree_plays, 1)
        return page

    def _make_table(self, headers, stretch=0):
        t = QTableWidget(0, len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setSelectionMode(QAbstractItemView.SingleSelection)
        t.setShowGrid(False)
        t.setAlternatingRowColors(True)
        t.setFocusPolicy(Qt.NoFocus)
        hdr = t.horizontalHeader()
        hdr.setStretchLastSection(False)
        for i in range(len(headers)):
            hdr.setSectionResizeMode(i, QHeaderView.Stretch if i == stretch else QHeaderView.ResizeToContents)
        return t

    # ---- recomendaciones
    def _build_recs_page(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        head, _ = self._header("Recomendaciones",
                               "Clic en un mapa para abrirlo en la web · botón osu!direct para abrirlo en el juego")
        lay.addWidget(head)

        bar = QFrame()
        bar.setObjectName("bar")
        bl = QVBoxLayout(bar)
        bl.setContentsMargins(18, 12, 18, 0)
        bl.setSpacing(0)

        row1 = QHBoxLayout()
        row1.setSpacing(0)
        self.goal = W.Tabs(list(GOAL_LABELS))
        self.goal.changed.connect(self._goal_changed)
        row1.addWidget(self.goal)
        row1.addSpacing(28)
        row1.addWidget(_label("Mods", "muted", "font-size: 12px;"))
        row1.addSpacing(8)
        self.mod_chips = W.ModChips()
        self.mod_chips.changed.connect(lambda _s: self._update_summary())
        row1.addWidget(self.mod_chips)
        row1.addStretch(1)
        self.b_stop = QPushButton("Detener")
        self.b_stop.setObjectName("secondary")
        self.b_stop.setFixedSize(100, 38)
        self.b_stop.setCursor(Qt.PointingHandCursor)
        self.b_stop.clicked.connect(self._stop_run)
        self.b_stop.setVisible(False)
        row1.addWidget(self.b_stop)
        row1.addSpacing(8)
        self.b_rec = QPushButton("Recomendar")
        self.b_rec.setObjectName("primary")
        self.b_rec.setFixedSize(150, 38)
        self.b_rec.setCursor(Qt.PointingHandCursor)
        self.b_rec.clicked.connect(self.run_recs)
        row1.addWidget(self.b_rec)
        bl.addLayout(row1)
        bl.addSpacing(4)
        bl.addWidget(_divider())
        bl.addSpacing(12)

        row2 = QHBoxLayout()
        row2.setSpacing(8)
        self.style_pill = W.Pill("Estilo", list(STYLE_LABELS), "Mi perfil")
        self.pp_pill = W.Pill("pp", list(PP_RANGE_OPTIONS), "0.8× – 1.3× · amplio")
        self.maps_pill = W.Pill("Analizar", list(MAPS_OPTIONS), "1000 · equilibrado")
        for p in (self.style_pill, self.pp_pill, self.maps_pill):
            p.changed.connect(lambda _v: self._update_summary())
            row2.addWidget(p)
        row2.addStretch(1)
        self.b_adv = QPushButton("⚙ Avanzado ▸")
        self.b_adv.setObjectName("ghost")
        self.b_adv.setCursor(Qt.PointingHandCursor)
        self.b_adv.clicked.connect(self._toggle_adv)
        row2.addWidget(self.b_adv)
        bl.addLayout(row2)

        self.lbl_summary = _label("", "muted", "font-size: 12px;")
        self.lbl_summary.setWordWrap(True)
        self.lbl_summary.setContentsMargins(4, 8, 0, 12)
        bl.addWidget(self.lbl_summary)

        self.adv = QWidget()
        al = QVBoxLayout(self.adv)
        al.setContentsMargins(0, 0, 0, 14)
        al.setSpacing(10)
        al.addWidget(_divider())
        self.profile_only = W.Toggle("Éxito solo con mi perfil",
                                     "No consulta leaderboards: mucho más rápido, sin clears ni FC de referencia",
                                     default=True)
        self.use_pp_range = W.Toggle("Buscar por rango de pp deseado",
                                     f"Solo pestaña PP · ignora estrellas y tus mejores plays · "
                                     f"tolerancia blanda ±{PP_SOFT * 100:.0f}%")
        self.pp_box = QWidget()
        pb = QHBoxLayout(self.pp_box)
        pb.setContentsMargins(0, 0, 0, 0)
        pb.setSpacing(8)
        self.e_pp_lo = QLineEdit()
        self.e_pp_hi = QLineEdit()
        for e in (self.e_pp_lo, self.e_pp_hi):
            e.setFixedWidth(90)
            e.setAlignment(Qt.AlignCenter)
            e.textChanged.connect(lambda _t: self._update_summary())
        pb.addWidget(_label("Mín", "muted", "font-size: 12px;"))
        pb.addWidget(self.e_pp_lo)
        pb.addSpacing(8)
        pb.addWidget(_label("Máx", "muted", "font-size: 12px;"))
        pb.addWidget(self.e_pp_hi)
        pb.addWidget(_label("pp", "muted", "font-size: 12px;"))
        pb.addStretch(1)
        self.pp_box.setVisible(False)
        self.use_top10 = W.Toggle("Basarme en mi top 10",
                                  "Usa el promedio de tus 10 mejores plays como referencia, no solo la mejor")
        self.use_session = W.Toggle("Usar mi sesión", "Ajusta dificultad y skills con las jugadas de hoy",
                                    default=True)
        self.auto = W.Toggle("Recomendar automáticamente",
                             f"Genera nuevas recomendaciones cada {C.REC_EVERY_PLAYS} jugadas")
        self.require_refs = W.Toggle("Solo mapas con referencias",
                                     f"Exige ≥{C.MIN_LB_SAMPLE} scores del mismo mod y al menos 1 FC "
                                     "(requiere leaderboards)")
        for wdg in (self.profile_only, self.use_pp_range, self.pp_box, self.use_top10, self.use_session,
                    self.auto, self.require_refs):
            al.addWidget(wdg)
        for tg in (self.profile_only, self.use_top10, self.use_session):
            tg.changed.connect(self._update_summary)
        self.use_pp_range.changed.connect(self._pp_range_toggled)
        self.adv.setVisible(False)
        bl.addWidget(self.adv)
        lay.addWidget(bar)

        self.rec_bar = QProgressBar()
        self.rec_bar.setTextVisible(False)
        self.rec_bar.setRange(0, 1)
        self.rec_bar.setValue(0)
        lay.addSpacing(6)
        lay.addWidget(self.rec_bar)

        rb = QHBoxLayout()
        rb.setContentsMargins(4, 6, 0, 8)
        self.lbl_count = _label("", style="font-size: 15px; font-weight: bold;")
        rb.addWidget(self.lbl_count)
        rb.addStretch(1)
        rb.addWidget(_label("Mostrar", "muted", "font-size: 12px;"))
        self.show_chips = W.ChipGroup(SHOW_OPTIONS, 10)
        self.show_chips.changed.connect(lambda _v: self._apply_view())
        rb.addWidget(self.show_chips)
        rb.addSpacing(8)
        self.sort_pill = W.Pill("Orden", list(SORT_OPTIONS), "Éxito")
        self.sort_pill.changed.connect(lambda _v: self._apply_view())
        rb.addWidget(self.sort_pill)
        lay.addLayout(rb)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.rec_inner = QWidget()
        self.rec_lay = QVBoxLayout(self.rec_inner)
        self.rec_lay.setContentsMargins(0, 0, 4, 0)
        self.rec_lay.setSpacing(12)
        self.rec_lay.addStretch(1)
        self.scroll.setWidget(self.rec_inner)
        lay.addWidget(self.scroll, 1)
        self._show_recs([])
        self._update_summary()
        return page

    def _toggle_adv(self):
        show = not self.adv.isVisible()
        self.adv.setVisible(show)
        self.b_adv.setText("⚙ Avanzado ▾" if show else "⚙ Avanzado ▸")
        self.b_adv.setStyleSheet(f"color: {T.ACCENT};" if show else "")

    def _pp_range_toggled(self):
        on = bool(self.use_pp_range.get())
        if on:
            self._fill_pp_defaults()
        self.pp_box.setVisible(on)
        self._update_summary()

    def _fill_pp_defaults(self):
        if self.e_pp_lo.text().strip() or self.e_pp_hi.text().strip() or not self.prof:
            return
        top = max(d["pp_max"] for d in self.prof["by_mod"].values())
        self.e_pp_lo.setText(f"{round(top * 0.9 / 10) * 10:.0f}")
        self.e_pp_hi.setText(f"{round(top * 1.1 / 10) * 10:.0f}")

    def _manual_pp(self):
        """None si está apagado; (min, max) si es válido; 'error' si los campos no sirven."""
        if not self.use_pp_range.get():
            return None
        try:
            lo = float(self.e_pp_lo.text().strip().replace(",", "."))
            hi = float(self.e_pp_hi.text().strip().replace(",", "."))
        except ValueError:
            return "error"
        return (lo, hi) if 0 < lo < hi else "error"

    def _goal_changed(self, _value=None):
        skill = GOAL_LABELS[self.goal.get()] == "skillcap"
        opts = SORT_SKILLCAP if skill else SORT_OPTIONS
        self.sort_pill.set_options(list(opts), next(iter(opts)))
        self.pp_pill.setVisible(not skill)
        self._update_summary()
        self._apply_view()

    def _sort_key(self):
        opts = SORT_SKILLCAP if GOAL_LABELS[self.goal.get()] == "skillcap" else SORT_OPTIONS
        return opts.get(self.sort_pill.get(), next(iter(opts.values())))

    def _ref_pp(self):
        return self.top10_pp if (self.use_top10.get() and self.top10_pp) else None

    def _update_summary(self, adj="keep"):
        if not isinstance(adj, str) or adj != "keep":
            self.last_adj = adj
        goal = GOAL_LABELS[self.goal.get()]
        top = max((d["pp_max"] for d in self.prof["by_mod"].values()), default=None) if self.prof else None
        ref = self._ref_pp() or top
        manual = self._manual_pp() if goal == "pp" else None
        parts = []
        if goal == "pp" and manual == "error":
            parts.append("PP · rango manual inválido (mín < máx, en números)")
        elif goal == "pp" and manual:
            parts.append(f"PP · {manual[0]:.0f}–{manual[1]:.0f} pp (manual, ±{PP_SOFT * 100:.0f}%, sin estrellas)")
        elif goal == "pp":
            lo, hi = PP_RANGE_OPTIONS[self.pp_pill.get()]
            tag = " (ref. top 10)" if self._ref_pp() else ""
            parts.append("PP · " + (f"{ref * lo:.0f}–{ref * hi:.0f} pp{tag}" if ref else f"{lo}×–{hi}× de tu top"))
        else:
            parts.append(f"Skillcap · cerca de tu techo (hasta +{SKILLCAP_ABOVE:.1f}★)")
        sel = self.mod_chips.get()
        parts.append("mods " + " + ".join(m for m in MOD_ORDER if m in sel))
        parts.append(f"estilo {self.style_pill.get().lower()}")
        parts.append(f"{MAPS_OPTIONS[self.maps_pill.get()]} mapas")
        adj = self.last_adj
        if not self.use_session.get():
            parts.append("solo perfil")
        elif adj:
            parts.append(f"perfil + sesión ({adj['n']} jugadas, {adj['star_shift']:+.2f}★)")
        else:
            parts.append("perfil (+ sesión si hay jugadas)")
        parts.append("éxito: solo perfil (rápido)" if self.profile_only.get() else "éxito: con leaderboards")
        if goal == "pp" and not manual and self.use_top10.get() and not self.top10_pp:
            parts.append("top 10 no disponible: usando tu mejor play")
        self.lbl_summary.setText("  ·  ".join(parts))

    # ---- perfil
    def _build_profile_page(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        head, hl = self._header("Mi perfil", "Calculado a partir de tu top 100")
        self.b_refresh = QPushButton("Actualizar perfil")
        self.b_refresh.setObjectName("primary")
        self.b_refresh.setFixedSize(170, 40)
        self.b_refresh.setCursor(Qt.PointingHandCursor)
        self.b_refresh.clicked.connect(self.refresh_profile)
        hl.addWidget(self.b_refresh)
        lay.addWidget(head)
        row, self.pc = W.cards_row([("skill", "Skill"), ("mod", "Mod principal"), ("star", "Techo ★"),
                                    ("pp", "pp máximo"), ("bpm", "BPM cómodo"), ("acc", "Acc mediana")])
        lay.addWidget(row)
        self.lbl_tags = _label("", "muted")
        self.lbl_tags.setContentsMargins(0, 10, 0, 10)
        lay.addWidget(self.lbl_tags)
        self.tree_prof = self._make_table(["Mod", "Scores", "Skill", "Speed/Aim", "★ mediana", "★ máx",
                                           "pp mediana", "Acc"])
        for i in range(8):
            self.tree_prof.horizontalHeader().setSectionResizeMode(i, QHeaderView.Stretch)
        lay.addWidget(self.tree_prof, 1)
        return page

    # ---------------------------------------------------------- account menu
    def _avatar_menu(self):
        m = QMenu(self)
        title = m.addAction(f"Conectado como {self.info['username'] if self.info else ''}")
        title.setEnabled(False)
        m.addSeparator()
        m.addAction("Cambiar de usuario", lambda: self.logout(False, switch=True))
        m.addAction("Cerrar sesión", lambda: self.logout(False))
        m.addAction("Cerrar sesión y olvidar credenciales", lambda: self.logout(True))
        m.exec(self.btn_avatar.mapToGlobal(self.btn_avatar.rect().bottomLeft()))

    def logout(self, forget, switch=False):
        self.epoch += 1
        self.stop_rec.set()
        if self.poller:
            self.poller.stop()
            self.poller = None
        self.tm = self.uid = self.prof = self.info = self.session_id = None
        self.rec_running = False
        self.new_since_rec = 0
        self.tree_plays.setRowCount(0)
        self.tree_prof.setRowCount(0)
        self.session_scores = []
        self.recs_all = []
        self.last_adj = None
        self.top10_pp = None
        self.e_pp_lo.setText("")
        self.e_pp_hi.setText("")
        self.lbl_count.setText("")
        self._show_recs([])
        self._update_summary()
        self.rec_bar.setRange(0, 1)
        self.rec_bar.setValue(0)
        self.b_stop.setVisible(False)
        self.b_rec.setEnabled(True)
        self.b_rec.setText("Recomendar")
        if forget:
            C.clear_credentials()
        self._prefill()
        if forget or switch:
            self.e_user.setText("")
        if switch:
            self.e_user.setFocus()
        self._login_busy(False, "Sesión cerrada.")
        self._show("login")

    # ------------------------------------------------------- session logic
    def _on_logged(self, payload):
        self.tm, self.info, self.prof, avatar, _remember = payload
        self.uid = self.info["id"]
        self.stop_rec.clear()
        self._login_busy(False)
        pix = QPixmap()
        if avatar:
            pix.loadFromData(avatar)
        self.btn_avatar.setIcon(QIcon(W.rounded_pixmap(pix, 88, 44)) if not pix.isNull() else QIcon())
        stats = self.info.get("statistics") or {}
        rank, pp = stats.get("global_rank"), stats.get("pp")
        self.lbl_name.setText(self.info["username"])
        self.lbl_rank.setText(f"#{rank:,} · {pp:,.0f} pp" if rank and pp else f"{pp:,.0f} pp" if pp else "")
        self._load_top10()
        self._fill_profile()
        if self.use_pp_range.get():
            self._fill_pp_defaults()
        self._update_summary()
        self._show("main")
        self._nav("session")
        self.new_session()

    def _fill_profile(self):
        pr = self.prof
        m = pr["by_mod"][pr["main_mod"]]
        self.pc["skill"].set(m["skill"].capitalize(), T.ACCENT)
        self.pc["mod"].set(pr["main_mod"])
        self.pc["star"].set(f"{m['stars_max']:.2f}★")
        self.pc["pp"].set(f"{m['pp_max']:.0f}")
        lo, _mid, hi = pr["bpm_range"]
        self.pc["bpm"].set(f"{lo:.0f}–{hi:.0f}")
        self.pc["acc"].set(f"{m['acc_p50'] * 100:.2f}%")
        tags = pr.get("style_tags") or {}
        self.lbl_tags.setText("Patrones de tu top: " + (
            "  ·  ".join(f"{tag_label(t)} {v * 100:.0f}%" for t, v in list(tags.items())[:5]) or "sin datos"))
        self.tree_prof.setRowCount(0)
        for mod, d in pr["by_mod"].items():
            r = self.tree_prof.rowCount()
            self.tree_prof.insertRow(r)
            vals = (mod, d["n"], d["skill"], f"{d['speed_ratio']:.2f}", f"{d['stars_p50']:.2f}",
                    f"{d['stars_max']:.2f}", f"{d['pp_p50']:.0f}", f"{d['acc_p50'] * 100:.2f}%")
            for c, v in enumerate(vals):
                self.tree_prof.setItem(r, c, QTableWidgetItem(str(v)))

    def refresh_profile(self):
        if not self.tm:
            return
        ep, tm, uid = self.epoch, self.tm, self.uid
        self.b_refresh.setEnabled(False)
        self.log.setText("Actualizando perfil...")

        def work():
            try:
                best = fetch_best(tm, uid)
                json.dump(best, open(C.best_file(uid), "w"))
                prof = build_profile(best, self._log)
                save_profile(prof)
                self.q.put(("profile", prof, ep))
            except Exception as e:
                self._log(f"Error al actualizar perfil: {e}")
                self.q.put(("profile", None, ep))
        threading.Thread(target=work, daemon=True).start()

    def new_session(self):
        if self.poller:
            self.poller.stop()
        self.tree_plays.setRowCount(0)
        self.session_scores = []
        since = now_iso()
        self.session_id = self.store.new_session(self.uid, since)
        self.new_since_rec = 0
        ep = self.epoch
        self.poller = Poller(self.tm, self.uid, self.store, self.session_id, since,
                             lambda new: self.q.put(("plays", new, ep)), self._log)
        self.poller.start()
        self._refresh_session()
        self.log.setText("Sesión nueva: registrando jugadas...")

    def _row_from_score(self, s):
        bm, bs = s.get("beatmap") or {}, s.get("beatmapset") or {}
        mods = "".join(m["acronym"] for m in s["mods"] if m["acronym"] != "CL")
        t = datetime.fromisoformat(s["ended_at"].replace("Z", "+00:00")).astimezone().strftime("%H:%M")
        title = f"{bs.get('artist', '?')} - {bs.get('title', '?')} [{bm.get('version', '?')}]"
        pp = f"{s['pp']:.0f}" if s.get("pp") else "-"
        res = s.get("rank", "?") if s.get("passed") else "FAIL"
        return (t, title, mods or "NM", f"{s['accuracy'] * 100:.2f}%",
                s.get("statistics", {}).get("miss", 0), pp, res)

    def _add_play(self, s):
        self.tree_plays.insertRow(0)
        vals = self._row_from_score(s)
        url = f"https://osu.ppy.sh/b/{s['beatmap_id']}"
        for c, v in enumerate(vals):
            it = QTableWidgetItem(str(v))
            if not s.get("passed"):
                it.setForeground(QColor(T.BAD))
            if c == 0:
                it.setData(Qt.UserRole, url)
            self.tree_plays.setItem(0, c, it)

    def _open_play(self, row, _col):
        it = self.tree_plays.item(row, 0)
        url = it.data(Qt.UserRole) if it else None
        if url:
            webbrowser.open(url)

    def _refresh_session(self):
        plays = self.store.session_plays(self.session_id) if self.session_id else []
        st = basic_stats(plays)
        self.sc["n"].set(str(st["n"]))
        self.sc["acc"].set("-" if st["acc"] is None else f"{st['acc'] * 100:.2f}%")
        fail = st["fail"]
        self.sc["fail"].set("-" if fail is None else f"{fail * 100:.0f}%",
                            None if fail is None else (T.BAD if fail > 0.4 else T.GOOD))
        self.sc["time"].set(f"{st['minutes']:.0f} min")
        adj = session_adjust(self.prof, plays) if self.prof else None
        if adj:
            col = T.GOOD if adj["star_shift"] > 0.02 else T.BAD if adj["star_shift"] < -0.02 else None
            self.sc["adj"].set(f"{adj['star_shift']:+.2f}★", col)
        else:
            self.sc["adj"].set("—")
        self.lbl_adj.setText(describe(adj))
        return adj

    # --------------------------------------------------------- recomendador
    def _stop_run(self):
        self.stop_rec.set()
        self.b_stop.setEnabled(False)
        self.b_stop.setText("Deteniendo…")

    def run_recs(self):
        if self.rec_running or not self.prof:
            return
        goal = GOAL_LABELS[self.goal.get()]
        manual = self._manual_pp() if goal == "pp" else None
        if manual == "error":
            self.log.setText("Rango de pp manual inválido: escribe números y que el mínimo sea menor que el "
                             "máximo (Avanzado).")
            return
        self.rec_running = True
        self.new_since_rec = 0
        self.b_rec.setEnabled(False)
        self.b_rec.setText("Calculando…")
        self.b_stop.setEnabled(True)
        self.b_stop.setText("Detener")
        self.b_stop.setVisible(True)
        self.rec_bar.setRange(0, 0)
        self.stop_rec.clear()
        style = STYLE_LABELS[self.style_pill.get()]
        lbs = not bool(self.profile_only.get())
        refs = bool(self.require_refs.get()) and lbs
        max_maps = MAPS_OPTIONS[self.maps_pill.get()]
        sort_by = self._sort_key()
        pp_range = PP_RANGE_OPTIONS[self.pp_pill.get()]
        mods_sel = self.mod_chips.get()
        ref_pp = self._ref_pp()
        session_adj = self._refresh_session()
        use_sess = bool(self.use_session.get())
        adj = session_adj if use_sess else None
        recent = list(self.session_scores) if use_sess else None
        self._update_summary(adj)
        ep, prof, tm = self.epoch, self.prof, self.tm

        def work():
            try:
                recs = evaluate(prof, goal, tm, adj=adj, progress=self._log, stop=self.stop_rec,
                                mods=mods_sel, style=style, require_refs=refs, max_maps=max_maps,
                                n_results=None, sort_by=sort_by, pp_range=pp_range, recent=recent,
                                ref_pp=ref_pp, pp_target=manual, leaderboards=lbs)
            except Exception as e:
                self._log(f"Error en recomendador: {e}")
                recs = []
            self.q.put(("recs", recs, ep))
        threading.Thread(target=work, daemon=True).start()

    def _apply_view(self):
        allr = self.recs_all
        if not allr:
            self.lbl_count.setText("")
            self._show_recs([])
            return
        ordered = sort_recs(allr, self._sort_key())
        n = self.show_chips.get()
        view = ordered if n is None else ordered[:n]
        self._show_recs(view)
        extra = f" · mostrando {len(view)}" if len(view) < len(allr) else ""
        self.lbl_count.setText(f"{len(allr)} mapas{extra}")

    def _clear_recs(self):
        while self.rec_lay.count() > 1:
            item = self.rec_lay.takeAt(0)
            wdg = item.widget()
            if wdg is not None:
                wdg.setParent(None)
                wdg.deleteLater()
        self.rows = []
        self.more_btn = None

    def _show_recs(self, recs):
        self._clear_recs()
        self.pending = list(recs)
        if not recs:
            hint = _label("Pulsa «Recomendar» para generar mapas.\nSin sesión activa se usa tu perfil histórico; "
                          "con «Usar mi sesión» apagado (en Avanzado) se ignora la sesión aunque estés jugando.",
                          "muted")
            hint.setAlignment(Qt.AlignCenter)
            hint.setContentsMargins(0, 60, 0, 0)
            self.rec_lay.insertWidget(0, hint)
            return
        self._render_batch()

    def _render_batch(self):
        if self.more_btn is not None:
            self.more_btn.setParent(None)
            self.more_btn.deleteLater()
            self.more_btn = None
        batch, self.pending = self.pending[:BATCH], self.pending[BATCH:]
        for c in batch:
            row = W.RecRow(c, self.thumb_pix.get(c.get("set_id")))
            row.card.clicked.connect(lambda url=c["url"]: webbrowser.open(url))
            row.direct_failed.connect(self._direct_failed)
            self.rec_lay.insertWidget(self.rec_lay.count() - 1, row)
            self.rows.append(row)
        self._load_thumbs(batch, self.epoch)
        if self.pending:
            self.more_btn = QPushButton(f"Mostrar {min(BATCH, len(self.pending))} más  ({len(self.pending)} restantes)")
            self.more_btn.setObjectName("more")
            self.more_btn.setFixedHeight(42)
            self.more_btn.setCursor(Qt.PointingHandCursor)
            self.more_btn.clicked.connect(self._render_batch)
            self.rec_lay.insertWidget(self.rec_lay.count() - 1, self.more_btn)

    def _load_thumbs(self, recs, ep):
        todo = [c.get("set_id") for c in recs if c.get("set_id") and c.get("set_id") not in self.thumb_pix]

        def work():
            for sid in todo:
                p = C.THUMBS_DIR / f"{sid}.jpg"
                try:
                    if not p.exists():
                        r = requests.get(f"https://assets.ppy.sh/beatmaps/{sid}/covers/list@2x.jpg", timeout=10)
                        if r.status_code != 200:
                            continue
                        p.write_bytes(r.content)
                    self.q.put(("thumb", (sid, str(p)), ep))
                except Exception:
                    continue
        if todo:
            threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------ cola UI
    def _drain(self):
        try:
            while True:
                msg = self.q.get_nowait()
                kind = msg[0]
                if kind == "log":
                    self.log.setText(msg[1])
                    continue
                if msg[-1] != self.epoch:
                    continue
                if kind == "login_status":
                    self._login_busy(True, msg[1])
                elif kind == "login_fail":
                    self._login_busy(False, msg[1], T.BAD)
                elif kind == "logged":
                    self._on_logged(msg[1])
                elif kind == "profile":
                    self.b_refresh.setEnabled(True)
                    if msg[1]:
                        self.prof = msg[1]
                        self._load_top10()
                        self._fill_profile()
                        self._update_summary()
                        self.log.setText("Perfil actualizado")
                elif kind == "plays":
                    for s in msg[1]:
                        self._add_play(s)
                        self.session_scores.append(s)
                    self.session_scores.sort(key=lambda x: x.get("ended_at", ""))
                    self.new_since_rec += len(msg[1])
                    self._refresh_session()
                    if self.auto.get() and self.new_since_rec >= C.REC_EVERY_PLAYS and not self.rec_running:
                        self.run_recs()
                elif kind == "recs":
                    self.rec_running = False
                    self.rec_bar.setRange(0, 1)
                    self.rec_bar.setValue(0)
                    self.b_stop.setVisible(False)
                    self.b_rec.setEnabled(True)
                    self.b_rec.setText("Recomendar")
                    self.recs_all = msg[1]
                    self._apply_view()
                    if not msg[1] and self.stop_rec.is_set():
                        self.log.setText("Búsqueda detenida antes de terminar: sin resultados.")
                    elif not msg[1]:
                        self.log.setText("Sin resultados con estos filtros: prueba otro estilo, más mods o un "
                                         "rango de pp más amplio.")
                    else:
                        self.log.setText(f"{len(msg[1])} recomendaciones calculadas")
                elif kind == "thumb":
                    sid, path = msg[1]
                    pix = W.rounded_pixmap(QPixmap(path), W.RecCard.THUMB, 14)
                    self.thumb_pix[sid] = pix
                    for row in self.rows:
                        if row.card.rec.get("set_id") == sid:
                            row.card.set_thumb(pix)
        except queue.Empty:
            pass

    def closeEvent(self, e):
        self.stop_rec.set()
        if self.poller:
            self.poller.stop()
        super().closeEvent(e)


def run():
    app = QApplication.instance() or QApplication(sys.argv)
    family = T.setup_fonts(app)
    app.setStyleSheet(T.stylesheet(family))
    win = MainWindow(family)
    win.show()
    sys.exit(app.exec())
