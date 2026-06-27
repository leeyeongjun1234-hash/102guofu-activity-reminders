#!/bin/zsh
set -e

cd "$(dirname "$0")"

if command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON=python
else
  echo "未找到 Python，请先安装 Python。"
  read -k 1 "?按任意键退出..."
  exit 1
fi

echo "开始生成提醒文件..."
$PYTHON generate_reminders.py
$PYTHON daily_reminder.py
$PYTHON build_reminders_html.py

echo
echo "开始提交本地修改..."
git add .

if git diff --cached --quiet; then
  echo "没有检测到需要提交的修改。"
else
  git commit -m "Update reminders $(date '+%Y-%m-%d %H:%M:%S')"
fi

echo
echo "同步 GitHub..."
git pull --rebase origin main
git push origin main

echo
echo "同步完成。GitHub Pages 稍等片刻会自动更新。"
read -k 1 "?按任意键退出..."
