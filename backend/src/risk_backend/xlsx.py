from __future__ import annotations

import io
import re
import zipfile
from pathlib import PurePosixPath
from xml.etree import ElementTree as ET

SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"a": SPREADSHEET_NS, "r": REL_NS, "pr": PACKAGE_REL_NS}
CELL_REF_RE = re.compile(r"([A-Z]+)")


def _column_index(cell_reference: str) -> int:
    """把 Excel 列号从字母形式转成数字。

    例如：
    - A  -> 1
    - Z  -> 26
    - AA -> 27
    """
    match = CELL_REF_RE.match(cell_reference or "")
    if not match:
        return 0
    letters = match.group(1)
    value = 0
    for letter in letters:
        value = value * 26 + (ord(letter) - 64)
    return value


def _string_value(node: ET.Element | None) -> str:
    if node is None:
        return ""
    return "".join(part or "" for part in node.itertext())


def _shared_strings(workbook: zipfile.ZipFile) -> list[str]:
    """读取 sharedStrings.xml。

    Excel 常见的字符串存储方式有两种：
    - inlineStr: 直接写在单元格节点里
    - sharedStrings: 把字符串集中放到 sharedStrings.xml，再通过索引引用

    这里把 shared strings 先全部加载好，后面解析单元格时就能按索引取值。
    """
    try:
        xml = workbook.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = ET.fromstring(xml)
    return [_string_value(item) for item in root.findall("a:si", NS)]


def _sheet_path(workbook: zipfile.ZipFile) -> str:
    """找到工作簿中的第一张工作表。"""
    if "xl/worksheets/sheet1.xml" in workbook.namelist():
        return "xl/worksheets/sheet1.xml"

    workbook_xml = ET.fromstring(workbook.read("xl/workbook.xml"))
    rels_xml = ET.fromstring(workbook.read("xl/_rels/workbook.xml.rels"))
    relationship_map = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in rels_xml.findall("pr:Relationship", NS)
    }
    first_sheet = workbook_xml.find("a:sheets/a:sheet", NS)
    if first_sheet is None:
        raise ValueError("Excel 文件中没有可读取的工作表")
    relationship_id = first_sheet.attrib.get(f"{{{REL_NS}}}id", "")
    target = relationship_map.get(relationship_id, "")
    if not target:
        raise ValueError("Excel 工作表关系信息缺失")
    return str(PurePosixPath("xl") / target)


def _cell_text(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t", "")
    if cell_type == "inlineStr":
        return _string_value(cell.find("a:is", NS)).strip()

    value_node = cell.find("a:v", NS)
    raw = _string_value(value_node).strip()
    if cell_type == "s":
        if not raw:
            return ""
        index = int(raw)
        return shared_strings[index] if 0 <= index < len(shared_strings) else ""
    if cell_type == "b":
        return "TRUE" if raw == "1" else "FALSE"
    return raw


def load_xlsx_rows(content: bytes) -> list[list[str]]:
    """把 xlsx 二进制内容解析成二维行列数据。

    这里故意只支持当前项目需要的最小子集：
    - 读取第一张工作表
    - 读取普通值、shared string、inline string

    这样既能满足导入功能，又不用引入 openpyxl 一类更重的依赖。
    """
    with zipfile.ZipFile(io.BytesIO(content)) as workbook:
        shared_strings = _shared_strings(workbook)
        sheet_xml = ET.fromstring(workbook.read(_sheet_path(workbook)))

    rows: list[list[str]] = []
    for row in sheet_xml.findall("a:sheetData/a:row", NS):
        values: dict[int, str] = {}
        max_column = 0
        for cell in row.findall("a:c", NS):
            column = _column_index(cell.attrib.get("r", ""))
            if column <= 0:
                continue
            values[column] = _cell_text(cell, shared_strings)
            max_column = max(max_column, column)
        if max_column == 0:
            rows.append([])
            continue
        rows.append([values.get(index, "") for index in range(1, max_column + 1)])
    return rows
