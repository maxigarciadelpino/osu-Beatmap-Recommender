import os
import sys
import webbrowser
import customtkinter as ctk
from . import widgets as W
from .filters import PILL, BORDER, TXT


def direct_url(beatmap_id):
    """Enlace del protocolo de osu!: abre ese beatmap (dificultad) dentro del cliente."""
    return f"osu://b/{beatmap_id}"


def open_direct(beatmap_id):
    """Abre el mapa en osu! (osu!direct / navegador de mapas de lazer). Devuelve False si falla."""
    url = direct_url(beatmap_id)
    try:
        if sys.platform.startswith("win"):
            os.startfile(url)
        else:
            webbrowser.open(url)
        return True
    except Exception:
        return False


def make_direct_button(parent, beatmap_id, on_fail=None):
    def go():
        if not open_direct(beatmap_id) and on_fail:
            on_fail(beatmap_id)

    return ctk.CTkButton(parent, text="osu!\ndirect", width=72, height=28, corner_radius=14, border_width=1,
                         fg_color=PILL, border_color=BORDER, hover_color=W.ACCENT, text_color=TXT,
                         font=ctk.CTkFont(size=12, weight="bold"), command=go)
