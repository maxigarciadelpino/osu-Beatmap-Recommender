import faulthandler
import sys
import threading
import traceback
from pathlib import Path

if getattr(sys, "frozen", False):
    BASE = Path(sys.executable).resolve().parent
else:
    BASE = Path(__file__).resolve().parent
LOG = BASE / "error.log"
DEBUG = BASE / "debug.log"


class _Tee:
    def __init__(self, *streams):
        self.streams = [s for s in streams if s is not None]

    def write(self, text):
        for s in self.streams:
            try:
                s.write(text)
            except Exception:
                pass
        return len(text)

    def flush(self):
        for s in self.streams:
            try:
                s.flush()
            except Exception:
                pass


def _setup_debug():
    """Guarda en debug.log todo lo que normalmente se pierde al abrir sin terminal (errores, avisos de Qt, pasos
    de arranque). Si el programa se queda colgado, a los 25 s vuelca dónde está atascado."""
    try:
        f = open(DEBUG, "w", buffering=1, encoding="utf-8")
    except Exception:
        return
    sys.stderr = _Tee(sys.stderr, f)
    if sys.stdout is None:
        sys.stdout = f
    try:
        faulthandler.enable(f)
        faulthandler.dump_traceback_later(25, file=f)
    except Exception:
        pass

    def hook(exc_type, exc, tb):
        f.write("".join(traceback.format_exception(exc_type, exc, tb)))
        f.flush()

    sys.excepthook = hook
    threading.excepthook = lambda a: hook(a.exc_type, a.exc_value, a.exc_traceback)


def _load_run():
    """Usa la interfaz Qt (PySide6); si PySide6 no está instalado, cae a la interfaz CustomTkinter."""
    try:
        import PySide6  # noqa: F401
    except ImportError:
        from osu_rec.ui.main_window import run
        return run
    from osu_rec.qt.launcher import run
    return run


def main():
    _setup_debug()
    try:
        _load_run()()
    except SystemExit:
        raise
    except Exception:
        text = traceback.format_exc()
        try:
            LOG.write_text(text, encoding="utf-8")
        except Exception:
            pass
        sys.stderr.write(text)
        msg = ("osu! Recommender no pudo iniciar.\n\nDetalles en:\n" + str(LOG) +
               "\n\nSi falta algun paquete, ejecuta dependencies.bat")
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, msg, "osu! Recommender", 0x10)
        except Exception:
            pass


if __name__ == "__main__":
    main()
