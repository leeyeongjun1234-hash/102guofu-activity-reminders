from __future__ import annotations

import csv
import re
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path


SOURCE = Path("102国服活动排期表.xlsx")
OUTPUT = Path("活动设置提醒.tsv")
YEAR = 2026


def week_monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def clean_text(value: str) -> str:
    value = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value


def parse_month_day(value: str) -> date | None:
    match = re.fullmatch(r"\s*(\d{1,2})月(\d{1,2})日\s*", value or "")
    if not match:
        return None
    return date(YEAR, int(match.group(1)), int(match.group(2)))


def reminder_rules(activity: str, start_day: date) -> list[tuple[date, str]]:
    if "区域迁徙" in activity:
        monday = week_monday(start_day) - timedelta(days=7)
        return [
            (monday, "区域迁徙：设置礼包+分组"),
            (monday + timedelta(days=2), "区域迁徙：设置活动+公布分组"),
        ]
    if "本服联盟GVE" in activity:
        return [(week_monday(start_day) - timedelta(days=7), "本服联盟GVE：设置活动")]
    if "跨服联盟GVE" in activity:
        return [(week_monday(start_day) - timedelta(days=2), "跨服联盟GVE：设置活动")]
    if "VIP商店" in activity or "黑骑士" in activity:
        return [(week_monday(start_day), "设置活动")]
    if "联盟远征" in activity or "功勋商店" in activity:
        return [(start_day, "设置活动")]
    if "土拨鼠" in activity:
        return [(start_day - timedelta(days=2), "设置活动")]
    if "自选周卡" in activity or "进化连冲" in activity:
        return [(start_day - timedelta(days=3), "设置活动")]
    return [(start_day - timedelta(days=1), "设置活动")]


def main() -> None:
    with SOURCE.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f, delimiter="\t"))

    if len(rows) < 2:
        raise SystemExit("排期表缺少日期行")

    dates: dict[int, date] = {}
    for col, value in enumerate(rows[1]):
        parsed = parse_month_day(value)
        if parsed:
            dates[col] = parsed

    reminders: dict[date, list[tuple[date, str, str]]] = defaultdict(list)
    for row in rows[2:]:
        for col, start_day in dates.items():
            if col >= len(row):
                continue
            activity = clean_text(row[col])
            if not activity:
                continue
            for setup_day, action in reminder_rules(activity, start_day):
                reminders[setup_day].append((start_day, action, activity))

    with OUTPUT.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter="\t", lineterminator="\n")
        writer.writerow(["设置日期", "活动开启日期", "提醒内容", "排期表活动内容"])
        for setup_day in sorted(reminders):
            for start_day, action, activity in sorted(reminders[setup_day], key=lambda item: item[0]):
                writer.writerow(
                    [
                        f"{setup_day.month}月{setup_day.day}日",
                        f"{start_day.month}月{start_day.day}日",
                        action,
                        activity,
                    ]
                )

    print(f"生成完成：{OUTPUT}")
    print(f"提醒日期数：{len(reminders)}")
    print(f"提醒条目数：{sum(len(items) for items in reminders.values())}")


if __name__ == "__main__":
    main()
