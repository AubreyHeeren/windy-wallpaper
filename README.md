# Windy Live Wallpaper

Live weather wallpaper for **Windows 10 (version 2004 / build 19041) and newer, 64-bit**.
Shows Windy's animated rain / thunder map behind your desktop icons, controlled from the system tray.

Default view: lat -29.208, lon 26.175, zoom 5, rain overlay with pressure isolines.

## Install
Download the latest `WindyWallpaper-Setup-x.y.z.exe` from **Releases**. It installs the
Microsoft Edge WebView2 runtime automatically if your PC doesn't have it.
A `WindyWallpaper-portable-x.y.z.zip` is also provided (needs WebView2 already installed).

Windows SmartScreen may warn about an unsigned app: choose **More info -> Run anyway**.

## Use
Tray icon menu: switch overlay (Rain, Thunderstorms, Rain accumulation, Wind, Clouds,
Temperature, Pressure), refresh, show/hide, start with Windows, open config, quit.

Config: `%APPDATA%\WindyWallpaper\config.json`
(`lat`, `lon`, `zoom`, `overlay`, `product`, `pressure_isolines`, `refresh_minutes`, `autoplay`, `custom_url`).

## Build
Automatic: every push to `main` builds via GitHub Actions (artifacts tab);
pushing a tag like `v1.0.0` also publishes a Release.

Manual (Windows): run `build.bat`, or `run.bat` to run from source.

## Notes
Data and map come from Windy's embed. For personal use; check Windy's terms before redistributing commercially.
