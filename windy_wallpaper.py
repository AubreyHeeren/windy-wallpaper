"""
Windy Live Wallpaper for Windows 10/11
--------------------------------------
Renders Windy's live weather map (rain / thunder by default) as your desktop
wallpaper, behind the desktop icons. Controlled from a system-tray icon.

Requires: Python 3.9+, the Edge WebView2 runtime (preinstalled on Windows 11).
"""
import copy
import ctypes
import functools
import json
import os
import re
import subprocess
import sys
import threading
import time
import webbrowser
import winreg
from ctypes import wintypes
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import pystray
import webview
from PIL import Image, ImageDraw

from monitors import compute_layout, get_monitors
from settings_ui import SETTINGS_HTML, SettingsApi
from smart_pause import SmartPause, power_state
from updater import (check_for_update, download_installer, installed_via_setup,
                     launch_installer, parse_version)
from version import __version__
from wallpaper_js import build_loop_js, build_panel_js, build_perf_js
from weather import analyze, eta_text, fetch_forecast, in_quiet_hours, is_online, panel_data

APP_NAME = "WindyWallpaper"
OFFLINE_HTML = ("<body style=\"margin:0;height:100vh;display:flex;align-items:center;justify-content:center;"
                "background:#0f1b2d;color:#8fa3c7;font:20px 'Segoe UI',sans-serif\">Waiting for an internet connection...</body>")
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
    # Storm alerts
    "alerts_enabled": True,
    "alert_thunder": True,
    "alert_rain": True,
    "alert_lead_minutes": 120,
    "alert_rain_mm": 5.0,
    "alert_watch_places": False,
    "auto_switch_overlay": True,
    "alert_quiet_hours": False,
    "alert_quiet_start": "22:00",
    "alert_quiet_end": "07:00",
    # Weather panel
    "panel_enabled": True,
    "panel_corner": "top-right",
    "panel_size": "medium",
    "panel_opacity": 0.75,
    "panel_clock": "24h",
    "units": "metric",
    "place_label": "",
    # Performance
    "performance": "full",
    "eco_on_battery": True,
    # Monitors: {"0": {"place": "<saved place name>", "overlay": "<overlay key>"}}
    "per_monitor": False,
    "monitor_views": {},
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
PERF_FPS = {"full": 0, "balanced": 30, "eco": 15, "minimal": 10}
PERF_ORDER = list(PERF_FPS)
PANEL_CORNERS = ("top-right", "top-left", "bottom-right", "bottom-left")
PANEL_SIZES = {"small": 0.85, "medium": 1.0, "large": 1.3}
LEAD_CHOICES = (30, 60, 120, 180, 360)
RAIN_CHOICES = (2.0, 5.0, 10.0)
BOOL_KEYS = ("pressure_isolines", "autoplay", "loop_animation", "check_updates", "pause_fullscreen",
             "pause_locked", "pause_battery_saver", "pause_on_battery", "alerts_enabled", "alert_thunder",
             "alert_rain", "alert_watch_places", "auto_switch_overlay", "alert_quiet_hours",
             "panel_enabled", "eco_on_battery", "per_monitor")
WEATHER_SECONDS = 15 * 60
ALERT_COOLDOWN = 3 * 3600
STORM_CLEAR_SECONDS = 30 * 60
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


