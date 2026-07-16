from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import xlrd
from xlrd.biffh import XLRDError

from risk_backend.xlsx import load_xlsx_rows

OLE2_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
ZIP_SIGNATURE = b"PK\x03\x04"
MAX_TABULAR_ROWS = 10_000
MAX_TABULAR_COLUMNS = 256
MAX_TABULAR_CELLS = 1_000_000


def _normalize_text_cell(value) -> str:
    """把不同来源的单元格值统一转成字符串。

    这里会尽量保留用户原意：
    - 空值转成空字符串
    - 布尔值转成 TRUE / FALSE
    - 整数形式的浮点数去掉 `.0`
    """
    if value in (None, ""):
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def load_xls_rows(content: bytes) -> list[list[str]]:
    """读取旧版 `.xls` 文件的第一张工作表。"""
    workbook = xlrd.open_workbook(file_contents=content)
    if workbook.nsheets == 0:
        raise ValueError("Excel 文件中没有可读取的工作表")
    sheet = workbook.sheet_by_index(0)
    if sheet.nrows > MAX_TABULAR_ROWS or sheet.ncols > MAX_TABULAR_COLUMNS:
        raise ValueError(
            f"Excel 工作表不能超过 {MAX_TABULAR_ROWS} 行或 {MAX_TABULAR_COLUMNS} 列"
        )
    if sheet.nrows * sheet.ncols > MAX_TABULAR_CELLS:
        raise ValueError(f"Excel 工作表单元格不能超过 {MAX_TABULAR_CELLS} 个")
    return [
        [
            _normalize_text_cell(sheet.cell_value(row_index, column))
            for column in range(sheet.ncols)
        ]
        for row_index in range(sheet.nrows)
    ]


def _decode_text_content(content: bytes) -> str:
    """把文本文件按常见编码解码。

    现场用户导出的 CSV/TXT 很可能来自 Excel 或国产办公软件，
    因此这里会优先尝试 UTF-8、UTF-16、GB18030 等常见编码。
    """
    encodings = ("utf-8-sig", "utf-16", "gb18030", "gbk", "utf-8")
    last_error: UnicodeDecodeError | None = None
    for encoding in encodings:
        try:
            return content.decode(encoding)
        except UnicodeDecodeError as error:
            last_error = error
    if last_error is not None:
        raise ValueError(
            "文件编码无法识别，请尝试另存为 UTF-8、CSV 或 XLSX"
        ) from last_error
    raise ValueError("文件内容为空")


def _split_plain_text_line(line: str) -> list[str]:
    """当 TXT 不是标准 CSV 时，按常见分隔形式兜底拆分。"""
    if "\t" in line:
        return [item.strip() for item in line.split("\t")]
    if "," in line:
        return [item.strip() for item in line.split(",")]
    if ";" in line:
        return [item.strip() for item in line.split(";")]
    return [item.strip() for item in line.split()]


def load_delimited_rows(content: bytes) -> list[list[str]]:
    """读取 `.csv` 或 `.txt` 文本表格。"""
    text = _decode_text_content(content)
    sample = text[:4096]
    delimiter: str | None = None
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = None

    if delimiter:
        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        rows: list[list[str]] = []
        cell_count = 0
        for row in reader:
            if len(rows) >= MAX_TABULAR_ROWS:
                raise ValueError(f"文本表格行数不能超过 {MAX_TABULAR_ROWS} 行")
            if len(row) > MAX_TABULAR_COLUMNS:
                raise ValueError(f"文本表格列数不能超过 {MAX_TABULAR_COLUMNS} 列")
            cell_count += len(row)
            if cell_count > MAX_TABULAR_CELLS:
                raise ValueError(f"文本表格单元格不能超过 {MAX_TABULAR_CELLS} 个")
            rows.append([cell.strip() for cell in row])
        return rows

    rows: list[list[str]] = []
    cell_count = 0
    for line in text.splitlines():
        if len(rows) >= MAX_TABULAR_ROWS:
            raise ValueError(f"文本表格行数不能超过 {MAX_TABULAR_ROWS} 行")
        stripped = line.strip()
        if not stripped:
            rows.append([])
            continue
        row = _split_plain_text_line(stripped)
        if len(row) > MAX_TABULAR_COLUMNS:
            raise ValueError(f"文本表格列数不能超过 {MAX_TABULAR_COLUMNS} 列")
        cell_count += len(row)
        if cell_count > MAX_TABULAR_CELLS:
            raise ValueError(f"文本表格单元格不能超过 {MAX_TABULAR_CELLS} 个")
        rows.append(row)
    return rows


def load_tabular_rows(
    content: bytes, filename: str = "", content_type: str = ""
) -> list[list[str]]:
    """按文件类型读取第一张工作表 / 文本表格。

    支持：
    - `.xlsx`
    - `.xls`
    - `.csv`
    - `.txt`
    """
    suffix = Path(filename).suffix.lower()
    try:
        if suffix == ".xlsx":
            return load_xlsx_rows(content)
        if suffix == ".xls":
            return load_xls_rows(content)
        if suffix in {".csv", ".txt"}:
            return load_delimited_rows(content)

        # 如果前端没有带扩展名，就再按文件签名兜底判断一次。
        if content.startswith(ZIP_SIGNATURE):
            return load_xlsx_rows(content)
        if content.startswith(OLE2_SIGNATURE):
            return load_xls_rows(content)

        guessed_text_type = content_type.lower()
        if (
            "csv" in guessed_text_type
            or "text/plain" in guessed_text_type
            or "text/" in guessed_text_type
        ):
            return load_delimited_rows(content)
    except (
        ET.ParseError,
        IndexError,
        KeyError,
        ValueError,
        XLRDError,
        zipfile.BadZipFile,
    ) as exc:
        if isinstance(exc, ValueError):
            raise
        raise ValueError("文件格式损坏或无法读取，请检查文件后重试") from exc

    raise ValueError("当前仅支持导入 .xlsx、.xls、.csv、.txt 文件")
