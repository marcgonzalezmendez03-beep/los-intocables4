@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
 echo Primero ejecuta INSTALAR_WINDOWS.bat
 pause
 exit /b 1
)
if not exist .env (
 echo Falta .env. Copia .env.example a .env y configura los secretos.
 pause
 exit /b 1
)
echo LOS INTOCABLES HUB - abre http://127.0.0.1:8000
.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
pause
