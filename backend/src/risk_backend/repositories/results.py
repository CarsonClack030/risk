from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from risk_backend.repositories.database import connect


class ResultRepository:
    """结果表仓储层。"""

    # reset 时只需要清空结果列，不动污染物编号、名称和工作区序号。
    RESET_SQL = {
        "db_exposure_ca": (
            "OISER_ca",
            "DCSER_ca",
            "PISER_ca",
            "IOVER_ca1",
            "IOVER_ca2",
            "IIVER_ca1",
            "IOVER_ca3",
            "IIVER_ca2",
            "DGWER_ca",
            "CGWER_ca",
        ),
        "db_exposure_nc": (
            "OISER_nc",
            "DCSER_nc",
            "PISER_nc",
            "IOVER_nc1",
            "IOVER_nc2",
            "IIVER_nc1",
            "IOVER_nc3",
            "IIVER_nc2",
            "DGWER_nc",
            "CGWER_nc",
        ),
        "db_hq": (
            "HQ_ois",
            "HQ_dcs",
            "HQ_pis",
            "HQ_iov1",
            "HQ_iov2",
            "HQ_iiv1",
            "HI_sn",
            "HQ_iov3",
            "HQ_iiv2",
            "HQ_dgw",
            "HQ_cgw",
            "HI_wn",
        ),
        "db_cr": (
            "CR_ois",
            "CR_dcs",
            "CR_pis",
            "CR_iov1",
            "CR_iov2",
            "CR_iiv1",
            "CR_sn",
            "CR_iov3",
            "CR_iiv2",
            "CR_dgw",
            "CR_cgw",
            "CR_wn",
        ),
        "db_pcr": (
            "PCR_ois",
            "PCR_dcs",
            "PCR_pis",
            "PCR_iov1",
            "PCR_iov2",
            "PCR_iiv1",
            "PCR_sn",
            "PCR_iov3",
            "PCR_iiv2",
            "PCR_dgw",
            "PCR_cgw",
            "PCR_wn",
        ),
        "db_phq": (
            "PHQ_ois",
            "PHQ_dcs",
            "PHQ_pis",
            "PHQ_iov1",
            "PHQ_iov2",
            "PHQ_iiv1",
            "PHI_sn",
            "PHQ_iov3",
            "PHQ_iiv2",
            "PHQ_dgw",
            "PHQ_cgw",
            "PHI_wn",
        ),
        "db_cv": ("RCVS_n", "HCVS_n", "RCVG_n", "HCVG_n", "CVS_pgw"),
    }

    def replace_results(
        self,
        results: dict[int, dict[str, dict[str, object]]],
    ) -> None:
        """Replace every result value atomically using one SQLite transaction."""
        grouped_updates: dict[tuple[str, tuple[str, ...]], list[tuple[object, ...]]] = (
            defaultdict(list)
        )
        for workspace_number, table_values in results.items():
            for table, values in table_values.items():
                if not values:
                    continue
                self._validate_update(table, values)
                columns = tuple(values)
                grouped_updates[(table, columns)].append(
                    tuple(self._database_value(values[column]) for column in columns)
                    + (workspace_number,)
                )

        with connect() as con:
            for table, columns in self.RESET_SQL.items():
                assignment = ", ".join(f"{column} = NULL" for column in columns)
                con.execute(f"update {table} set {assignment}")

            for (table, columns), params in grouped_updates.items():
                set_sql = ", ".join(f"{column} = ?" for column in columns)
                con.executemany(
                    f"update {table} set {set_sql} where number = ?",
                    params,
                )

    def _validate_update(self, table: str, values: dict[str, object]) -> None:
        allowed_columns = self.RESET_SQL.get(table)
        if allowed_columns is None:
            raise ValueError(f"不支持的结果表：{table}")
        invalid_columns = set(values).difference(allowed_columns)
        if invalid_columns:
            names = "、".join(sorted(invalid_columns))
            raise ValueError(f"结果表 {table} 包含不支持的列：{names}")

    @staticmethod
    def _database_value(value: object) -> object:
        return float(value) if isinstance(value, Decimal) else value

    def fetch_table(self, table: str) -> list[list[object]]:
        """按工作区序号读取结果表，用于前端展示和导出。

        `ID` 是污染物库编号，同一种污染物重复加入工作区时会拥有相同的 ID；
        `number` 才是本次工作区中每一条记录的唯一序号。因此所有结果表必须按
        number 排序，才能与工作区列表和各条浓度记录保持一一对应。
        """
        if table not in self.RESET_SQL:
            raise ValueError(f"不支持的结果表：{table}")
        with connect() as con:
            rows = con.execute(f"select * from {table} order by number").fetchall()
        return [list(row) for row in rows]
