from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from html import escape
from pathlib import Path
import re
from urllib.parse import quote
from zipfile import ZipFile
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parent
SHEETS = [
    (ROOT / "102国服赛季排期表.xlsx", "season-cn.html", "国服赛季排期"),
    (ROOT / "102海外赛季排期表.xlsx", "season-overseas.html", "海外赛季排期"),
]
OUTPUT_DIRS = [ROOT, ROOT / "site"]
MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS = {"m": MAIN_NS, "r": REL_NS, "p": PACKAGE_REL_NS, "a": DRAWING_NS}
DATE_FORMAT_IDS = set(range(14, 23)) | set(range(27, 37)) | set(range(45, 48)) | set(range(50, 59))
INDEXED_COLORS = [
    "000000", "FFFFFF", "FF0000", "00FF00", "0000FF", "FFFF00", "FF00FF", "00FFFF",
    "000000", "FFFFFF", "FF0000", "00FF00", "0000FF", "FFFF00", "FF00FF", "00FFFF",
    "800000", "008000", "000080", "808000", "800080", "008080", "C0C0C0", "808080",
    "9999FF", "993366", "FFFFCC", "CCFFFF", "660066", "FF8080", "0066CC", "CCCCFF",
    "000080", "FF00FF", "FFFF00", "00FFFF", "800080", "800000", "008080", "0000FF",
    "00CCFF", "CCFFFF", "CCFFCC", "FFFF99", "99CCFF", "FF99CC", "CC99FF", "FFCC99",
    "3366FF", "33CCCC", "99CC00", "FFCC00", "FF9900", "FF6600", "666699", "969696",
    "003366", "339966", "003300", "333300", "993300", "993366", "333399", "333333",
]


@dataclass
class Cell:
    value: str = ""
    style_id: int = 0
    date_value: datetime | None = None


@dataclass
class SheetData:
    title: str
    rows: int
    columns: int
    cells: dict[tuple[int, int], Cell]
    merges: dict[tuple[int, int], tuple[int, int]]
    covered: set[tuple[int, int]]
    column_widths: dict[int, float]
    hidden_columns: set[int]
    row_heights: dict[int, float]
    hidden_rows: set[int]
    style_rules: list[str]


def column_index(column: str) -> int:
    result = 0
    for char in column:
        result = result * 26 + ord(char) - ord("A") + 1
    return result - 1


def split_ref(reference: str) -> tuple[int, int]:
    match = re.fullmatch(r"([A-Z]+)(\d+)", reference)
    if not match:
        raise ValueError(f"无效单元格引用：{reference}")
    return int(match.group(2)) - 1, column_index(match.group(1))


def parse_dimension(reference: str) -> tuple[int, int]:
    end = reference.split(":")[-1]
    row, column = split_ref(end)
    return row + 1, column + 1


def node_text(node: ET.Element | None, path: str) -> str:
    if node is None:
        return ""
    return "".join(item.text or "" for item in node.findall(path, NS))


def theme_colors(archive: ZipFile) -> list[str]:
    if "xl/theme/theme1.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/theme/theme1.xml"))
    scheme = root.find(".//a:clrScheme", NS)
    colors_by_name: dict[str, str] = {}
    if scheme is None:
        return []
    for item in list(scheme):
        color = next(iter(item), None)
        name = item.tag.rsplit("}", 1)[-1]
        colors_by_name[name] = "" if color is None else color.attrib.get("lastClr", color.attrib.get("val", ""))[-6:].upper()
    order = ["lt1", "dk1", "lt2", "dk2", "accent1", "accent2", "accent3", "accent4", "accent5", "accent6", "hlink", "folHlink"]
    return [colors_by_name.get(name, "") for name in order]


def apply_tint(rgb: str, tint: float) -> str:
    channels = [int(rgb[index:index + 2], 16) for index in (0, 2, 4)]
    adjusted = []
    for channel in channels:
        value = channel * (1 + tint) if tint < 0 else channel + (255 - channel) * tint
        adjusted.append(max(0, min(255, round(value))))
    return "".join(f"{value:02X}" for value in adjusted)


