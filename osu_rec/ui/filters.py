import time
import tkinter as tk
import customtkinter as ctk
from . import widgets as W

PILL = "#22222e"
PILL_HOVER = "#2b2b39"
BORDER = "#33333f"
TXT = "#f2f2f5"


class Tabs(ctk.CTkFrame):
    """Pestañas de texto con línea de acento bajo la activa (sin fondo propio)."""

    def __init__(self, master, values, font, on_change=None):
        super().__init__(master, fg_color="transparent")
        self.values, self.on_change = list(values), on_change
        self.btns, self.bars = {}, {}
        for i, v in enumerate(self.values):
            col = ctk.CTkFrame(self, fg_color="transparent")
            col.pack(side="left", padx=(0 if i == 0 else 22, 0))
            b = ctk.CTkButton(col, text=v, font=font, width=10, height=30, fg_color="transparent",
                              hover=False, text_color=W.MUTED, corner_radius=6,
                              command=lambda x=v: self._click(x))
            b.pack()
            bar = ctk.CTkFrame(col, height=3, corner_radius=2, fg_color="transparent")
            bar.pack(fill="x", padx=6)
            self.btns[v], self.bars[v] = b, bar
        self.value = self.values[0]
        self.set(self.value)

    def _click(self, v):
        if v != self.value:
            self.set(v)
            if self.on_change:
                self.on_change(v)

    def get(self):
        return self.value

    def set(self, v):
        self.value = v
        for k in self.values:
            on = k == v
            self.btns[k].configure(text_color=W.ACCENT if on else W.MUTED)
            self.bars[k].configure(fg_color=W.ACCENT if on else "transparent")


class Pill(ctk.CTkButton):
    """Filtro plano tipo etiqueta; al hacer clic abre una lista emergente. Borde rosado si no es el valor por defecto."""

    def __init__(self, master, label, options, default, font, family, on_change=None, width=None):
        super().__init__(master, text="", font=font, height=34, corner_radius=17, border_width=1,
                         fg_color=PILL, hover_color=PILL_HOVER, border_color=BORDER, text_color=TXT,
                         command=self._p_open, **({"width": width} if width else {}))
        self.p_label, self.p_family, self.p_cb = label, family, on_change
        self.p_opts = list(options)
        self.p_default = default
        self.p_value = default
        self.p_closed_at = 0.0
        self._p_refresh()

    def _p_refresh(self):
        self.configure(text=f"{self.p_label}:  {self.p_value}  ▾" if self.p_label else f"{self.p_value}  ▾",
                       border_color=W.ACCENT if self.p_value != self.p_default else BORDER)

    def get(self):
        return self.p_value

    def set(self, v):
        self.p_value = v
        self._p_refresh()

    def set_options(self, options, default):
        self.p_opts, self.p_default = list(options), default
        self.set(default)

    def _p_mark_closed(self):
        self.p_closed_at = time.time()

    def _p_open(self):
        if time.time() - self.p_closed_at < 0.3:
            return
        PopupList(self, self.p_opts, self.p_value, self.p_family, self._p_pick, on_close=self._p_mark_closed)

    def _p_pick(self, v):
        changed = v != self.p_value
        self.set(v)
        if changed and self.p_cb:
            self.p_cb(v)


class ChipGroup(ctk.CTkFrame):
    """Grupo de botones pequeños (uno activo) con borde rosado en el activo."""

    def __init__(self, master, options, default, font, on_change=None):
        super().__init__(master, fg_color="transparent")
        self.options, self.on_change = list(options), on_change
        self.btns = {}
        for label, val in self.options:
            b = ctk.CTkButton(self, text=label, font=font, height=30, width=48, corner_radius=15,
                              border_width=1, fg_color="transparent", hover_color=PILL_HOVER,
                              command=lambda v=val: self._click(v))
            b.pack(side="left", padx=3)
            self.btns[val] = b
        self.value = default
        self.set(default)

    def _click(self, v):
        if v != self.value:
            self.set(v)
            if self.on_change:
                self.on_change(v)

    def get(self):
        return self.value

    def set(self, v):
        self.value = v
        for val, b in self.btns.items():
            on = val == v
            b.configure(border_color=W.ACCENT if on else BORDER, text_color=TXT if on else W.MUTED,
                        fg_color=PILL if on else "transparent")