def attach_to_desktop(title, rect):
    hwnd = user32.FindWindowW(None, title)
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

    # Place the window on its monitor (or across all of them), in the parent's coordinates.
    x, y, w, h = rect
    origin = wintypes.RECT()
    user32.GetWindowRect(parent, ctypes.byref(origin))
    user32.SetWindowPos(hwnd, insert_after, x - origin.left, y - origin.top, w, h,
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
        self.windows = []             # one pywebview window per layout entry
        self.layout = []              # see monitors.compute_layout
        self.monitors = []
        self.icon = None
        self.settings_window = None
        self.user_visible = True      # manual tray toggle
        self.auto_reason = None       # smart-pause reason, or None
        self.online = True
        self._last_load = time.time()
        self.update_info = None       # newer release found on GitHub, or None
        self.update_status = ""       # dev | error | current | available
        self.update_busy = False
        self._last_update_check = 0.0
        self._last_weather = 0.0
        self._weather_busy = False
        self._panel_data = {}         # window index -> panel dict
        self._alerted = {}            # (place, kind) -> time of last notification
        self.auto_overlay = None      # "thunder" while a storm is near
        self._storm_hold = False      # user changed the overlay during a storm
        self._clear_since = None
        self._on_battery = False
        self.stop_event = threading.Event()
        self.pauser = SmartPause(lambda: self.cfg, self.on_pause_change)

    # -- per-window view of the configuration
    def view_cfg(self, i):
        v = dict(self.cfg)
        entry = self.layout[i] if i < len(self.layout) else None
        own_place = False
        if entry and entry["monitor"] is not None:
            ov = self.cfg["monitor_views"].get(str(entry["monitor"]), {})
            place = next((p for p in self.cfg["places"] if p["name"] == ov.get("place")), None)
            if place:
                v.update(lat=place["lat"], lon=place["lon"], zoom=place["zoom"],
                         place_label=place["name"], custom_url="")
                own_place = True
            if ov.get("overlay") in OVERLAYS.values():
                v["overlay"] = ov["overlay"]
                return v
        if self.auto_overlay and not own_place:
            v["overlay"] = self.auto_overlay
        return v

    def panel_cfg(self, i):
        c = self.cfg
        return {"enabled": c["panel_enabled"], "corner": c["panel_corner"],
                "scale": PANEL_SIZES[c["panel_size"]], "opacity": c["panel_opacity"],
                "clock": c["panel_clock"], "anchor": self.layout[i]["anchor"]}

    def effective_perf(self):
        level = self.cfg["performance"]
        if self.cfg["eco_on_battery"] and self._on_battery and PERF_ORDER.index(level) < PERF_ORDER.index("eco"):
            level = "eco"
        return level

    # -- page control
    def reload(self, index=None):
        """Reloads the map(s). While offline the last map stays on screen instead of an error page."""
        if not is_online():
            self._set_online(False)
            return False
        self._last_load = time.time()
        targets = range(len(self.windows)) if index is None else [index]
        for i in targets:
            self.windows[i].load_url(build_url(self.view_cfg(i)))
        return True

    def _on_page_loaded(self, i):
        # Runs after every page load; use a thread so we never block pywebview's event dispatch.
        threading.Thread(target=self._inject_page_script, args=(i,), daemon=True).start()

    def _inject_page_script(self, i):
        try:
            win = self.windows[i]
            win.events.loaded.wait(10)
            v = self.view_cfg(i)
            win.evaluate_js("\n".join([build_loop_js(v["autoplay"], v["loop_animation"]),
                                       build_perf_js(), build_panel_js(self.panel_cfg(i))]))
            self._push_flags(i)
            self._push_panel(i)
        except Exception:
            pass

    def _flags_js(self):
        paused = bool(self.auto_reason) or not self.user_visible
        level = self.effective_perf()
        js = (f"window.__windyPaused = {str(paused).lower()}; window.__windyOffline = {str(not self.online).lower()}; "
              f"window.__windyFps = {PERF_FPS[level]};")
        if level == "minimal":
            js += " try { window.W.store.set('particlesAnim', 'off'); } catch (e) {}"
        return js

    def _push_flags(self, i):
        self.windows[i].evaluate_js(self._flags_js())

    def _push_panel(self, i):
        data = self._panel_data.get(i)
        if data:
            self.windows[i].evaluate_js(
                "window.__windyPanelUpdate && window.__windyPanelUpdate(" + json.dumps(data) + ")")

    def apply_page_state(self):
        """Pushes panel config, frame-rate cap and pause/offline flags into every open page."""
        for i, win in enumerate(self.windows):
            try:
                win.evaluate_js(build_panel_js(self.panel_cfg(i)) + "\n" + self._flags_js())
                self._push_panel(i)
            except Exception:
                pass

    def set_overlay(self, overlay):
        if self.auto_overlay:                 # the user overrides the automatic storm overlay
            self.auto_overlay = None
            self._storm_hold = True
        self.cfg["overlay"] = overlay
        save_config(self.cfg)
        self.reload()
        self.refresh_tray()

    # -- network
    def _set_online(self, online):
        if online == self.online:
            return
        self.online = online
        for data in self._panel_data.values():
            data["offline"] = not online
        if online:
            self._last_weather = 0.0
        self.apply_page_state()
        self.refresh_tray()

    def _net_check(self):
        was = self.online
        now = is_online()
        self._set_online(now)
        if now and not was:
            self.reload()                     # recover from the offline placeholder / stale map

    # -- visibility / smart pause
    def apply_visibility(self):
        show = self.user_visible and not self.auto_reason
        for entry in self.layout:
            hwnd = user32.FindWindowW(None, entry["title"])
            if hwnd:
                user32.ShowWindow(hwnd, SW_SHOWNA if show else SW_HIDE)
        for i in range(len(self.windows)):
            try:
                self._push_flags(i)
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
            "online": self.online,
            "monitors": [{"index": m["index"], "width": m["width"], "height": m["height"],
                          "primary": m["primary"]} for m in self.monitors],
            "per_monitor_active": len(self.layout) > 1,
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
        for key in BOOL_KEYS:
            if key in data:
                c[key] = bool(data[key])
        for key, allowed in (("performance", PERF_FPS), ("panel_corner", PANEL_CORNERS),
                             ("panel_size", PANEL_SIZES), ("panel_clock", ("off", "12h", "24h")),
                             ("units", ("metric", "imperial"))):
            if data.get(key) in allowed:
                c[key] = data[key]
        try:
            c["panel_opacity"] = round(_clamp(float(data["panel_opacity"]), 0.3, 1.0), 2)
        except (KeyError, TypeError, ValueError):
            pass
        try:
            if int(data["alert_lead_minutes"]) in LEAD_CHOICES:
                c["alert_lead_minutes"] = int(data["alert_lead_minutes"])
            if float(data["alert_rain_mm"]) in RAIN_CHOICES:
                c["alert_rain_mm"] = float(data["alert_rain_mm"])
        except (KeyError, TypeError, ValueError):
            pass
        for key in ("alert_quiet_start", "alert_quiet_end"):
            if re.fullmatch(r"\d{2}:\d{2}", str(data.get(key, ""))):
                c[key] = data[key]
        if "place_label" in data:
            c["place_label"] = str(data["place_label"]).strip()[:60]
        if isinstance(data.get("monitor_views"), dict):
            views = {}
            for idx, ov in data["monitor_views"].items():
                if str(idx).isdigit() and isinstance(ov, dict):
                    views[str(idx)] = {
                        "place": str(ov.get("place", ""))[:60],
                        "overlay": ov.get("overlay") if ov.get("overlay") in OVERLAYS.values() else "",
                    }
            c["monitor_views"] = views
        url = str(data.get("custom_url", "")).strip()
        c["custom_url"] = url if url.lower().startswith(("https://", "http://")) else ""
        if not c["auto_switch_overlay"]:
            self.auto_overlay = None
        save_config(c)
        self.reload()
        self.apply_page_state()
        self._last_weather = 0.0              # refresh panel/alerts on the next tick
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
            self.cfg.update(lat=p["lat"], lon=p["lon"], zoom=p["zoom"], place_label=p["name"], custom_url="")
            save_config(self.cfg)
            self.reload()
            self._last_weather = 0.0
        return self.get_state()

    def set_autostart(self, enable):
        set_autostart(enable)
        self.refresh_tray()

    def restart_app(self):
        if getattr(sys, "frozen", False):
            target = f'"{sys.executable}"'
        else:
            target = f'"{Path(sys.executable).with_name("pythonw.exe")}" "{Path(__file__).resolve()}"'
        subprocess.Popen(f"cmd /c ping -n 4 127.0.0.1 >nul & {target}",
                         creationflags=0x08000000 | 0x00000200, close_fds=True)
        self.quit()

    # -- weather: panel data, storm alerts, automatic overlay
    def _maybe_check_weather(self):
        c = self.cfg
        wanted = c["alerts_enabled"] or c["panel_enabled"] or c["auto_switch_overlay"]
        if wanted and not self._weather_busy and time.time() - self._last_weather >= WEATHER_SECONDS:
            self._last_weather = time.time()
            self._weather_busy = True
            threading.Thread(target=self._weather_cycle, daemon=True).start()

    def _weather_cycle(self):
        try:
            if not self.online:
                return
            now = datetime.now(timezone.utc)
            cache = {}

            def get(lat, lon):
                key = (round(lat, 2), round(lon, 2))
                if key not in cache:
                    try:
                        cache[key] = fetch_forecast(lat, lon)
                    except Exception:
                        cache[key] = None
                return cache[key]

            for i in range(len(self.windows)):
                v = self.view_cfg(i)
                fc = get(v["lat"], v["lon"])
                if fc:
                    self._panel_data[i] = panel_data(fc, self.cfg["units"], self.cfg["alert_rain_mm"],
                                                     now, v.get("place_label") or "")
                    self._push_panel(i)
            main_fc = get(self.cfg["lat"], self.cfg["lon"])
            if self.cfg["alerts_enabled"]:
                watch = [(self.cfg["lat"], self.cfg["lon"], self.cfg["place_label"] or "your location")]
                if self.cfg["alert_watch_places"]:
                    watch += [(p["lat"], p["lon"], p["name"]) for p in self.cfg["places"]]
                seen = set()
                for lat, lon, label in watch:
                    key = (round(lat, 2), round(lon, 2))
                    fc = get(lat, lon)
                    if key not in seen and fc:
                        seen.add(key)
                        self._alert_for(key, label, fc, now)
            if main_fc and self.cfg["auto_switch_overlay"]:
                res = analyze(main_fc, now, self.cfg["alert_lead_minutes"], self.cfg["alert_rain_mm"])
                self._auto_switch("thunder" in res)
        except Exception:
            pass
        finally:
            self._weather_busy = False

    def _alert_for(self, key, label, fc, now):
        c = self.cfg
        res = analyze(fc, now, c["alert_lead_minutes"], c["alert_rain_mm"])
        for kind, enabled in (("thunder", c["alert_thunder"]), ("rain", c["alert_rain"])):
            hit = res.get(kind) if enabled else None
            slot = (key, kind)
            if not hit:
                self._alerted.pop(slot, None)         # cleared: a new storm will alert again
                continue
            if time.time() - self._alerted.get(slot, 0) < ALERT_COOLDOWN:
                continue
            if c["alert_quiet_hours"] and in_quiet_hours(datetime.now(), c["alert_quiet_start"],
                                                         c["alert_quiet_end"]):
                continue
            self._alerted[slot] = time.time()
            if kind == "thunder":
                self.notify(f"Thunderstorm near {label}", f"Thunder expected {eta_text(hit['eta'])}.")
            else:
                self.notify(f"Heavy rain near {label}",
                            f"About {hit['mm']:.0f} mm/h expected {eta_text(hit['eta'])}.")

    def _auto_switch(self, storm):
        if storm:
            self._clear_since = None
            if not self.auto_overlay and not self._storm_hold and self.cfg["overlay"] != "thunder":
                self.auto_overlay = "thunder"
                self.reload()
        else:
            self._storm_hold = False
            if self.auto_overlay:
                if self._clear_since is None:
                    self._clear_since = time.time()
                elif time.time() - self._clear_since >= STORM_CLEAR_SECONDS:
                    self.auto_overlay = None
                    self._clear_since = None
                    self.reload()

    def _power_check(self):
        on_battery = power_state()[0]
        if on_battery != self._on_battery:
            self._on_battery = on_battery
            if self.cfg["eco_on_battery"]:
                self.apply_page_state()

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
            width=540, height=680, min_size=(460, 420), resizable=True,
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
            pystray.MenuItem("Offline: showing the last map", None,
                             enabled=False, visible=lambda item: not self.online),
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
    def on_ready(self, first_window):
        for win in self.windows:
            win.events.loaded.wait(30)
        for entry in self.layout:
            attach_to_desktop(entry["title"], entry["rect"])
        self.pauser.start()
        # every 20 s: connectivity, updates, weather, power state, and the periodic map refresh
        while not self.stop_event.wait(20):
            self._net_check()
            self._maybe_check_updates()
            self._maybe_check_weather()
            self._power_check()
            interval = max(5, int(self.cfg["refresh_minutes"])) * 60
            if self.auto_reason or not self.online or time.time() - self._last_load < interval:
                continue
            try:
                self.reload()
            except Exception:
                pass

    def run(self):
        self.monitors = get_monitors()
        self.layout = compute_layout(self.monitors, self.cfg["per_monitor"])
        self.online = is_online()
        for entry in self.layout:
            x, y, w, h = entry["rect"]
            common = dict(width=w, height=h, x=x, y=y, frameless=True, easy_drag=False, focus=False)
            if self.online:
                win = webview.create_window(entry["title"], build_url(self.view_cfg(entry["index"])), **common)
            else:
                win = webview.create_window(entry["title"], html=OFFLINE_HTML, **common)
            win.events.loaded += functools.partial(self._on_page_loaded, entry["index"])
            self.windows.append(win)
        self.build_tray()
        try:
            webview.start(self.on_ready, self.windows[0], gui="edgechromium")
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