def color_value(node: ET.Element | None, themes: list[str], default: str = "") -> str:
    if node is None:
        return default
    rgb = node.attrib.get("rgb", "")[-6:]
    if not rgb and "theme" in node.attrib:
        index = int(node.attrib["theme"])
        rgb = themes[index] if index < len(themes) else ""
    if not rgb and "indexed" in node.attrib:
        index = int(node.attrib["indexed"])
        rgb = INDEXED_COLORS[index] if index < len(INDEXED_COLORS) else ""
    if not rgb or rgb.upper() in {"000000", "FFFFFF"} and node.attrib.get("auto") == "1":
        return default
    tint = float(node.attrib.get("tint", "0"))
    return apply_tint(rgb.upper(), tint) if tint else rgb.upper()


def css_border(side: ET.Element | None, themes: list[str]) -> str:
    if side is None or not side.attrib.get("style"):
        return "none"
    style = side.attrib["style"]
    width = "2px" if style in {"medium", "mediumDashed", "mediumDashDot", "mediumDashDotDot", "thick", "double"} else "1px"
    line = "dashed" if "dash" in style.lower() else "dotted" if style in {"dotted", "hair"} else "double" if style == "double" else "solid"
    color = color_value(side.find("m:color", NS), themes, "B8C1CE")
    return f"{width} {line} #{color}"


def style_rules(archive: ZipFile) -> tuple[list[str], list[int], dict[int, str]]:
    root = ET.fromstring(archive.read("xl/styles.xml"))
    themes = theme_colors(archive)
    fonts = root.findall("m:fonts/m:font", NS)
    fills = root.findall("m:fills/m:fill", NS)
    borders = root.findall("m:borders/m:border", NS)
    xfs = root.findall("m:cellXfs/m:xf", NS)
    custom_formats = {
        int(item.attrib["numFmtId"]): item.attrib.get("formatCode", "")
        for item in root.findall("m:numFmts/m:numFmt", NS)
    }
    rules: list[str] = []
    format_ids: list[int] = []
    for style_id, xf in enumerate(xfs):
        declarations: list[str] = []
        font_id = int(xf.attrib.get("fontId", "0"))
        if font_id < len(fonts):
            font = fonts[font_id]
            size = font.find("m:sz", NS)
            if size is not None:
                declarations.append(f"font-size:{float(size.attrib.get('val', '11')):.2f}pt")
            if font.find("m:b", NS) is not None:
                declarations.append("font-weight:700")
            if font.find("m:i", NS) is not None:
                declarations.append("font-style:italic")
            decorations = []
            if font.find("m:u", NS) is not None:
                decorations.append("underline")
            if font.find("m:strike", NS) is not None:
                decorations.append("line-through")
            if decorations:
                declarations.append("text-decoration:" + " ".join(decorations))
            color = color_value(font.find("m:color", NS), themes)
            if color:
                declarations.append(f"color:#{color}")
        fill_id = int(xf.attrib.get("fillId", "0"))
        if fill_id < len(fills):
            pattern = fills[fill_id].find("m:patternFill", NS)
            if pattern is not None and pattern.attrib.get("patternType") not in {None, "none"}:
                color = color_value(pattern.find("m:fgColor", NS), themes)
                if color:
                    declarations.append(f"background-color:#{color}")
        border_id = int(xf.attrib.get("borderId", "0"))
        if border_id < len(borders):
            border = borders[border_id]
            for css_name, xml_name in (("top", "top"), ("right", "right"), ("bottom", "bottom"), ("left", "left")):
                value = css_border(border.find(f"m:{xml_name}", NS), themes)
                if value != "none":
                    declarations.append(f"border-{css_name}:{value}")
        alignment = xf.find("m:alignment", NS)
        if alignment is not None:
            horizontal = alignment.attrib.get("horizontal")
            vertical = alignment.attrib.get("vertical")
            if horizontal in {"left", "center", "right", "justify"}:
                declarations.append(f"text-align:{horizontal}")
            if vertical in {"top", "center", "bottom"}:
                declarations.append(f"vertical-align:{'middle' if vertical == 'center' else vertical}")
            if alignment.attrib.get("wrapText") == "1":
                declarations.append("white-space:pre-wrap")
            rotation = int(alignment.attrib.get("textRotation", "0"))
            if rotation and rotation <= 90:
                declarations.append(f"writing-mode:vertical-rl;transform:rotate({rotation - 90}deg)")
        rules.append(f".s{style_id}{{{';'.join(declarations)}}}")
        format_ids.append(int(xf.attrib.get("numFmtId", "0")))
    return rules, format_ids, custom_formats


