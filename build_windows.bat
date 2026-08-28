@echo off
REM Build a standalone Windows .exe — run this ON Windows (PyInstaller does
REM not cross-compile). End users won't need Python installed.

pip install -r requirements-dev.txt

pyinstaller --onefile --windowed --name VideoConverter main.py

echo.
echo Build done: dist\VideoConverter.exe
echo Copy ffmpeg.exe and ffprobe.exe (https://www.gyan.dev/ffmpeg/builds/)
echo into the dist\ folder next to VideoConverter.exe so it needs no PATH setup.
