from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from html import escape
from pathlib import Path
import re
from urllib.parse import quote
from zoneinfo import ZoneInfo

from build_season_pages import navigation, read_sheet


ROOT = Path(__file__).resolve().parent
TODAY = datetime.now(ZoneInfo("Asia/Shanghai")).date()
OUTPUT_DIRS = [ROOT, ROOT / "site"]
REGISTRATION_ACTIVITY = "1000404：跨区召集"
PREVIEW_ACTIVITY = "1000407：赛季预告（方案B）"
SCHEDULE_INTERVAL_DAYS = 63
SCHEDULE_BATCH_INCREMENT = 3
CN_SOURCE = ROOT / "102国服赛季排期表.xlsx"
OVERSEAS_SOURCE = ROOT / "102海外赛季排期表.xlsx"
CN_SEASONS = [(0, "一赛季"), (1, "二赛季"), (2, "三赛季（密林）"), (3, "四赛季（湿地）"), (4, "3X1赛季（异变密林）")]
OVERSEAS_SEASONS = [
    (1, "一赛季（海岛）"),
    (2, "二赛季（荒野）"),
    (4, "三赛季（密林）"),
    (6, "四赛季（湿地）"),
    (7, "3X1赛季"),
    (8, "2X1赛季"),
]


@dataclass
class SeasonReminder:
    region: str
    batch: str
    kind: str
    reminder_day: date
    registration_day: date
    lead_days: int
    seasons: set[str] = field(default_factory=set)


@dataclass
class SeasonSchedule:
    region: str
    batch: str
    registration_day: date
    seasons: set[str] = field(default_factory=set)


def parse_date_text(value: str) -> date | None:
    match = re.search(r"(\d{1,2})\s*[月/](\d{1,2})\s*日?", value)
    if not match:
        return None
    try:
        return date(TODAY.year, int(match.group(1)), int(match.group(2)))
    except ValueError:
        return None


def row_date(sheet, row: int, column: int) -> date | None:
    cell = sheet.cells.get((row, column))
    if cell is None:
        return None
    if cell.date_value is not None:
        return cell.date_value.date()
    return parse_date_text(cell.value)


def active_seasons(sheet, row: int, season_columns: list[tuple[int, str]]) -> list[str]:
    result = []
    for column, name in season_columns:
        value = sheet.cells.get((row, column))
        text = value.value.strip() if value else ""
        if text and text not in {"/", "-"} and "不开赛季" not in text:
            result.append(name)
    return result


def batch_name(sheet, row: int) -> str:
    cell = sheet.cells.get((row, 0))
    if cell is None:
        return ""
    return next((line.strip() for line in cell.value.splitlines() if line.strip()), "")


def batch_identity(value: str) -> str:
    match = re.search(r"第\s*0*(\d+)\s*批", value)
    return f"第{int(match.group(1))}批" if match else value


def collect_reminders(
    source: Path,
    region: str,
    registration_column: int,
    season_columns: list[tuple[int, str]],
) -> list[SeasonReminder]:
    sheet = read_sheet(source)
    merged: dict[tuple[str, str, date, int], SeasonReminder] = {}
    for row in range(sheet.rows):
        batch = batch_identity(batch_name(sheet, row))
        if not batch.startswith("第"):
            continue
        registration_day = row_date(sheet, row, registration_column)
        if registration_day is None or registration_day < TODAY:
            continue
        seasons = active_seasons(sheet, row, season_columns)
        if not seasons:
            continue

        if region == "海外赛季":
            early_seasons = [name for index, name in season_columns if index in {1, 2} and name in seasons]
            regular_seasons = [name for index, name in season_columns if index not in {1, 2} and name in seasons]
            preview_groups = [(early_seasons, 28), (regular_seasons, 10)]
        else:
            preview_groups = [(seasons, 10)]

        for names, lead_days in preview_groups:
            if names:
                add_reminder(merged, region, batch, "预告活动", registration_day, lead_days, names)
        add_reminder(merged, region, batch, "报名活动", registration_day, 3, seasons)

    return sorted(
        merged.values(),
        key=lambda item: (item.reminder_day, item.region, batch_number(item.batch), item.kind),
    )


