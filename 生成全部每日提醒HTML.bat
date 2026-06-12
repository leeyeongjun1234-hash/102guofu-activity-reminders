@echo off
chcp 65001 >nul
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 build_reminders_html.py
) else (
    where python3 >nul 2>nul
    if %errorlevel%==0 (
        python3 build_reminders_html.py
    ) else (
        python build_reminders_html.py
    )
)
pause
