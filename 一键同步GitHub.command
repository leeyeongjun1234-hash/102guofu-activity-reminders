#!/bin/zsh
set -e

cd "$(dirname "$0")"

trap 'echo; echo "同步失败，请查看上面的错误信息。"; read -k 1 "?按任意键退出..."; exit 1' ERR

if command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON=python
else
  echo "未找到 Python，请先安装 Python。"
  read -k 1 "?按任意键退出..."
  exit 1
fi

ensure_git_ready() {
  if [ -d "$(git rev-parse --git-path rebase-merge)" ] || [ -d "$(git rev-parse --git-path rebase-apply)" ]; then
    echo "检测到上一次 Git 同步未完成。"
    echo "请先处理完成后再运行一键同步。当前状态："
    git status
    exit 1
  fi

  CURRENT_BRANCH="$(git branch --show-current)"
  if [ "$CURRENT_BRANCH" != "main" ]; then
    echo "当前不在 main 分支，正在切换到 main..."
    git switch main
  fi
}

ensure_git_ready

echo "先同步 GitHub 最新内容..."
git pull --rebase --autostash origin main

echo "开始生成提醒文件..."
$PYTHON generate_reminders.py
$PYTHON daily_reminder.py
$PYTHON build_reminders_html.py
$PYTHON build_season_reminders.py

echo
echo "开始提交本地修改..."
git add .

if git diff --cached --quiet; then
  echo "没有检测到需要提交的修改。"
else
  git commit -m "Update reminders $(date '+%Y-%m-%d %H:%M:%S')"
fi

echo
echo "推送前再次同步 GitHub..."
git pull --rebase --autostash origin main
git push origin main

echo
echo "同步完成。GitHub Pages 稍等片刻会自动更新。"
read -k 1 "?按任意键退出..."