class PopupList(tk.Toplevel):
    """Lista emergente propia: fondo del programa, filas planas con hover y la opción actual en rosa."""

    def __init__(self, anchor, options, current, family, on_pick, on_close=None):
        root = anchor.winfo_toplevel()
        super().__init__(root)
        self.on_pick, self.on_close, self.root, self.bind_id = on_pick, on_close, root, None
        self.withdraw()
        self.overrideredirect(True)
        try:
            self.attributes("-topmost", True)
        except tk.TclError:
            pass
        self.configure(bg=BORDER)
        inner = tk.Frame(self, bg=W.CARD)
        inner.pack(padx=1, pady=1)
        width = max(anchor.winfo_width(), 190)
        font = ctk.CTkFont(family=family, size=13)
        font_on = ctk.CTkFont(family=family, size=13, weight="bold")
        tk.Frame(inner, bg=W.CARD, height=6).pack()
        for opt in options:
            on = opt == current
            ctk.CTkButton(
                inner, text=("●  " if on else "     ") + opt, anchor="w", width=width - 12, height=32,
                corner_radius=8, fg_color="transparent", hover_color=PILL_HOVER,
                text_color=W.ACCENT if on else TXT, font=font_on if on else font,
                command=lambda o=opt: self._pick(o)).pack(padx=6, pady=1)
        tk.Frame(inner, bg=W.CARD, height=6).pack()
        self.update_idletasks()
        x = anchor.winfo_rootx()
        y = anchor.winfo_rooty() + anchor.winfo_height() + 6
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        x = max(0, min(x, sw - self.winfo_reqwidth() - 8))
        if y + self.winfo_reqheight() > sh - 40:
            y = max(0, anchor.winfo_rooty() - self.winfo_reqheight() - 6)
        self.geometry(f"+{x}+{y}")
        self.deiconify()
        self.bind("<Escape>", lambda _e: self._close())
        self.bind("<FocusOut>", lambda _e: self.after(150, self._maybe_close))
        self.bind_id = root.bind("<Button-1>", lambda _e: self._close(), add="+")
        try:
            self.focus_force()
        except tk.TclError:
            pass

    def _maybe_close(self):
        try:
            if self.focus_displayof() is None:
                self._close()
        except Exception:
            self._close()

    def _pick(self, v):
        self._close()
        self.on_pick(v)

    def _close(self):
        if self.bind_id is not None:
            try:
                self.root.unbind("<Button-1>", self.bind_id)
            except Exception:
                pass
            self.bind_id = None
        if self.on_close:
            cb, self.on_close = self.on_close, None
            cb()
        try:
            self.destroy()
        except Exception:
            pass


class Toggle(ctk.CTkFrame):
    """Fila de ajuste: título y descripción a la izquierda, interruptor a la derecha."""

    OFF_TRACK = "#2f2f3c"
    OFF_KNOB = "#8a8a98"

    def __init__(self, master, title, desc, command=None, default=False):
        super().__init__(master, fg_color="transparent")
        self.t_cmd = command
        text = ctk.CTkFrame(self, fg_color="transparent")
        text.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(text, text=title, anchor="w", text_color=TXT,
                     font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(text, text=desc, anchor="w", text_color=W.MUTED,
                     font=ctk.CTkFont(size=11)).pack(anchor="w")
        self.t_sw = ctk.CTkSwitch(
            self, text="", width=48, switch_width=44, switch_height=22, corner_radius=11, border_width=3,
            fg_color=self.OFF_TRACK, progress_color=W.ACCENT, button_color=self.OFF_KNOB,
            button_hover_color=self.OFF_KNOB, command=self._changed)
        self.t_sw.pack(side="right", padx=(16, 0))
        if default:
            self.t_sw.select()
        self._restyle()

    def _restyle(self):
        col = "white" if self.t_sw.get() else self.OFF_KNOB
        self.t_sw.configure(button_color=col, button_hover_color=col)

    def _changed(self):
        self._restyle()
        if self.t_cmd:
            self.t_cmd()

    def get(self):
        return int(self.t_sw.get())

    def select(self):
        self.t_sw.select()
        self._restyle()

    def deselect(self):
        self.t_sw.deselect()
        self._restyle()
