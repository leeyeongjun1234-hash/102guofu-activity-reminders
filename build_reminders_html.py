from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from html import escape
from pathlib import Path
import re
from textwrap import dedent
from zoneinfo import ZoneInfo

from daily_reminder import (
    MARMOT_MAIL_ITEMS,
    MARMOT_PACKAGE_LINE,
    Reminder,
    activity_name,
    compact_one_day_range,
    custom_reminder_lines,
    display_activity_name,
    duration_for,
    generic_package_blocks,
    is_marmot_shield_mail,
    load_reminders,
    marmot_shield_mail_text,
    server_text,
    time_range,
)


OUTPUT = Path("全部每日提醒.html")
ROOT_OUTPUT = Path("index.html")
SITE_OUTPUT = Path("site/index.html")
CHINA_TZ = ZoneInfo("Asia/Shanghai")
GENERATED_DAY = datetime.now(CHINA_TZ).date()
THEME_PACKAGES = {
    "万物新生": "29118: 万物新生神秘特供",
    "潮起潮落": "29119: 潮起潮落神秘特供",
    "旱季来临": "29120: 旱季来临神秘特供",
    "回归自然": "29121: 回归自然神秘特供",
}
CODED_LINE_RE = re.compile(r"^\s*(\d{5,7})(\s*[:：]\s*)(.*)$")
CODE_KIND_LABELS = {
    "activity": "活动",
    "package": "礼包",
}


def sort_key(item: Reminder) -> tuple[date, str, str]:
    return (item.start_day, activity_name(item.raw), item.raw)


def raw_time_range(line: str) -> str:
    line = line.strip()
    line = line.replace("开启时间：", "").replace("时间：", "").strip()
    line = line.replace("----", "~")
    return line


def raw_server_text(line: str) -> str:
    line = line.strip()
    line = line.replace("服务器：服务器：", "服务器：")
    return line


def leading_code_kind(value: str) -> str:
    match = CODED_LINE_RE.match(value.strip())
    if not match:
        return ""

    length = len(match.group(1))
    if length == 7:
        return "activity"
    if length == 5:
        return "package"
    return ""


def render_coded_line(value: str) -> str:
    line = value.strip()
    match = CODED_LINE_RE.match(line)
    if not match:
        return escape(line)

    code, separator, rest = match.groups()
    kind = leading_code_kind(line)
    if not kind:
        return escape(line)

    label = CODE_KIND_LABELS[kind]
    return (
        f'<span class="coded-line coded-line-{kind}">'
        f'<span class="item-code item-code-{kind}" data-kind="{escape(label, quote=True)}" '
        f'title="{escape(label, quote=True)}编号">{escape(code)}</span>'
        f'<span class="item-separator">{escape(separator)}</span>'
        f"{escape(rest)}"
        f"</span>"
    )


def block_code_classes(lines: list[str]) -> str:
    kinds = sorted({leading_code_kind(line) for line in lines if leading_code_kind(line)})
    return "".join(f" package-block-{kind}" for kind in kinds)


def card_code_class(value: str) -> str:
    for line in text_lines(value):
        kind = leading_code_kind(line)
        if kind:
            return f" card-{kind}-id"
    return ""


def package_section(title: str, lines: list[str], details: list[str]) -> str:
    package_rows = "\n".join(f"<div>{render_coded_line(line)}</div>" for line in lines)
    detail_rows = "\n".join(f'<div class="meta">{escape(line)}</div>' for line in details)
    classes = "package-block" + block_code_classes(lines)
    return f"""
      <div class="{classes}">
        <div class="package-title">{escape(title)}</div>
        <div class="package-lines">{package_rows}</div>
        {detail_rows}
      </div>
    """


def text_lines(value: str) -> list[str]:
    return [line.strip() for line in value.splitlines() if line.strip()] or [value.strip()]


def render_activity_name_lines(value: str) -> str:
    return "\n".join(f'<span class="activity-name-line">{render_coded_line(line)}</span>' for line in text_lines(value))


def render_text_lines(value: str) -> str:
    return "\n".join(
        '<span class="text-line text-line-empty"></span>' if not line.strip()
        else f'<span class="text-line">{render_coded_line(line)}</span>'
        for line in value.splitlines()
    )


