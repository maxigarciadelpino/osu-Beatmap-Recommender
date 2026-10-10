import io, json, queue, sys, threading, webbrowser
from datetime import datetime
import tkinter as tk
import requests
import customtkinter as ctk
from PIL import Image

from .. import config as C
from ..api import TokenManager, get_user, fetch_best
from ..profile import build_profile, save_profile, load_profile
from ..recommend import evaluate, top_n_mean, SKILLCAP_ABOVE, PP_SOFT
from ..session import session_adjust, describe, basic_stats
from ..storage import Store, now_iso
from ..poller import Poller
from . import widgets as W
from .options import (GOAL_LABELS, STYLE_LABELS, SORT_OPTIONS, SORT_SKILLCAP, PP_RANGE_OPTIONS,
                      MAPS_OPTIONS, SHOW_OPTIONS, tag_label)
from .filters import Tabs, Pill, ChipGroup, Toggle, BORDER, PILL
from .mods_ui import ModChips, make_badge, MOD_ORDER
from .osu_direct import make_direct_button, direct_url
from .sorting import sort_recs

HELP_URL = "https://osu.ppy.sh/home/account/edit#oauth"
BATCH = 20


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        self.font_family = W.setup_fonts(self)
        W.style_dark(self.font_family)
        self.btn_family = W.button_family(self) or self.font_family
        self.title("osu! Beatmap Recommender")
        self.geometry("1320x860")
        self.minsize(1120, 720)
        self.configure(fg_color=W.BG)
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
        self.avatar_img = None
        self.cards = []
        self.pending = []
        self.more_btn = None
        self.thumb_imgs = {}
        self.play_urls = {}
        self.session_scores = []
        self.recs_all = []
        self.last_adj = None
        self.top10_pp = None
        self.thumb_ph = W.thumb_placeholder()

        self._build_login()
        self._build_main()
        self._show("login")
        self._prefill()
        self.after(250, self._drain)
        self.protocol("WM_DELETE_WINDOW", self._close)

    # ----------------------------------------------------------------- utils
    def _set_icon(self):
        ico, png = C.resource_path("assets/icon.ico"), C.resource_path("assets/icon.png")
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("osu.beatmap.recommender")
        except Exception:
            pass

        def apply():
            try:
                if sys.platform.startswith("win") and ico.exists():
                    self.iconbitmap(str(ico))
                elif png.exists():
                    self._icon_photo = tk.PhotoImage(file=str(png))
                    self.iconphoto(True, self._icon_photo)
            except Exception:
                pass
        apply()
        self.after(300, apply)

    def _h1(self):
        return ctk.CTkFont(size=26, weight="bold")

    def _bf(self, size=15):
        return ctk.CTkFont(family=self.btn_family, size=size, weight="bold")

    def _load_top10(self):
        """Promedio de pp de tus 10 mejores scores, leído de tu archivo de best scores."""
        self.top10_pp = None
        try:
            with open(C.best_file(self.uid), encoding="utf-8") as f:
                self.top10_pp = top_n_mean(json.load(f), 10)
        except Exception:
            self.top10_pp = None

    def _direct_failed(self, beatmap_id):
        self.log.configure(text=f"No se pudo abrir {direct_url(beatmap_id)}: ¿está osu! instalado? "
                                "Haz clic en el mapa para abrirlo en la web.")

    # ------------------------------------------------------------ login view
    def _build_login(self):
        self.login = ctk.CTkFrame(self, fg_color=W.BG)
        col = ctk.CTkFrame(self.login, fg_color="transparent")
        col.place(relx=0.5, rely=0.5, anchor="center")

        try:
            self.logo_img = W.circle_image(Image.open(C.resource_path("assets/icon.png")), 76)
            ctk.CTkLabel(col, text="", image=self.logo_img).pack(pady=(0, 14))
        except Exception:
            pass
        ctk.CTkLabel(col, text="osu! Recommender", font=ctk.CTkFont(size=26, weight="bold")).pack()
        ctk.CTkLabel(col, text="Inicia sesión para continuar", text_color=W.MUTED).pack(pady=(4, 22))

        def field(label, show=""):
            head = ctk.CTkFrame(col, fg_color="transparent")
            head.pack(fill="x", pady=(10, 4))
            ctk.CTkLabel(head, text=label, text_color=W.MUTED, font=ctk.CTkFont(size=12)).pack(side="left")
            e = ctk.CTkEntry(col, width=340, height=44, corner_radius=10, border_width=1,
                             border_color="#2c2c38", fg_color=W.CARD, show=show)
            e.pack()
            e.bind("<Return>", lambda _e: self.login_action())
            return head, e

        _, self.e_user = field("Usuario de osu!")
        _, self.e_id = field("Client ID")
        head, self.e_secret = field("Client Secret", "•")
        self.show_btn = ctk.CTkButton(head, text="Mostrar", width=60, height=20, fg_color="transparent",
                                      hover=False, text_color=W.ACCENT, font=ctk.CTkFont(size=12),
                                      command=self._toggle_secret)
        self.show_btn.pack(side="right")

        self.remember = ctk.CTkCheckBox(col, text="Recordarme en este equipo", fg_color=W.ACCENT,
                                        hover_color=W.ACCENT_H, corner_radius=6, border_width=2,
                                        font=ctk.CTkFont(size=13))
        self.remember.select()
        self.remember.pack(anchor="w", pady=(18, 0))

        self.b_login = ctk.CTkButton(col, text="Iniciar sesión", height=46, width=340, corner_radius=10,
                                     fg_color=W.ACCENT, hover_color=W.ACCENT_H, text_color="white",
                                     font=self._bf(16), command=self.login_action)
        self.b_login.pack(pady=(18, 0))
        self.login_slot = ctk.CTkFrame(col, fg_color="transparent", height=10)
        self.login_slot.pack(fill="x", pady=(8, 0))
        self.login_bar = ctk.CTkProgressBar(self.login_slot, mode="indeterminate", progress_color=W.ACCENT, height=4)
        self.login_status = ctk.CTkLabel(col, text="", text_color=W.MUTED, wraplength=340,
                                         font=ctk.CTkFont(size=12))
        self.login_status.pack(pady=(4, 0))
        ctk.CTkButton(col, text="¿Cómo obtener Client ID y Secret?", fg_color="transparent",
                      text_color=W.MUTED, hover=False, font=ctk.CTkFont(size=12),
                      command=lambda: webbrowser.open(HELP_URL)).pack(pady=(6, 0))

    def _toggle_secret(self):
        showing = self.e_secret.cget("show") == ""
        self.e_secret.configure(show="•" if showing else "")
        self.show_btn.configure(text="Mostrar" if showing else "Ocultar")

    def _prefill(self):
        cid, sec, user = C.saved_credentials()
        for e, v in ((self.e_id, cid), (self.e_secret, sec), (self.e_user, user)):
            e.delete(0, "end")
            e.insert(0, v)

    def _login_busy(self, busy, text=""):
        self.b_login.configure(state="disabled" if busy else "normal")
        if busy:
            self.login_bar.pack(fill="x")
            self.login_bar.start()
        else:
            self.login_bar.stop()
            self.login_bar.pack_forget()
        self.login_status.configure(text=text, text_color=W.MUTED)

    def login_action(self):
        cid, sec, user = self.e_id.get().strip(), self.e_secret.get().strip(), self.e_user.get().strip()
        if not (cid and sec and user):
            self.login_status.configure(text="Completa usuario, Client ID y Client Secret.", text_color=W.BAD)
            return
        self.epoch += 1
        ep = self.epoch
        remember = bool(self.remember.get())
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
            pil = None
            try:
                r = requests.get(info["avatar_url"], timeout=C.TIMEOUT)
                pil = Image.open(io.BytesIO(r.content)).convert("RGBA")
                pil.load()
            except Exception:
                pass
            self.q.put(("logged", (tm, info, prof, pil, remember), ep))
        except Exception as e:
            fail(f"Error: {e}")

    # ------------------------------------------------------------- main view
    def _build_main(self):
        self.main = ctk.CTkFrame(self, fg_color=W.BG)
        self.main.grid_columnconfigure(1, weight=1)
        self.main.grid_rowconfigure(0, weight=1)

        side = ctk.CTkFrame(self.main, fg_color=W.SIDE, corner_radius=0, width=270)
        side.grid(row=0, column=0, sticky="ns")
        side.grid_propagate(False)
        self.btn_avatar = ctk.CTkButton(side, text="", width=96, height=96, corner_radius=48,
                                        fg_color="transparent", hover_color=W.CARD,
                                        command=self._avatar_menu)
        self.btn_avatar.pack(pady=(30, 8))
        self.lbl_name = ctk.CTkLabel(side, text="", font=ctk.CTkFont(size=20, weight="bold"))
        self.lbl_name.pack()
        self.lbl_rank = ctk.CTkLabel(side, text="", text_color=W.MUTED)
        self.lbl_rank.pack()
        self.lbl_conn = ctk.CTkLabel(side, text="● Conectado", text_color=W.GOOD, font=ctk.CTkFont(size=12))
        self.lbl_conn.pack(pady=(2, 22))

        self.nav_btns = {}
        for key, label in (("session", "📊   Sesión"), ("recs", "🎯   Recomendaciones"), ("profile", "👤   Mi perfil")):
            b = ctk.CTkButton(side, text=label, anchor="w", height=44, corner_radius=12,
                              fg_color="transparent", hover_color=W.CARD,
                              font=self._bf(15), command=lambda k=key: self._nav(k))
            b.pack(fill="x", padx=16, pady=3)
            self.nav_btns[key] = b
        ctk.CTkButton(side, text="Cerrar sesión", height=42, fg_color="#2a2a35", hover_color=W.BAD,
                      text_color="white", font=self._bf(14),
                      command=lambda: self.logout(False)).pack(side="bottom", fill="x", padx=16, pady=18)

        content = ctk.CTkFrame(self.main, fg_color="transparent")
        content.grid(row=0, column=1, sticky="nsew", padx=24, pady=20)
        content.grid_rowconfigure(0, weight=1)
        content.grid_columnconfigure(0, weight=1)
        self.pages = {}
        for key in ("session", "recs", "profile"):
            f = ctk.CTkFrame(content, fg_color="transparent")
            f.grid(row=0, column=0, sticky="nsew")
            self.pages[key] = f
        self.log = ctk.CTkLabel(content, text="", anchor="w", text_color=W.MUTED, font=ctk.CTkFont(size=12))
        self.log.grid(row=1, column=0, sticky="ew", pady=(10, 0))

        self._build_session_page(self.pages["session"])
        self._build_recs_page(self.pages["recs"])
        self._build_profile_page(self.pages["profile"])

    def _header(self, parent, title, subtitle=""):
        h = ctk.CTkFrame(parent, fg_color="transparent")
        h.pack(fill="x", pady=(0, 14))
        box = ctk.CTkFrame(h, fg_color="transparent")
        box.pack(side="left")
        ctk.CTkLabel(box, text=title, font=self._h1(), anchor="w").pack(anchor="w")
        if subtitle:
            ctk.CTkLabel(box, text=subtitle, text_color=W.MUTED, anchor="w").pack(anchor="w")
        return h

    def _build_session_page(self, p):
        h = self._header(p, "Sesión actual", "Se registra cada jugada mientras tienes la app abierta · doble clic abre el mapa")
        ctk.CTkButton(h, text="Nueva sesión", width=150, height=40, fg_color=W.ACCENT, hover_color=W.ACCENT_H,
                      text_color="white", font=self._bf(15), command=self.new_session).pack(side="right")
        row, self.sc = W.cards_row(p, [("n", "Jugadas"), ("acc", "Precisión (pases)"), ("fail", "Fallos"),
                                       ("time", "Duración"), ("adj", "Ajuste de dificultad")])
        row.pack(fill="x")
        self.lbl_adj = ctk.CTkLabel(p, text="", text_color=W.MUTED, anchor="w")
        self.lbl_adj.pack(fill="x", pady=(10, 10))
        f, self.tree_plays = W.make_tree(
            p, [("time", "Hora"), ("title", "Mapa"), ("mods", "Mods"), ("acc", "Acc"),
                ("miss", "Miss"), ("pp", "pp"), ("res", "Resultado")],
            [80, 560, 80, 90, 60, 70, 100],
            empty="Aún no hay jugadas en esta sesión.\nJuega un mapa y aparecerá aquí en unos segundos.")
        f.pack(fill="both", expand=True)
        self.tree_plays.bind("<Double-1>", self._open_play)

    def _build_recs_page(self, p):
        self._header(p, "Recomendaciones", "Clic en un mapa para abrirlo en la web · botón osu!direct para abrirlo en el juego")
        bar = ctk.CTkFrame(p, fg_color=W.CARD, corner_radius=16)
        bar.pack(fill="x", pady=(0, 8))
        fam = self.btn_family
        pf = self._bf(12)

        row1 = ctk.CTkFrame(bar, fg_color="transparent")
        row1.pack(fill="x", padx=18, pady=(12, 0))
        self.goal = Tabs(row1, list(GOAL_LABELS), self._bf(16), on_change=self._goal_changed)
        self.goal.pack(side="left")
        ctk.CTkLabel(row1, text="Mods", text_color=W.MUTED,
                     font=ctk.CTkFont(size=12)).pack(side="left", padx=(28, 6))
        self.mod_chips = ModChips(row1, pf, on_change=lambda _s: self._update_summary())
        self.mod_chips.pack(side="left")
        self.b_rec = ctk.CTkButton(
            row1, text="Recomendar", width=150, height=38, corner_radius=12, font=self._bf(14),
            fg_color=W.ACCENT, hover_color=W.ACCENT_H, text_color="white",
            text_color_disabled="#ffe3f0", command=self.run_recs)
        self.b_rec.pack(side="right")
        self.b_stop = ctk.CTkButton(
            row1, text="Detener", width=100, height=38, corner_radius=12, font=self._bf(13),
            fg_color="#2a2a35", hover_color=W.BAD, text_color="white", command=self._stop_run)

        ctk.CTkFrame(bar, height=1, fg_color=BORDER).pack(fill="x", padx=18, pady=(0, 12))

        row2 = ctk.CTkFrame(bar, fg_color="transparent")
        row2.pack(fill="x", padx=18)
        self.style_pill = Pill(row2, "Estilo", list(STYLE_LABELS), "Mi perfil", pf, fam,
                               on_change=lambda _v: self._update_summary())
        self.style_pill.pack(side="left", padx=(0, 8))
        self.pp_pill = Pill(row2, "pp", list(PP_RANGE_OPTIONS), "0.8× – 1.3× · amplio", pf, fam,
                            on_change=lambda _v: self._update_summary())
        self.pp_pill.pack(side="left", padx=(0, 8))
        self.maps_pill = Pill(row2, "Analizar", list(MAPS_OPTIONS), "1000 · equilibrado", pf, fam,
                              on_change=lambda _v: self._update_summary())
        self.maps_pill.pack(side="left", padx=(0, 8))
        self.b_adv = ctk.CTkButton(row2, text="⚙ Avanzado ▸", width=110, height=30, fg_color="transparent",
                                   hover_color="#2a2a35", text_color=W.MUTED, font=ctk.CTkFont(size=12),
                                   command=self._toggle_adv)
        self.b_adv.pack(side="right")

        self.lbl_summary = ctk.CTkLabel(bar, text="", text_color=W.MUTED, anchor="w",
                                        font=ctk.CTkFont(size=12))
        self.lbl_summary.pack(fill="x", padx=22, pady=(8, 12))

        self.adv = ctk.CTkFrame(bar, fg_color="transparent")
        self.adv_open = False
        ctk.CTkFrame(self.adv, height=1, fg_color=BORDER).pack(fill="x", padx=18)
        self.profile_only = Toggle(
            self.adv, "Éxito solo con mi perfil",
            "No consulta leaderboards: mucho más rápido, sin clears ni FC de referencia",
            command=self._update_summary, default=True)
        self.profile_only.pack(fill="x", padx=22, pady=(12, 10))
        self.use_pp_range = Toggle(
            self.adv, "Buscar por rango de pp deseado",
            f"Solo pestaña PP · ignora estrellas y tus mejores plays · tolerancia blanda ±{PP_SOFT * 100:.0f}%",
            command=self._pp_range_toggled)
        self.use_pp_range.pack(fill="x", padx=22, pady=(0, 6))
        self.pp_box = ctk.CTkFrame(self.adv, fg_color="transparent")
        ctk.CTkLabel(self.pp_box, text="Mín", text_color=W.MUTED, font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 6))
        self.e_pp_lo = ctk.CTkEntry(self.pp_box, width=90, height=32, corner_radius=10, border_width=1,
                                    border_color=BORDER, fg_color=PILL, justify="center")
        self.e_pp_lo.pack(side="left")
        ctk.CTkLabel(self.pp_box, text="Máx", text_color=W.MUTED, font=ctk.CTkFont(size=12)).pack(side="left", padx=(16, 6))
        self.e_pp_hi = ctk.CTkEntry(self.pp_box, width=90, height=32, corner_radius=10, border_width=1,
                                    border_color=BORDER, fg_color=PILL, justify="center")
        self.e_pp_hi.pack(side="left")
        ctk.CTkLabel(self.pp_box, text="pp", text_color=W.MUTED, font=ctk.CTkFont(size=12)).pack(side="left", padx=(8, 0))
        for e in (self.e_pp_lo, self.e_pp_hi):
            e.bind("<KeyRelease>", lambda _e: self._update_summary())
        self.use_top10 = Toggle(self.adv, "Basarme en mi top 10",
                                "Usa el promedio de tus 10 mejores plays como referencia, no solo la mejor",
                                command=self._update_summary)
        self.use_top10.pack(fill="x", padx=22, pady=(6, 10))
        self.use_session = Toggle(self.adv, "Usar mi sesión",
                                  "Ajusta dificultad y skills con las jugadas de hoy",
                                  command=self._update_summary, default=True)
        self.use_session.pack(fill="x", padx=22, pady=(0, 10))
        self.auto = Toggle(self.adv, "Recomendar automáticamente",
                           f"Genera nuevas recomendaciones cada {C.REC_EVERY_PLAYS} jugadas")
        self.auto.pack(fill="x", padx=22, pady=(0, 10))
        self.require_refs = Toggle(self.adv, "Solo mapas con referencias",
                                   f"Exige ≥{C.MIN_LB_SAMPLE} scores del mismo mod y al menos 1 FC (requiere leaderboards)")
        self.require_refs.pack(fill="x", padx=22, pady=(0, 14))

        self.rec_slot = ctk.CTkFrame(p, fg_color="transparent", height=8)
        self.rec_slot.pack(fill="x", pady=(0, 2))
        self.rec_bar = ctk.CTkProgressBar(self.rec_slot, mode="indeterminate", progress_color=W.ACCENT, height=4)

        rb = ctk.CTkFrame(p, fg_color="transparent")
        rb.pack(fill="x", pady=(2, 8))
        self.lbl_count = ctk.CTkLabel(rb, text="", font=self._bf(15), anchor="w")
        self.lbl_count.pack(side="left", padx=(4, 0))
        self.sort_pill = Pill(rb, "Orden", list(SORT_OPTIONS), "Éxito", pf, fam,
                              on_change=lambda _v: self._apply_view())
        self.sort_pill.pack(side="right")
        self.show_chips = ChipGroup(rb, SHOW_OPTIONS, 10, pf, on_change=lambda _v: self._apply_view())
        self.show_chips.pack(side="right", padx=(0, 10))
        ctk.CTkLabel(rb, text="Mostrar", text_color=W.MUTED, font=ctk.CTkFont(size=12)).pack(side="right", padx=(0, 4))

        self.rec_list = ctk.CTkScrollableFrame(p, fg_color="transparent", scrollbar_fg_color="transparent",
                                               scrollbar_button_color=W.SCROLL,
                                               scrollbar_button_hover_color=W.ACCENT)
        self.rec_list.pack(fill="both", expand=True)
        self._show_recs([])
        self._update_summary()

    def _toggle_adv(self):
        self.adv_open = not self.adv_open
        if self.adv_open:
            self.adv.pack(fill="x")
            self.b_adv.configure(text="⚙ Avanzado ▾", text_color=W.ACCENT)
        else:
            self.adv.pack_forget()
            self.b_adv.configure(text="⚙ Avanzado ▸", text_color=W.MUTED)

    def _pp_range_toggled(self):
        if self.use_pp_range.get():
            self._fill_pp_defaults()
            self.pp_box.pack(fill="x", padx=22, pady=(0, 10), after=self.use_pp_range)
        else:
            self.pp_box.pack_forget()
        self._update_summary()

    def _fill_pp_defaults(self):
        """Si los campos están vacíos, propone ±10% alrededor de tu mejor play."""
        if self.e_pp_lo.get().strip() or self.e_pp_hi.get().strip() or not self.prof:
            return
        top = max(d["pp_max"] for d in self.prof["by_mod"].values())
        self.e_pp_lo.insert(0, f"{round(top * 0.9 / 10) * 10:.0f}")
        self.e_pp_hi.insert(0, f"{round(top * 1.1 / 10) * 10:.0f}")

    def _manual_pp(self):
        """None si está apagado; (min, max) si es válido; 'error' si los campos no sirven."""
        if not self.use_pp_range.get():
            return None
        try:
            lo = float(self.e_pp_lo.get().strip().replace(",", "."))
            hi = float(self.e_pp_hi.get().strip().replace(",", "."))
        except ValueError:
            return "error"
        return (lo, hi) if 0 < lo < hi else "error"

    def _goal_changed(self, _value=None):
        skill = GOAL_LABELS[self.goal.get()] == "skillcap"
        opts = SORT_SKILLCAP if skill else SORT_OPTIONS
        self.sort_pill.set_options(list(opts), next(iter(opts)))
        if skill:
            self.pp_pill.pack_forget()
        else:
            self.pp_pill.pack(side="left", padx=(0, 8), before=self.maps_pill)
        self._update_summary()
        self._apply_view()

    def _sort_key(self):
        opts = SORT_SKILLCAP if GOAL_LABELS[self.goal.get()] == "skillcap" else SORT_OPTIONS
        return opts.get(self.sort_pill.get(), next(iter(opts.values())))

    def _apply_view(self):
        allr = self.recs_all
        if not allr:
            self.lbl_count.configure(text="")
            self._show_recs([])
            return
        ordered = sort_recs(allr, self._sort_key())
        n = self.show_chips.get()
        view = ordered if n is None else ordered[:n]
        self._show_recs(view)
        extra = f" · mostrando {len(view)}" if len(view) < len(allr) else ""
        self.lbl_count.configure(text=f"{len(allr)} mapas{extra}")

    def _ref_pp(self):
        """pp de referencia elegido: promedio del top 10 si el ajuste está activo y hay datos; si no, None."""
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
        self.lbl_summary.configure(text="  ·  ".join(parts))

    def _build_profile_page(self, p):
        h = self._header(p, "Mi perfil", "Calculado a partir de tu top 100")
        self.b_refresh = ctk.CTkButton(h, text="Actualizar perfil", width=170, height=40, fg_color=W.ACCENT,
                                       hover_color=W.ACCENT_H, text_color="white", font=self._bf(15),
                                       command=self.refresh_profile)
        self.b_refresh.pack(side="right")
        row, self.pc = W.cards_row(p, [("skill", "Skill"), ("mod", "Mod principal"), ("star", "Techo ★"),
                                       ("pp", "pp máximo"), ("bpm", "BPM cómodo"), ("acc", "Acc mediana")])
        row.pack(fill="x", pady=(0, 10))
        self.lbl_tags = ctk.CTkLabel(p, text="", text_color=W.MUTED, anchor="w")
        self.lbl_tags.pack(fill="x", pady=(0, 10))
        f, self.tree_prof = W.make_tree(
            p, [("mod", "Mod"), ("n", "Scores"), ("skill", "Skill"), ("ratio", "Speed/Aim"),
                ("p50", "★ mediana"), ("max", "★ máx"), ("pp", "pp mediana"), ("acc", "Acc")],
            [100, 80, 110, 110, 110, 110, 120, 110], empty="Sin datos de perfil.")
        f.pack(fill="both", expand=True)

    def _nav(self, key):
        self.pages[key].tkraise()
        for k, b in self.nav_btns.items():
            b.configure(fg_color=W.CARD if k == key else "transparent")

    def _show(self, view):
        self.login.pack_forget()
        self.main.pack_forget()
        (self.login if view == "login" else self.main).pack(fill="both", expand=True)

    # ---------------------------------------------------------- account menu
    def _avatar_menu(self):
        m = tk.Menu(self, tearoff=0, bg=W.CARD, fg="white", activebackground=W.ACCENT,
                    activeforeground="white", borderwidth=0, font=(self.font_family, 11))
        m.add_command(label=f"Conectado como {self.info['username'] if self.info else ''}", state="disabled")
        m.add_separator()
        m.add_command(label="Cambiar de usuario", command=lambda: self.logout(False, switch=True))
        m.add_command(label="Cerrar sesión", command=lambda: self.logout(False))
        m.add_command(label="Cerrar sesión y olvidar credenciales", command=lambda: self.logout(True))
        x, y = self.btn_avatar.winfo_rootx(), self.btn_avatar.winfo_rooty() + self.btn_avatar.winfo_height()
        try:
            m.tk_popup(x, y)
        finally:
            m.grab_release()

    def logout(self, forget, switch=False):
        self.epoch += 1
        self.stop_rec.set()
        if self.poller:
            self.poller.stop()
            self.poller = None
        self.tm = self.uid = self.prof = self.info = self.session_id = None
        self.rec_running = False
        self.new_since_rec = 0
        for t in (self.tree_plays, self.tree_prof):
            t.delete(*t.get_children())
        self.play_urls = {}
        self.session_scores = []
        self.recs_all = []
        self.last_adj = None
        self.top10_pp = None
        self.e_pp_lo.delete(0, "end")
        self.e_pp_hi.delete(0, "end")
        self.lbl_count.configure(text="")
        self._show_recs([])
        self._update_summary()
        self.rec_bar.stop()
        self.rec_bar.pack_forget()
        self.b_stop.pack_forget()
        self.b_rec.configure(state="normal", text="Recomendar")
        if forget:
            C.clear_credentials()
        self._prefill()
        if forget or switch:
            self.e_user.delete(0, "end")
        if switch:
            self.e_user.focus()
        self._login_busy(False, "Sesión cerrada.")
        self._show("login")

    # ------------------------------------------------------- session logic
    def _on_logged(self, payload):
        self.tm, self.info, self.prof, pil, _remember = payload
        self.uid = self.info["id"]
        self.stop_rec.clear()
        self._login_busy(False)
        self._set_avatar(pil)
        stats = self.info.get("statistics") or {}
        rank, pp = stats.get("global_rank"), stats.get("pp")
        self.lbl_name.configure(text=self.info["username"])
        self.lbl_rank.configure(text=(f"#{rank:,} · {pp:,.0f} pp" if rank and pp else
                                      f"{pp:,.0f} pp" if pp else ""))
        self._load_top10()
        self._fill_profile()
        if self.use_pp_range.get():
            self._fill_pp_defaults()
        self._update_summary()
        self._show("main")
        self._nav("session")
        self.new_session()

    def _set_avatar(self, pil):
        self.avatar_img = W.circle_image(pil, 88) if pil else W.placeholder(self.info["username"], 88)
        self.btn_avatar.configure(image=self.avatar_img)

    def _fill_profile(self):
        pr = self.prof
        m = pr["by_mod"][pr["main_mod"]]
        self.pc["skill"].set(m["skill"].capitalize(), W.ACCENT)
        self.pc["mod"].set(pr["main_mod"])
        self.pc["star"].set(f"{m['stars_max']:.2f}★")
        self.pc["pp"].set(f"{m['pp_max']:.0f}")
        lo, _mid, hi = pr["bpm_range"]
        self.pc["bpm"].set(f"{lo:.0f}–{hi:.0f}")
        self.pc["acc"].set(f"{m['acc_p50']*100:.2f}%")
        tags = pr.get("style_tags") or {}
        self.lbl_tags.configure(text="Patrones de tu top: " + (
            "  ·  ".join(f"{tag_label(t)} {v*100:.0f}%" for t, v in list(tags.items())[:5]) or "sin datos"))
        self.tree_prof.delete(*self.tree_prof.get_children())
        for i, (mod, d) in enumerate(pr["by_mod"].items()):
            self.tree_prof.insert("", "end", tags=("odd",) if i % 2 else (), values=(
                mod, d["n"], d["skill"], f"{d['speed_ratio']:.2f}", f"{d['stars_p50']:.2f}",
                f"{d['stars_max']:.2f}", f"{d['pp_p50']:.0f}", f"{d['acc_p50']*100:.2f}%"))

    def refresh_profile(self):
        if not self.tm:
            return
        ep, tm, uid = self.epoch, self.tm, self.uid
        self.b_refresh.configure(state="disabled")
        self.log.configure(text="Actualizando perfil...")

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
        self.tree_plays.delete(*self.tree_plays.get_children())
        self.play_urls = {}
        self.session_scores = []
        since = now_iso()
        self.session_id = self.store.new_session(self.uid, since)
        self.new_since_rec = 0
        ep = self.epoch
        self.poller = Poller(self.tm, self.uid, self.store, self.session_id, since,
                             lambda new: self.q.put(("plays", new, ep)), self._log)
        self.poller.start()
        self._refresh_session()
        self.log.configure(text="Sesión nueva: registrando jugadas...")

    def _row_from_score(self, s):
        bm, bs = s.get("beatmap") or {}, s.get("beatmapset") or {}
        mods = "".join(m["acronym"] for m in s["mods"] if m["acronym"] != "CL")
        t = datetime.fromisoformat(s["ended_at"].replace("Z", "+00:00")).astimezone().strftime("%H:%M")
        title = f"{bs.get('artist', '?')} - {bs.get('title', '?')} [{bm.get('version', '?')}]"
        pp = f"{s['pp']:.0f}" if s.get("pp") else "-"
        res = s.get("rank", "?") if s.get("passed") else "FAIL"
        return (t, title, mods or "NM", f"{s['accuracy']*100:.2f}%",
                s.get("statistics", {}).get("miss", 0), pp, res)

    def _open_play(self, _event):
        sel = self.tree_plays.selection()
        if sel and sel[0] in self.play_urls:
            webbrowser.open(self.play_urls[sel[0]])

    def _refresh_session(self):
        plays = self.store.session_plays(self.session_id) if self.session_id else []
        st = basic_stats(plays)
        self.sc["n"].set(str(st["n"]))
        self.sc["acc"].set("-" if st["acc"] is None else f"{st['acc']*100:.2f}%")
        fail = st["fail"]
        self.sc["fail"].set("-" if fail is None else f"{fail*100:.0f}%",
                            None if fail is None else (W.BAD if fail > 0.4 else W.GOOD))
        self.sc["time"].set(f"{st['minutes']:.0f} min")
        adj = session_adjust(self.prof, plays) if self.prof else None
        if adj:
            col = W.GOOD if adj["star_shift"] > 0.02 else W.BAD if adj["star_shift"] < -0.02 else None
            self.sc["adj"].set(f"{adj['star_shift']:+.2f}★", col)
        else:
            self.sc["adj"].set("—")
        self.lbl_adj.configure(text=describe(adj))
        return adj

    # --------------------------------------------------------- recomendador
    def _stop_run(self):
        self.stop_rec.set()
        self.b_stop.configure(state="disabled", text="Deteniendo…")

    def run_recs(self):
        if self.rec_running or not self.prof:
            return
        goal = GOAL_LABELS[self.goal.get()]
        manual = self._manual_pp() if goal == "pp" else None
        if manual == "error":
            self.log.configure(text="Rango de pp manual inválido: escribe números y que el mínimo sea menor que el máximo (Avanzado).")
            return
        self.rec_running = True
        self.new_since_rec = 0
        self.b_rec.configure(state="disabled", text="Calculando…")
        self.b_stop.configure(state="normal", text="Detener")
        self.b_stop.pack(side="right", padx=(0, 8))
        self.rec_bar.pack(fill="x")
        self.rec_bar.start()
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

    def _show_recs(self, recs):
        for child in self.rec_list.winfo_children():
            child.destroy()
        self.cards = []
        self.more_btn = None
        self.pending = list(recs)
        if not recs:
            ctk.CTkLabel(self.rec_list, text="Pulsa «Recomendar» para generar mapas.\n"
                         "Sin sesión activa se usa tu perfil histórico; con «Usar mi sesión» apagado "
                         "(en Avanzado) se ignora la sesión aunque estés jugando.",
                         text_color=W.MUTED, justify="center").pack(pady=60)
            return
        self._render_batch()

    def _render_batch(self):
        if self.more_btn is not None:
            self.more_btn.destroy()
            self.more_btn = None
        batch, self.pending = self.pending[:BATCH], self.pending[BATCH:]
        for c in batch:
            img = self.thumb_imgs.get(c.get("set_id")) or self.thumb_ph
            row = ctk.CTkFrame(self.rec_list, fg_color="transparent")
            row.pack(fill="x", pady=(0, 12), padx=(0, 8))
            make_badge(row, c.get("mods", "NM")).pack(side="left", fill="y", padx=(0, 10))
            make_direct_button(row, c["id"], on_fail=self._direct_failed).pack(side="right", fill="y", padx=(10, 0))
            card = W.RecCard(row, c, img, lambda url=c["url"]: webbrowser.open(url))
            card.pack(side="left", fill="x", expand=True)
            self.cards.append(card)
        self._load_thumbs(batch, self.epoch)
        if self.pending:
            self.more_btn = ctk.CTkButton(
                self.rec_list, text=f"Mostrar {min(BATCH, len(self.pending))} más  ({len(self.pending)} restantes)",
                height=42, fg_color="#2a2a35", hover_color=W.ACCENT_H, text_color="white",
                font=self._bf(14), command=self._render_batch)
            self.more_btn.pack(pady=(4, 16))

    def _load_thumbs(self, recs, ep):
        def work():
            for c in recs:
                sid = c.get("set_id")
                if not sid:
                    continue
                p = C.THUMBS_DIR / f"{sid}.jpg"
                try:
                    if not p.exists():
                        r = requests.get(f"https://assets.ppy.sh/beatmaps/{sid}/covers/list@2x.jpg", timeout=10)
                        if r.status_code != 200:
                            continue
                        p.write_bytes(r.content)
                    img = Image.open(p).convert("RGBA")
                    img.load()
                    self.q.put(("thumb", (sid, img), ep))
                except Exception:
                    continue
        threading.Thread(target=work, daemon=True).start()

    def _log(self, text):
        self.q.put(("log", text))

    # ------------------------------------------------------------ cola UI
    def _drain(self):
        try:
            while True:
                msg = self.q.get_nowait()
                kind = msg[0]
                if kind == "log":
                    self.log.configure(text=msg[1])
                    continue
                if msg[-1] != self.epoch:
                    continue
                if kind == "login_status":
                    self.login_status.configure(text=msg[1], text_color=W.MUTED)
                elif kind == "login_fail":
                    self._login_busy(False)
                    self.login_status.configure(text=msg[1], text_color=W.BAD)
                elif kind == "logged":
                    self._on_logged(msg[1])
                elif kind == "profile":
                    self.b_refresh.configure(state="normal")
                    if msg[1]:
                        self.prof = msg[1]
                        self._load_top10()
                        self._fill_profile()
                        self._update_summary()
                        self.log.configure(text="Perfil actualizado")
                elif kind == "plays":
                    for s in msg[1]:
                        n = len(self.tree_plays.get_children())
                        tags = ("fail",) if not s.get("passed") else (("odd",) if n % 2 else ())
                        iid = self.tree_plays.insert("", 0, values=self._row_from_score(s), tags=tags)
                        self.play_urls[iid] = f"https://osu.ppy.sh/b/{s['beatmap_id']}"
                        self.session_scores.append(s)
                    self.session_scores.sort(key=lambda x: x.get("ended_at", ""))
                    self.new_since_rec += len(msg[1])
                    self._refresh_session()
                    if self.auto.get() and self.new_since_rec >= C.REC_EVERY_PLAYS and not self.rec_running:
                        self.run_recs()
                elif kind == "recs":
                    self.rec_running = False
                    self.rec_bar.stop()
                    self.rec_bar.pack_forget()
                    self.b_stop.pack_forget()
                    self.b_rec.configure(state="normal", text="Recomendar")
                    self.recs_all = msg[1]
                    self._apply_view()
                    if not msg[1] and self.stop_rec.is_set():
                        self.log.configure(text="Búsqueda detenida antes de terminar: sin resultados.")
                    elif not msg[1]:
                        self.log.configure(text="Sin resultados con estos filtros: prueba otro estilo, más mods o un rango de pp más amplio.")
                    else:
                        self.log.configure(text=f"{len(msg[1])} recomendaciones calculadas")
                elif kind == "thumb":
                    sid, pil = msg[1]
                    img = W.rounded_image(pil, W.THUMB, 14)
                    self.thumb_imgs[sid] = img
                    for card in self.cards:
                        if card.rec.get("set_id") == sid:
                            card.set_thumb(img)
        except queue.Empty:
            pass
        self.after(250, self._drain)

    def _close(self):
        self.stop_rec.set()
        if self.poller:
            self.poller.stop()
        self.destroy()


def run():
    App().mainloop()
