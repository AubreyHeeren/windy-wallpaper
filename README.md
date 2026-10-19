# Windy Live Wallpaper

Live weather wallpaper for **Windows 10 (version 2004 / build 19041) and newer, 64-bit**.
Shows Windy's animated rain / thunder map behind your desktop icons, controlled from the system tray.

Default view: lat -29.208, lon 26.175, zoom 5, rain overlay with pressure isolines.

## Features
- **Settings window** (tray icon double-click, or tray menu -> Settings): search any city, set zoom,
  overlay, forecast model, refresh rate and more. No JSON editing needed.
- **Saved places**: save locations and switch between them from the tray **Places** menu.
- **Smart pause**: the wallpaper stops rendering while a fullscreen app/game is running, the screen is locked,
  Battery Saver is on, or (optionally) whenever you're on battery. It resumes, and refreshes if the data is stale,
  as soon as the condition clears.
- Tray controls: overlay switch (Rain, Thunderstorms, Rain accumulation, Wind, Clouds, Temperature, Pressure),
  refresh, show/hide, start with Windows.

## Install
Download the latest `WindyWallpaper-Setup-x.y.z.exe` from **Releases**. It installs the
Microsoft Edge WebView2 runtime automatically if your PC doesn't have it.
A `WindyWallpaper-portable-x.y.z.zip` is also provided (needs WebView2 already installed).

Windows SmartScreen may warn about an unsigned app: choose **More info -> Run anyway**.

## Config
`%APPDATA%\WindyWallpaper\config.json` (normally edited through the Settings window):
`lat`, `lon`, `zoom`, `overlay`, `product`, `pressure_isolines`, `refresh_minutes`, `autoplay`, `custom_url`,
`pause_fullscreen`, `pause_locked`, `pause_battery_saver`, `pause_on_battery`, `places`.

City search uses the free [Open-Meteo geocoding API](https://open-meteo.com/en/docs/geocoding-api) (no key needed).

## Build
Automatic: every push to `main` builds via GitHub Actions (artifacts tab);
pushing a tag like `v1.1.0` also publishes a Release.

Manual (Windows): run `build.bat`, or `run.bat` to run from source.

## Notes
Data and map come from Windy's embed. For personal use; check Windy's terms before redistributing commercially.