def is_date_format(format_id: int, custom_formats: dict[int, str]) -> bool:
    if format_id in DATE_FORMAT_IDS:
        return True
    code = re.sub(r'"[^"]*"|\\.', "", custom_formats.get(format_id, "")).lower()
    return bool(code and re.search(r"[ymdhis]", code))


def format_excel_number(value: str, format_id: int, custom_formats: dict[int, str]) -> str:
    try:
        number = float(value)
    except ValueError:
        return value
    if number > 0 and is_date_format(format_id, custom_formats):
        moment = datetime(1899, 12, 30) + timedelta(days=number)
        code = custom_formats.get(format_id, "").lower()
        if "h" in code or "s" in code:
            return moment.strftime("%Y-%m-%d %H:%M:%S")
        if "年" in code or "y" in code:
            return moment.strftime("%Y年%-m月%-d日")
        return moment.strftime("%-m月%-d日")
    if number.is_integer():
        return str(int(number))
    return f"{number:g}"


def workbook_sheet_path(archive: ZipFile) -> tuple[str, str]:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    targets = {item.attrib["Id"]: item.attrib["Target"] for item in relationships.findall("p:Relationship", NS)}
    sheet = workbook.find("m:sheets/m:sheet", NS)
    if sheet is None:
        raise ValueError("Excel 中没有工作表")
    target = targets[sheet.attrib[f"{{{REL_NS}}}id"]]
    path = target.lstrip("/") if target.startswith("/") else "xl/" + target.replace("../", "")
    return sheet.attrib.get("name", "Sheet1"), path


