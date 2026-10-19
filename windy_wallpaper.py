"""
Windy Live Wallpaper for Windows 10/11
--------------------------------------
Renders Windy's live weather map (rain / thunder by default) as your desktop
wallpaper, behind the desktop icons. Controlled from a system-tray icon.

Requires: Python 3.9+, the Edge WebView2 runtime (preinstalled on Windows 11).
"""
import ctypes
import json
import os
import sys
import threading
import winreg
from ctypes import wintypes
from pathlib import Path
from urllib.parse import urlencode

import pystray
import webview
from PIL import Image, ImageDraw

APP_NAME = "WindyWallpaper"
WINDOW_TITLE = "WindyWallpaperHost"
APP_DIR = (
    Path(sys.executable).parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent
)
# Config lives in %APPDATA% so it stays writable even when installed to Program Files.
DATA_DIR = Path(os.environ.get("APPDATA", str(APP_DIR))) / APP_NAME
DATA_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_PATH = DATA_DIR / "config.json"

DEFAULTS = {
    "lat": -29.208,
    "lon": 26.175,
    "zoom": 5,
    "overlay": "rain",          # rain | thunder | rainAccu | wind | clouds | temp | pressure
    "product": "ecmwf",         # ecmwf | gfs | icon ...
    "pressure_isolines": True,  # the "i:pressure" part of your link
    "refresh_minutes": 30,      # reload so forecast data stays current
    "autoplay": True,           # try to start Windy's time animation
    "custom_url": "",           # if set, this exact URL is loaded instead
}

OVERLAYS = {
    "Rain": "rain",
    "Thunderstorms": "thunder",
    "Rain accumulation": "rainAccu",
    "Wind": "wind",
    "Clouds": "clouds",
    "Temperature": "temp",
    "Pressure": "pressure",
}


# ----------------------------------------------------------------- config ---
def load_config():
    cfg = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        try:
            cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except Exception:
            pass
    else:
        save_config(cfg)
    return cfg


def save_config(cfg):
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def build_url(cfg):
    if cfg["custom_url"]:
        return cfg["custom_url"]
    params = {
        "lat": cfg["lat"],
        "lon": cfg["lon"],
        "detailLat": cfg["lat"],
        "detailLon": cfg["lon"],
        "zoom": cfg["zoom"],
        "level": "surface",
        "overlay": cfg["overlay"],
        "product": cfg["product"],
        "menu": "",
        "message": "",
        "marker": "",
        "calendar": "now",
        "pressure": "true" if cfg["pressure_isolines"] else "",
        "type": "map",
        "location": "coordinates",
        "detail": "",
        "metricWind": "default",
        "metricTemp": "default",
        "radarRange": "-1",
    }
    return "https://embed.windy.com/embed2.html?" + urlencode(params)


# ------------------------------------------------------------------ win32 ---
user32 = ctypes.windll.user32
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # physical pixels
except Exception:
    pass

HWND = wintypes.HWND
user32.FindWindowW.restype = HWND
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowExW.restype = HWND
user32.FindWindowExW.argtypes = [HWND, HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.SetParent.restype = HWND
user32.SetParent.argtypes = [HWND, HWND]
user32.SetWindowPos.argtypes = [HWND, HWND, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.GetWindowRect.argtypes = [HWND, ctypes.POINTER(wintypes.RECT)]
user32.ShowWindow.argtypes = [HWND, ctypes.c_int]
user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.GetWindowLongPtrW.argtypes = [HWND, ctypes.c_int]
user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.SetWindowLongPtrW.argtypes = [HWND, ctypes.c_int, ctypes.c_ssize_t]
user32.SendMessageTimeoutW.argtypes = [HWND, wintypes.UINT, wintypes.WPARAM,
                                       wintypes.LPARAM, wintypes.UINT, wintypes.UINT,
                                       ctypes.c_void_p]
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, HWND, wintypes.LPARAM)

GWL_STYLE, GWL_EXSTYLE = -16, -20
WS_POPUP, WS_CHILD = 0x80000000, 0x40000000
WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE = 0x80, 0x08000000
SWP_NOACTIVATE, SWP_FRAMECHANGED, SWP_SHOWWINDOW = 0x10, 0x20, 0x40
HWND_TOP = HWND(0)


def _find_classic_workerw():
    """Win10 / early Win11: WorkerW that sits behind the desktop icons."""
    found = []

    def cb(hwnd, _):
        if user32.FindWindowExW(hwnd, None, "SHELLDLL_DefView", None):
            nxt = user32.FindWindowExW(None, hwnd, "WorkerW", None)
            if nxt:
                found.append(nxt)
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return found[0] if found else None


def attach_to_desktop():
    hwnd = user32.FindWindowW(None, WINDOW_TITLE)
    progman = user32.FindWindowW("Progman", None)
    if not hwnd or not progman:
        return None

    # Ask Explorer to spawn the WorkerW layer used for wallpapers.
    user32.SendMessageTimeoutW(progman, 0x052C, 0xD, 0x1, 0, 1000, None)

    insert_after = HWND_TOP
    child_worker = user32.FindWindowExW(progman, None, "WorkerW", None)
    if child_worker:  # Windows 11 24H2+: WorkerW is a child of Progman
        parent = progman
        defview = user32.FindWindowExW(progman, None, "SHELLDLL_DefView", None)
        if defview:
            insert_after = defview  # sit directly beneath the icons
    else:
        parent = _find_classic_workerw() or progman

    style = user32.GetWindowLongPtrW(hwnd, GWL_STYLE)
    user32.SetWindowLongPtrW(hwnd, GWL_STYLE, (style & ~WS_POPUP) | WS_CHILD)
    ex = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE)
    user32.SetParent(hwnd, parent)

    # Cover every monitor (virtual screen), in the parent's coordinates.
    vx, vy = user32.GetSystemMetrics(76), user32.GetSystemMetrics(77)
    vw, vh = user32.GetSystemMetrics(78), user32.GetSystemMetrics(79)
    rect = wintypes.RECT()
    user32.GetWindowRect(parent, ctypes.byref(rect))
    user32.SetWindowPos(hwnd, insert_after, vx - rect.left, vy - rect.top, vw, vh,
                        SWP_NOACTIVATE | SWP_FRAMECHANGED | SWP_SHOWWINDOW)
    return hwnd


