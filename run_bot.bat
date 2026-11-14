@echo off
echo === AI Health Coach bot ===
if not exist .env (
  copy .env.example .env >nul
  echo A new .env file was created. Fill in your keys, save, close Notepad, then run this again.
  notepad .env
  pause
  exit /b
)
if not exist .venv (
  echo Creating Python environment...
  python -m venv .venv
)
call .venv\Scripts\activate
echo Installing core packages - progress is shown below...
pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo INSTALL FAILED - scroll up to see the error and send it to your helper.
  pause
  exit /b 1
)
echo.
echo Installing OPTIONAL voice-note package. This can take several minutes.
echo If it fails or you press Ctrl+C, the bot still works without them.
pip install -r requirements-extra.txt
if errorlevel 1 echo Optional package not installed: voice notes will be off.
echo.
echo Starting the bot. KEEP THIS WINDOW OPEN - the bot only answers while it runs. Ctrl+C stops it.
python -m hc.channels.telegram_bot
echo.
echo The bot stopped. Read any error above.
pause
