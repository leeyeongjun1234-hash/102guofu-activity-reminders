@echo off
chcp 65001 >nul
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
    set "PYTHON=py -3"
) else (
    where python3 >nul 2>nul
    if %errorlevel%==0 (
        set "PYTHON=python3"
    ) else (
        set "PYTHON=python"
    )
)

%PYTHON% generate_reminders.py
if errorlevel 1 goto error
%PYTHON% daily_reminder.py
if errorlevel 1 goto error
%PYTHON% build_reminders_html.py
if errorlevel 1 goto error
echo.
echo 已更新：活动设置提醒.tsv
echo 已更新：每日活动提醒.txt
echo 已更新：全部每日提醒.html
echo 已更新：index.html
echo 已更新：site\index.html
pause
exit /b 0

:error
echo.
echo 更新失败，请查看上面的错误信息。
pause
exit /b 1