def render_labeled_meta(label: str, value: str) -> str:
    if "\n" in value:
        return f'<div class="meta meta-lines"><span>{escape(label)}：</span>{render_text_lines(value)}</div>'
    return f'<div class="meta"><span>{escape(label)}：</span>{escape(value)}</div>'


def render_server_meta(base_name: str, value: str) -> str:
    if base_name == "进化连冲":
        return f'<div class="meta meta-lines">{render_text_lines(value)}</div>'
    return render_labeled_meta("服务器", value)


def marmot_shield_mail_details(item: Reminder) -> str:
    active_range = compact_one_day_range(item.start_day)
    mail_time_text = marmot_shield_mail_text(item.start_day).splitlines()[5].replace("邮件，赛季外，定时：", "")
    mail_rows = "\n".join(f'<div>{render_coded_line(line)}</div>' for line in MARMOT_MAIL_ITEMS)
    return f"""
      <div class="package-block package-block-package">
        <div class="package-title">土拨鼠服</div>
        <div class="package-lines"><div>{render_coded_line(MARMOT_PACKAGE_LINE)}</div></div>
        <div class="meta">时间：{escape(active_range)} UTC+8</div>
        <div class="meta">新服不自动开启，每日刷新 pop2</div>
      </div>
      <div class="package-block">
        <div class="package-title">区域征战服</div>
        <div class="meta">保护罩【{escape(active_range)} UTC+8】定时24h【赛季外，区域征战范围服 】</div>
      </div>
      <div class="package-block">
        <div class="package-title">邮件，赛季外</div>
        <div class="meta">定时：{escape(mail_time_text)}</div>
        <div class="package-lines">{mail_rows}</div>
      </div>
    """


def following_line_details(lines: list[str], prefixes: tuple[str, ...]) -> list[str]:
    details: list[str] = []
    for index, line in enumerate(lines):
        if not line.startswith(prefixes):
            continue
        details.append(line)
        if index + 1 < len(lines) and lines[index + 1].startswith("时间："):
            details.append(raw_time_range(lines[index + 1]))
    return details


