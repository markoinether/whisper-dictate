@echo off
cd /d "%~dp0..\.."
echo Starting Whisper Dictation...
python whisper_dictate.py 2>nul
pause
