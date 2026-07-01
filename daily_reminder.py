from __future__ import annotations

import argparse
import csv
import re
from functools import lru_cache
from zipfile import ZipFile
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET

from workday_calendar import adjusted_setup_rules, has_fixed_sunday_setup


SOURCE = Path("102国服活动排期表.xlsx")
OUTPUT = Path("每日活动提醒.txt")
ACTIVITY_MAPPING_SOURCE = Path("活动与礼包对应关系.xlsx")
YEAR = 2026
FORCED_ACTIVITY_ID_NAMES = {"落潮海岸", "黑骑士", "珍宝商店", "自选周卡", "特化蚁对决", "蚁后对决"}
EIGHT_FIFTEEN_ACTIVITIES = {"特化蚁对决", "蚁后对决"}
EVOLUTION_RECHARGE_ACTIVITY_LINES = [
    "1900133: 连续充值（进化开启第二套）",
    "1900162: 连续充值（进化开启第三套）",
    "1900163: 连续充值（改造，开启进化第2/3套以外的服务器）",
    "1900084:【国服】五日随心储",
]
DISPLAY_NAME_OVERRIDES = {
    "进化连冲": "\n".join(EVOLUTION_RECHARGE_ACTIVITY_LINES),
}
MARMOT_SHIELD_MAIL_TITLE = "土拨鼠、罩子、邮件"
MARMOT_PACKAGE_LINE = "29145: 火力全开：进攻土拨鼠128~648"
MARMOT_MAIL_ITEMS = [
    "204115：野任饲料*30000",
    "202042: 2小时兵蚁解化加速*10",
    "202044:2小时治 加速*10",
    "204042：奇异密雯V*1",
    "200077: 100钻石*4",
    "203001：巢六保护8小时*1",
]
CODED_TITLE_RE = re.compile(r"^\s*(\d{5,7})\s*[:：]\s*(.+)$")
DIRECT_ACTION_NAMES = {"礼包+分组预设+活动确认", "活动预设+公布分组"}


DURATIONS = [
    ("功勋商店", "10年", None),
    ("战斗礼包", "1天", 1),
    ("最强限定：战斗特供", "1天", 1),
    ("土拨鼠", "1天", 1),
    ("罩子", "1天", 1),
    ("邮件", "1天", 1),
    ("标头展示活动", "6天", 6),
    ("强力野怪", "6天", 6),
    ("洞穴探险", "6天", 6),
    ("蚁群派对", "6天", 6),
    ("落潮海岸", "6天", 6),
    ("珍宝商店", "6天", 6),
    ("双倍券BP活动", "4天", 4),
    ("拼图折扣活动", "6天", 6),
    ("5代买蚂蚁送觉醒活动", "6天", 6),
    ("蜂群宝藏", "3天", 3),
    ("惊喜转盘", "7天", 7),
    ("常规大事典", "7天", 7),
    ("常规小事典", "7天", 7),
    ("自选周卡", "7天", 7),
    ("端午节签到", "10天", 10),
    ("特化蚁的馈赠", "10天", 10),
    ("无限寻宝", "2天", 2),
    ("蚁群狂欢", "3天", 3),
    ("蚁群嘉年华", "5天", 5),
    ("旱季来临", "7天", 7),
    ("回归自然", "7天", 7),
    ("万物新生", "7天", 7),
    ("潮起潮落", "7天", 7),
    ("野怪孵化周", "7天", 7),
    ("十连抽", "3天", 3),
    ("进化连冲", "7天", 7),
    ("新野怪连储", "7天", 7),
    ("新变异连储", "7天", 7),
    ("蚁后对决", "45天", 45),
    ("特化蚁对决", "14天", 14),
    ("联盟远征", "7天", 7),
    ("区域迁徙", "3天", 3),
    ("世界BOSS", "6天", 6),
    ("蚂蚁寻宝", "7天", 7),
    ("本服联盟GVE", "5天", 5),
    ("跨服联盟GVE", "5天", 5),
    ("通服跨服联盟GVE", "5天", 5),
    ("黑骑士", "1天", 1),
    ("VIP商店", "2天", 2),
]


@dataclass
class Reminder:
    setup_day: date
    start_day: date
    action: str
    raw: str
    detail_raw: str = ""


