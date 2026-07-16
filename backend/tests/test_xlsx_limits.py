from __future__ import annotations

import io
import unittest
import zipfile
from unittest.mock import patch

from risk_backend.xlsx import load_xlsx_rows


class XlsxSafetyLimitTests(unittest.TestCase):
    def test_rejects_archive_with_excessive_uncompressed_size(self) -> None:
        content = io.BytesIO()
        with zipfile.ZipFile(content, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("xl/workbook.xml", b"x" * 1024)

        with (
            patch("risk_backend.xlsx.MAX_ARCHIVE_UNCOMPRESSED_BYTES", 512),
            self.assertRaisesRegex(ValueError, "解压后体积过大"),
        ):
            load_xlsx_rows(content.getvalue())

    def test_rejects_sheet_with_too_many_rows(self) -> None:
        content = io.BytesIO()
        sheet = (
            '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            "<sheetData>"
            + '<row r="1"><c r="A1"><v>1</v></c></row>' * 3
            + "</sheetData></worksheet>"
        ).encode()
        with zipfile.ZipFile(content, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("xl/workbook.xml", b"<workbook/>")
            archive.writestr("xl/worksheets/sheet1.xml", sheet)

        with (
            patch("risk_backend.xlsx.MAX_SHEET_ROWS", 2),
            self.assertRaisesRegex(ValueError, "行数不能超过"),
        ):
            load_xlsx_rows(content.getvalue())


if __name__ == "__main__":
    unittest.main()
