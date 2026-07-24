from __future__ import annotations

import csv
import re
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from workday_calendar import adjusted_setup_rules, has_fixed_sunday_setup


SOURCE = Path("102国服活动排期表.xlsx")
OUTPUT = Path("活动设置提醒.tsv")
YEAR = 2026
MARMOT_PACKAGE_LINE = "32364: 火力全开：进攻土拨鼠（26/6/30版本）"
SPECIAL_SETUP_OVERRIDES = {
    ("32364", date(2026, 7, 26)): date(2026, 7, 24),
    ("1000296", date(2026, 7, 27)): date(2026, 7, 24),
}


def week_monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def clean_text(value: str) -> str:
    value = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value


def normalize_marmot_package_line(value: str) -> list[str]:
    line = value.strip()
    if not (
        "火力全开" in line
        and "土拨鼠" in line
        and ("29145" in line or "32364" in line)
    ):
        return [value]

    wrapped = line.startswith(("（", "("))
    package = f"（{MARMOT_PACKAGE_LINE}）" if wrapped else MARMOT_PACKAGE_LINE
    server_match = re.search(
        r"(?:[）)]\s*)?((?:S\s*)?1\s*[-~～—–]\s*(?:xxx|XXX|\d+)|S\s*\d+\s*[-~～—–]\s*S?\s*(?:xxx|XXX|\d+))\s*(?:[）)]\s*)?$",
        line,
        re.I,
    )
    if server_match:
        return [package, server_match.group(1).strip()]
    return [package]


def normalize_marmot_activity_text(value: str) -> str:
    lines: list[str] = []
    for line in value.splitlines():
        lines.extend(normalize_marmot_package_line(line))
    return "\n".join(lines)


def parse_month_day(value: str) -> date | None:
    match = re.fullmatch(r"\s*(\d{1,2})月(\d{1,2})日\s*", value or "")
    if not match:
        return None
    return date(YEAR, int(match.group(1)), int(match.group(2)))


def reminder_rules(activity: str, start_day: date, row_context: str = "") -> list[tuple[date, str]]:
    for activity_id, special_start_day in SPECIAL_SETUP_OVERRIDES:
        if activity_id in activity and start_day == special_start_day:
            return [(SPECIAL_SETUP_OVERRIDES[(activity_id, special_start_day)], "设置活动")]

    if has_fixed_sunday_setup(activity, row_context):
        rules = [(week_monday(start_day) - timedelta(days=1), "设置活动")]
    elif "区域迁徙" in activity:
        monday = week_monday(start_day) - timedelta(days=7)
        rules = [
            (monday, "区域迁徙：设置礼包+分组"),
            (monday + timedelta(days=2), "区域迁徙：设置活动+公布分组"),
        ]
    elif "本服联盟GVE" in activity:
        rules = [(week_monday(start_day) - timedelta(days=7), "本服联盟GVE：设置活动")]
    elif "跨服联盟GVE" in activity:
        rules = [(week_monday(start_day) - timedelta(days=2), "跨服联盟GVE：设置活动")]
    elif "VIP商店" in activity or "黑骑士" in activity:
        rules = [(week_monday(start_day), "设置活动")]
    elif "联盟远征" in activity or "功勋商店" in activity:
        rules = [(start_day, "设置活动")]
    elif "29145" in activity or "32364" in activity or "火力全开" in activity:
        rules = [(start_day - timedelta(days=1), "设置活动")]
    elif "土拨鼠" in activity:
        rules = [(start_day - timedelta(days=2), "设置活动")]
    elif "自选周卡" in activity or "进化连冲" in activity:
        rules = [(start_day - timedelta(days=3), "设置活动")]
    else:
        rules = [(start_day - timedelta(days=1), "设置活动")]
    return adjusted_setup_rules(rules, activity, row_context)


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
        row_context = clean_text("\n".join(value for value in row[:4] if value.strip()))
        for col, start_day in dates.items():
            if col >= len(row):
                continue
            activity = normalize_marmot_activity_text(clean_text(row[col]))
            if not activity:
                continue
            for setup_day, action in reminder_rules(activity, start_day, row_context):
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
