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

echo 自动更新 HTML 已启动。
echo 保存排期表或礼包对应关系后，会自动重新生成：
echo   - 活动设置提醒.tsv
echo   - 每日活动提醒.txt
echo   - 全部每日提醒.html
echo   - index.html
echo   - site\index.html
echo.
echo 停止自动更新：按 Ctrl+C，或关闭这个窗口。
echo.

%PYTHON% watch_html_auto_update.py
pause