def week_monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def clean_text(value: str) -> str:
    value = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value


def nonempty_lines(value: str) -> list[str]:
    return [line.strip() for line in value.splitlines() if line.strip()]


def normalized_direct_action(value: str) -> str:
    value = re.sub(r"【.*?】", "", value)
    value = re.sub(r"\s+", "", value)
    return value


def is_direct_action_line(value: str) -> bool:
    return normalized_direct_action(value) in DIRECT_ACTION_NAMES


def direct_action_name(value: str) -> str:
    lines = nonempty_lines(value)
    if not lines:
        return ""
    normalized = normalized_direct_action(lines[0])
    return normalized if normalized in DIRECT_ACTION_NAMES else ""


def parse_month_day(value: str) -> date | None:
    match = re.fullmatch(r"\s*(\d{1,2})月(\d{1,2})日\s*", value or "")
    if not match:
        return None
    return date(YEAR, int(match.group(1)), int(match.group(2)))


def parse_query_date(value: str | None) -> date:
    if not value:
        return date.today()
    return datetime.strptime(value, "%Y-%m-%d").date()


def reminder_rules(activity: str, start_day: date, row_context: str = "") -> list[tuple[date, str]]:
    if has_fixed_sunday_setup(activity, row_context):
        rules = [(week_monday(start_day) - timedelta(days=1), "设置活动")]
    elif "区域迁徙" in activity:
        monday = week_monday(start_day) - timedelta(days=7)
        rules = [
            (monday, "设置礼包+分组"),
            (monday + timedelta(days=2), "设置活动+公布分组"),
        ]
    elif "本服联盟GVE" in activity:
        rules = [(week_monday(start_day) - timedelta(days=7), "设置活动")]
    elif "跨服联盟GVE" in activity or "通服跨服联盟GVE" in activity:
        rules = [(week_monday(start_day) - timedelta(days=2), "设置活动")]
    elif "VIP商店" in activity or "黑骑士" in activity:
        rules = [(week_monday(start_day), "设置活动")]
    elif "联盟远征" in activity or "功勋商店" in activity:
        rules = [(start_day, "设置活动")]
    elif "29145" in activity or "火力全开" in activity:
        rules = [(start_day - timedelta(days=1), "设置活动")]
    elif "土拨鼠" in activity:
        rules = [(start_day - timedelta(days=2), "设置活动")]
    elif "自选周卡" in activity or "进化连冲" in activity:
        rules = [(start_day - timedelta(days=3), "设置活动")]
    else:
        rules = [(start_day - timedelta(days=1), "设置活动")]
    return adjusted_setup_rules(rules, activity, row_context)


def load_reminders() -> list[Reminder]:
    with SOURCE.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f, delimiter="\t"))

    dates: dict[int, date] = {}
    for col, value in enumerate(rows[1]):
        parsed = parse_month_day(value)
        if parsed:
            dates[col] = parsed

    reminders: list[Reminder] = []
    for row in rows[2:]:
        row_context = clean_text("\n".join(value for value in row[:4] if value.strip()))
        direct_details = direct_details_by_day(row, dates)
        for col, start_day in dates.items():
            if col >= len(row):
                continue
            activity = clean_text(row[col])
            if not activity:
                continue
            if is_non_activity_note(activity):
                continue
            for setup_day, action in reminder_rules(activity, start_day, row_context):
                detail_raw = direct_detail_for_action(direct_details, setup_day, action)
                reminders.append(Reminder(setup_day, start_day, action, activity, detail_raw))
    return reminders


def direct_details_by_day(row: list[str], dates: dict[int, date]) -> dict[date, str]:
    details: dict[date, str] = {}
    for col, day in dates.items():
        if col >= len(row):
            continue
        value = clean_text(row[col])
        if direct_action_name(value):
            details[day] = value
    return details


def direct_detail_for_action(direct_details: dict[date, str], setup_day: date, action: str) -> str:
    detail = direct_details.get(setup_day, "")
    detail_action = direct_action_name(detail)
    if action == "设置礼包+分组" and detail_action == "礼包+分组预设+活动确认":
        return detail
    if action == "设置活动+公布分组" and detail_action == "活动预设+公布分组":
        return detail
    return ""