def package_details(item: Reminder) -> str:
    name = activity_name(item.raw)
    lines = [line.strip() for line in item.raw.splitlines() if line.strip()]
    duration_label, days = duration_for(name, item.raw)
    default_details = [
        f"服务器：{server_text(item.raw, item.start_day)}",
        f"时间：{time_range(item.start_day, duration_label, days, name)}",
    ]

    if name == "蜂群宝藏" and "29811" in item.raw:
        package_lines = [line for line in lines if line.startswith(("29811", "29812", "29813", "29814"))]
        return package_section("配套礼包", package_lines, [*default_details, "每日刷新，新服不自动开启"])

    if name in THEME_PACKAGES:
        return package_section(
            "配套礼包",
            [THEME_PACKAGES[name]],
            [*default_details, "每日刷新：是", "新服自动开启：否"],
        )

    if name == "惊喜转盘" and "31444" in item.raw:
        package_lines = [line for line in lines if line.startswith(("31444", "31445", "31446", "31447"))]
        details = [
            raw_server_text(next((line for line in lines if line.startswith("服务器：")), default_details[0])),
            "新服不自动开，每日不刷新",
            raw_time_range(next((line for line in lines if line.startswith("时间：")), default_details[1])),
        ]
        return package_section("配套礼包", package_lines, details)

    if name == "无限寻宝" and "32134" in item.raw:
        package_lines = [line for line in lines if line.startswith("32134")]
        package_index = next((index for index, line in enumerate(lines) if line.startswith("32134")), -1)
        package_details = []
        if package_index >= 0:
            package_details = [
                raw_server_text(line) if line.startswith("服务器：") else f"时间：{raw_time_range(line)}" if line.startswith("时间：") else line
                for line in lines[package_index + 1 :]
                if line.startswith(("服务器：", "时间：", "每日刷新"))
            ]
        return package_section("配套礼包", package_lines, package_details or default_details)

    if name == "双倍盛典":
        giant_offer_lines = [line for line in lines if line.startswith(("32244", "32245", "32246"))]
        limited_offer_lines = [line for line in lines if line.startswith(("32173", "31924", "31925", "31926"))]
        package_time = next((line for line in reversed(lines) if line.startswith("时间：")), "")
        details = ["服务器：" + server_text(item.raw, item.start_day)]
        if package_time:
            details.append(raw_time_range(package_time))
        details.append("新服不自动开启，每日不刷新")

        sections = []
        if giant_offer_lines:
            sections.append(package_section("双倍巨献特惠", giant_offer_lines, details))
        if limited_offer_lines:
            sections.append(package_section("盛典限定", limited_offer_lines, details))
        return "\n".join(sections)

    if name == "落潮海岸" and any(package_id in item.raw for package_id in ("32346", "29681")):
        five_day_lines = [
            line
            for line in lines
            if line.startswith(("32346", "32347", "32348", "32351", "29681", "29682", "29683", "31937", "31938", "29686"))
        ]
        six_day_lines = [line for line in lines if line.startswith(("32345", "29680"))]
        five_day_details = ["服务器：" + server_text(item.raw, item.start_day)]
        five_day_time = next((line for line in lines if line.startswith("开启时间：")), "")
        if five_day_time:
            five_day_details.append(raw_time_range(five_day_time))
        five_day_details.append("每日刷新：是，新服自动开启：否")
        six_day_details = ["服务器：" + server_text(item.raw, item.start_day)]
        six_day_time = next((line for line in lines if line.startswith("时间：") and "（6天）" in line), "")
        if six_day_time:
            six_day_details.append(raw_time_range(six_day_time))
        six_day_details.append("每日刷新：是，新服自动开启：否")
        return "\n".join(
            [
                package_section("每日刷新礼包（5天）", five_day_lines, five_day_details),
                package_section("每日刷新礼包（6天）", six_day_lines, six_day_details),
            ]
        )

    if name == "蚁群派对" and "29750" in item.raw:
        package_lines = [
            line
            for line in lines
            if line.startswith(("29750", "29751", "29752", "29753", "31975", "31976", "29734"))
        ]
        details = ["服务器：" + server_text(item.raw, item.start_day)]
        package_time = next((line for line in lines if re.match(r"^\d{4}-\d{2}-\d{2} ", line)), "")
        if package_time:
            details.append(raw_time_range(package_time))
        details.append("每日刷新，新服不自动开启")
        return package_section("配套礼包", package_lines, details)

    if name == "蚁群狂欢":
        free_lines = following_line_details(lines, ("31714", "31715", "31716"))
        paid_lines = [line for line in lines if line.startswith(("32295", "32163", "32164", "32165", "32166"))]
        sections = []
        if free_lines:
            sections.append(package_section("免费礼包", free_lines, ["服务器：" + server_text(item.raw, item.start_day)]))
        if paid_lines:
            detail_time = next((line for line in lines if line.startswith("时间：") and "----" in line), "")
            details = ["服务器：" + server_text(item.raw, item.start_day)]
            if detail_time:
                details.append(raw_time_range(detail_time))
            details.append("新服不自动开启，每日不刷新")
            sections.append(package_section("付费礼包", paid_lines, details))
        return "\n".join(sections)

    # 通用识别：活动内容下方的礼包分组（5~6 位 ID 行）
    generic_sections = []
    for display, detail_lines in generic_package_blocks(item.raw):
        details = []
        for line in detail_lines:
            if line.startswith("服务器"):
                details.append(raw_server_text(line))
            elif line.startswith(("时间", "开启时间")) or re.match(r"^\d{4}-\d{2}-\d{2}", line):
                details.append(f"时间：{raw_time_range(line)}")
            else:
                details.append(line)
        generic_sections.append(package_section("配套礼包", display, details))
    return "\n".join(generic_sections)


