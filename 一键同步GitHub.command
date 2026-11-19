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

rebuild_reminders() {
  $PYTHON generate_reminders.py &&
  $PYTHON daily_reminder.py &&
  $PYTHON build_reminders_html.py &&
  $PYTHON build_season_reminders.py
}

sync_latest() {
  local sync_result=0
  git pull --rebase --autostash origin main || sync_result=$?

  while true; do
    local -a conflict_files
    local conflict_file
    conflict_files=()
    while IFS= read -r -d '' conflict_file; do
      case "$conflict_file" in
        index.html|site/index.html|全部每日提醒.html|每日活动提醒.txt|活动设置提醒.tsv|season-cn.html|season-overseas.html|site/season-cn.html|site/season-overseas.html)
          conflict_files+=("$conflict_file")
          ;;
        *)
          echo "排期源表或其他文件发生冲突，已停止自动处理：$conflict_file"
          git -c core.quotePath=false status
          return 1
          ;;
      esac
    done < <(git diff --name-only --diff-filter=U -z)

    if [ "${#conflict_files[@]}" -eq 0 ]; then
      return "$sync_result"
    fi

    echo "检测到提醒生成文件冲突，按当前排期重新生成..."
    if ! rebuild_reminders; then
      return 1
    fi
    git add -- index.html site/index.html 全部每日提醒.html 每日活动提醒.txt 活动设置提醒.tsv \
      season-cn.html season-overseas.html site/season-cn.html site/season-overseas.html || return 1

    if [ -d "$(git rev-parse --git-path rebase-merge)" ] || [ -d "$(git rev-parse --git-path rebase-apply)" ]; then
      sync_result=0
      GIT_EDITOR=true git rebase --continue || sync_result=$?
    else
      # pull 已完成，但恢复 autostash 时产生了生成文件冲突。
      return 0
    fi
  done
}

echo "先同步 GitHub 最新内容..."
sync_latest

echo "开始生成提醒文件..."
rebuild_reminders

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
sync_latest
# 同步后可能恢复了新的排期修改，再生成一次，确保提交内容与最新排期一致。
rebuild_reminders
git add .
if ! git diff --cached --quiet; then
  git commit -m "chore: regenerate reminders after sync"
fi
git push origin main

echo
echo "同步完成。GitHub Pages 稍等片刻会自动更新。"
read -k 1 "?按任意键退出..."
