@echo off
setlocal
cd /d "%~dp0..\.."

echo ============================================
echo  Whisper Dictation — Windows Installer
echo ============================================
echo.

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python not found. Install Python 3.10+ from https://python.org
    pause & exit /b 1
)

echo [1/4] Installing core dependencies...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo ERROR: Failed to install core dependencies.
    pause & exit /b 1
)

echo.
echo [2/4] Installing GPU support (NVIDIA only, ~1.2 GB)...
echo       Skip with Ctrl+C if you have no NVIDIA GPU or already have CUDA Toolkit installed.
echo.
pip install --no-cache-dir -r requirements-windows-gpu.txt
if %errorlevel% neq 0 (
    echo WARNING: GPU packages failed. Will run on CPU ^(slower^).
)

echo.
echo [3/4] Adding to Windows startup...
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
copy /Y "%~dp0WhisperDictation.vbs" "%STARTUP%\WhisperDictation.vbs" >nul
echo       Startup entry created.

echo.
echo [4/4] Launching now...
wscript "%~dp0WhisperDictation.vbs"

echo.
echo ============================================
echo  Installation complete!
echo  Hotkey: Ctrl+Alt+R  (toggle record/stop)
echo  Log:    whisper_dictate.log
echo ============================================
pause