def render_card(item: Reminder) -> str:
    custom_lines = custom_reminder_lines(item)
    if custom_lines:
        name = custom_lines[1] if len(custom_lines) > 1 and custom_lines[1].startswith(("100", "190", "291")) else custom_lines[0]
        details = custom_lines[1:] if name == custom_lines[0] else [custom_lines[0], *custom_lines[2:]]
        detail_rows = "\n".join(f'<div class="meta">{render_coded_line(line)}</div>' for line in details)
        return f"""
        <article class="card{card_code_class(name)}">
          <h3 class="activity-name">{render_activity_name_lines(name)}</h3>
          {detail_rows}
        </article>
        """

    name = display_activity_name(item.raw)
    if is_marmot_shield_mail(item.raw):
        action = "" if item.action == "设置活动" else f'<div class="meta action">{escape(item.action)}</div>'
        return f"""
        <article class="card{card_code_class(name)}">
          <h3 class="activity-name">{render_activity_name_lines(name)}</h3>
          {action}
          {marmot_shield_mail_details(item)}
        </article>
        """

    base_name = activity_name(item.raw)
    duration_label, days = duration_for(base_name, item.raw)
    action = "" if item.action == "设置活动" else f'<div class="meta action">{escape(item.action)}</div>'
    packages = package_details(item)
    return f"""
    <article class="card{card_code_class(name)}">
      <h3 class="activity-name">{render_activity_name_lines(name)}</h3>
      {action}
      {render_server_meta(base_name, server_text(item.raw, item.start_day))}
      {render_labeled_meta("时间", time_range(item.start_day, duration_label, days, base_name))}
      {packages}
    </article>
    """


def summary_display_name(item: Reminder) -> str:
    custom_lines = custom_reminder_lines(item)
    if custom_lines:
        if len(custom_lines) > 1 and custom_lines[1].startswith(("100", "190", "291")):
            return custom_lines[1]
        return custom_lines[0]
    return display_activity_name(item.raw)


def render_summary(
    title: str,
    target_day: date | None,
    items: list[Reminder],
    empty_text: str,
    highlight: str = "",
    summary_id: str = "",
) -> str:
    id_attr = f' id="{escape(summary_id, quote=True)}"' if summary_id else ""
    if target_day is None or not items:
        return dedent(f"""
        <section class="summary-card"{id_attr}>
          <div class="summary-label">{escape(title)}</div>
          <div class="summary-date">{escape(empty_text)}</div>
          <div class="summary-meta">当前没有可展示的提醒</div>
        </section>
        """).strip()

    names = [summary_display_name(item) for item in sorted(items, key=sort_key)]
    unique_names = list(dict.fromkeys(names))
    display_names = "\n".join(
        f'<div class="summary-name activity-name">{render_activity_name_lines(name)}</div>'
        for name in unique_names
    )

    badge = f'<span class="next-badge">{escape(highlight)}</span>' if highlight else ""
    return dedent(f"""
    <section class="summary-card"{id_attr}>
      <div class="summary-label">{escape(title)}{badge}</div>
      <div class="summary-date">{target_day:%Y-%m-%d}</div>
      <div class="summary-meta">{display_names}</div>
    </section>
    """).strip()


