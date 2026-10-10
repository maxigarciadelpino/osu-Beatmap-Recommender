import tkinter.font as tkfont
from tkinter import ttk
import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont

from .options import TAG_COLORS, tag_label

BG = "#15151a"
SIDE = "#1a1a21"
CARD = "#1f1f27"
CARD_ALT = "#252530"
HOVER = "#29293a"
ACCENT = "#ff66aa"
ACCENT_H = "#e0508f"
MUTED = "#9aa0a6"
GOOD = "#5bd68a"
WARN = "#f2c94c"
BAD = "#ff6b6b"
TEXT = "#e8e8ee"
SCROLL = "#3a3a4a"
THUMB = 84


def setup_fonts(root):
    avail = set(tkfont.families(root))
    family = next((f for f in ("Segoe UI Variable Text", "Segoe UI", "Inter", "SF Pro Text",
                               "Helvetica Neue", "Arial") if f in avail), None)
    if family is None:
        family = tkfont.nametofont("TkDefaultFont").actual("family")
    try:
        ctk.ThemeManager.theme["CTkFont"]["family"] = family
        ctk.ThemeManager.theme["CTkFont"]["size"] = 14
    except Exception:
        pass
    return family


def button_family(root):
    avail = set(tkfont.families(root))
    for f in ("Bahnschrift SemiBold", "Bahnschrift", "Segoe UI Black", "Segoe UI Semibold", "Trebuchet MS"):
        if f in avail:
            return f
    return None


def style_dark(family="Segoe UI"):
    s = ttk.Style()
    s.theme_use("default")
    s.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
    s.configure("Treeview", background=CARD, foreground=TEXT, fieldbackground=CARD,
                rowheight=34, borderwidth=0, relief="flat", font=(family, 11))
    s.configure("Treeview.Heading", background=CARD_ALT, foreground="#ffffff", relief="flat",
                borderwidth=0, padding=(10, 8), font=(family, 11, "bold"))
    s.map("Treeview", background=[("selected", ACCENT_H)], foreground=[("selected", "#ffffff")])
    s.map("Treeview.Heading", background=[("active", "#34344a")])


def make_tree(parent, columns, widths, height=10, empty=""):
    frame = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=14)
    tree = ttk.Treeview(frame, columns=[c for c, _ in columns], show="headings",
                        height=height, selectmode="browse")
    for (cid, label), wd in zip(columns, widths):
        tree.heading(cid, text=label, anchor="w")
        tree.column(cid, width=wd, minwidth=40, anchor="w", stretch=(cid in ("name", "title")))
    tree.tag_configure("odd", background="#23232d")
    tree.tag_configure("fail", foreground=BAD)
    sb = ctk.CTkScrollbar(frame, orientation="vertical", command=tree.yview, width=12,
                          fg_color="transparent", button_color=SCROLL, button_hover_color=ACCENT)
    tree.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y", padx=(0, 6), pady=10)
    tree.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=10)

    tree.empty_label = ctk.CTkLabel(frame, text=empty, text_color=MUTED, wraplength=520, justify="center")

    def tick():
        if not tree.winfo_exists():
            return
        if tree.get_children():
            tree.empty_label.place_forget()
        elif empty:
            tree.empty_label.place(relx=0.5, rely=0.55, anchor="center")
        tree.after(400, tick)
    tick()
    return frame, tree


class StatCard(ctk.CTkFrame):
    def __init__(self, parent, title, value="-"):
        super().__init__(parent, fg_color=CARD, corner_radius=14)
        ctk.CTkLabel(self, text=title, text_color=MUTED, font=ctk.CTkFont(size=12)).pack(
            anchor="w", padx=16, pady=(12, 0))
        self.v = ctk.CTkLabel(self, text=value, font=ctk.CTkFont(size=24, weight="bold"))
        self.v.pack(anchor="w", padx=16, pady=(0, 12))

    def set(self, value, color=None):
        self.v.configure(text=value, text_color=color or TEXT)


def cards_row(parent, specs):
    row = ctk.CTkFrame(parent, fg_color="transparent")
    out = {}
    for i, (key, title) in enumerate(specs):
        row.grid_columnconfigure(i, weight=1, uniform="c")
        c = StatCard(row, title)
        c.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 10, 0))
        out[key] = c
    return row, out


def circle_image(img, size):
    big = size * 3
    img = img.convert("RGBA").resize((big, big))
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, big - 1, big - 1), fill=255)
    out = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return ctk.CTkImage(light_image=out, dark_image=out, size=(size, size))


def placeholder(name, size):
    big = size * 3
    img = Image.new("RGBA", (big, big), ACCENT)
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", int(big * 0.5))
    except Exception:
        font = ImageFont.load_default()
    d.text((big / 2, big / 2), (name or "?")[0].upper(), fill="white", font=font, anchor="mm")
    return circle_image(img, size)


