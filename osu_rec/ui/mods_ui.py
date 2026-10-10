import customtkinter as ctk
from . import widgets as W
from .filters import PILL, PILL_HOVER, BORDER, TXT

MOD_COLORS = {"NM": "#4b5563", "HD": "#d97706", "DT": "#db2777", "HDDT": "#7c3aed"}
MOD_ORDER = ("NM", "HD", "DT")


class ModChips(ctk.CTkFrame):
    """Interruptores NM / HD / DT (multi-selección, siempre al menos uno activo)."""

    def __init__(self, master, font, on_change=None, default=("NM",)):
        super().__init__(master, fg_color="transparent")
        self.on_change = on_change
        self.sel = set(default)
        self.btns = {}
        for v in MOD_ORDER:
            b = ctk.CTkButton(self, text=v, font=font, width=46, height=30, corner_radius=15,
                              border_width=1, fg_color="transparent", hover_color=PILL_HOVER,
                              command=lambda x=v: self._toggle(x))
            b.pack(side="left", padx=2)
            self.btns[v] = b
        self._paint()

    def _toggle(self, v):
        new = set(self.sel) ^ {v}
        if not new:
            return
        self.sel = new
        self._paint()
        if self.on_change:
            self.on_change(set(self.sel))

    def _paint(self):
        for v, b in self.btns.items():
            on = v in self.sel
            b.configure(border_color=W.ACCENT if on else BORDER, text_color=TXT if on else W.MUTED,
                        fg_color=PILL if on else "transparent")

    def get(self):
        return set(self.sel)


def make_badge(parent, combo):
    """Columna de color a la izquierda de la tarjeta con los mods con los que se debe jugar."""
    col = MOD_COLORS.get(combo, "#4b5563")
    box = ctk.CTkFrame(parent, width=64, height=1, corner_radius=14, fg_color=col)
    box.pack_propagate(False)
    inner = ctk.CTkFrame(box, fg_color="transparent")
    inner.place(relx=0.5, rely=0.5, anchor="center")
    ctk.CTkLabel(inner, text="MODS", font=ctk.CTkFont(size=9, weight="bold"), text_color="#f3f4f6").pack()
    ctk.CTkLabel(inner, text=combo, font=ctk.CTkFont(size=16, weight="bold"), text_color="white").pack()
    return box