def is_non_activity_note(activity: str) -> bool:
    lines = nonempty_lines(activity)
    normalized = activity.replace(" ", "")
    if normalized in {
        "兑换",
        "兑换多一天",
        "这轮不开，等0602版本改竞技场规则",
    }:
        return True
    return bool(lines and is_direct_action_line(lines[0]))


def is_marmot_shield_mail(raw: str) -> bool:
    return "土拨鼠" in raw and "罩子" in raw and "邮件" in raw


def activity_name(raw: str) -> str:
    if "功勋商店" in raw:
        return "延长功勋商店 / 功勋商店"
    if "战斗礼包" in raw or "最强限定：战斗特供" in raw:
        return "战斗礼包 / 最强限定：战斗特供"
    if "标头展示活动" in raw or "强力野怪" in raw:
        return "标头展示活动 / 强力野怪"
    if "新变异连储" in raw:
        return "新变异连储 & 7充5 / 随心储"
    if "新野怪连储" in raw:
        return "新野怪连储 & 7充5"
    if "跨服联盟GVE" in raw or "通服跨服联盟GVE" in raw:
        return "跨服联盟GVE / 通服跨服联盟GVE"
    if "特化蚁的馈赠" in raw:
        return "特化蚁的馈赠"
    if "蚁群嘉年华" in raw:
        return "蚁群嘉年华"
    for key, _, _ in DURATIONS:
        if key in raw:
            return key
    first_line = raw.splitlines()[0]
    first_line = re.sub(r"【.*?】", "", first_line)
    first_line = re.sub(r"[;；（(].*$", "", first_line)
    first_line = re.sub(r"\s*S?\d.*$", "", first_line).strip()
    return first_line or "未识别活动"


def inline_direct_title(raw: str) -> str | None:
    lines = nonempty_lines(raw)
    if len(lines) < 2 or not is_direct_action_line(lines[0]):
        return None

    match = CODED_TITLE_RE.match(lines[1])
    if not match:
        return None
    return lines[1]


def normalize_mapping_text(value: str) -> str:
    return value.replace("\xa0", " ").replace("：", ":").strip()


def activity_key(value: str) -> str:
    value = normalize_mapping_text(value)
    value = re.sub(r"\s+", "", value)
    return value


def load_xlsx_rows(path: Path) -> list[list[str]]:
    ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with ZipFile(path) as xlsx:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in xlsx.namelist():
            root = ET.fromstring(xlsx.read("xl/sharedStrings.xml"))
            for item in root.findall("a:si", ns):
                shared_strings.append("".join(text.text or "" for text in item.findall(".//a:t", ns)))

        sheet = ET.fromstring(xlsx.read("xl/worksheets/sheet1.xml"))
        rows: list[list[str]] = []
        for row in sheet.findall(".//a:sheetData/a:row", ns):
            values: list[str] = []
            for cell in row.findall("a:c", ns):
                ref = cell.attrib.get("r", "")
                col_match = re.match(r"([A-Z]+)", ref)
                col_index = column_index(col_match.group(1)) if col_match else len(values)
                while len(values) < col_index:
                    values.append("")

                cell_type = cell.attrib.get("t")
                value_node = cell.find("a:v", ns)
                value = "" if value_node is None or value_node.text is None else value_node.text
                if cell_type == "s" and value:
                    value = shared_strings[int(value)]
                elif cell_type == "inlineStr":
                    value = "".join(text.text or "" for text in cell.findall(".//a:t", ns))
                values.append(normalize_mapping_text(value))
            rows.append(values)
    return rows


def column_index(column: str) -> int:
    index = 0
    for char in column:
        index = index * 26 + ord(char) - ord("A") + 1
    return index - 1


@lru_cache(maxsize=1)
def regular_activity_id_map() -> dict[str, str]:
    if not ACTIVITY_MAPPING_SOURCE.exists():
        return {}

    mapping: dict[str, str] = {}
    for row in load_xlsx_rows(ACTIVITY_MAPPING_SOURCE)[1:]:
        name = row[0] if len(row) > 0 else ""
        activity_id = row[1] if len(row) > 1 else ""
        is_regular = row[2] if len(row) > 2 else ""
        if name and activity_id and (is_regular == "1" or name in FORCED_ACTIVITY_ID_NAMES):
            mapping[activity_key(name)] = activity_id
    return mapping