def collect_source_schedules(
    source: Path,
    region: str,
    registration_column: int,
    season_columns: list[tuple[int, str]],
) -> list[SeasonSchedule]:
    sheet = read_sheet(source)
    merged: dict[tuple[str, date], SeasonSchedule] = {}
    for row in range(sheet.rows):
        raw_batch = batch_name(sheet, row)
        if not raw_batch.startswith("第"):
            continue
        registration_day = row_date(sheet, row, registration_column)
        if registration_day is None or registration_day < TODAY:
            continue
        seasons = active_seasons(sheet, row, season_columns)
        batch = batch_identity(raw_batch)
        key = (batch, registration_day)
        item = merged.setdefault(key, SeasonSchedule(region, batch, registration_day))
        item.seasons.update(seasons)
    return sorted(merged.values(), key=lambda item: (item.registration_day, batch_number(item.batch)))


def schedule_horizon() -> date:
    return date(TODAY.year + 3, TODAY.month, TODAY.day)


def collect_schedules(
    source: Path,
    region: str,
    registration_column: int,
    season_columns: list[tuple[int, str]],
) -> list[SeasonSchedule]:
    sheet = read_sheet(source)
    source_items: list[SeasonSchedule] = []
    for row in range(sheet.rows):
        raw_batch = batch_name(sheet, row)
        if not raw_batch.startswith("第"):
            continue
        registration_day = row_date(sheet, row, registration_column)
        if registration_day is None:
            continue
        source_items.append(
            SeasonSchedule(
                region,
                batch_identity(raw_batch),
                registration_day,
            )
        )
    if not source_items:
        return []

    anchor = max(source_items, key=lambda item: (batch_number(item.batch), item.registration_day))
    anchor_number = batch_number(anchor.batch)
    first_index = max(
        0,
        (TODAY - anchor.registration_day).days // SCHEDULE_INTERVAL_DAYS + 1,
    ) if anchor.registration_day < TODAY else 0
    rows: list[SeasonSchedule] = []
    index = first_index
    while True:
        registration_day = anchor.registration_day + timedelta(days=SCHEDULE_INTERVAL_DAYS * index)
        if registration_day > schedule_horizon():
            break
        rows.append(
            SeasonSchedule(
                region,
                f"第{anchor_number + SCHEDULE_BATCH_INCREMENT * index}批",
                registration_day,
            )
        )
        index += 1
    return rows


def add_reminder(
    merged: dict[tuple[str, str, date, int], SeasonReminder],
    region: str,
    batch: str,
    kind: str,
    registration_day: date,
    lead_days: int,
    seasons: list[str],
) -> None:
    key = (region, batch, registration_day, lead_days)
    reminder_day = registration_day - timedelta(days=lead_days)
    item = merged.get(key)
    if item is None:
        item = SeasonReminder(region, batch, kind, reminder_day, registration_day, lead_days)
        merged[key] = item
    item.seasons.update(seasons)


def batch_number(value: str) -> int:
    match = re.search(r"第\s*(\d+)\s*批", value)
    return int(match.group(1)) if match else 9999


def date_text(value: date) -> str:
    return value.strftime("%Y-%m-%d")


def reminder_title(item: SeasonReminder) -> str:
    return f"{item.region} · {item.batch}"


def render_reminder(item: SeasonReminder) -> str:
    activity = PREVIEW_ACTIVITY if item.kind == "预告活动" else REGISTRATION_ACTIVITY
    seasons = "、".join(sorted(item.seasons))
    return f"""
      <article class="reminder-card">
        <div class="reminder-kind">{escape(item.kind)}</div>
        <h2>{escape(reminder_title(item))}</h2>
        <div class="reminder-line"><span>需要开启：</span>{escape(activity)}</div>
        <div class="reminder-line"><span>涉及赛季：</span>{escape(seasons)}</div>
        <div class="reminder-line"><span>报名期开始：</span>{date_text(item.registration_day)}</div>
        <div class="reminder-line"><span>提前：</span>{item.lead_days} 天</div>
      </article>
    """


