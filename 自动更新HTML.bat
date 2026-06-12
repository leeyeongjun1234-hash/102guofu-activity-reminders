@echo off
chcp 65001 >nul
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 watch_html_auto_update.py
) else (
    where python3 >nul 2>nul
    if %errorlevel%==0 (
        python3 watch_html_auto_update.py
    ) else (
        python watch_html_auto_update.py
    )
)
pause
