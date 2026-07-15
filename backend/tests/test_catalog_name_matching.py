from __future__ import annotations

import os
import tempfile
import unittest

# 测试数据库必须放进临时目录，不能读写用户正在使用的正式工作区数据库。
TEST_DATA_DIR = tempfile.TemporaryDirectory()
os.environ["RISK_APP_DATA_DIR"] = TEST_DATA_DIR.name

from risk_backend.application import RiskBackend  # noqa: E402
from risk_backend.repositories.catalog import (  # noqa: E402
    CatalogRepository,
    _normalize_pollutant_name,
    _pollutant_name_search_anchor,
)


class PollutantNameNormalizationTests(unittest.TestCase):
    def test_cis_name_variants_share_one_normalized_key(self) -> None:
        expected = _normalize_pollutant_name("1,2-顺式-二氯乙烯")
        variants = (
            "顺式-1,2二氯乙烯",
            "顺式12二氯乙烯",
            "12顺式二氯乙烯",
            "顺式-1，2二氯乙烯",
        )

        for variant in variants:
            with self.subTest(variant=variant):
                self.assertEqual(_normalize_pollutant_name(variant), expected)

    def test_cis_and_trans_names_remain_distinct(self) -> None:
        self.assertNotEqual(
            _normalize_pollutant_name("顺式12二氯乙烯"),
            _normalize_pollutant_name("反式12二氯乙烯"),
        )

    def test_search_anchor_ignores_locant_punctuation(self) -> None:
        self.assertEqual(_pollutant_name_search_anchor("顺式-1，2二氯乙烯"), "二氯乙烯")


class CatalogNameLookupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repository = CatalogRepository()

    def test_all_cis_variants_resolve_to_the_same_catalog_record(self) -> None:
        canonical = self.repository.find_by_name("1,2-顺式-二氯乙烯")
        self.assertIsNotNone(canonical)

        for variant in (
            "顺式-1,2二氯乙烯",
            "顺式12二氯乙烯",
            "12顺式二氯乙烯",
            "顺式-1，2二氯乙烯",
        ):
            with self.subTest(variant=variant):
                matched = self.repository.find_by_name(variant)
                self.assertIsNotNone(matched)
                self.assertEqual(matched.id, canonical.id)

    def test_trans_variant_does_not_resolve_to_cis_record(self) -> None:
        cis = self.repository.find_by_name("顺式12二氯乙烯")
        trans = self.repository.find_by_name("反式12二氯乙烯")
        self.assertIsNotNone(cis)
        self.assertIsNotNone(trans)
        self.assertNotEqual(cis.id, trans.id)


class WorkspaceImportMatchingTests(unittest.TestCase):
    def test_csv_import_accepts_reordered_cis_name(self) -> None:
        backend = RiskBackend()
        content = "污染物名称,地表浓度\n顺式12二氯乙烯,1.25\n".encode()

        payload = backend.import_workspace_file(
            content,
            filename="污染物测试.csv",
            content_type="text/csv",
        )

        self.assertEqual(payload["imported"], 1)
        imported = payload["items"][0]
        self.assertEqual(imported["pollutant"]["id"], 41)
        self.assertEqual(imported["pollutant"]["name"], "1,2-顺式-二氯乙烯")


if __name__ == "__main__":
    unittest.main()
