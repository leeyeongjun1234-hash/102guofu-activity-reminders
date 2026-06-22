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

echo "自动更新 HTML 已启动。"
echo "保存排期表或礼包对应关系后，会自动重新生成："
echo "  - 活动设置提醒.tsv"
echo "  - 每日活动提醒.txt"
echo "  - 全部每日提醒.html"
echo "  - index.html"
echo "  - site/index.html"
echo
echo "停止自动更新：按 Ctrl+C，或关闭这个窗口。"
echo

$PYTHON watch_html_auto_update.py
