"""
Windy Live Wallpaper for Windows 10/11
--------------------------------------
Renders Windy's live weather map (rain / thunder by default) as your desktop
wallpaper, behind the desktop icons. Controlled from a system-tray icon.

Requires: Python 3.9+, the Edge WebView2 runtime (preinstalled on Windows 11).
"""
import copy
import ctypes
import json
import os
import sys
import threading
import time
import webbrowser
import winreg
from ctypes import wintypes
from pathlib import Path
from urllib.parse import urlencode

import pystray
import webview
from PIL import Image, ImageDraw

from settings_ui import SETTINGS_HTML, SettingsApi
from smart_pause import SmartPause
from updater import (check_for_update, download_installer, installed_via_setup,
                     launch_installer, parse_version)
from version import __version__
from wallpaper_js import build_loop_js

APP_NAME = "WindyWallpaper"
WINDOW_TITLE = "WindyWallpaperHost"
SETTINGS_TITLE = "Windy Live Wallpaper - Settings"
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
    "product": "ecmwf",         # ecmwf | gfs | icon
    "pressure_isolines": True,  # the "i:pressure" part of the original link
    "refresh_minutes": 30,      # reload so forecast data stays current
    "autoplay": True,           # try to start Windy's time animation
    "loop_animation": True,     # restart the animation when a cycle ends
    "custom_url": "",           # if set, this exact URL is loaded instead
    # Smart pause
    "pause_fullscreen": True,
    "pause_locked": True,
    "pause_battery_saver": True,
    "pause_on_battery": False,
    # Updates
    "check_updates": True,
    "last_notified_version": "",
    # Saved places: [{"name": str, "lat": float, "lon": float, "zoom": int}]
    "places": [],
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
PRODUCTS = ["ecmwf", "gfs", "icon"]
UPDATE_CHECK_SECONDS = 12 * 3600
IS_DEV_BUILD = parse_version(__version__) in (None, (0, 0, 0))  # unstamped / CI dev build


# ----------------------------------------------------------------- config ---
def load_config():
    cfg = copy.deepcopy(DEFAULTS)
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


def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


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
SW_HIDE, SW_SHOWNA = 0, 8
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


