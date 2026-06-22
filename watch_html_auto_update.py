from __future__ import annotations

import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
WATCHED_FILES = [
    ROOT / "102国服活动排期表.xlsx",
    ROOT / "活动与礼包对应关系.xlsx",
    ROOT / "活动设置提醒.tsv",
    ROOT / "generate_reminders.py",
    ROOT / "daily_reminder.py",
    ROOT / "build_reminders_html.py",
    ROOT / "watch_html_auto_update.py",
]
INTERVAL_SECONDS = 3


def file_signature(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return None
    return (stat.st_mtime_ns, stat.st_size)


def watched_signature() -> dict[str, tuple[int, int] | None]:
    return {str(path): file_signature(path) for path in WATCHED_FILES}


def log(message: str) -> None:
    now = datetime.now().strftime("%H:%M:%S")
    print(f"[{now}] {message}", flush=True)


def rebuild() -> bool:
    steps = [
        ("活动设置提醒 TSV", ROOT / "generate_reminders.py"),
        ("每日活动提醒", ROOT / "daily_reminder.py"),
        ("HTML", ROOT / "build_reminders_html.py"),
    ]

    log("开始更新 TSV、提醒文本和 HTML...")
    for label, script in steps:
        result = subprocess.run([sys.executable, str(script)], cwd=ROOT, text=True)
        if result.returncode != 0:
            log(f"{label} 更新失败，请查看上面的错误信息。")
            return False

    log("已更新：活动设置提醒.tsv / 每日活动提醒.txt / 全部每日提醒.html / index.html / site/index.html")
    return True


def main() -> None:
    missing = [path.name for path in WATCHED_FILES if not path.exists()]
    if missing:
        raise SystemExit("缺少文件：" + "、".join(missing))

    log("自动更新已启动。按 Ctrl+C 停止。")
    rebuild()
    last_signature = watched_signature()

    while True:
        time.sleep(INTERVAL_SECONDS)
        current_signature = watched_signature()
        if current_signature == last_signature:
            continue

        changed = [
            Path(path).name
            for path, signature in current_signature.items()
            if signature != last_signature.get(path)
        ]
        log("检测到变动：" + "、".join(changed))
        if rebuild():
            last_signature = watched_signature()
        else:
            last_signature = current_signature


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("自动更新 HTML 已停止。")
