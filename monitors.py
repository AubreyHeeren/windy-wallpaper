"""Monitor discovery (Win32) and wallpaper-window layout."""
import ctypes
from ctypes import wintypes


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


def get_monitors():
    """[{index, left, top, width, height, work:[l,t,r,b], primary}], primary monitor first."""
    user32 = ctypes.windll.user32
    found = []
    try:
        proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HANDLE, wintypes.HDC,
                                       ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
        user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MONITORINFO)]
        user32.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.RECT),
                                               proc_type, wintypes.LPARAM]

        def cb(hmon, hdc, rect, lparam):
            mi = MONITORINFO()
            mi.cbSize = ctypes.sizeof(MONITORINFO)
            if user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
                r, w = mi.rcMonitor, mi.rcWork
                found.append({"left": r.left, "top": r.top, "width": r.right - r.left,
                              "height": r.bottom - r.top, "work": [w.left, w.top, w.right, w.bottom],
                              "primary": bool(mi.dwFlags & 1)})
            return True

        user32.EnumDisplayMonitors(None, None, proc_type(cb), 0)
    except Exception:
        found = []
    if not found:  # fall back to one big virtual screen
        vx, vy = user32.GetSystemMetrics(76), user32.GetSystemMetrics(77)
        vw, vh = user32.GetSystemMetrics(78), user32.GetSystemMetrics(79)
        found = [{"left": vx, "top": vy, "width": vw, "height": vh,
                  "work": [vx, vy, vx + vw, vy + vh], "primary": True}]
    found.sort(key=lambda m: (not m["primary"], m["left"], m["top"]))
    for i, m in enumerate(found):
        m["index"] = i
    return found


def compute_layout(monitors, per_monitor):
    """One wallpaper window per monitor, or a single window spanning all of them.

    rect   = [x, y, w, h] in screen pixels
    anchor = usable area (excluding the taskbar) of the monitor the weather panel sits on,
             relative to the window's top-left corner
    """
    def rel(work, ox, oy):
        l, t, r, b = work
        return [l - ox, t - oy, r - l, b - t]

    if per_monitor and len(monitors) > 1:
        return [{"index": i, "title": f"WindyWallpaperHost-{i}", "monitor": m["index"],
                 "rect": [m["left"], m["top"], m["width"], m["height"]],
                 "anchor": rel(m["work"], m["left"], m["top"])} for i, m in enumerate(monitors)]
    left = min(m["left"] for m in monitors)
    top = min(m["top"] for m in monitors)
    right = max(m["left"] + m["width"] for m in monitors)
    bottom = max(m["top"] + m["height"] for m in monitors)
    return [{"index": 0, "title": "WindyWallpaperHost-0", "monitor": None,
             "rect": [left, top, right - left, bottom - top],
             "anchor": rel(monitors[0]["work"], left, top)}]
