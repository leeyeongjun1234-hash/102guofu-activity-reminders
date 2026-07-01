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

if exist ".git\rebase-merge" (
    echo 检测到上一次 Git 同步未完成。
    echo 请先处理完成后再运行一键同步。当前状态：
    git status
    goto error
)

if exist ".git\rebase-apply" (
    echo 检测到上一次 Git 同步未完成。
    echo 请先处理完成后再运行一键同步。当前状态：
    git status
    goto error
)

for /f "delims=" %%i in ('git branch --show-current') do set "CURRENT_BRANCH=%%i"
if not "%CURRENT_BRANCH%"=="main" (
    echo 当前不在 main 分支，正在切换到 main...
    git switch main
    if errorlevel 1 goto error
)

echo 先同步 GitHub 最新内容...
git pull --rebase --autostash origin main
if errorlevel 1 goto error

echo 开始生成提醒文件...
%PYTHON% generate_reminders.py
if errorlevel 1 goto error
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
echo 推送前再次同步 GitHub...
git pull --rebase --autostash origin main
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