def read_sheet(path: Path) -> SheetData:
    with ZipFile(path) as archive:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            shared_strings = [node_text(item, ".//m:t") for item in root.findall("m:si", NS)]
        rules, format_ids, custom_formats = style_rules(archive)
        title, sheet_path = workbook_sheet_path(archive)
        root = ET.fromstring(archive.read(sheet_path))
        dimension = root.find("m:dimension", NS)
        rows, columns = parse_dimension(dimension.attrib.get("ref", "A1") if dimension is not None else "A1")
        cells: dict[tuple[int, int], Cell] = {}
        row_heights: dict[int, float] = {}
        hidden_rows: set[int] = set()
        for row_node in root.findall("m:sheetData/m:row", NS):
            row_index = int(row_node.attrib["r"]) - 1
            if row_node.attrib.get("hidden") == "1":
                hidden_rows.add(row_index)
            if "ht" in row_node.attrib:
                row_heights[row_index] = float(row_node.attrib["ht"]) * 4 / 3
            for cell_node in row_node.findall("m:c", NS):
                row, column = split_ref(cell_node.attrib["r"])
                style_id = int(cell_node.attrib.get("s", "0"))
                cell_type = cell_node.attrib.get("t")
                date_value = None
                if cell_type == "inlineStr":
                    value = node_text(cell_node, ".//m:t")
                else:
                    value_node = cell_node.find("m:v", NS)
                    value = "" if value_node is None else value_node.text or ""
                    if cell_type == "s" and value:
                        value = shared_strings[int(value)]
                    elif cell_type == "b":
                        value = "是" if value == "1" else "否"
                    elif cell_type not in {"str", "e"} and value:
                        format_id = format_ids[style_id] if style_id < len(format_ids) else 0
                        if value and is_date_format(format_id, custom_formats):
                            try:
                                date_value = datetime(1899, 12, 30) + timedelta(days=float(value))
                            except ValueError:
                                date_value = None
                        value = format_excel_number(value, format_id, custom_formats)
                    elif not value:
                        formula = cell_node.find("m:f", NS)
                        if formula is not None and formula.text:
                            value = "=" + formula.text
                cells[(row, column)] = Cell(value, style_id, date_value)
        merges: dict[tuple[int, int], tuple[int, int]] = {}
        covered: set[tuple[int, int]] = set()
        for merge in root.findall("m:mergeCells/m:mergeCell", NS):
            start_ref, end_ref = merge.attrib["ref"].split(":")
            start_row, start_column = split_ref(start_ref)
            end_row, end_column = split_ref(end_ref)
            merges[(start_row, start_column)] = (end_row - start_row + 1, end_column - start_column + 1)
            for row in range(start_row, end_row + 1):
                for column in range(start_column, end_column + 1):
                    if (row, column) != (start_row, start_column):
                        covered.add((row, column))
        sheet_format = root.find("m:sheetFormatPr", NS)
        default_width = float(sheet_format.attrib.get("defaultColWidth", "8.43")) if sheet_format is not None else 8.43
        column_widths = {column: max(24, default_width * 7 + 5) for column in range(columns)}
        hidden_columns: set[int] = set()
        for col in root.findall("m:cols/m:col", NS):
            start = int(col.attrib["min"]) - 1
            end = int(col.attrib["max"]) - 1
            width = max(20, float(col.attrib.get("width", default_width)) * 7 + 5)
            for column in range(start, min(end + 1, columns)):
                column_widths[column] = width
                if col.attrib.get("hidden") == "1":
                    hidden_columns.add(column)
        return SheetData(
            title, rows, columns, cells, merges, covered, column_widths, hidden_columns,
            row_heights, hidden_rows, rules,
        )


def navigation(active: str) -> str:
    links = [
        ("reminders", "index.html", "活动提醒"),
        ("season-cn", "season-cn.html", "国服赛季"),
        ("season-overseas", "season-overseas.html", "海外赛季"),
    ]
    rendered = []
    for key, href, label in links:
        active_class = " active" if key == active else ""
        current = ' aria-current="page"' if key == active else ""
        rendered.append(f'<a href="{href}" class="nav-link{active_class}"{current}>{label}</a>')
    return "".join(rendered)


def render_table(sheet: SheetData) -> str:
    columns = []
    for column in range(sheet.columns):
        width = 0 if column in sheet.hidden_columns else sheet.column_widths[column]
        columns.append(f'<col style="width:{width:.1f}px;min-width:{width:.1f}px">')
    rows = []
    for row in range(sheet.rows):
        row_style = "display:none" if row in sheet.hidden_rows else ""
        if row in sheet.row_heights and row not in sheet.hidden_rows:
            row_style = f"height:{sheet.row_heights[row]:.1f}px"
        cells = []
        for column in range(sheet.columns):
            if (row, column) in sheet.covered:
                continue
            cell = sheet.cells.get((row, column), Cell())
            rowspan, colspan = sheet.merges.get((row, column), (1, 1))
            attributes = [f'class="s{cell.style_id}"']
            if rowspan > 1:
                attributes.append(f'rowspan="{rowspan}"')
            if colspan > 1:
                attributes.append(f'colspan="{colspan}"')
            value = escape(cell.value).replace("\n", "<br>")
            cells.append(f'<td {" ".join(attributes)}>{value}</td>')
        rows.append(f'<tr style="{row_style}">{"".join(cells)}</tr>')
    return f'<table id="seasonTable"><colgroup>{"".join(columns)}</colgroup><tbody>{"".join(rows)}</tbody></table>'