def render_groups(items: list[SeasonReminder]) -> str:
    groups: dict[date, list[SeasonReminder]] = defaultdict(list)
    for item in items:
        groups[item.reminder_day].append(item)
    sections = []
    for reminder_day in sorted(groups):
        label = "今天" if reminder_day == TODAY else ""
        cards = "".join(render_reminder(item) for item in groups[reminder_day])
        sections.append(
            f"""
            <section class="reminder-day">
              <header class="reminder-day-header">
                <span class="reminder-date">{date_text(reminder_day)}</span>
                {f'<span class="today-badge">{label}</span>' if label else ""}
                <span class="reminder-count">{len(groups[reminder_day])} 个提醒</span>
              </header>
              <div class="reminder-cards">{cards}</div>
            </section>
            """
        )
    return "".join(sections) or '<div class="empty">当前没有需要显示的赛季提醒。</div>'


def render_date(value: date) -> str:
    return value.strftime("%Y-%m-%d")


def render_batch_cell(item: SeasonSchedule, nearest: bool) -> str:
    marker = '<span class="nearest-marker" title="最近的批次"></span>' if nearest else ""
    return f'<td class="batch-cell">{marker}<strong>{escape(item.batch)}</strong></td>'


def render_date_cell(value: date) -> str:
    date_value = render_date(value)
    if value == TODAY:
        return f'<td class="date-cell today-date"><span class="today-date-value">{date_value}</span></td>'
    return f'<td class="date-cell">{date_value}</td>'


def render_schedule_table(items: list[SeasonSchedule], region: str) -> str:
    if not items:
        return '<div class="empty">当前没有需要显示的赛季提醒。</div>'
    nearest_day = min(item.registration_day for item in items)
    rows = []
    for item in items:
        nearest = item.registration_day == nearest_day
        registration_day = item.registration_day
        registration_reminder = registration_day - timedelta(days=3)
        if region == "国服赛季":
            preview_day = registration_day - timedelta(days=10)
            preview_reminder = preview_day - timedelta(days=3)
            cells = [
                render_batch_cell(item, nearest),
                render_date_cell(preview_day),
                render_date_cell(preview_reminder),
                render_date_cell(registration_day),
                render_date_cell(registration_reminder),
            ]
        else:
            early_preview_day = registration_day - timedelta(days=28)
            early_preview_reminder = early_preview_day - timedelta(days=7)
            regular_preview_day = registration_day - timedelta(days=10)
            regular_preview_reminder = regular_preview_day - timedelta(days=3)
            cells = [
                render_batch_cell(item, nearest),
                render_date_cell(early_preview_day),
                render_date_cell(early_preview_reminder),
                render_date_cell(regular_preview_day),
                render_date_cell(regular_preview_reminder),
                render_date_cell(registration_day),
                render_date_cell(registration_reminder),
            ]
        row_class = ' class="nearest-row"' if nearest else ""
        rows.append(f"<tr{row_class}>{''.join(cells)}</tr>")

    if region == "国服赛季":
        headers = ["批次", "预告日期", "提醒日期", "报名日期", "提醒日期"]
    else:
        headers = ["批次", "一二赛季预告日期", "提醒日期", "预告日期", "提醒日期", "报名日期", "提醒日期"]
    header_html = "".join(f"<th>{escape(header)}</th>" for header in headers)
    return f"""
      <div class="schedule-table-wrap">
        <table class="schedule-table">
          <thead><tr>{header_html}</tr></thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
      </div>
    """


