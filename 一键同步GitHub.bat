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

echo 开始生成提醒文件...
%PYTHON% daily_reminder.py
if errorlevel 1 goto error
%PYTHON% build_reminders_html.py
if errorlevel 1 goto error

echo.
echo 开始提交本地修改...
git add .
if errorlevel 1 goto error

git diff --cached --quiet
if errorlevel 1 (
    git commit -m "Update reminders %date% %time%"
    if errorlevel 1 goto error
) else (
    echo 没有检测到需要提交的修改。
)

echo.
echo 同步 GitHub...
git pull --rebase origin main
if errorlevel 1 goto error
git push origin main
if errorlevel 1 goto error

echo.
echo 同步完成。GitHub Pages 稍等片刻会自动更新。
pause
exit /b 0

:error
echo.
echo 同步失败，请查看上面的错误信息。
pause
exit /b 1