def render_page(source: Path, page_title: str, active: str, output: Path) -> str:
    sheet = read_sheet(source)
    source_href = ("../" if output.parent.name == "site" else "") + quote(source.name)
    modified = datetime.fromtimestamp(source.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(page_title)}</title>
  <style>
    :root {{ color-scheme: light; --bg:#f5f6f8; --panel:#fff; --text:#1f2937; --muted:#667085; --line:#d8dee8; --accent:#166534; }}
    * {{ box-sizing:border-box; }}
    html, body {{ height:100%; }}
    body {{ margin:0; overflow:hidden; background:var(--bg); color:var(--text); font:14px/1.45 "Segoe UI","PingFang SC","Microsoft YaHei",sans-serif; }}
    body.locked .app {{ visibility:hidden; }}
    body:not(.locked) .lock-screen {{ display:none; }}
    .lock-screen {{ position:fixed; inset:0; z-index:100; display:grid; place-items:center; padding:20px; background:var(--bg); }}
    .lock-panel {{ width:min(400px,100%); display:grid; gap:14px; padding:24px; border:1px solid var(--line); border-radius:8px; background:var(--panel); box-shadow:0 12px 32px rgba(15,23,42,.12); }}
    .lock-panel h1 {{ margin:0; font-size:24px; }}
    .lock-panel label {{ color:var(--muted); font-weight:700; }}
    .lock-row {{ display:grid; grid-template-columns:minmax(0,1fr) auto; gap:10px; }}
    .lock-row input, .lock-row button, .search, .zoom-button, .download {{ min-height:40px; border:1px solid var(--line); border-radius:6px; font:inherit; }}
    .lock-row input, .search {{ min-width:0; padding:9px 11px; background:#fff; color:var(--text); }}
    .lock-row button {{ padding:9px 14px; border-color:var(--accent); background:var(--accent); color:#fff; font-weight:700; cursor:pointer; }}
    .lock-error {{ min-height:20px; color:#b91c1c; font-weight:700; }}
    .app {{ height:100%; display:grid; grid-template-rows:auto auto minmax(0,1fr); }}
    .page-header {{ display:flex; align-items:center; justify-content:space-between; gap:20px; padding:14px 20px 10px; background:var(--panel); border-bottom:1px solid var(--line); }}
    .title-block {{ min-width:0; }}
    h1 {{ margin:0; font-size:22px; line-height:1.25; }}
    .subtitle {{ margin-top:3px; color:var(--muted); font-size:13px; }}
    .page-nav {{ display:flex; gap:4px; padding:4px; border:1px solid var(--line); border-radius:8px; background:#f8fafc; white-space:nowrap; }}
    .nav-link {{ padding:7px 11px; border-radius:5px; color:#475467; text-decoration:none; font-weight:700; }}
    .nav-link:hover {{ background:#eef2f6; }}
    .nav-link.active {{ background:#fff; color:#111827; box-shadow:0 1px 3px rgba(15,23,42,.12); }}
    .toolbar {{ display:flex; align-items:center; gap:8px; padding:10px 20px; background:var(--panel); border-bottom:1px solid var(--line); }}
    .search {{ width:min(420px,40vw); }}
    .match-count {{ min-width:70px; color:var(--muted); }}
    .toolbar-spacer {{ flex:1; }}
    .zoom-button, .download {{ display:inline-flex; align-items:center; justify-content:center; padding:8px 11px; background:#fff; color:var(--text); text-decoration:none; cursor:pointer; }}
    .zoom-value {{ min-width:46px; text-align:center; font-variant-numeric:tabular-nums; }}
    .sheet-viewport {{ min-height:0; overflow:auto; padding:12px 20px 20px; }}
    .sheet-frame {{ width:max-content; min-width:100%; border:1px solid #b8c1ce; background:#fff; box-shadow:0 4px 16px rgba(15,23,42,.06); transform-origin:top left; }}
    table {{ border-collapse:collapse; table-layout:fixed; font-size:12px; background:#fff; }}
    td {{ height:22px; padding:2px 4px; border:1px solid #d7dde5; vertical-align:middle; white-space:nowrap; overflow:hidden; text-overflow:clip; }}
    td.search-match {{ outline:3px solid #f59e0b; outline-offset:-3px; position:relative; z-index:1; }}
    {''.join(sheet.style_rules)}
    @media (max-width:760px) {{
      .page-header {{ align-items:flex-start; flex-direction:column; gap:10px; padding:12px; }}
      .page-nav {{ width:100%; overflow-x:auto; }}
      .toolbar {{ flex-wrap:wrap; padding:8px 12px; }}
      .search {{ width:100%; }}
      .toolbar-spacer {{ display:none; }}
      .sheet-viewport {{ padding:8px 12px 12px; }}
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
      <div class="title-block"><h1>{escape(page_title)}</h1><div class="subtitle">{escape(sheet.title)} · 更新于 {modified}</div></div>
      <nav class="page-nav" aria-label="页面导航">{navigation(active)}</nav>
    </header>
    <div class="toolbar">
      <input id="search" class="search" type="search" placeholder="搜索批次、服务器、日期或活动">
      <span id="matchCount" class="match-count"></span>
      <span class="toolbar-spacer"></span>
      <button id="zoomOut" class="zoom-button" type="button" title="缩小">−</button>
      <span id="zoomValue" class="zoom-value">100%</span>
      <button id="zoomIn" class="zoom-button" type="button" title="放大">＋</button>
      <a class="download" href="{source_href}" download>下载原表</a>
    </div>
    <main class="sheet-viewport"><div id="sheetFrame" class="sheet-frame">{render_table(sheet)}</div></main>
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
    const authenticatedUntil = Number(localStorage.getItem(AUTH_KEY) || 0);
    if (authenticatedUntil > Date.now()) unlockPage(); else localStorage.removeItem(AUTH_KEY);
    lockForm.addEventListener('submit', async (event) => {{
      event.preventDefault();
      if (await sha256(lockPassword.value) === PASSWORD_HASH) {{
        localStorage.setItem(AUTH_KEY, String(Date.now() + AUTH_TTL_MS));
        lockPassword.value = ''; lockError.textContent = ''; unlockPage();
      }} else {{ lockError.textContent = '密码错误'; lockPassword.select(); }}
    }});
    const cells = [...document.querySelectorAll('#seasonTable td')];
    const search = document.getElementById('search');
    const matchCount = document.getElementById('matchCount');
    search.addEventListener('input', () => {{
      const query = search.value.trim().toLowerCase();
      let matches = 0;
      cells.forEach((cell) => {{
        const matched = Boolean(query) && cell.textContent.toLowerCase().includes(query);
        cell.classList.toggle('search-match', matched);
        if (matched) matches += 1;
      }});
      matchCount.textContent = query ? `${{matches}} 处匹配` : '';
    }});
    let zoom = 100;
    const sheetFrame = document.getElementById('sheetFrame');
    const zoomValue = document.getElementById('zoomValue');
    function setZoom(next) {{ zoom = Math.max(50, Math.min(160, next)); sheetFrame.style.zoom = `${{zoom}}%`; zoomValue.textContent = `${{zoom}}%`; }}
    document.getElementById('zoomOut').addEventListener('click', () => setZoom(zoom - 10));
    document.getElementById('zoomIn').addEventListener('click', () => setZoom(zoom + 10));
  </script>
</body>
</html>
"""


def main() -> None:
    for source, filename, title in SHEETS:
        if not source.exists():
            raise SystemExit(f"缺少文件：{source.name}")
        active = "season-cn" if filename == "season-cn.html" else "season-overseas"
        for directory in OUTPUT_DIRS:
            directory.mkdir(parents=True, exist_ok=True)
            output = directory / filename
            output.write_text(render_page(source, title, active, output), encoding="utf-8")
            print(f"已生成：{output.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