def render_page(
    source: Path,
    title: str,
    active: str,
    region: str,
    registration_column: int,
    season_columns: list[tuple[int, str]],
    output: Path,
) -> str:
    items = collect_schedules(source, region, registration_column, season_columns)
    source_href = ("../" if output.parent.name == "site" else "") + quote(source.name)
    subtitle = f"报名期早于 {date_text(TODAY)} 的批次已隐藏 · 已生成未来三年排期 · 最近批次已标红"
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <style>
    :root {{ color-scheme: light; --bg:#f5f6f8; --panel:#fff; --text:#1f2937; --muted:#667085; --line:#d8dee8; --green:#166534; --orange:#c2410c; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; min-height:100vh; background:var(--bg); color:var(--text); font:14px/1.5 "Segoe UI","PingFang SC","Microsoft YaHei",sans-serif; }}
    body.locked .app {{ visibility:hidden; }}
    body:not(.locked) .lock-screen {{ display:none; }}
    .lock-screen {{ position:fixed; inset:0; z-index:100; display:grid; place-items:center; padding:20px; background:var(--bg); }}
    .lock-panel {{ width:min(400px,100%); display:grid; gap:14px; padding:24px; border:1px solid var(--line); border-radius:8px; background:var(--panel); box-shadow:0 12px 32px rgba(15,23,42,.12); }}
    .lock-panel h1 {{ margin:0; font-size:24px; }}
    .lock-panel label {{ color:var(--muted); font-weight:700; }}
    .lock-row {{ display:grid; grid-template-columns:minmax(0,1fr) auto; gap:10px; }}
    .lock-row input, .lock-row button {{ min-height:40px; border:1px solid var(--line); border-radius:6px; font:inherit; }}
    .lock-row input {{ min-width:0; padding:9px 11px; background:#fff; color:var(--text); }}
    .lock-row button {{ padding:9px 14px; border-color:var(--green); background:var(--green); color:#fff; font-weight:700; cursor:pointer; }}
    .lock-error {{ min-height:20px; color:#b91c1c; font-weight:700; }}
    .app {{ max-width:1200px; margin:0 auto; padding:24px; }}
    .page-header {{ display:flex; align-items:flex-start; justify-content:space-between; gap:20px; margin-bottom:18px; }}
    h1 {{ margin:0; font-size:28px; line-height:1.25; }}
    .subtitle {{ margin-top:5px; color:var(--muted); }}
    .page-nav {{ display:flex; gap:4px; padding:4px; border:1px solid var(--line); border-radius:8px; background:#f8fafc; white-space:nowrap; }}
    .nav-link {{ padding:7px 11px; border-radius:5px; color:#475467; text-decoration:none; font-weight:700; }}
    .nav-link:hover {{ background:#eef2f6; }}
    .nav-link.active {{ background:#fff; color:#111827; box-shadow:0 1px 3px rgba(15,23,42,.12); }}
    .rule-strip {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px; margin-bottom:18px; }}
    .rule {{ padding:12px 14px; border:1px solid var(--line); border-radius:8px; background:var(--panel); }}
    .rule strong {{ display:block; margin-bottom:2px; }}
    .rule span {{ color:var(--muted); }}
    .schedule-table-wrap {{ overflow-x:auto; border:1px solid var(--line); border-radius:8px; background:#fff; }}
    .schedule-table {{ width:100%; min-width:760px; border-collapse:collapse; table-layout:fixed; }}
    .schedule-table th, .schedule-table td {{ padding:11px 12px; border:1px solid var(--line); text-align:center; vertical-align:middle; white-space:nowrap; }}
    .schedule-table th {{ background:#eef2f6; color:#475467; font-weight:700; }}
    .schedule-table th:first-child, .schedule-table td:first-child {{ width:24%; text-align:left; }}
    .schedule-table tbody tr:hover {{ background:#fffaf5; }}
    .batch-cell {{ position:relative; }}
    .batch-cell strong {{ display:block; }}
    .date-cell {{ font-variant-numeric:tabular-nums; }}
    .today-date-value {{ display:inline-block; padding:3px 9px; border:2px solid #d4a017; border-radius:999px; background:#fffaf0; color:#8a5a00; font-weight:700; box-shadow:0 0 0 3px rgba(212,160,23,.2), 0 0 14px rgba(212,160,23,.45); }}
    .nearest-row {{ background:#fff7ed; box-shadow:inset 0 0 0 2px #dc2626; }}
    .nearest-marker {{ display:inline-block; width:12px; height:12px; margin-right:7px; border:3px solid #dc2626; border-radius:50%; vertical-align:-1px; }}
    .empty {{ padding:24px; border:1px solid var(--line); border-radius:8px; background:#fff; color:var(--muted); }}
    .download {{ display:inline-flex; margin-top:2px; padding:8px 11px; border:1px solid var(--line); border-radius:6px; background:#fff; color:var(--text); text-decoration:none; }}
    @media (max-width:760px) {{
      .app {{ padding:16px; }}
      .page-header {{ flex-direction:column; gap:10px; }}
      .page-nav {{ width:100%; overflow-x:auto; }}
      .rule-strip {{ grid-template-columns:1fr; }}
      .lock-row {{ grid-template-columns:1fr; }}
    }}
  </style>
</head>
<body class="locked">
  <section class="lock-screen" aria-label="密码验证">
    <form id="lockForm" class="lock-panel">
      <h1>请输入密码</h1>
      <label for="lockPassword">密码</label>
      <div class="lock-row"><input id="lockPassword" type="password" autocomplete="current-password" autofocus><button type="submit">进入</button></div>
      <div id="lockError" class="lock-error" role="alert"></div>
    </form>
  </section>
  <div class="app">
    <header class="page-header">
      <div><h1>{escape(title)}</h1><div class="subtitle">{escape(subtitle)}</div></div>
      <nav class="page-nav" aria-label="页面导航">{navigation(active)}</nav>
    </header>
    <section class="rule-strip">
      <div class="rule"><strong>预告周期</strong><span>10天</span></div>
      <div class="rule"><strong>报名期</strong><span>10天</span></div>
      <div class="rule"><strong>报名活动提醒</strong><span>报名期开始前3天</span></div>
    </section>
    <a class="download" href="{source_href}" download>下载原始排期表</a>
    <main>{render_schedule_table(items, region)}</main>
  </div>
  <script>
    const AUTH_KEY = 'activity-reminders-authenticated-until';
    const AUTH_TTL_MS = 48 * 60 * 60 * 1000;
    const PASSWORD_HASH = '542df2c1e629af51b87cf02f575af7fc8cd25a26d6cf9a54e7ac3775bce0d8f6';
    const lockForm = document.getElementById('lockForm');
    const lockPassword = document.getElementById('lockPassword');
    const lockError = document.getElementById('lockError');
    function unlockPage() {{ document.body.classList.remove('locked'); }}
    async function sha256(value) {{
      const bytes = new TextEncoder().encode(value);
      const digest = await crypto.subtle.digest('SHA-256', bytes);
      return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, '0')).join('');
    }}
    if (Number(localStorage.getItem(AUTH_KEY) || 0) > Date.now()) unlockPage();
    lockForm.addEventListener('submit', async (event) => {{
      event.preventDefault();
      if (await sha256(lockPassword.value) === PASSWORD_HASH) {{
        localStorage.setItem(AUTH_KEY, String(Date.now() + AUTH_TTL_MS));
        lockPassword.value = ''; lockError.textContent = ''; unlockPage();
      }} else {{ lockError.textContent = '密码错误'; lockPassword.select(); }}
    }});
  </script>
</body>
</html>
"""


def main() -> None:
    configs = [
        (CN_SOURCE, "国服赛季提醒", "season-cn", "国服赛季", 16, CN_SEASONS),
        (OVERSEAS_SOURCE, "海外赛季提醒", "season-overseas", "海外赛季", 20, OVERSEAS_SEASONS),
    ]
    for source, title, active, region, registration_column, seasons in configs:
        if not source.exists():
            raise SystemExit(f"缺少文件：{source.name}")
        filename = "season-cn.html" if active == "season-cn" else "season-overseas.html"
        for directory in OUTPUT_DIRS:
            output = directory / filename
            output.write_text(
                render_page(source, title, active, region, registration_column, seasons, output),
                encoding="utf-8",
            )
            print(f"已生成：{output.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
