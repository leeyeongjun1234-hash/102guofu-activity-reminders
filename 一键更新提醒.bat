@echo off
cd /d "%~dp0"
python daily_reminder.py
if errorlevel 1 goto error
python build_reminders_html.py
if errorlevel 1 goto error
echo.
echo 已更新：每日活动提醒.txt
echo 已更新：全部每日提醒.html
echo 已更新：site\index.html
pause
exit /b 0

:error
echo.
echo 更新失败，请查看上面的错误信息。
pause
exit /b 1
