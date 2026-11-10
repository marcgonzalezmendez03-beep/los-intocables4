@echo off
cd /d "%~dp0"
if not exist .venv (
  py -m venv .venv
)
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
if not exist .env copy .env.example .env
echo.
echo Edita .env y configura CLUB_NAME y, si quieres Discord, DISCORD_TOKEN y DISCORD_CHANNEL_ID.
echo Abre .env con el Bloc de notas y luego vuelve a ejecutar este archivo.
pause
