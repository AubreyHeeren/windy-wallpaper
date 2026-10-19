"""Detects situations where the live wallpaper should stop rendering."""
import ctypes
import threading
from ctypes import wintypes

shell32 = ctypes.windll.shell32
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

user32.OpenInputDesktop.restype = ctypes.c_void_p
user32.OpenInputDesktop.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
user32.CloseDesktop.argtypes = [ctypes.c_void_p]

DESKTOP_SWITCHDESKTOP = 0x0100
# SHQueryUserNotificationState: 2 = fullscreen app, 3 = D3D fullscreen (game), 4 = presentation mode
FULLSCREEN_STATES = (2, 3, 4)


class SYSTEM_POWER_STATUS(ctypes.Structure):
    _fields_ = [
        ("ACLineStatus", ctypes.c_ubyte),
        ("BatteryFlag", ctypes.c_ubyte),
        ("BatteryLifePercent", ctypes.c_ubyte),
        ("SystemStatusFlag", ctypes.c_ubyte),   # bit 0 = battery saver on
        ("BatteryLifeTime", wintypes.DWORD),
        ("BatteryFullLifeTime", wintypes.DWORD),
    ]


def fullscreen_app_running():
    state = ctypes.c_int(0)
    if shell32.SHQueryUserNotificationState(ctypes.byref(state)) != 0:
        return False
    return state.value in FULLSCREEN_STATES


def screen_locked():
    """The input desktop can't be opened while the lock screen / secure desktop is up."""
    hdesk = user32.OpenInputDesktop(0, False, DESKTOP_SWITCHDESKTOP)
    if not hdesk:
        return True
    user32.CloseDesktop(hdesk)
    return False


def power_state():
    """Returns (on_battery, battery_saver_on)."""
    sps = SYSTEM_POWER_STATUS()
    if not kernel32.GetSystemPowerStatus(ctypes.byref(sps)):
        return False, False
    return sps.ACLineStatus == 0, bool(sps.SystemStatusFlag & 1)


class SmartPause:
    """Polls system state and calls on_change(reason_or_None) when it changes.

    A change must be seen on two consecutive polls, which avoids flicker
    (e.g. while alt-tabbing out of a game).
    """

    def __init__(self, get_cfg, on_change, interval=1.5):
        self._get_cfg = get_cfg
        self._on_change = on_change
        self._interval = interval
        self._stop = threading.Event()
        self._thread = None
        self.current = None

    def evaluate(self):
        cfg = self._get_cfg()
        if cfg.get("pause_locked", True) and screen_locked():
            return "screen locked"
        if cfg.get("pause_fullscreen", True) and fullscreen_app_running():
            return "fullscreen app running"
        on_battery, saver = power_state()
        if cfg.get("pause_battery_saver", True) and saver:
            return "battery saver on"
        if cfg.get("pause_on_battery", False) and on_battery:
            return "running on battery"
        return None

    def _run(self):
        candidate, streak = None, 0
        while not self._stop.wait(self._interval):
            try:
                reason = self.evaluate()
            except Exception:
                continue
            if reason == self.current:
                candidate, streak = None, 0
                continue
            if reason == candidate:
                streak += 1
            else:
                candidate, streak = reason, 1
            if streak >= 2:
                self.current = reason
                candidate, streak = None, 0
                try:
                    self._on_change(reason)
                except Exception:
                    pass

    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def stop(self):
        self._stop.set()
