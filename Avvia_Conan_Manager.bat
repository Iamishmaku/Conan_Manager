@echo off
cd /d "%~dp0"
where pyw >nul 2>nul
if not errorlevel 1 (
  start "" /b pyw -3 "%~dp0server.py" --no-browser
) else (
  where pythonw >nul 2>nul
  if errorlevel 1 (
    echo Python 3 non trovato. Installalo da https://www.python.org/downloads/
    pause
    exit /b 1
  )
  start "" /b pythonw "%~dp0server.py" --no-browser
)
ping 127.0.0.1 -n 2 >nul
start "" "http://127.0.0.1:8765/"
exit /b 0
