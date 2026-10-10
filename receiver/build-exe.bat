@echo off
cd /d "%~dp0"
REM One windowed GUI exe (no console). Cleans old builds so dist has a single file.
if not exist dist mkdir dist
del /q dist\clicx-receiver.exe 2>nul
del /q dist\clicx-host.exe 2>nul

python -m PyInstaller --noconfirm --clean --onefile --windowed --noconsole --uac-admin --name clicx-host ^
  --hidden-import websockets ^
  --hidden-import websockets.sync ^
  --hidden-import websockets.sync.server ^
  --hidden-import pynput.mouse._win32 ^
  --hidden-import pynput.keyboard._win32 ^
  --hidden-import comtypes ^
  --hidden-import comtypes.stream ^
  --hidden-import pycaw ^
  --hidden-import pycaw.pycaw ^
  --hidden-import gui_app ^
  --hidden-import deck_store ^
  --hidden-import icon_extract ^
  --hidden-import windows_apps ^
  --hidden-import app_picker ^
  --hidden-import protocol ^
  --hidden-import authorization ^
  --hidden-import clipboard_sync ^
  --hidden-import file_transfer ^
  --hidden-import actions ^
  --hidden-import media ^
  --hidden-import app_volume ^
  --hidden-import window_manager ^
  --hidden-import system_status ^
  --hidden-import usage_stats ^
  --hidden-import host_backend ^
  --hidden-import control_server ^
  --hidden-import psutil ^
  --hidden-import qrcode ^
  --hidden-import qrcode.image.pil ^
  --hidden-import PIL ^
  --hidden-import PIL.ImageTk ^
  --collect-all pycaw ^
  --collect-submodules comtypes ^
  main.py
if errorlevel 1 exit /b 1

REM Remove leftover old names if any
del /q dist\clicx-receiver.exe 2>nul
echo.
echo OK — un solo archivo: dist\clicx-host.exe
exit /b 0