def rounded_image(img, size, radius=14):
    big = size * 3
    img = img.convert("RGBA")
    s = min(img.size)
    left, top = (img.width - s) // 2, (img.height - s) // 2
    img = img.crop((left, top, left + s, top + s)).resize((big, big))
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, big - 1, big - 1), radius=radius * 3, fill=255)
    out = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return ctk.CTkImage(light_image=out, dark_image=out, size=(size, size))


def thumb_placeholder(size=THUMB, radius=14):
    return rounded_image(Image.new("RGBA", (size, size), "#2a2a35"), size, radius)


class RecCard(ctk.CTkFrame):
    def __init__(self, parent, rec, thumb, on_click):
        super().__init__(parent, fg_color=CARD, corner_radius=16)
        self.rec, self.on_click = rec, on_click
        self.grid_columnconfigure(1, weight=1)

        self.thumb = ctk.CTkLabel(self, text="", image=thumb, width=THUMB, height=THUMB)
        self.thumb.grid(row=0, column=0, rowspan=3, padx=(14, 16), pady=14)

        ctk.CTkLabel(self, text=rec["name"], anchor="w", justify="left", wraplength=500,
                     font=ctk.CTkFont(size=15, weight="bold")).grid(row=0, column=1, sticky="w", pady=(14, 0))
        secs = int(rec.get("length_eff", rec.get("length", 0)) or 0)
        meta = (f"{rec['stars']:.2f}★   ·   {rec['bpm_eff']:.0f} BPM   ·   "
                f"{secs // 60}:{secs % 60:02d}   ·   ratio {rec['sr']:.2f}")
        ctk.CTkLabel(self, text=meta, text_color=MUTED, anchor="w").grid(row=1, column=1, sticky="w", pady=(2, 6))

        chips = ctk.CTkFrame(self, fg_color="transparent")
        chips.grid(row=2, column=1, sticky="w", pady=(0, 14))
        for t in rec.get("tags") or []:
            ctk.CTkLabel(chips, text=f"  {tag_label(t)}  ", text_color="white", height=22, corner_radius=8,
                         fg_color=TAG_COLORS.get(t, "#6b7280"),
                         font=ctk.CTkFont(size=11, weight="bold")).pack(side="left", padx=(0, 6))

        right = ctk.CTkFrame(self, fg_color="transparent")
        right.grid(row=0, column=2, rowspan=3, padx=(10, 20), pady=14, sticky="e")
        ctk.CTkLabel(right, text=f"{rec['pp']:.0f} pp", text_color=ACCENT,
                     font=ctk.CTkFont(size=24, weight="bold")).pack(anchor="e")

        known = rec.get("p_known", True)
        p = rec["p"]
        if known:
            ptxt, pcol = f"Éxito {p * 100:.0f}%", GOOD if p >= 0.55 else WARN if p >= 0.35 else BAD
        else:
            ptxt, pcol = "Éxito n/d", MUTED
        ctk.CTkLabel(right, text=ptxt, text_color=pcol,
                     font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="e")

        sk = rec.get("skill")
        if sk is not None:
            scol = GOOD if sk >= 0.7 else WARN if sk >= 0.45 else BAD
            ctk.CTkLabel(right, text=f"Afinidad con tu estilo {sk * 100:.0f}%", text_color=scol,
                         font=ctk.CTkFont(size=12)).pack(anchor="e")

        cr, n = rec.get("cr"), rec.get("n_lb", 0)
        if cr is None:
            clear = f"Sin referencia ({n}/{rec.get('min_sample', 8)} scores)"
        else:
            clear = f"≤3 miss {cr * 100:.0f}%  ·  FC {rec.get('n_fc', 0)}/{n}"
        ctk.CTkLabel(right, text=clear, text_color=MUTED, font=ctk.CTkFont(size=12)).pack(anchor="e")

        self._wire(self)

    def _wire(self, w):
        for ev, fn in (("<Button-1>", self._click), ("<Enter>", self._enter), ("<Leave>", self._leave)):
            try:
                w.bind(ev, fn, add="+")
            except Exception:
                pass
        try:
            w.configure(cursor="hand2")
        except Exception:
            pass
        for ch in w.winfo_children():
            self._wire(ch)

    def _click(self, _e=None):
        self.on_click()

    def _enter(self, _e=None):
        self.configure(fg_color=HOVER)

    def _leave(self, _e=None):
        try:
            x, y = self.winfo_pointerxy()
            wdg = self.winfo_containing(x, y)
            inside = wdg is not None and str(wdg).startswith(str(self))
        except Exception:
            inside = False
        if not inside:
            self.configure(fg_color=CARD)

    def set_thumb(self, img):
        self.thumb.configure(image=img)