def display_activity_name(raw: str) -> str:
    if is_marmot_shield_mail(raw):
        return MARMOT_SHIELD_MAIL_TITLE
    direct_title = inline_direct_title(raw)
    if direct_title:
        return direct_title
    name = activity_name(raw)
    if name in DISPLAY_NAME_OVERRIDES:
        return DISPLAY_NAME_OVERRIDES[name]
    mapped = regular_activity_id_map().get(activity_key(name))
    if mapped:
        return mapped
    inline_id = re.match(r"\s*(\d{5,7})[:：]\s*([^\n]+)", raw)
    if inline_id:
        return normalize_mapping_text(f"{inline_id.group(1)}:{inline_id.group(2)}")
    return name


def duration_for(name: str, raw: str) -> tuple[str, int | None]:
    if "功勋商店" in name:
        return "10年", None
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("时间："):
            continue
        explicit_duration = re.search(r"[（(]\s*(\d+)\s*天\s*[)）]", line)
        if explicit_duration:
            days = int(explicit_duration.group(1))
            return f"{days}天", days
    for key, label, days in DURATIONS:
        if key in name or key in raw:
            return label, days
    return "未知", 1


def weeks_between(day: date, base: date) -> int | None:
    delta_days = (day - base).days
    if delta_days % 7:
        return None
    return delta_days // 7


def cycles_between(day: date, base: date, days: int) -> int | None:
    delta_days = (day - base).days
    if delta_days % days:
        return None
    return delta_days // days


def rotating_recharge_server(start_day: date) -> str | None:
    cycles = cycles_between(start_day, date(2026, 6, 15), 14)
    if cycles is None:
        return None
    return f"S1-S{854 + cycles * 2}"


def evolution_recharge_server_text(start_day: date) -> str | None:
    rotating_server = rotating_recharge_server(start_day)
    if rotating_server is None:
        return None
    config_server = rotating_server.replace("S1-S", "1～S", 1)
    return "\n".join(
        [
            EVOLUTION_RECHARGE_ACTIVITY_LINES[0],
            EVOLUTION_RECHARGE_ACTIVITY_LINES[1],
            EVOLUTION_RECHARGE_ACTIVITY_LINES[2],
            "服务器：平台设置全服，实际开启读取配置",
            "",
            EVOLUTION_RECHARGE_ACTIVITY_LINES[3],
            f"服务器：{config_server}（读实际配置）",
        ]
    )


def computed_server_text(raw: str, start_day: date) -> str | None:
    name = activity_name(raw)

    if name == "VIP商店":
        weeks = weeks_between(start_day, date(2026, 6, 20))
        if weeks is not None:
            return f"S1-S{855 + weeks}"

    if name in {"万物新生", "潮起潮落", "旱季来临", "回归自然"}:
        weeks = weeks_between(start_day, date(2026, 6, 16))
        if weeks is not None and weeks >= 0:
            return f"S1-S{852 + weeks}"

    if name == "土拨鼠":
        cycles = cycles_between(start_day, date(2026, 6, 14), 14)
        if cycles is not None:
            return f"S1-S{854 + cycles * 2}"

    if name == "延长功勋商店 / 功勋商店":
        weeks = weeks_between(start_day, date(2026, 6, 15))
        if weeks is not None:
            return f"S{854 + weeks}"

    if name == "战斗礼包 / 最强限定：战斗特供":
        return "全服"

    if name == "进化连冲":
        return evolution_recharge_server_text(start_day)

    if name in {"新野怪连储 & 7充5", "新变异连储 & 7充5 / 随心储"}:
        return rotating_recharge_server(start_day)

    if name == "联盟远征":
        weeks = weeks_between(start_day, date(2026, 6, 15))
        if weeks is not None:
            return f"S1-S{854 + weeks}"

    if name == "本服联盟GVE":
        weeks = weeks_between(start_day, date(2026, 6, 22))
        if weeks is not None:
            return f"S{857 + weeks}"

    if name == "跨服联盟GVE / 通服跨服联盟GVE":
        weeks = weeks_between(start_day, date(2026, 6, 15))
        if weeks is not None:
            server = 855 + weeks
            if "通服跨服联盟GVE" in raw:
                return f"S{server}，S1-S{853 + weeks}"
            return f"S{server}"

    return None


