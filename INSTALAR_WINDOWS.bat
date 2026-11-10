@echo off
cd /d "%~dp0"
echo ========================================
echo     LOS INTOCABLES HUB - INSTALACION
 echo ========================================
py -3.11 --version >nul 2>&1
if errorlevel 1 (
  echo ERROR: Necesitas Python 3.11 instalado en Windows.
  echo Descargalo desde python.org y vuelve a ejecutar este archivo.
  pause
  exit /b 1
)
py -3.11 -m venv .venv
if errorlevel 1 goto error
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 goto error
if not exist .env copy .env.example .env >nul
echo.
echo Instalacion terminada. IMPORTANTE: abre .env con el Bloc de notas
 echo y sustituye ADMIN_PASSWORD, SESSION_SECRET y HUB_SYNC_TOKEN.
echo Despues ejecuta INICIAR_WINDOWS.bat
pause
exit /b 0
:error
echo Fallo la instalacion. Revisa los mensajes de error.
pause
exit /b 1
