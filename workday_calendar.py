from __future__ import annotations

import re
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET


CALENDAR_SOURCE = Path("工作休日日历.xlsx")
CALENDAR_SHEET_NAME = "每日明细"
FIXED_REST_DAY_SETUP_IDS = {"1000905", "1000927"}
FIXED_SUNDAY_SETUP_IDS = {"1000927"}
FIXED_REST_DAY_SETUP_KEYWORDS = {"国服-拯救蚜虫-跨服", "飞蜥之战"}

NS = {
    "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


def week_monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def excel_serial_date(value: str) -> date | None:
    try:
        serial = float(value)
    except ValueError:
        return None
    return date(1899, 12, 30) + timedelta(days=serial)


def parse_calendar_date(value: str) -> date | None:
    value = value.strip()
    if not value:
        return None

    serial_day = excel_serial_date(value)
    if serial_day:
        return serial_day

    match = re.fullmatch(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", value)
    if match:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))

    match = re.fullmatch(r"(\d{1,2})月(\d{1,2})日", value)
    if match:
        return date(2026, int(match.group(1)), int(match.group(2)))

    return None


def column_index(column: str) -> int:
    index = 0
    for char in column:
        index = index * 26 + ord(char) - ord("A") + 1
    return index - 1


def shared_strings(xlsx: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in xlsx.namelist():
        return []

    root = ET.fromstring(xlsx.read("xl/sharedStrings.xml"))
    return ["".join(text.text or "" for text in item.findall(".//a:t", NS)) for item in root.findall("a:si", NS)]


def workbook_sheet_paths(xlsx: ZipFile) -> dict[str, str]:
    workbook = ET.fromstring(xlsx.read("xl/workbook.xml"))
    rels = ET.fromstring(xlsx.read("xl/_rels/workbook.xml.rels"))
    rel_targets = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels.findall("rel:Relationship", NS)}

    paths: dict[str, str] = {}
    for sheet in workbook.findall(".//a:sheets/a:sheet", NS):
        rel_id = sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
        target = rel_targets[rel_id]
        if not target.startswith("xl/"):
            target = "xl/" + target.lstrip("/")
        paths[sheet.attrib["name"]] = target
    return paths


def load_xlsx_sheet(path: Path, sheet_name: str) -> list[list[str]]:
    with ZipFile(path) as xlsx:
        strings = shared_strings(xlsx)
        sheet_paths = workbook_sheet_paths(xlsx)
        if sheet_name not in sheet_paths:
            raise ValueError(f"{path} 缺少工作表：{sheet_name}")

        root = ET.fromstring(xlsx.read(sheet_paths[sheet_name]))
        rows: list[list[str]] = []
        for row in root.findall(".//a:sheetData/a:row", NS):
            values: list[str] = []
            for cell in row.findall("a:c", NS):
                ref = cell.attrib.get("r", "")
                match = re.match(r"([A-Z]+)", ref)
                cell_index = column_index(match.group(1)) if match else len(values)
                while len(values) < cell_index:
                    values.append("")

                cell_type = cell.attrib.get("t")
                value_node = cell.find("a:v", NS)
                value = "" if value_node is None or value_node.text is None else value_node.text
                if cell_type == "s" and value:
                    value = strings[int(value)]
                elif cell_type == "inlineStr":
                    value = "".join(text.text or "" for text in cell.findall(".//a:t", NS))
                values.append(value.strip())
            rows.append(values)
    return rows


def normalized_header(value: str) -> str:
    return re.sub(r"\s+", "", value)


def is_rest_state(value: str) -> bool:
    normalized = normalized_header(value)
    return normalized in {"1", "是", "休", "休息", "true", "TRUE"}


def row_value(row: list[str], index: int | None) -> str:
    if index is None or index >= len(row):
        return ""
    return row[index].strip()


@lru_cache(maxsize=1)
def workday_map() -> dict[date, bool]:
    if not CALENDAR_SOURCE.exists():
        return {}

    rows = load_xlsx_sheet(CALENDAR_SOURCE, CALENDAR_SHEET_NAME)
    if not rows:
        return {}

    header = [normalized_header(value) for value in rows[0]]
    date_col = header.index("日期") if "日期" in header else None
    status_col = header.index("状态") if "状态" in header else None
    rest_col = header.index("是否休息") if "是否休息" in header else None
    if date_col is None:
        raise ValueError(f"{CALENDAR_SOURCE} 的 {CALENDAR_SHEET_NAME} 缺少 日期 列")

    calendar: dict[date, bool] = {}
    for row in rows[1:]:
        day = parse_calendar_date(row_value(row, date_col))
        if day is None:
            continue

        rest_value = row_value(row, rest_col)
        status_value = row_value(row, status_col)
        if rest_value:
            is_rest = is_rest_state(rest_value)
        else:
            is_rest = "休" in status_value and "上班" not in status_value
        calendar[day] = not is_rest
    return calendar


def is_workday(day: date) -> bool:
    calendar = workday_map()
    if day in calendar:
        return calendar[day]
    return day.weekday() < 5


def previous_workday(day: date) -> date:
    while not is_workday(day):
        day -= timedelta(days=1)
    return day


def fixed_setup_context(activity: str, row_context: str = "") -> str:
    return f"{activity}\n{row_context}"


def has_fixed_rest_day_setup(activity: str, row_context: str = "") -> bool:
    context = fixed_setup_context(activity, row_context)
    return any(activity_id in context for activity_id in FIXED_REST_DAY_SETUP_IDS) or any(
        keyword in context for keyword in FIXED_REST_DAY_SETUP_KEYWORDS
    )


def has_fixed_sunday_setup(activity: str, row_context: str = "") -> bool:
    context = fixed_setup_context(activity, row_context)
    return any(activity_id in context for activity_id in FIXED_SUNDAY_SETUP_IDS) or "飞蜥之战" in context


def adjusted_setup_rules(
    rules: list[tuple[date, str]],
    activity: str,
    row_context: str = "",
) -> list[tuple[date, str]]:
    if has_fixed_rest_day_setup(activity, row_context):
        return rules
    return [(previous_workday(setup_day), action) for setup_day, action in rules]
