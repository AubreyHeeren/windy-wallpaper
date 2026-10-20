# Windy Live Wallpaper

Live weather wallpaper for **Windows 10 (version 2004 / build 19041) and newer, 64-bit**.
Shows Windy's animated rain / thunder map behind your desktop icons, controlled from the system tray.

Default view: lat -29.208, lon 26.175, zoom 5, rain overlay with pressure isolines.

## Features
- **Settings window** (tray icon double-click, or tray menu -> Settings): search any city, set zoom,
  overlay, forecast model, refresh rate and more. Changes save automatically.
- **Saved places**: save locations and switch between them from the tray **Places** menu.
- **Continuous loop**: the weather animation restarts by itself when a cycle ends.
- **Smart pause**: the wallpaper stops rendering while a fullscreen app/game is running, the screen is locked,
  Battery Saver is on, or (optionally) whenever you're on battery. It resumes as soon as the condition clears.
- **Auto-update**: checks GitHub Releases at startup and every 12 hours. When a newer version exists you get a
  notification and an **Install update** item in the tray menu; one click downloads it, installs it and restarts the app.
  Turn it off in Settings -> Updates. (Portable zip users get a link to the download page instead.)
- Tray controls: overlay switch (Rain, Thunderstorms, Rain accumulation, Wind, Clouds, Temperature, Pressure),
  refresh, show/hide, start with Windows, check for updates.

## Install
Download the latest `WindyWallpaper-Setup-x.y.z.exe` from **Releases**. It installs the
Microsoft Edge WebView2 runtime automatically if your PC doesn't have it.
A `WindyWallpaper-portable-x.y.z.zip` is also provided (needs WebView2 already installed).

Windows SmartScreen may warn about an unsigned app: choose **More info -> Run anyway**.

## Config
`%APPDATA%\WindyWallpaper\config.json` (normally edited through the Settings window).
City search uses the free [Open-Meteo geocoding API](https://open-meteo.com/en/docs/geocoding-api) (no key needed).

## Build & release
Every push to `main` builds via GitHub Actions (see the run's Artifacts).
**To publish a release** (which installed copies then pick up automatically): push a version tag such as `v1.2.0`.
CI stamps that version into the app, builds the installer + portable zip and attaches them to a GitHub Release.

Manual (Windows): run `build.bat`, or `run.bat` to run from source (source runs are "dev" builds and don't self-update).

## Notes
Data and map come from Windy's embed. For personal use; check Windy's terms before redistributing commercially.
