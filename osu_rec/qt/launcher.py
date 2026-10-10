import faulthandler
import json
import sys
from pathlib import Path


def _log(msg):
    print(msg, file=sys.stderr, flush=True)


def _state_file():
    try:
        from .. import config as C
        return Path(C.DATA_DIR) / "window.json"
    except Exception:
        return Path(__file__).resolve().parents[2] / "window.json"


def _restore_window(win, app):
    """Recupera posición y tamaño de la última vez; si no hay datos (o no caben) la ajusta a tu pantalla."""
    from PySide6.QtCore import QByteArray
    screen = app.primaryScreen().availableGeometry()
    win.setMinimumSize(min(1120, screen.width() - 20), min(720, screen.height() - 40))
    ok = False
    try:
        data = json.loads(_state_file().read_text(encoding="utf-8"))
        ok = bool(win.restoreGeometry(QByteArray.fromBase64(data["geometry"].encode("ascii"))))
    except Exception:
        ok = False
    if not ok:
        width, height = min(1320, screen.width() - 40), min(860, screen.height() - 60)
        win.resize(width, height)
        win.move(screen.x() + (screen.width() - width) // 2, screen.y() + (screen.height() - height) // 2)
    _log(f"[osu] geometria {'restaurada' if ok else 'por defecto'}: {win.geometry()}")


def _save_window(win):
    try:
        geo = bytes(win.saveGeometry().toBase64()).decode("ascii")
        _state_file().write_text(json.dumps({"geometry": geo}), encoding="utf-8")
    except Exception as e:
        _log(f"[osu] no se pudo guardar la posicion de la ventana: {e}")


def _bring_front(win):
    """Segunda llamada a show: Windows ignora la primera si el proceso se lanzó con la ventana oculta."""
    win.showNormal()
    win.raise_()
    win.activateWindow()
    _log(f"[osu] ventana al frente: visible={win.isVisible()} geometria={win.geometry()}")


def _auto_login(win, app):
    """Si hay credenciales guardadas inicia sesión sola. Mantén Shift al abrir para evitarlo."""
    from PySide6.QtCore import Qt
    try:
        if app.keyboardModifiers() & Qt.ShiftModifier:
            _log("[osu] Shift pulsado: sin inicio de sesion automatico")
            return
    except Exception:
        pass
    if all(e.text().strip() for e in (win.e_user, win.e_id, win.e_secret)):
        _log("[osu] credenciales guardadas: iniciando sesion automaticamente")
        win.login_action()


def run():
    """Arranque de la interfaz Qt con registro paso a paso en debug.log para detectar dónde se detiene."""
    _log("[osu] importando Qt...")
    from PySide6.QtCore import QTimer, qInstallMessageHandler
    from PySide6.QtWidgets import QApplication
    from . import theme as T

    qInstallMessageHandler(lambda mode, ctx, msg: _log(f"[qt] {msg}"))
    _log("[osu] creando QApplication...")
    app = QApplication.instance() or QApplication(sys.argv)
    _log(f"[osu] plataforma de Qt: {app.platformName()}")
    family = T.setup_fonts(app)
    _log(f"[osu] fuente elegida: {family}")
    app.setStyleSheet(T.stylesheet(family))
    from . import extras
    extras.apply()
    _log("[osu] cargando la ventana principal...")
    from .profile_view import ProfileWindow
    win = ProfileWindow(family)
    _restore_window(win, app)
    app.aboutToQuit.connect(lambda: _save_window(win))
    _log("[osu] mostrando la ventana...")
    win.show()
    QTimer.singleShot(250, lambda: _bring_front(win))
    QTimer.singleShot(500, lambda: _auto_login(win, app))
    try:
        faulthandler.cancel_dump_traceback_later()
    except Exception:
        pass
    sys.exit(app.exec())