def restore_wallpaper():
    # SPI_SETDESKWALLPAPER with NULL = re-read & repaint the normal wallpaper
    user32.SystemParametersInfoW(0x0014, 0, None, 3)


# --------------------------------------------------------------- autostart ---
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def autostart_enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, APP_NAME)
            return True
    except OSError:
        return False


def set_autostart(enable):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if enable:
            if getattr(sys, "frozen", False):
                cmd = f'"{sys.executable}"'
            else:
                pyw = Path(sys.executable).with_name("pythonw.exe")
                cmd = f'"{pyw}" "{Path(__file__).resolve()}"'
            winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(k, APP_NAME)
            except OSError:
                pass


# --------------------------------------------------------------------- app ---
# Best-effort: click Windy's play button so the forecast animates continuously.
AUTOPLAY_JS = """
(function () {
  let tries = 0;
  const t = setInterval(() => {
    const btn = document.querySelector(
      '#playpause, #play-pause, .play-pause, [data-do="play"], [data-do="playpause"]');
    if (btn) { btn.click(); clearInterval(t); }
    if (++tries > 20) clearInterval(t);
  }, 1000);
})();
"""


class WallpaperApp:
    def __init__(self):
        self.cfg = load_config()
        self.window = None
        self.icon = None
        self.visible = True
        self.stop_event = threading.Event()

    # -- page control
    def reload(self):
        self.window.load_url(build_url(self.cfg))
        if self.cfg["autoplay"]:
            self.window.events.loaded.wait(20)
            self.window.evaluate_js(AUTOPLAY_JS)

    def set_overlay(self, overlay):
        self.cfg["overlay"] = overlay
        save_config(self.cfg)
        self.reload()

    def toggle_visible(self):
        self.visible = not self.visible
        hwnd = user32.FindWindowW(None, WINDOW_TITLE)
        if hwnd:
            user32.ShowWindow(hwnd, 5 if self.visible else 0)

    def quit(self):
        self.stop_event.set()
        if self.icon:
            self.icon.stop()
        if self.window:
            self.window.destroy()

    # -- tray
    def make_icon_image(self):
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.ellipse((6, 14, 58, 50), fill=(60, 120, 200, 255))
        d.polygon([(34, 30), (24, 46), (32, 46), (28, 58), (42, 40), (34, 40)],
                  fill=(255, 215, 0, 255))
        return img

    def build_tray(self):
        def overlay_item(label, key):
            return pystray.MenuItem(
                label,
                lambda: self.set_overlay(key),
                checked=lambda item: self.cfg["overlay"] == key,
                radio=True,
            )

        menu = pystray.Menu(
            pystray.MenuItem(
                "Overlay", pystray.Menu(*[overlay_item(k, v) for k, v in OVERLAYS.items()])
            ),
            pystray.MenuItem("Refresh now", lambda: self.reload()),
            pystray.MenuItem(
                "Show wallpaper", lambda: self.toggle_visible(),
                checked=lambda item: self.visible,
            ),
            pystray.MenuItem(
                "Start with Windows",
                lambda: set_autostart(not autostart_enabled()),
                checked=lambda item: autostart_enabled(),
            ),
            pystray.MenuItem("Open config.json",
                             lambda: os.startfile(CONFIG_PATH)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", lambda: self.quit()),
        )
        self.icon = pystray.Icon(APP_NAME, self.make_icon_image(), "Windy Live Wallpaper", menu)
        self.icon.run_detached()

    # -- lifecycle
    def on_ready(self, window):
        window.events.loaded.wait(30)
        attach_to_desktop()
        if self.cfg["autoplay"]:
            window.evaluate_js(AUTOPLAY_JS)
        # periodic reload keeps forecast data fresh
        interval = max(5, int(self.cfg["refresh_minutes"])) * 60
        while not self.stop_event.wait(interval):
            try:
                self.reload()
            except Exception:
                pass

    def run(self):
        w = user32.GetSystemMetrics(78)
        h = user32.GetSystemMetrics(79)
        self.window = webview.create_window(
            WINDOW_TITLE, build_url(self.cfg),
            width=w, height=h, x=0, y=0,
            frameless=True, easy_drag=False, focus=False,
        )
        self.build_tray()
        try:
            webview.start(self.on_ready, self.window, gui="edgechromium")
        finally:
            restore_wallpaper()


def selftest():
    """Used by CI: verify the frozen bundle can load its GUI dependencies."""
    try:
        import clr  # noqa: F401  (pythonnet)
        from webview.platforms import edgechromium  # noqa: F401
        import pystray._win32  # noqa: F401
        return 0
    except Exception as exc:  # pragma: no cover
        Path(os.environ.get("TEMP", ".")).joinpath("windy_selftest.txt").write_text(repr(exc))
        return 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    # Single instance guard
    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, f"Local\\{APP_NAME}")
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        sys.exit(0)
    WallpaperApp().run()
