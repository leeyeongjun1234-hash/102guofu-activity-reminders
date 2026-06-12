@echo off
chcp 65001 >nul
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 daily_reminder.py
) else (
    where python3 >nul 2>nul
    if %errorlevel%==0 (
        python3 daily_reminder.py
    ) else (
        python daily_reminder.py
    )
)
pause