def server_text(raw: str, start_day: date | None = None) -> str:
    raw_one_line = " ".join(raw.split())
    if re.search(r"服务器[:：]\s*全服", raw_one_line):
        return "全服"

    explicit_servers = []
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("服务器"):
            continue
        server_value = re.sub(r"^服务器[:：]\s*", "", line)
        server_value = re.sub(r"^服务器[:：]\s*", "", server_value)
        for item in re.findall(r"S\s*\d+\s*[-~～—–]+\s*S?\s*(?:xxx|\d+)|S\s*\d+|S\s*xxx|(?<![\d.])1\s*[-~～—–]+\s*(?:xxx|XXX|\d+)", server_value, re.I):
            explicit_servers.append(normalize_server(item))
    if explicit_servers:
        return "，".join(dict.fromkeys(explicit_servers))

    if "功勋商店" in raw:
        merit = re.search(r"功勋商店\s*(\d+|xxx)", raw_one_line, re.I)
        if merit:
            return f"S{merit.group(1)}"

    if "黑骑士" in raw:
        client = re.search(r"客户端\s*(S?\d+\s*[-~～]\s*S?\d+|S?\d+)", raw_one_line)
        mini = re.search(r"小程序\s*(S?\d+\s*[-~～]\s*S?\d+|S?\d+)", raw_one_line)
        parts = []
        if client:
            parts.append(f"客户端 {normalize_server(client.group(1))}")
        if mini:
            parts.append(f"小程序 {normalize_server(mini.group(1))}")
        if parts:
            return "；".join(parts)

    server_matches = re.findall(r"S\s*\d+\s*[-~～—–]+\s*S?\s*(?:xxx|\d+)|S\s*xxx", raw_one_line, re.I)
    if server_matches:
        return "，".join(dict.fromkeys(normalize_server(item) for item in server_matches))

    range_matches = re.findall(r"(?<![\d.])1\s*[-~～—–]+\s*(?:xxx|XXX|\d+)", raw_one_line)
    if range_matches:
        return "，".join(dict.fromkeys(normalize_server(item) for item in range_matches))

    bracket = re.search(r"【([^】]*\d+\s*[-~～]\s*\d+[^】]*)】", raw_one_line)
    if bracket:
        return bracket.group(1).strip()

    if start_day is not None:
        computed = computed_server_text(raw, start_day)
        if computed:
            return computed

    return "排期表未标明"


def normalize_server(value: str) -> str:
    value = value.strip().replace("～", "-").replace("~", "-").replace("—", "-").replace("–", "-")
    value = re.sub(r"\s+", "", value)
    value = re.sub(r"-+", "-", value)
    value = re.sub(r"^1-", "S1-S", value)
    value = re.sub(r"^1-", "S1-S", value, flags=re.I)
    value = re.sub(r"(?i)^S(\d+)-(\d+|xxx)$", r"S\1-S\2", value)
    value = re.sub(r"(?i)^S(\d+)-S?(\d+|xxx)$", r"S\1-S\2", value)
    value = re.sub(r"(?i)^Sxxx$", "Sxxx", value)
    return value


def time_range(start_day: date, duration_label: str, days: int | None, name: str = "") -> str:
    start_hour = 8
    start_minute = 15 if name in EIGHT_FIFTEEN_ACTIVITIES else 0
    start = datetime(start_day.year, start_day.month, start_day.day, start_hour, start_minute, 0)
    if days is None:
        end = datetime(start_day.year + 10, start_day.month, start_day.day, 7, 59, 59) + timedelta(days=1)
    else:
        end = start + timedelta(days=days) - timedelta(seconds=1)
    return f"{start:%Y-%m-%d %H:%M:%S} ~ {end:%Y-%m-%d %H:%M:%S}（{duration_label}） UTC+8"


def display_server_group(value: str) -> str:
    return value.replace("-", "~")