def build_html(reminders: list[Reminder]) -> str:
    grouped: dict[date, list[Reminder]] = defaultdict(list)
    for item in reminders:
        if item.setup_day < GENERATED_DAY:
            continue
        grouped[item.setup_day].append(item)

    ordered_days = sorted(grouped)
    today_items = sorted(grouped.get(GENERATED_DAY, []), key=sort_key)
    next_day = next((day for day in ordered_days if day > GENERATED_DAY), None)
    next_items = sorted(grouped.get(next_day, []), key=sort_key) if next_day else []

    sections: list[str] = []
    for setup_day in ordered_days:
        items = sorted(grouped[setup_day], key=sort_key)
        marker = '<span class="inline-badge">下一次</span>' if setup_day == next_day else ""
        cards = "\n".join(render_card(item) for item in items)
        sections.append(
            f"""
            <details class="day" data-date="{setup_day:%Y-%m-%d}" open>
              <summary>
                <span class="date"><span class="date-text">{setup_day:%Y-%m-%d}</span>{marker}</span>
                <span class="count">{len(items)} 个提醒</span>
              </summary>
              <div class="cards">
                {cards}
              </div>
            </details>
            """
        )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>全部每日活动提醒</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f5f6f8;
      --panel: #ffffff;
      --panel-2: #f0f3f8;
      --text: #1f2937;
      --muted: #586274;
      --line: #d8dee8;
      --accent: #c2410c;
      --accent-soft: #fff1ea;
      --shadow: 0 8px 24px rgba(15, 23, 42, 0.06);
    }}

    * {{
      box-sizing: border-box;
    }}

    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 14px/1.5 "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
    }}

    .wrap {{
      max-width: 1200px;
      margin: 0 auto;
      padding: 24px;
    }}

    .page-nav {{
      display: inline-flex;
      gap: 4px;
      margin-bottom: 18px;
      padding: 4px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #f8fafc;
      white-space: nowrap;
    }}

    .nav-link {{
      padding: 7px 11px;
      border-radius: 5px;
      color: #475467;
      text-decoration: none;
      font-weight: 700;
    }}

    .nav-link:hover {{
      background: #eef2f6;
    }}

    .nav-link.active {{
      background: #ffffff;
      color: #111827;
      box-shadow: 0 1px 3px rgba(15, 23, 42, 0.12);
    }}

    .top {{
      display: grid;
      gap: 8px;
      margin-bottom: 20px;
    }}

    h1 {{
      margin: 0;
      font-size: 28px;
      font-weight: 700;
    }}

    .sub {{
      color: var(--muted);
      font-size: 14px;
    }}

    .summary-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 18px;
    }}

    .summary-card {{
      display: grid;
      gap: 6px;
      padding: 16px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      box-shadow: var(--shadow);
      min-height: 112px;
    }}

    .summary-label {{
      color: var(--muted);
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 15px;
    }}

    .summary-date {{
      font-size: 34px;
      font-weight: 700;
      line-height: 1.1;
    }}

    .summary-meta {{
      color: var(--text);
      font-size: 14px;
      display: grid;
      gap: 4px;
      word-break: break-word;
    }}

    .summary-name {{
      display: grid;
      gap: 2px;
    }}

    .activity-name {{
      word-break: break-word;
      overflow-wrap: anywhere;
    }}

    .activity-name-line {{
      display: block;
    }}

    .next-badge,
    .inline-badge {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 2px 8px;
      border-radius: 999px;
      background: #dcfce7;
      color: #166534;
      font-size: 12px;
      font-weight: 700;
      vertical-align: middle;
    }}

    .inline-badge {{
      margin-left: 8px;
    }}

    .toolbar {{
      position: sticky;
      top: 0;
      z-index: 10;
      display: flex;
      gap: 12px;
      align-items: center;
      padding: 12px 0 16px;
      background: linear-gradient(to bottom, var(--bg) 75%, rgba(245, 246, 248, 0));
    }}

    .search {{
      flex: 1;
      min-width: 220px;
      padding: 10px 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      color: var(--text);
      font: inherit;
    }}

    .toolbar button {{
      padding: 10px 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      color: var(--text);
      cursor: pointer;
      font: inherit;
    }}

    .day {{
      margin-bottom: 16px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      box-shadow: var(--shadow);
      overflow: hidden;
    }}

    .day summary {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      list-style: none;
      cursor: pointer;
      padding: 14px 16px;
      background: var(--panel-2);
    }}

    .day summary::-webkit-details-marker {{
      display: none;
    }}

    .date {{
      font-size: 18px;
      font-weight: 700;
    }}

    .count {{
      color: var(--muted);
      white-space: nowrap;
    }}

    .cards {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      grid-auto-rows: auto;
      grid-auto-flow: dense;
      align-items: start;
      gap: 10px;
      padding: 16px;
    }}

    body.layout-ready .cards {{
      grid-auto-rows: 8px;
    }}

    .card {{
      align-self: start;
      display: grid;
      gap: 8px;
      padding: 14px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
    }}

    .card h3 {{
      margin: 0;
      font-size: 18px;
      line-height: 1.3;
    }}

    .meta {{
      color: var(--text);
      word-break: break-word;
    }}

    .meta span {{
      color: var(--muted);
    }}

    .meta-lines {{
      display: grid;
      gap: 3px;
    }}

    .text-line {{
      display: block;
    }}

    .package-block {{
      display: grid;
      gap: 6px;
      margin-top: 8px;
      padding-top: 12px;
      border-top: 1px solid var(--line);
    }}

    .package-title {{
      color: var(--muted);
      font-weight: 700;
    }}

    .package-lines {{
      display: grid;
      gap: 3px;
      font-weight: 700;
      word-break: break-word;
    }}

    .action {{
      color: var(--accent);
      background: var(--accent-soft);
      border-radius: 6px;
      padding: 6px 8px;
      width: fit-content;
    }}

    .hidden {{
      display: none;
    }}

    .hidden-by-date {{
      display: none;
    }}

    body.locked .wrap {{
      display: none;
    }}

    body:not(.locked) .lock-screen {{
      display: none;
    }}

    .lock-screen {{
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 24px;
    }}

    .lock-panel {{
      width: min(420px, 100%);
      display: grid;
      gap: 14px;
      padding: 24px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      box-shadow: var(--shadow);
    }}

    .lock-panel h1 {{
      font-size: 24px;
    }}

    .lock-panel label {{
      color: var(--muted);
      font-weight: 700;
    }}

    .lock-row {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 10px;
    }}

    .lock-row input {{
      min-width: 0;
      padding: 10px 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      color: var(--text);
      font: inherit;
    }}

    .lock-row button {{
      padding: 10px 14px;
      border: 1px solid #166534;
      border-radius: 8px;
      background: #166534;
      color: #ffffff;
      cursor: pointer;
      font: inherit;
      font-weight: 700;
    }}

    .lock-error {{
      min-height: 20px;
      color: #b91c1c;
      font-weight: 700;
    }}

    @media (max-width: 720px) {{
      .wrap {{
        padding: 16px;
      }}

      .page-nav {{
        display: flex;
        overflow-x: auto;
      }}

      h1 {{
        font-size: 24px;
      }}

      .summary-grid {{
        grid-template-columns: 1fr;
      }}

      .summary-date {{
        font-size: 28px;
      }}

      .toolbar {{
        flex-wrap: wrap;
      }}

      .toolbar button,
      .search {{
        width: 100%;
      }}

      .day summary {{
        align-items: flex-start;
        flex-direction: column;
      }}

      .cards {{
        grid-template-columns: 1fr;
      }}

      .lock-row {{
        grid-template-columns: 1fr;
      }}
    }}

    @media (min-width: 721px) and (max-width: 980px) {{
      .cards {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
    }}
  </style>
</head>
<body class="locked">
  <section class="lock-screen" aria-label="密码验证">
    <form id="lockForm" class="lock-panel">
      <h1>请输入密码</h1>
      <label for="lockPassword">密码</label>
      <div class="lock-row">
        <input id="lockPassword" type="password" autocomplete="current-password" autofocus>
        <button type="submit">进入</button>
      </div>
      <div id="lockError" class="lock-error" role="alert"></div>
    </form>
  </section>
  <div class="wrap">
    <nav class="page-nav" aria-label="页面导航">
      <a href="index.html" class="nav-link active" aria-current="page">活动提醒</a>
      <a href="season-cn.html" class="nav-link">国服赛季</a>
      <a href="season-overseas.html" class="nav-link">海外赛季</a>
    </nav>
    <header class="top">
      <h1>全部每日活动提醒</h1>
      <div class="sub">按设置日期汇总展示，日期与时间均按北京时间 UTC+8 计算。</div>
    </header>

    <div class="toolbar">
      <input id="search" class="search" type="search" placeholder="搜索日期、活动名、服务器">
      <button type="button" id="expandAll">全部展开</button>
      <button type="button" id="collapseAll">全部收起</button>
    </div>

    <section class="summary-grid">
      {render_summary("今天要设置什么", GENERATED_DAY, today_items, "今天没有要设置的活动", summary_id="todaySummary")}
      {render_summary("下一次要设置什么", next_day, next_items, "没有下一次提醒", "下一次", summary_id="nextSummary")}
    </section>

    <main id="days">
      {"".join(sections)}
    </main>
  </div>

  <script>
    const AUTH_KEY = 'activity-reminders-authenticated-until';
    const AUTH_TTL_MS = 48 * 60 * 60 * 1000;
    const PASSWORD_HASH = '542df2c1e629af51b87cf02f575af7fc8cd25a26d6cf9a54e7ac3775bce0d8f6';
    const lockForm = document.getElementById('lockForm');
    const lockPassword = document.getElementById('lockPassword');
    const lockError = document.getElementById('lockError');

    function unlockPage() {{
      document.body.classList.remove('locked');
      window.dispatchEvent(new Event('activity-reminders-unlocked'));
    }}

    async function sha256(value) {{
      const bytes = new TextEncoder().encode(value);
      const digest = await crypto.subtle.digest('SHA-256', bytes);
      return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, '0')).join('');
    }}

    const authenticatedUntil = Number(localStorage.getItem(AUTH_KEY) || 0);
    if (authenticatedUntil > Date.now()) {{
      unlockPage();
    }} else {{
      localStorage.removeItem(AUTH_KEY);
    }}

    lockForm.addEventListener('submit', async (event) => {{
      event.preventDefault();
      const inputHash = await sha256(lockPassword.value);
      if (inputHash === PASSWORD_HASH) {{
        localStorage.setItem(AUTH_KEY, String(Date.now() + AUTH_TTL_MS));
        lockPassword.value = '';
        lockError.textContent = '';
        unlockPage();
        return;
      }}

      lockError.textContent = '密码错误';
      lockPassword.select();
    }});

    const search = document.getElementById('search');
    const dayNodes = [...document.querySelectorAll('.day')];
    const expandAll = document.getElementById('expandAll');
    const collapseAll = document.getElementById('collapseAll');
    const todaySummary = document.getElementById('todaySummary');
    const nextSummary = document.getElementById('nextSummary');
    const cardContainers = [...document.querySelectorAll('.cards')];
    let layoutQueued = false;

    function todayString() {{
      const formatter = new Intl.DateTimeFormat('en-CA', {{
        timeZone: 'Asia/Shanghai',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
      }});
      const parts = Object.fromEntries(
        formatter.formatToParts(new Date()).map((part) => [part.type, part.value])
      );
      return `${{parts.year}}-${{parts.month}}-${{parts.day}}`;
    }}

    function localTodayString() {{
      const now = new Date();
      const year = now.getFullYear();
      const month = String(now.getMonth() + 1).padStart(2, '0');
      const day = String(now.getDate()).padStart(2, '0');
      return `${{year}}-${{month}}-${{day}}`;
    }}

    function activityNameText(node) {{
      const lines = [...node.querySelectorAll('.activity-name-line')]
        .map((line) => line.textContent.trim())
        .filter(Boolean);
      return lines.length ? lines.join('\\n') : node.textContent.trim();
    }}

    function appendActivityNameLines(container, name) {{
      name.split('\\n').map((line) => line.trim()).filter(Boolean).forEach((line) => {{
        const lineNode = document.createElement('span');
        lineNode.className = 'activity-name-line';
        appendCodedLine(lineNode, line);
        container.appendChild(lineNode);
      }});
    }}

    function appendCodedLine(container, line) {{
      const match = line.trim().match(/^(\\d{{5,7}})(\\s*[:：]\\s*)(.*)$/);
      if (!match) {{
        container.textContent = line;
        return;
      }}

      const [, code, separator, rest] = match;
      const kind = code.length === 7 ? 'activity' : code.length === 5 ? 'package' : '';
      if (!kind) {{
        container.textContent = line;
        return;
      }}

      const label = kind === 'activity' ? '活动' : '礼包';
      const wrapper = document.createElement('span');
      wrapper.className = `coded-line coded-line-${{kind}}`;

      const codeNode = document.createElement('span');
      codeNode.className = `item-code item-code-${{kind}}`;
      codeNode.dataset.kind = label;
      codeNode.title = `${{label}}编号`;
      codeNode.textContent = code;

      const separatorNode = document.createElement('span');
      separatorNode.className = 'item-separator';
      separatorNode.textContent = separator;

      wrapper.append(codeNode, separatorNode, document.createTextNode(rest));
      container.appendChild(wrapper);
    }}

    function uniqueCardNames(day) {{
      const names = [...day.querySelectorAll('.card h3')].map(activityNameText);
      return [...new Set(names)];
    }}

    function setSummary(card, title, day, emptyText, badgeText = '') {{
      const label = card.querySelector('.summary-label');
      const summaryDate = card.querySelector('.summary-date');
      const meta = card.querySelector('.summary-meta');
      label.textContent = title;
      if (badgeText) {{
        const badge = document.createElement('span');
        badge.className = 'next-badge';
        badge.textContent = badgeText;
        label.appendChild(badge);
      }}

      meta.replaceChildren();
      if (!day) {{
        summaryDate.textContent = emptyText;
        const empty = document.createElement('div');
        empty.textContent = '当前没有可展示的提醒';
        meta.appendChild(empty);
        return;
      }}

      summaryDate.textContent = day.dataset.date;
      uniqueCardNames(day).forEach((name) => {{
        const row = document.createElement('div');
        row.className = 'summary-name activity-name';
        appendActivityNameLines(row, name);
        meta.appendChild(row);
      }});
    }}

    function layoutCards(container) {{
      if (!container.getClientRects().length) return;
      const styles = getComputedStyle(container);
      const rowHeight = parseFloat(styles.gridAutoRows) || 8;
      const rowGap = parseFloat(styles.rowGap) || 0;
      container.querySelectorAll('.card').forEach((card) => {{
        card.style.gridRowEnd = 'auto';
      }});

      container.querySelectorAll('.card').forEach((card) => {{
        const height = card.getBoundingClientRect().height;
        const span = Math.max(1, Math.ceil((height + rowGap) / (rowHeight + rowGap)));
        card.style.gridRowEnd = `span ${{span}}`;
      }});
    }}

    function layoutAllCards() {{
      cardContainers.forEach(layoutCards);
    }}

    function scheduleCardLayout() {{
      if (document.body.classList.contains('locked')) return;
      if (layoutQueued) return;
      layoutQueued = true;
      requestAnimationFrame(() => {{
        layoutQueued = false;
        document.body.classList.add('layout-ready');
        layoutAllCards();
      }});
    }}

    function scheduleVisibleCardLayout() {{
      if (document.body.classList.contains('locked')) return;
      scheduleCardLayout();
      requestAnimationFrame(() => {{
        document.body.classList.add('layout-ready');
        layoutAllCards();
        requestAnimationFrame(layoutAllCards);
      }});
    }}

    function syncDateState() {{
      const today = todayString();
      const availableDays = [];
      dayNodes.forEach((day) => {{
        const isPast = day.dataset.date < today;
        day.classList.toggle('hidden-by-date', isPast);
        day.querySelectorAll('.inline-badge').forEach((badge) => badge.remove());
        if (!isPast) availableDays.push(day);
      }});

      const todayDay = availableDays.find((day) => day.dataset.date === today);
      const nextDay = availableDays.find((day) => day.dataset.date > today);
      if (nextDay) {{
        const badge = document.createElement('span');
        badge.className = 'inline-badge';
        badge.textContent = '下一次';
        nextDay.querySelector('.date').appendChild(badge);
      }}

      setSummary(todaySummary, '今天要设置什么', todayDay, '今天没有要设置的活动');
      setSummary(nextSummary, '下一次要设置什么', nextDay, '没有下一次提醒', '下一次');
    }}

    function applyFilter() {{
      const query = search.value.trim().toLowerCase();
      dayNodes.forEach((day) => {{
        if (day.classList.contains('hidden-by-date')) {{
          day.classList.add('hidden');
          return;
        }}
        const text = day.textContent.toLowerCase();
        const matched = !query || text.includes(query);
        day.classList.toggle('hidden', !matched);
        if (query && matched) day.open = true;
      }});
    }}

    search.addEventListener('input', applyFilter);
    search.addEventListener('input', scheduleCardLayout);
    expandAll.addEventListener('click', () => {{
      dayNodes.forEach((day) => day.open = true);
      scheduleCardLayout();
    }});
    collapseAll.addEventListener('click', () => {{
      dayNodes.forEach((day) => day.open = false);
      scheduleCardLayout();
    }});
    dayNodes.forEach((day) => {{
      day.addEventListener('toggle', () => {{
        if (day.open) scheduleVisibleCardLayout();
      }});
    }});
    window.addEventListener('resize', scheduleVisibleCardLayout);
    window.addEventListener('load', scheduleVisibleCardLayout);
    window.addEventListener('activity-reminders-unlocked', scheduleVisibleCardLayout);
    syncDateState();
    applyFilter();
    scheduleVisibleCardLayout();
  </script>
</body>
</html>
"""


def main() -> None:
    reminders = load_reminders()
    html = build_html(reminders)
    OUTPUT.write_text(html, encoding="utf-8")
    ROOT_OUTPUT.write_text(html, encoding="utf-8")
    SITE_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    SITE_OUTPUT.write_text(html, encoding="utf-8")
    print(f"已生成：{OUTPUT}")
    print(f"已生成：{ROOT_OUTPUT}")
    print(f"已生成：{SITE_OUTPUT}")


if __name__ == "__main__":
    main()
