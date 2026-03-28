from __future__ import annotations

from typing import Iterable

from risk_backend.models.entities import to_decimal
from risk_backend.repositories.database import connect


class ResultRepository:
    """结果表仓储层。"""

    # reset 时只需要清空结果列，不动污染物编号、名称和工作区序号。
    RESET_SQL = {
        "db_exposure_ca": (
            "OISER_ca", "DCSER_ca", "PISER_ca", "IOVER_ca1", "IOVER_ca2",
            "IIVER_ca1", "IOVER_ca3", "IIVER_ca2", "DGWER_ca", "CGWER_ca",
        ),
        "db_exposure_nc": (
            "OISER_nc", "DCSER_nc", "PISER_nc", "IOVER_nc1", "IOVER_nc2",
            "IIVER_nc1", "IOVER_nc3", "IIVER_nc2", "DGWER_nc", "CGWER_nc",
        ),
        "db_hq": (
            "HQ_ois", "HQ_dcs", "HQ_pis", "HQ_iov1", "HQ_iov2", "HQ_iiv1",
            "HI_sn", "HQ_iov3", "HQ_iiv2", "HQ_dgw", "HQ_cgw", "HI_wn",
        ),
        "db_cr": (
            "CR_ois", "CR_dcs", "CR_pis", "CR_iov1", "CR_iov2", "CR_iiv1",
            "CR_sn", "CR_iov3", "CR_iiv2", "CR_dgw", "CR_cgw", "CR_wn",
        ),
        "db_pcr": (
            "PCR_ois", "PCR_dcs", "PCR_pis", "PCR_iov1", "PCR_iov2", "PCR_iiv1",
            "PCR_sn", "PCR_iov3", "PCR_iiv2", "PCR_dgw", "PCR_cgw", "PCR_wn",
        ),
        "db_phq": (
            "PHQ_ois", "PHQ_dcs", "PHQ_pis", "PHQ_iov1", "PHQ_iov2", "PHQ_iiv1",
            "PHI_sn", "PHQ_iov3", "PHQ_iiv2", "PHQ_dgw", "PHQ_cgw", "PHI_wn",
        ),
        "db_cv": ("RCVS_n", "HCVS_n", "RCVG_n", "HCVG_n", "CVS_pgw"),
    }

    # 不同结果表沿用旧项目里的排序习惯。
    TABLE_ORDERS = {
        "db_exposure_ca": "order by ID, number",
        "db_exposure_nc": "order by ID, number",
        "db_cr": "order by ID, number",
        "db_hq": "order by ID, number",
        "db_pcr": "order by number, ID",
        "db_phq": "order by ID, number",
        "db_cv": "order by ID, number",
    }

    def reset(self) -> None:
        """清空所有结果值，但保留工作区占位行。"""
        with connect() as con:
            for table, columns in self.RESET_SQL.items():
                assignment = ", ".join(f"{column} = NULL" for column in columns)
                con.execute(f"update {table} set {assignment}")

    def update_table(self, table: str, workspace_number: int, values: dict[str, object]) -> None:
        """把某条工作区记录的计算结果写回指定结果表。"""
        if not values:
            return
        set_sql = ", ".join(f"{column} = ?" for column in values)
        params = [float(value) if hasattr(value, "quantize") else value for value in values.values()]
        params.append(workspace_number)
        with connect() as con:
            con.execute(
                f"update {table} set {set_sql} where number = ?",
                params,
            )

    def fetch_table(self, table: str) -> list[list[object]]:
        """读取整张结果表，用于前端展示和导出。"""
        with connect() as con:
            rows = con.execute(f"select * from {table} {self.TABLE_ORDERS[table]}").fetchall()
        return [list(row) for row in rows]
