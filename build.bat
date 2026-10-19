@echo off
REM Local build (Windows). GitHub Actions does this automatically on every push.
python -m pip install -r requirements.txt pyinstaller
python tools\make_icon.py
pyinstaller --noconfirm --clean --noconsole --name WindyWallpaper --icon assets\icon.ico --collect-all webview --collect-all pythonnet --collect-all clr_loader --collect-submodules pystray windy_wallpaper.py
echo.
echo Done: dist\WindyWallpaper\WindyWallpaper.exe
pause
