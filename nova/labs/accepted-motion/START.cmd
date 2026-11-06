@echo off
setlocal
cd /d "%~dp0"
echo NOVA Bewegungsfassung: http://127.0.0.1:31350/motion/
echo Beenden mit Strg+C.
python serve.py
exit /b %errorlevel%
