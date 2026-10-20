"""Forecast data (Open-Meteo, no API key), storm analysis and weather-panel formatting."""
import json
import socket
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

API_URL = "https://api.open-meteo.com/v1/forecast"
THUNDER_CODES = (95, 96, 99)

WEATHER_TEXT = {
    0: "Clear sky", 1: "Mostly clear", 2: "Partly cloudy", 3: "Overcast", 45: "Fog", 48: "Fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle", 56: "Freezing drizzle", 57: "Freezing drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain", 66: "Freezing rain", 67: "Freezing rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Light showers", 81: "Showers", 82: "Violent showers", 85: "Snow showers", 86: "Snow showers",
    95: "Thunderstorm", 96: "Thunderstorm, hail", 99: "Thunderstorm, hail",
}


def is_online(host="embed.windy.com", port=443, timeout=3):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _num(value, default=0.0):
    return float(value) if isinstance(value, (int, float)) else default


def parse_forecast(data):
    tz = timezone(timedelta(seconds=int(data.get("utc_offset_seconds") or 0)))

    def stamp(text):
        return datetime.fromisoformat(text).replace(tzinfo=tz)

    cur = data.get("current") or {}
    hourly = data.get("hourly") or {}

    def col(name, i):
        vals = hourly.get(name) or []
        return vals[i] if i < len(vals) else None

    rows = []
    for i, t in enumerate(hourly.get("time") or []):
        rows.append({
            "time": stamp(t),
            "precip": _num(col("precipitation", i)),
            "prob": _num(col("precipitation_probability", i)),
            "code": int(_num(col("weather_code", i), -1)),
        })
    return {
        "current": {
            "temp": _num(cur.get("temperature_2m")),
            "wind": _num(cur.get("wind_speed_10m")),
            "code": int(_num(cur.get("weather_code"), -1)),
            "precip": _num(cur.get("precipitation")),
        },
        "hourly": rows,
    }


def fetch_forecast(lat, lon, timeout=10):
    params = {
        "latitude": lat, "longitude": lon,
        "current": "temperature_2m,precipitation,weather_code,wind_speed_10m",
        "hourly": "precipitation,precipitation_probability,weather_code",
        "forecast_hours": 24, "timezone": "auto", "wind_speed_unit": "kmh",
    }
    req = urllib.request.Request(API_URL + "?" + urllib.parse.urlencode(params),
                                 headers={"User-Agent": "WindyLiveWallpaper/1.3"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return parse_forecast(json.load(resp))


def analyze(fc, now, lead_minutes, rain_mm):
    """Looks ahead `lead_minutes`; returns {'thunder': {'eta': min}, 'rain': {'eta': min, 'mm': x}}."""
    limit = now + timedelta(minutes=lead_minutes)
    out = {}

    def eta(start):
        return max(0, int((start - now).total_seconds() // 60))

    if fc["current"]["code"] in THUNDER_CODES:
        out["thunder"] = {"eta": 0}
    for h in fc["hourly"]:
        start, end = h["time"], h["time"] + timedelta(hours=1)
        if end <= now or start > limit:
            continue
        if h["code"] in THUNDER_CODES and "thunder" not in out:
            out["thunder"] = {"eta": eta(start)}
        if h["precip"] >= rain_mm and "rain" not in out:
            out["rain"] = {"eta": eta(start), "mm": h["precip"]}
    return out


def eta_text(minutes):
    if minutes <= 5:
        return "now"
    if minutes < 90:
        return f"in about {int(round(minutes / 5.0) * 5)} min"
    return f"in about {round(minutes / 60.0)} h"


def _minutes(hhmm):
    try:
        h, m = str(hhmm).split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return 0


def in_quiet_hours(now_local, start, end):
    s, e, n = _minutes(start), _minutes(end), now_local.hour * 60 + now_local.minute
    if s == e:
        return False
    return s <= n < e if s < e else (n >= s or n < e)


def panel_data(fc, units, rain_mm, now, label):
    cur = fc["current"]
    probs = [h["prob"] for h in fc["hourly"] if h["time"] + timedelta(hours=1) > now][:3]
    res = analyze(fc, now, 24 * 60, rain_mm)
    if "thunder" in res:
        storm, alert = "Thunder " + eta_text(res["thunder"]["eta"]), True
    elif "rain" in res:
        storm, alert = "Heavy rain " + eta_text(res["rain"]["eta"]), True
    else:
        storm, alert = "No storms expected", False
    if units == "imperial":
        temp, wind = f"{cur['temp'] * 9 / 5 + 32:.0f}\u00b0F", f"{cur['wind'] * 0.621371:.0f} mph"
    else:
        temp, wind = f"{cur['temp']:.0f}\u00b0C", f"{cur['wind']:.0f} km/h"
    return {
        "place": label, "temp": temp, "cond": WEATHER_TEXT.get(cur["code"], "Unknown"),
        "rain": f"{max(probs) if probs else 0:.0f}%", "wind": wind,
        "storm": storm, "alert": alert, "offline": False,
    }
