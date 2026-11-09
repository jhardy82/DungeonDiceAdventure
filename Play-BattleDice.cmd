@echo off
rem Double-click launcher for Battle Dice. Sets up .venv on first run, then starts the game.
rem The execution-policy bypass applies to this one process only; nothing on the machine is changed.
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Start-BattleDice.ps1" %*
if errorlevel 1 (
    echo.
    echo Battle Dice could not start. Read the message above, then press a key to close.
    pause >nul
)
endlocal