class WallpaperApp:
    def __init__(self):
        self.cfg = load_config()
        self.window = None
        self.icon = None
        self.settings_window = None
        self.user_visible = True      # manual tray toggle
        self.auto_reason = None       # smart-pause reason, or None
        self._last_load = time.time()
        self.update_info = None       # newer release found on GitHub, or None
        self.update_status = ""       # dev | error | current | available
        self.update_busy = False
        self._last_update_check = 0.0
        self.stop_event = threading.Event()
        self.pauser = SmartPause(lambda: self.cfg, self.on_pause_change)

    # -- page control
    def reload(self):
        self._last_load = time.time()
        self.window.load_url(build_url(self.cfg))

    def _on_page_loaded(self):
        # Runs after every page load; use a thread so we never block pywebview's event dispatch.
        threading.Thread(target=self._inject_page_script, daemon=True).start()

    def _inject_page_script(self):
        try:
            self.window.events.loaded.wait(10)
            self.window.evaluate_js(build_loop_js(self.cfg["autoplay"], self.cfg["loop_animation"]))
            self._push_paused_flag()
        except Exception:
            pass

    def _push_paused_flag(self):
        paused = bool(self.auto_reason) or not self.user_visible
        self.window.evaluate_js("window.__windyPaused = " + ("true" if paused else "false"))

    def set_overlay(self, overlay):
        self.cfg["overlay"] = overlay
        save_config(self.cfg)
        self.reload()
        self.refresh_tray()

    # -- visibility / smart pause
    def apply_visibility(self):
        hwnd = user32.FindWindowW(None, WINDOW_TITLE)
        if hwnd:
            show = self.user_visible and not self.auto_reason
            user32.ShowWindow(hwnd, SW_SHOWNA if show else SW_HIDE)
            try:
                self._push_paused_flag()
            except Exception:
                pass
        self.refresh_tray()

    def toggle_visible(self):
        self.user_visible = not self.user_visible
        self.apply_visibility()

    def on_pause_change(self, reason):
        was_paused = self.auto_reason
        self.auto_reason = reason
        self.apply_visibility()
        if was_paused and not reason:
            stale = time.time() - self._last_load > max(5, int(self.cfg["refresh_minutes"])) * 60
            if stale:
                try:
                    self.reload()
                except Exception:
                    pass

    # -- settings / places (also used by the settings window)
    def get_state(self):
        return {
            "config": self.cfg,
            "overlays": OVERLAYS,
            "products": PRODUCTS,
            "autostart": autostart_enabled(),
            "paused": self.auto_reason,
            "version": __version__,
            "update": self.update_info,
            "update_status": self.update_status,
            "can_auto_install": self.can_auto_install(),
        }

    def update_settings(self, data):
        c = self.cfg
        try:
            c["lat"] = _clamp(float(data["lat"]), -90.0, 90.0)
            c["lon"] = _clamp(float(data["lon"]), -180.0, 180.0)
            c["zoom"] = _clamp(int(data["zoom"]), 3, 12)
            c["refresh_minutes"] = _clamp(int(data["refresh_minutes"]), 5, 240)
        except (KeyError, TypeError, ValueError):
            return self.get_state()
        if data.get("overlay") in OVERLAYS.values():
            c["overlay"] = data["overlay"]
        if data.get("product") in PRODUCTS:
            c["product"] = data["product"]
        for key in ("pressure_isolines", "autoplay", "loop_animation", "check_updates", "pause_fullscreen",
                    "pause_locked", "pause_battery_saver", "pause_on_battery"):
            if key in data:
                c[key] = bool(data[key])
        url = str(data.get("custom_url", "")).strip()
        c["custom_url"] = url if url.lower().startswith(("https://", "http://")) else ""
        save_config(c)
        self.reload()
        self.refresh_tray()
        return self.get_state()

    def add_place(self, name, lat, lon, zoom=None):
        lat, lon = float(lat), float(lon)
        name = (name or "").strip()[:60] or f"{lat:.2f}, {lon:.2f}"
        places = [p for p in self.cfg["places"] if p["name"] != name]
        places.append({"name": name, "lat": round(lat, 4), "lon": round(lon, 4),
                       "zoom": int(zoom or self.cfg["zoom"])})
        self.cfg["places"] = places[-20:]
        save_config(self.cfg)
        self.refresh_tray()
        return self.get_state()

    def remove_place(self, index):
        places = self.cfg["places"]
        if 0 <= int(index) < len(places):
            del places[int(index)]
            save_config(self.cfg)
            self.refresh_tray()
        return self.get_state()

    def go_to_place(self, index):
        places = self.cfg["places"]
        if 0 <= int(index) < len(places):
            p = places[int(index)]
            self.cfg.update(lat=p["lat"], lon=p["lon"], zoom=p["zoom"], custom_url="")
            save_config(self.cfg)
            self.reload()
        return self.get_state()

    def set_autostart(self, enable):
        set_autostart(enable)
        self.refresh_tray()

    # -- updates
    def notify(self, title, message):
        if self.icon:
            try:
                self.icon.notify(message, title)
            except Exception:
                pass

    def can_auto_install(self):
        return bool(self.update_info and self.update_info.get("url")
                    and getattr(sys, "frozen", False) and installed_via_setup(APP_DIR))

    def _do_check(self, manual):
        if IS_DEV_BUILD:
            status = "dev"
        else:
            try:
                self.update_info = check_for_update(__version__)
                status = "available" if self.update_info else "current"
            except Exception:
                status = "error"
        self.update_status = status
        self.refresh_tray()
        if status == "available":
            version = self.update_info["version"]
            if manual or self.cfg.get("last_notified_version") != version:
                self.cfg["last_notified_version"] = version
                save_config(self.cfg)
                self.notify(f"Update available: {version}",
                            "Right-click the tray icon and choose Install update.")
        elif manual:
            text = {"current": f"You're up to date (version {__version__}).",
                    "dev": "Development build: update checks are disabled.",
                    "error": "Couldn't reach GitHub. Try again later."}[status]
            self.notify("Windy Live Wallpaper", text)
        return status

    def check_updates(self, manual=False):
        threading.Thread(target=self._do_check, args=(manual,), daemon=True).start()

    def check_updates_now(self):
        self._do_check(manual=False)
        return self.get_state()

    def _maybe_check_updates(self):
        if self.cfg["check_updates"] and time.time() - self._last_update_check > UPDATE_CHECK_SECONDS:
            self._last_update_check = time.time()
            self.check_updates()

    def install_update(self):
        info = self.update_info
        if not info or self.update_busy:
            return self.get_state()
        if not self.can_auto_install():
            webbrowser.open(info["page"])   # portable / source run: let the user download it
            return self.get_state()
        self.update_busy = True
        self.refresh_tray()

        def work():
            try:
                self.notify("Downloading update...", f"Version {info['version']}")
                path = download_installer(info)
                self.notify("Installing update", "The wallpaper restarts automatically when done.")
                launch_installer(path)
                self.quit()   # exit now so the installer can replace the files
            except Exception as exc:
                self.update_busy = False
                self.refresh_tray()
                self.notify("Update failed", str(exc)[:120])

        threading.Thread(target=work, daemon=True).start()
        return self.get_state()

    def open_settings(self):
        if self.settings_window is not None:
            try:
                self.settings_window.show()
                return
            except Exception:
                self.settings_window = None
        win = webview.create_window(
            SETTINGS_TITLE, html=SETTINGS_HTML, js_api=SettingsApi(self),
            width=540, height=640, min_size=(460, 420), resizable=True,
        )
        win.events.closed += lambda: setattr(self, "settings_window", None)
        self.settings_window = win

    def close_settings(self):
        if self.settings_window is not None:
            self.settings_window.destroy()

    def quit(self):
        self.stop_event.set()
        self.pauser.stop()
        if self.icon:
            self.icon.stop()
        for win in list(webview.windows):
            try:
                win.destroy()
            except Exception:
                pass

    # -- tray
    def make_icon_image(self):
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.ellipse((6, 14, 58, 50), fill=(60, 120, 200, 255))
        d.polygon([(34, 30), (24, 46), (32, 46), (28, 58), (42, 40), (34, 40)],
                  fill=(255, 215, 0, 255))
        return img

    def refresh_tray(self):
        if self.icon:
            try:
                self.icon.update_menu()
            except Exception:
                pass

    def _place_items(self):
        for i, place in enumerate(self.cfg["places"]):
            yield pystray.MenuItem(place["name"], self._goto(i))

    def _goto(self, index):
        return lambda: self.go_to_place(index)

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
                lambda item: f"Paused: {self.auto_reason}", None,
                enabled=False, visible=lambda item: bool(self.auto_reason),
            ),
            pystray.MenuItem(
                lambda item: ("Installing update..." if self.update_busy
                              else f"Install update {self.update_info['version']}"),
                lambda: self.install_update(),
                enabled=lambda item: not self.update_busy,
                visible=lambda item: bool(self.update_info),
            ),
            pystray.MenuItem("Settings...", lambda: self.open_settings(), default=True),
            pystray.MenuItem("Places", pystray.Menu(self._place_items),
                             visible=lambda item: bool(self.cfg["places"])),
            pystray.MenuItem(
                "Overlay", pystray.Menu(*[overlay_item(k, v) for k, v in OVERLAYS.items()])
            ),
            pystray.MenuItem("Refresh now", lambda: self.reload()),
            pystray.MenuItem(
                "Show wallpaper", lambda: self.toggle_visible(),
                checked=lambda item: self.user_visible,
            ),
            pystray.MenuItem(
                "Start with Windows",
                lambda: self.set_autostart(not autostart_enabled()),
                checked=lambda item: autostart_enabled(),
            ),
            pystray.MenuItem("Check for updates", lambda: self.check_updates(manual=True)),
            pystray.MenuItem("Open config.json", lambda: os.startfile(CONFIG_PATH)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", lambda: self.quit()),
        )
        self.icon = pystray.Icon(APP_NAME, self.make_icon_image(), "Windy Live Wallpaper", menu)
        self.icon.run_detached()

    # -- lifecycle
    def on_ready(self, window):
        window.events.loaded.wait(30)
        attach_to_desktop()
        self.pauser.start()
        # periodic reload keeps forecast data fresh (skipped while paused)
        while not self.stop_event.wait(60):
            self._maybe_check_updates()
            interval = max(5, int(self.cfg["refresh_minutes"])) * 60
            if self.auto_reason or time.time() - self._last_load < interval:
                continue
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
        self.window.events.loaded += self._on_page_loaded
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