def migration_activity_setup_lines(item: Reminder) -> list[str]:
    duration_label, days = duration_for("区域迁徙", item.raw)
    days = days or 3
    start = datetime(item.start_day.year, item.start_day.month, item.start_day.day, 9, 0, 0)
    end = datetime(item.start_day.year, item.start_day.month, item.start_day.day, 7, 59, 59) + timedelta(days=days)
    server = server_text(item.raw, item.start_day)
    group = display_server_group(server)
    if server == "排期表未标明":
        scope_line = "范围：S1，排期表未标明"
    else:
        scope_line = f"范围：S1，{group}；{group}为1组"
    return [
        "活动预设+公布分组",
        display_activity_name(item.raw),
        f"时间：{start:%Y-%m-%d %H:%M:%S} - {end:%Y-%m-%d %H:%M:%S} UTC+8【{duration_label}】",
        scope_line,
        "备注：",
        "1. 北京时间09:00:00开启，避免跨天结算问题",
        "2. 1服确认已选，分组已设置",
    ]


def direct_detail_lines(detail_raw: str) -> list[str] | None:
    title = inline_direct_title(detail_raw)
    if not title:
        return None

    lines = nonempty_lines(detail_raw)
    return [title, lines[0], *lines[2:]]


def custom_reminder_lines(item: Reminder) -> list[str] | None:
    if activity_name(item.raw) == "区域迁徙" and item.action == "设置礼包+分组" and item.detail_raw:
        return direct_detail_lines(item.detail_raw)

    if activity_name(item.raw) == "区域迁徙" and item.action == "设置活动+公布分组":
        return migration_activity_setup_lines(item)

    if item.detail_raw:
        return direct_detail_lines(item.detail_raw)

    return direct_detail_lines(item.raw)


def compact_one_day_range(start_day: date) -> str:
    start = datetime(start_day.year, start_day.month, start_day.day, 8, 0, 0)
    end = start + timedelta(days=1) - timedelta(seconds=1)
    return f"{start:%Y-%m-%d %H:%M:%S}~{end:%Y-%m-%d %H:%M:%S}"


def marmot_shield_mail_text(start_day: date) -> str:
    active_range = compact_one_day_range(start_day)
    mail_time = datetime(start_day.year, start_day.month, start_day.day, 16, 0, 11) - timedelta(days=1)
    lines = [
        "土拨鼠服：",
        MARMOT_PACKAGE_LINE,
        f"时间：{active_range} UTC+8",
        "新服不自动开启，每日刷新 pop2",
        f"区域征战服：保护罩【{active_range} UTC+8】定时24h【赛季外，区域征战范围服 】",
        f"邮件，赛季外，定时：{mail_time:%Y-%m-%d %H:%M:%S}",
        *MARMOT_MAIL_ITEMS,
    ]
    return "\n".join(lines)


def labeled_text(label: str, value: str) -> str:
    if "\n" in value:
        return f"{label}：\n{value}"
    return f"{label}：{value}"


def render(reminders: list[Reminder], target: date) -> str:
    todays = [item for item in reminders if item.setup_day == target]
    todays.sort(key=lambda item: (item.start_day, activity_name(item.raw), item.raw))

    header = f"{target:%Y-%m-%d} 今日需要设置的活动"
    if not todays:
        return f"{header}\n\n今天没有需要设置的活动。\n"

    chunks = [header]
    for item in todays:
        custom_lines = custom_reminder_lines(item)
        if custom_lines:
            chunks.append("\n".join(custom_lines))
            continue

        if is_marmot_shield_mail(item.raw):
            chunks.append(marmot_shield_mail_text(item.start_day))
            continue

        name = display_activity_name(item.raw)
        base_name = activity_name(item.raw)
        duration_label, days = duration_for(base_name, item.raw)
        action_line = "" if item.action == "设置活动" else f"{item.action}\n"
        server = server_text(item.raw, item.start_day)
        server_line = server if base_name == "进化连冲" else labeled_text("服务器", server)
        chunks.append(
            "\n".join(
                [
                    name,
                    f"{action_line}开始时间~结束时间",
                    server_line,
                    f"时间：{time_range(item.start_day, duration_label, days, base_name)}",
                ]
            )
        )
    return "\n\n".join(chunks) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="生成每日活动设置提醒")
    parser.add_argument("--date", help="指定提醒日期，例如 2026-06-08")
    args = parser.parse_args()

    target = parse_query_date(args.date)
    text = render(load_reminders(), target)
    OUTPUT.write_text(text, encoding="utf-8")
    print(text)
    print(f"已写入：{OUTPUT}")


if __name__ == "__main__":
    main()
