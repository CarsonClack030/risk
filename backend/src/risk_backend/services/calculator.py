from __future__ import annotations

import math
from decimal import Decimal

from risk_backend.models.entities import (
    ZERO,
    AttributeMap,
    SelectedPollutant,
    SiteSelection,
    to_decimal,
)
from risk_backend.repositories.parameters import ParameterRepository

# PATHWAY_FLAGS 把前端路径 key 映射到旧项目里常见的拼音缩写。
# 这份映射本身不参与公式计算，但它保留了旧版业务语义，
# 方便后续核对旧代码或纸质公式时快速对照。
PATHWAY_FLAGS = {
    "ois": "jinkou",
    "dcs": "pitu",
    "pis": "xiru",
    "dgw": "pishui",
    "cgw": "yinshui",
    "iov3": "xiwaishui",
    "iiv2": "xineishui",
    "iov1": "xiwaibiaotu",
    "iov2": "xiwaixiatu",
    "iiv1": "xineixiatu",
}

# 这些参数会直接出现在分母、对数或迁移公式中，必须严格大于 0。
# 字典值同时作为用户可读的报错名称，避免只显示难懂的英文符号。
POSITIVE_PARAMETER_LABELS = {
    "A": "污染源区面积",
    "Ab": "室内地板面积",
    "ACR": "单一污染物可接受致癌风险",
    "AHQ": "单一污染物可接受危害熵",
    "ATca": "致癌效应平均时间",
    "ATnc": "非致癌效应平均时间",
    "BWa": "成人平均体重",
    "DAIRa": "成人每日空气呼吸量",
    "Delta_air": "混合区高度",
    "Delta_gw": "地下水混合区厚度",
    "Eit": "地基和墙体裂隙表面积所占面积",
    "ER": "室内空气交换速率",
    "I": "土壤中水的入渗速率",
    "LB": "室内空间体积与气态污染物入渗面积之比",
    "Lcrack": "室内地基厚度",
    "Lgw": "地下水埋深",
    "LS": "下层污染土壤层埋深",
    "Rho_b": "土壤容重",
    "Rho_s": "土壤颗粒密度",
    "Tau": "气态污染物入侵持续时间",
    "Uair": "混合区大气流速",
    "Ugw": "地下水达西速率",
    "W": "污染源区宽度",
    "X_crack": "室内地板周长",
    "Z_crack": "室内地面到地板底部厚度",
}

# 比例参数必须位于 0 到 1 之间。这里保留 0 和 1 两个边界，
# 因为部分路径允许“不吸收”或“全部分配”这类极端但有效的配置。
UNIT_INTERVAL_PARAMETER_LABELS = {
    "ABSo": "经口摄入吸收因子",
    "Eit": "地基和墙体裂隙表面积所占面积",
    "fspi": "室内土壤颗粒物比例",
    "fspo": "室外土壤颗粒物比例",
    "PIAF": "吸入颗粒物体内滞留比例",
    "Pws": "土壤含水率",
    "SERa": "成人暴露皮肤面积比",
    "SERc": "儿童暴露皮肤面积比",
    "Theta_acap": "毛细管层孔隙空气体积比",
    "Theta_acrack": "地基裂隙空气体积比",
    "Theta_wcap": "毛细管层孔隙水体积比",
    "Theta_wcrack": "地基裂隙水体积比",
    "WAF": "地下水参考剂量分配比例",
}


class RiskCalculator:
    """风险评估公式核心。

    可以把这个类看成整个项目的“计算发动机”：
    前端负责采集条件，仓储层负责读写数据库，
    而真正把参数和浓度变成风险结果的，是这里。
    """

    def __init__(self, parameter_repository: ParameterRepository):
        self.parameter_repository = parameter_repository
        # 下面这些常量名称保留了旧项目写法，
        # 目的是在重构时尽量不改变原公式的视觉结构。
        self.diansansan = Decimal("3.33")
        self.pai = Decimal("3.14159")
        self.dianwu = Decimal("0.5")
        self.dianqi = Decimal("1.7")
        self.dianba = Decimal("0.000181")
        self.dianliu = Decimal("0.000001")
        self.diansan = Decimal("0.001")

    def calculate(
        self,
        selection: SiteSelection,
        selected_pollutants: list[SelectedPollutant],
        pathway_flags: dict[str, bool],
    ) -> dict[int, dict[str, dict[str, Decimal]]]:
        """批量计算整个工作区。

        返回值第一层 key 是 workspace_number，
        这样即使同一个污染物被加入多次，也能分别保存结果。
        """
        parameter_values = self.parameter_repository.get_parameter_map(selection)
        self.validate_parameters(selection, parameter_values)
        parameters = AttributeMap(parameter_values)
        return {
            item.workspace_number: self._calculate_single(
                selection, parameters, item, pathway_flags
            )
            for item in selected_pollutants
        }

    def validate_parameters(
        self, selection: SiteSelection, values: dict[str, Decimal]
    ) -> None:
        """在进入公式前校验参数的数值范围和组合关系。

        单个参数即使看起来是数字，组合后也可能破坏公式定义域。例如土壤含水率
        过大时，`总孔隙率 - 充水孔隙率` 会成为负数，随后进行 3.33 次方就会触发
        `Decimal.InvalidOperation`。这里把底层数学异常提前翻译成可操作的中文提示。
        """
        errors: list[str] = []
        finite_values: dict[str, Decimal] = {}

        for name, raw_value in values.items():
            value = (
                raw_value if isinstance(raw_value, Decimal) else to_decimal(raw_value)
            )
            if not value.is_finite():
                errors.append(f"参数 {name}={value} 不是有限数字")
                continue
            finite_values[name] = value

            label = POSITIVE_PARAMETER_LABELS.get(
                name,
                UNIT_INTERVAL_PARAMETER_LABELS.get(name, name),
            )
            if name in POSITIVE_PARAMETER_LABELS:
                if value <= ZERO:
                    errors.append(f"{label}（{name}）必须大于 0，当前为 {value}")
            elif value < ZERO:
                errors.append(f"{label}（{name}）不能小于 0，当前为 {value}")

            if name in UNIT_INTERVAL_PARAMETER_LABELS and value > 1:
                ratio_label = UNIT_INTERVAL_PARAMETER_LABELS[name]
                errors.append(
                    f"{ratio_label}（{name}）必须在 0 到 1 之间，当前为 {value}"
                )

        # 第一类用地公式包含儿童暴露量，儿童体重会直接作为分母。
        bwc = finite_values.get("BWc")
        if selection.area_type == "I" and bwc is not None and bwc <= ZERO:
            errors.append(f"儿童平均体重（BWc）在第一类用地中必须大于 0，当前为 {bwc}")

        rho_b = finite_values.get("Rho_b")
        rho_s = finite_values.get("Rho_s")
        pws = finite_values.get("Pws")
        if rho_b is not None and rho_s is not None and pws is not None and rho_s > ZERO:
            total_porosity = Decimal("1") - rho_b / rho_s
            air_porosity = total_porosity - rho_b * pws
            if total_porosity <= ZERO:
                errors.append(
                    f"土壤容重 Rho_b={rho_b} 必须小于土壤颗粒密度 Rho_s={rho_s}"
                )
            elif air_porosity < ZERO:
                errors.append(
                    "土壤含水率与密度组合导致土壤空气孔隙率小于 0："
                    f"Rho_b={rho_b}，Rho_s={rho_s}，Pws={pws}，计算值={air_porosity}"
                )

        for air_name, water_name, label in (
            ("Theta_acap", "Theta_wcap", "毛细管层总孔隙体积比"),
            ("Theta_acrack", "Theta_wcrack", "地基裂隙总孔隙体积比"),
        ):
            air_value = finite_values.get(air_name)
            water_value = finite_values.get(water_name)
            if air_value is None or water_value is None:
                continue
            total = air_value + water_value
            if total <= ZERO or total > 1:
                errors.append(
                    f"{label}必须大于 0 且不超过 1："
                    f"{air_name}={air_value}，{water_name}={water_value}，合计={total}"
                )

        hcap = finite_values.get("hcap")
        hv = finite_values.get("hv")
        if hcap is not None and hv is not None and hcap + hv <= ZERO:
            errors.append(
                f"毛细管层厚度 hcap={hcap} 与非饱和土层厚度 hv={hv} 不能同时为 0"
            )

        # 建筑物气体入侵公式包含该比值的自然对数；比值等于 1 时分母为 0。
        log_names = ("Z_crack", "X_crack", "Ab", "Eit")
        if all(
            name in finite_values and finite_values[name] > ZERO for name in log_names
        ):
            log_argument = (
                2
                * finite_values["Z_crack"]
                * finite_values["X_crack"]
                / (finite_values["Ab"] * finite_values["Eit"])
            )
            if log_argument == 1:
                errors.append(
                    "建筑物参数使气体入侵公式的对数分母为 0："
                    "2×Z_crack×X_crack 不能等于 Ab×Eit"
                )

        if errors:
            standard_label = "国家标准" if selection.standard == "G" else "浙江标准"
            area_label = "第一类用地" if selection.area_type == "I" else "第二类用地"
            details = "；".join(errors[:5])
            more = "；还有其他参数错误，请逐项修正" if len(errors) > 5 else ""
            raise ValueError(
                f"参数校验失败（{standard_label} · {area_label}）：{details}{more}。"
                "请修改参数或使用“恢复默认”。"
            )

    def _calculate_single(
        self,
        selection: SiteSelection,
        parameters: AttributeMap,
        item: SelectedPollutant,
        pathway_flags: dict[str, bool],
    ) -> dict[str, dict[str, Decimal]]:
        """计算单个工作区污染物。

        主流程非常值得记住：
        1. 先创建一份“全部字段都为 0”的状态表。
        2. 判断污染物是否挥发。
        3. 挥发型先算气态迁移中间量，再执行所有路径。
        4. 非挥发型只执行直接接触相关路径。
        5. 最后把中间结果整理成 7 张结果表的字段。
        """
        pollutant = item.pollutant
        concentration = item.concentration
        state = self._build_empty_state()

        if pollutant.henry == ZERO:
            self._run_nonvolatile(
                selection, parameters, pollutant, concentration, state, pathway_flags
            )
        else:
            gas = self._gaspd(parameters, pollutant, pollutant.name)
            state.update(gas)
            self._run_all_pathways(
                selection, parameters, pollutant, concentration, state, pathway_flags
            )

        summary = self._build_summaries(
            parameters, pollutant, concentration, state, pollutant.name
        )
        return {
            "db_exposure_ca": self._pick(
                summary,
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
            "db_exposure_nc": self._pick(
                summary,
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
            "db_cr": self._pick(
                summary,
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
            "db_hq": self._pick(
                summary,
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
            "db_pcr": self._pick(
                summary,
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
            "db_phq": self._pick(
                summary,
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
            "db_cv": self._pick(
                summary, "RCVS_n", "HCVS_n", "RCVG_n", "HCVG_n", "CVS_pgw"
            ),
        }

    def _build_empty_state(self) -> dict[str, Decimal]:
        """准备统一的零值状态表。

        好处是后续所有路径都可以直接往 state 里写值；
        未计算的路径自动保持 0，汇总时也不用做空值判断。
        """
        columns = [
            "OISER_ca",
            "OISER_nc",
            "CR_ois",
            "HQ_ois",
            "DCSER_ca",
            "DCSER_nc",
            "CR_dcs",
            "HQ_dcs",
            "PISER_ca",
            "PISER_nc",
            "CR_pis",
            "HQ_pis",
            "DGWER_ca",
            "DGWER_nc",
            "CR_dgw",
            "HQ_dgw",
            "CGWER_ca",
            "CGWER_nc",
            "CR_cgw",
            "HQ_cgw",
            "IOVER_ca1",
            "IOVER_nc1",
            "CR_iov1",
            "HQ_iov1",
            "IOVER_ca2",
            "IOVER_nc2",
            "CR_iov2",
            "HQ_iov2",
            "IIVER_ca1",
            "IIVER_nc1",
            "CR_iiv1",
            "HQ_iiv1",
            "IOVER_ca3",
            "IOVER_nc3",
            "CR_iov3",
            "HQ_iov3",
            "IIVER_ca2",
            "IIVER_nc2",
            "CR_iiv2",
            "HQ_iiv2",
            "VF_subia",
            "VF_suboa",
            "VF_suroa",
            "VF_gwia",
            "VF_gwoa",
            "Theta",
            "Theta_ws",
            "Theta_as",
            "D_eff_s",
            "D_eff_cap",
            "D_eff_gws",
            "D_eff_crack",
            "f_oc",
            "K_d",
            "K_sw",
            "DF_oa",
            "DF_ia",
            "Q_s",
        ]
        return {column: ZERO for column in columns}

    def _run_nonvolatile(
        self,
        selection: SiteSelection,
        par: AttributeMap,
        pollutant,
        concentration,
        state: dict[str, Decimal],
        pathways: dict[str, bool],
    ) -> None:
        """非挥发污染物只跑直接接触路径。"""
        for key in ("ois", "dcs", "pis", "dgw", "cgw"):
            if pathways.get(key):
                getattr(self, f"_calc_{key}")(
                    selection, par, pollutant, concentration, state
                )

    def _run_all_pathways(
        self,
        selection: SiteSelection,
        par: AttributeMap,
        pollutant,
        concentration,
        state: dict[str, Decimal],
        pathways: dict[str, bool],
    ) -> None:
        """挥发污染物可走全部路径。"""
        for key in PATHWAY_FLAGS:
            if pathways.get(key):
                getattr(self, f"_calc_{key}")(
                    selection, par, pollutant, concentration, state
                )

    def _first_type(self, selection: SiteSelection) -> bool:
        """第一类用地通常要同时考虑儿童和成人暴露。"""
        return selection.area_type == "I"

    def _safe_div(self, numerator: Decimal, denominator: Decimal) -> Decimal:
        """安全除法，避免除零导致整次计算失败。"""
        try:
            if denominator == ZERO:
                return ZERO
            return numerator / denominator
        except Exception:
            return ZERO

    def _safe_min(self, left: Decimal, right: Decimal) -> Decimal:
        """安全取最小值。"""
        try:
            return min(left, right)
        except Exception:
            return ZERO

    def _ln(self, value: Decimal) -> Decimal:
        """安全求自然对数。"""
        try:
            return value.ln()
        except Exception:
            try:
                return Decimal(str(math.log(float(value))))
            except Exception:
                return ZERO

    def _pow_e(self, value: Decimal) -> Decimal:
        """安全计算 e 的指数次幂。"""
        try:
            return Decimal(str(math.e ** float(value)))
        except Exception:
            return ZERO

    def _sfd(self, pollutant) -> Decimal:
        """皮肤接触路径用到的斜率因子折算。"""
        return self._safe_div(pollutant.sfo, pollutant.absgi)

    def _rfdd(self, pollutant) -> Decimal:
        """皮肤接触路径用到的参考剂量折算。"""
        return pollutant.rfdo * pollutant.absgi

    def _sfi(self, par: AttributeMap, pollutant) -> Decimal:
        """吸入路径用到的致癌斜率因子折算。"""
        return pollutant.iur * self._safe_div(par.BWa, par.DAIRa)

    def _rfdi(self, par: AttributeMap, pollutant) -> Decimal:
        """吸入路径用到的参考剂量折算。"""
        return pollutant.rfc * self._safe_div(par.DAIRa, par.BWa)

    def _calc_ois(self, selection, par, pollutant, concentration, state):
        """口摄入土壤颗粒物路径。"""
        if self._first_type(selection):
            state["OISER_ca"] = (
                (
                    (par.OSIRc * par.EDc * par.EFc / par.BWc)
                    + (par.OSIRa * par.EDa * par.EFa / par.BWa)
                )
                * par.ABSo
                / par.ATca
                * self.dianliu
            )
            state["OISER_nc"] = (
                par.OSIRc
                * par.EDc
                * par.EFc
                * par.ABSo
                / par.BWc
                / par.ATnc
                * self.dianliu
            )
        else:
            state["OISER_ca"] = (
                par.OSIRa
                * par.EDa
                * par.EFa
                / par.BWa
                * par.ABSo
                / par.ATca
                * self.dianliu
            )
            state["OISER_nc"] = (
                par.OSIRa
                * par.EDa
                * par.EFa
                / par.BWa
                * par.ABSo
                / par.ATnc
                * self.dianliu
            )
        state["CR_ois"] = (
            state["OISER_ca"] * concentration.surface_concentration * pollutant.sfo
        )
        state["HQ_ois"] = self._safe_div(
            state["OISER_nc"] * concentration.surface_concentration,
            pollutant.rfdo * pollutant.saf,
        )

    def _calc_dcs(self, selection, par, pollutant, concentration, state):
        """皮肤接触土壤颗粒物路径。"""
        if self._first_type(selection):
            state["DCSER_ca"] = (
                par.SAEc
                * par.SSARc
                * par.EFc
                * par.EDc
                * par.Ev
                * pollutant.absd
                * self.dianliu
                / par.BWc
                / par.ATca
                + par.SAEa
                * par.SSARa
                * par.EFa
                * par.EDa
                * par.Ev
                * pollutant.absd
                * self.dianliu
                / par.BWa
                / par.ATca
            )
            state["DCSER_nc"] = (
                par.SAEc
                * par.SSARc
                * par.EFc
                * par.EDc
                * par.Ev
                * pollutant.absd
                * self.dianliu
                / par.BWc
                / par.ATnc
            )
        else:
            state["DCSER_ca"] = (
                par.SAEa
                * par.SSARa
                * par.EFa
                * par.EDa
                * par.Ev
                * pollutant.absd
                * self.dianliu
                / par.BWa
                / par.ATca
            )
            state["DCSER_nc"] = (
                par.SAEa
                * par.SSARa
                * par.EFa
                * par.EDa
                * par.Ev
                * pollutant.absd
                * self.dianliu
                / par.BWa
                / par.ATnc
            )
        state["CR_dcs"] = (
            state["DCSER_ca"]
            * concentration.surface_concentration
            * self._sfd(pollutant)
        )
        state["HQ_dcs"] = self._safe_div(
            state["DCSER_nc"] * concentration.surface_concentration,
            self._rfdd(pollutant) * pollutant.saf,
        )

    def _calc_pis(self, selection, par, pollutant, concentration, state):
        """吸入土壤颗粒物路径。"""
        if self._first_type(selection):
            state["PISER_ca"] = (
                par.PM10
                * par.DAIRc
                * par.EDc
                * par.PIAF
                * (par.fspo * par.EFOc + par.fspi * par.EFIc)
                * self.dianliu
                / par.BWc
                / par.ATca
                + par.PM10
                * par.DAIRa
                * par.EDa
                * par.PIAF
                * (par.fspo * par.EFOa + par.fspi * par.EFIa)
                * self.dianliu
                / par.BWa
                / par.ATca
            )
            state["PISER_nc"] = (
                par.PM10
                * par.DAIRc
                * par.EDc
                * par.PIAF
                * (par.fspo * par.EFOc + par.fspi * par.EFIc)
                * self.dianliu
                / par.BWc
                / par.ATnc
            )
        else:
            state["PISER_ca"] = (
                par.PM10
                * par.DAIRa
                * par.EDa
                * par.PIAF
                * (par.fspo * par.EFOa + par.fspi * par.EFIa)
                * self.dianliu
                / par.BWa
                / par.ATca
            )
            state["PISER_nc"] = (
                par.PM10
                * par.DAIRa
                * par.EDa
                * par.PIAF
                * (par.fspo * par.EFOa + par.fspi * par.EFIa)
                * self.dianliu
                / par.BWa
                / par.ATnc
            )
        state["CR_pis"] = (
            state["PISER_ca"]
            * concentration.surface_concentration
            * self._sfi(par, pollutant)
        )
        state["HQ_pis"] = self._safe_div(
            state["PISER_nc"] * concentration.surface_concentration,
            self._rfdi(par, pollutant) * pollutant.saf,
        )

    def _calc_dgw(self, selection, par, pollutant, concentration, state):
        """皮肤接触地下水路径。"""
        daec = (
            pollutant.kp
            * concentration.groundwater_concentration
            * par.tc
            * self.diansan
        )
        daea = (
            pollutant.kp
            * concentration.groundwater_concentration
            * par.ta
            * self.diansan
        )
        if self._first_type(selection):
            state["DGWER_ca"] = (
                par.SAEc
                * par.EFc
                * par.EDc
                * par.Ev
                * daec
                * self.dianliu
                / par.BWc
                / par.ATca
                + par.SAEa
                * par.EFa
                * par.EDa
                * par.Ev
                * daea
                * self.dianliu
                / par.BWa
                / par.ATca
            )
            state["DGWER_nc"] = (
                par.SAEc
                * par.EFc
                * par.EDc
                * par.Ev
                * daec
                * self.dianliu
                / par.BWc
                / par.ATnc
            )
        else:
            state["DGWER_ca"] = (
                par.SAEa
                * par.EFa
                * par.EDa
                * par.Ev
                * daea
                * self.dianliu
                / par.BWa
                / par.ATca
            )
            state["DGWER_nc"] = (
                par.SAEa
                * par.EFa
                * par.EDa
                * par.Ev
                * daea
                * self.dianliu
                / par.BWa
                / par.ATnc
            )
        state["CR_dgw"] = state["DGWER_ca"] * self._sfd(pollutant)
        state["HQ_dgw"] = self._safe_div(state["DGWER_nc"], self._rfdd(pollutant))

    def _calc_cgw(self, selection, par, pollutant, concentration, state):
        """饮用地下水路径。"""
        if self._first_type(selection):
            state["CGWER_ca"] = (
                par.GWCRc * par.EFc * par.EDc / par.BWc / par.ATca
                + par.GWCRa * par.EFa * par.EDa / par.BWa / par.ATca
            )
            state["CGWER_nc"] = par.GWCRc * par.EFc * par.EDc / par.BWc / par.ATnc
        else:
            state["CGWER_ca"] = par.GWCRa * par.EFa * par.EDa / par.BWa / par.ATca
            state["CGWER_nc"] = par.GWCRa * par.EFa * par.EDa / par.BWa / par.ATnc
        state["CR_cgw"] = (
            state["CGWER_ca"] * concentration.groundwater_concentration * pollutant.sfo
        )
        state["HQ_cgw"] = self._safe_div(
            state["CGWER_nc"] * concentration.groundwater_concentration,
            pollutant.rfdo * pollutant.saf,
        )

    def _gaspd(
        self, par: AttributeMap, pollutant, pollutant_name: str
    ) -> dict[str, Decimal]:
        """计算挥发相关的关键中间量。

        这些值会被后面的室内/室外空气暴露路径复用。
        可以理解为“先算污染物如何从土壤或地下水迁移到空气中”。
        """
        gas = self._build_empty_state()
        # 土壤孔隙相参数。
        gas["Theta"] = to_decimal(1) - self._safe_div(par.Rho_b, par.Rho_s)
        gas["Theta_ws"] = par.Rho_b * par.Pws
        gas["Theta_as"] = gas["Theta"] - gas["Theta_ws"]
        # 分别计算土壤层、覆盖层、地下水层和裂缝中的有效扩散系数。
        gas["D_eff_s"] = self._safe_div(
            pollutant.da * (gas["Theta_as"] ** self.diansansan), gas["Theta"] ** 2
        ) + self._safe_div(
            pollutant.dw * (gas["Theta_ws"] ** self.diansansan),
            (gas["Theta"] ** 2) * pollutant.henry,
        )
        gas["D_eff_cap"] = self._safe_div(
            pollutant.da * (par.Theta_acap**self.diansansan),
            (par.Theta_acap + par.Theta_wcap) ** 2,
        ) + self._safe_div(
            pollutant.dw * (par.Theta_wcap**self.diansansan),
            ((par.Theta_acap + par.Theta_wcap) ** 2) * pollutant.henry,
        )
        gas["D_eff_gws"] = self._safe_div(
            par.Lgw,
            self._safe_div(par.hcap, gas["D_eff_cap"])
            + self._safe_div(par.hv, gas["D_eff_s"]),
        )
        gas["D_eff_crack"] = self._safe_div(
            pollutant.da * (par.Theta_acrack**self.diansansan),
            (par.Theta_acrack + par.Theta_wcrack) ** 2,
        ) + self._safe_div(
            pollutant.dw * (par.Theta_wcrack**self.diansansan),
            ((par.Theta_acrack + par.Theta_wcrack) ** 2) * pollutant.henry,
        )
        gas["f_oc"] = par.fom / self.dianqi / 1000
        # 某些污染物保留旧项目中的经验 Kd 值，避免和原模型结果偏离。
        if pollutant_name == "汞（无机）":
            gas["K_d"] = Decimal("52")
        elif pollutant_name == "氰化物":
            gas["K_d"] = Decimal("9.9")
        elif pollutant_name == "次氯酸钠":
            gas["K_d"] = Decimal("{:.3e}".format(10 ** (-0.207608310501746)))
        elif pollutant_name == "铀（可溶性盐）":
            gas["K_d"] = Decimal("{:.3e}".format(10**3.47))
        else:
            gas["K_d"] = pollutant.koc * gas["f_oc"]
        gas["K_sw"] = self._safe_div(
            gas["Theta_ws"]
            + gas["K_d"] * par.Rho_b
            + pollutant.henry * gas["Theta_as"],
            par.Rho_b,
        )
        gas["DF_oa"] = self._safe_div(par.Uair * par.W * par.Delta_air, par.A)
        gas["DF_ia"] = par.LB * par.ER / 86400
        denominator = self._ln(2 * par.Z_crack * par.X_crack / (par.Ab * par.Eit))
        gas["Q_s"] = self._safe_div(
            2 * self.pai * par.dP * par.K_v * par.X_crack, self.dianba * denominator
        )
        xxx = self._safe_div(
            gas["Q_s"] * par.Lcrack, par.Ab * gas["D_eff_crack"] * par.Eit
        )
        exp_x = self._pow_e(xxx)

        # 如果存在下层污染土壤，则还要考虑寿命/衰减约束，最后取更保守的最小值。
        if par.dsub > 0:
            if gas["Q_s"] == ZERO:
                gas["VF_subia"] = self._safe_div(
                    1000,
                    self._safe_div(gas["K_sw"], pollutant.henry)
                    * (
                        1
                        + self._safe_div(gas["D_eff_s"], gas["DF_ia"] * par.LS)
                        + self._safe_div(
                            gas["D_eff_s"] * par.Lcrack,
                            gas["D_eff_crack"] * par.LS * par.Eit,
                        )
                    )
                    * self._safe_div(gas["DF_ia"] * par.LS, gas["D_eff_s"]),
                )
            else:
                gas["VF_subia"] = self._safe_div(
                    1000,
                    self._safe_div(gas["K_sw"], pollutant.henry)
                    * (
                        exp_x
                        + self._safe_div(gas["D_eff_s"], gas["DF_ia"] * par.LS)
                        + self._safe_div(
                            gas["D_eff_s"] * par.Ab * (exp_x - 1), gas["Q_s"] * par.LS
                        )
                    )
                    * self._safe_div(gas["DF_ia"] * par.LS, gas["D_eff_s"] * exp_x),
                )
            vf_subia2 = par.dsub * par.Rho_b * 1000 / gas["DF_ia"] / par.Tau / 31536000
            gas["VF_subia"] = self._safe_min(gas["VF_subia"], vf_subia2)
            vf_suboa1 = self._safe_div(
                1, 1 + self._safe_div(gas["DF_oa"] * par.LS, gas["D_eff_s"])
            ) * self._safe_div(pollutant.henry * 1000, gas["K_sw"])
            vf_suboa2 = par.dsub * par.Rho_b * 1000 / gas["DF_oa"] / par.Tau / 31536000
            gas["VF_suboa"] = self._safe_min(vf_suboa1, vf_suboa2)
        else:
            if gas["Q_s"] == ZERO:
                gas["VF_subia"] = self._safe_div(
                    1000,
                    self._safe_div(gas["K_sw"], pollutant.henry)
                    * (
                        1
                        + self._safe_div(gas["D_eff_s"], gas["DF_ia"] * par.LS)
                        + self._safe_div(
                            gas["D_eff_s"] * par.Lcrack,
                            gas["D_eff_crack"] * par.LS * par.Eit,
                        )
                    )
                    * self._safe_div(gas["DF_ia"] * par.LS, gas["D_eff_s"]),
                )
            else:
                gas["VF_subia"] = self._safe_div(
                    1000,
                    self._safe_div(gas["K_sw"], pollutant.henry)
                    * (
                        exp_x
                        + self._safe_div(gas["D_eff_s"], gas["DF_ia"] * par.LS)
                        + self._safe_div(
                            gas["D_eff_s"] * par.Ab * (exp_x - 1), gas["Q_s"] * par.LS
                        )
                    )
                    * self._safe_div(gas["DF_ia"] * par.LS, gas["D_eff_s"] * exp_x),
                )
            gas["VF_suboa"] = self._safe_div(
                1, 1 + self._safe_div(gas["DF_oa"] * par.LS, gas["D_eff_s"])
            ) * self._safe_div(pollutant.henry * 1000, gas["K_sw"])

        vf_suroa1 = (
            self._safe_div(
                par.Rho_b,
                gas["DF_oa"],
            )
            * (
                self._safe_div(
                    4 * gas["D_eff_s"] * pollutant.henry,
                    self.pai * par.Tau * 31536000 * gas["K_sw"] * par.Rho_b,
                )
            )
            ** self.dianwu
            * 1000
        )
        vf_suroa2 = par.d * par.Rho_b / gas["DF_oa"] / par.Tau / 31536000 * 1000
        gas["VF_suroa"] = self._safe_min(vf_suroa1, vf_suroa2)

        if gas["Q_s"] == ZERO:
            gas["VF_gwia"] = self._safe_div(
                1000 * pollutant.henry * gas["D_eff_gws"],
                (
                    1
                    + self._safe_div(gas["D_eff_gws"], gas["DF_ia"] * par.Lgw)
                    + self._safe_div(
                        gas["D_eff_gws"] * par.Lcrack,
                        gas["D_eff_crack"] * par.Lgw * par.Eit,
                    )
                )
                * gas["DF_ia"]
                * par.Lgw,
            )
        else:
            gas["VF_gwia"] = self._safe_div(
                1000 * pollutant.henry * gas["D_eff_gws"] * exp_x,
                (
                    1
                    + self._safe_div(gas["D_eff_gws"], gas["DF_ia"] * par.Lgw)
                    + self._safe_div(
                        gas["D_eff_gws"] * par.Ab * (exp_x - 1), gas["Q_s"] * par.Lgw
                    )
                )
                * gas["DF_ia"]
                * par.Lgw,
            )
        gas["VF_gwoa"] = self._safe_div(
            1000 * pollutant.henry,
            1 + self._safe_div(gas["DF_oa"] * par.Lgw, gas["D_eff_gws"]),
        )
        return gas

    def _calc_iov3(self, selection, par, pollutant, concentration, state):
        """吸入室外空气中来自地下水的气态污染物。"""
        if self._first_type(selection):
            state["IOVER_ca3"] = state["VF_gwoa"] * (
                par.DAIRc * par.EFOc * par.EDc / par.BWc / par.ATca
                + par.DAIRa * par.EFOa * par.EDa / par.BWa / par.ATca
            )
            state["IOVER_nc3"] = (
                state["VF_gwoa"] * par.DAIRc * par.EFOc * par.EDc / par.BWc / par.ATnc
            )
        else:
            state["IOVER_ca3"] = (
                state["VF_gwoa"] * par.DAIRa * par.EFOa * par.EDa / par.BWa / par.ATca
            )
            state["IOVER_nc3"] = (
                state["VF_gwoa"] * par.DAIRa * par.EFOa * par.EDa / par.BWa / par.ATnc
            )
        state["CR_iov3"] = (
            state["IOVER_ca3"]
            * concentration.groundwater_concentration
            * self._sfi(par, pollutant)
        )
        state["HQ_iov3"] = self._safe_div(
            state["IOVER_nc3"] * concentration.groundwater_concentration,
            self._rfdi(par, pollutant) * pollutant.saf,
        )

    def _calc_iiv2(self, selection, par, pollutant, concentration, state):
        """吸入室内空气中来自地下水的气态污染物。"""
        if self._first_type(selection):
            state["IIVER_ca2"] = state["VF_gwia"] * (
                par.DAIRc * par.EFIc * par.EDc / par.BWc / par.ATca
                + par.DAIRa * par.EFIa * par.EDa / par.BWa / par.ATca
            )
            state["IIVER_nc2"] = (
                state["VF_gwia"] * par.DAIRc * par.EFIc * par.EDc / par.BWc / par.ATnc
            )
        else:
            state["IIVER_ca2"] = (
                state["VF_gwia"] * par.DAIRa * par.EFIa * par.EDa / par.BWa / par.ATca
            )
            state["IIVER_nc2"] = (
                state["VF_gwia"] * par.DAIRa * par.EFIa * par.EDa / par.BWa / par.ATnc
            )
        state["CR_iiv2"] = (
            state["IIVER_ca2"]
            * concentration.groundwater_concentration
            * self._sfi(par, pollutant)
        )
        state["HQ_iiv2"] = self._safe_div(
            state["IIVER_nc2"] * concentration.groundwater_concentration,
            self._rfdi(par, pollutant) * pollutant.saf,
        )

    def _calc_iov1(self, selection, par, pollutant, concentration, state):
        """吸入室外空气中来自表层土壤的气态污染物。"""
        if self._first_type(selection):
            state["IOVER_ca1"] = state["VF_suroa"] * (
                par.DAIRc * par.EFOc * par.EDc / par.BWc / par.ATca
                + par.DAIRa * par.EFOa * par.EDa / par.BWa / par.ATca
            )
            state["IOVER_nc1"] = (
                state["VF_suroa"] * par.DAIRc * par.EFOc * par.EDc / par.BWc / par.ATnc
            )
        else:
            state["IOVER_ca1"] = (
                state["VF_suroa"] * par.DAIRa * par.EFOa * par.EDa / par.BWa / par.ATca
            )
            state["IOVER_nc1"] = (
                state["VF_suroa"] * par.DAIRa * par.EFOa * par.EDa / par.BWa / par.ATnc
            )
        state["CR_iov1"] = (
            state["IOVER_ca1"]
            * concentration.surface_concentration
            * self._sfi(par, pollutant)
        )
        state["HQ_iov1"] = self._safe_div(
            state["IOVER_nc1"] * concentration.surface_concentration,
            self._rfdi(par, pollutant) * pollutant.saf,
        )

    def _calc_iov2(self, selection, par, pollutant, concentration, state):
        """吸入室外空气中来自下层土壤的气态污染物。"""
        if self._first_type(selection):
            state["IOVER_ca2"] = state["VF_suboa"] * (
                par.DAIRc * par.EFOc * par.EDc / par.BWc / par.ATca
                + par.DAIRa * par.EFOa * par.EDa / par.BWa / par.ATca
            )
            state["IOVER_nc2"] = (
                state["VF_suboa"] * par.DAIRc * par.EFOc * par.EDc / par.BWc / par.ATnc
            )
        else:
            state["IOVER_ca2"] = (
                state["VF_suboa"] * par.DAIRa * par.EFOa * par.EDa / par.BWa / par.ATca
            )
            state["IOVER_nc2"] = (
                state["VF_suboa"] * par.DAIRa * par.EFOa * par.EDa / par.BWa / par.ATnc
            )
        state["CR_iov2"] = (
            state["IOVER_ca2"]
            * concentration.lower_soil_concentration
            * self._sfi(par, pollutant)
        )
        state["HQ_iov2"] = self._safe_div(
            state["IOVER_nc2"] * concentration.lower_soil_concentration,
            self._rfdi(par, pollutant) * pollutant.saf,
        )

    def _calc_iiv1(self, selection, par, pollutant, concentration, state):
        """吸入室内空气中来自下层土壤的气态污染物。"""
        if self._first_type(selection):
            state["IIVER_ca1"] = state["VF_subia"] * (
                par.DAIRc * par.EFIc * par.EDc / par.BWc / par.ATca
                + par.DAIRa * par.EFIa * par.EDa / par.BWa / par.ATca
            )
            state["IIVER_nc1"] = (
                state["VF_subia"] * par.DAIRc * par.EFIc * par.EDc / par.BWc / par.ATnc
            )
        else:
            state["IIVER_ca1"] = (
                state["VF_subia"] * par.DAIRa * par.EFIa * par.EDa / par.BWa / par.ATca
            )
            state["IIVER_nc1"] = (
                state["VF_subia"] * par.DAIRa * par.EFIa * par.EDa / par.BWa / par.ATnc
            )
        state["CR_iiv1"] = (
            state["IIVER_ca1"]
            * concentration.lower_soil_concentration
            * self._sfi(par, pollutant)
        )
        state["HQ_iiv1"] = self._safe_div(
            state["IIVER_nc1"] * concentration.lower_soil_concentration,
            self._rfdi(par, pollutant) * pollutant.saf,
        )

    def _build_summaries(
        self, par, pollutant, concentration, state, pollutant_name: str
    ) -> dict[str, Decimal]:
        """汇总各路径结果，并反推控制值。

        到这里时，各条单一路径的暴露量/风险已经写入 state。
        这里再完成三件事：
        1. 土壤相关路径的总风险与贡献率
        2. 地下水相关路径的总风险与贡献率
        3. 土壤/地下水风险控制值
        """
        result = dict(state)

        # 土壤相关路径总致癌风险与贡献率。
        result["CR_sn"] = (
            result["CR_ois"]
            + result["CR_dcs"]
            + result["CR_pis"]
            + result["CR_iov1"]
            + result["CR_iov2"]
            + result["CR_iiv1"]
        )
        result["PCR_ois"] = self._safe_div(result["CR_ois"], result["CR_sn"])
        result["PCR_dcs"] = self._safe_div(result["CR_dcs"], result["CR_sn"])
        result["PCR_pis"] = self._safe_div(result["CR_pis"], result["CR_sn"])
        result["PCR_iov1"] = self._safe_div(result["CR_iov1"], result["CR_sn"])
        result["PCR_iov2"] = self._safe_div(result["CR_iov2"], result["CR_sn"])
        result["PCR_iiv1"] = self._safe_div(result["CR_iiv1"], result["CR_sn"])
        result["PCR_sn"] = (
            result["PCR_ois"]
            + result["PCR_dcs"]
            + result["PCR_pis"]
            + result["PCR_iov1"]
            + result["PCR_iov2"]
            + result["PCR_iiv1"]
        )

        result["HI_sn"] = (
            result["HQ_ois"]
            + result["HQ_dcs"]
            + result["HQ_pis"]
            + result["HQ_iov1"]
            + result["HQ_iov2"]
            + result["HQ_iiv1"]
        )
        result["PHQ_ois"] = self._safe_div(result["HQ_ois"], result["HI_sn"])
        result["PHQ_dcs"] = self._safe_div(result["HQ_dcs"], result["HI_sn"])
        result["PHQ_pis"] = self._safe_div(result["HQ_pis"], result["HI_sn"])
        result["PHQ_iov1"] = self._safe_div(result["HQ_iov1"], result["HI_sn"])
        result["PHQ_iov2"] = self._safe_div(result["HQ_iov2"], result["HI_sn"])
        result["PHQ_iiv1"] = self._safe_div(result["HQ_iiv1"], result["HI_sn"])
        result["PHI_sn"] = (
            result["PHQ_ois"]
            + result["PHQ_dcs"]
            + result["PHQ_pis"]
            + result["PHQ_iov1"]
            + result["PHQ_iov2"]
            + result["PHQ_iiv1"]
        )

        # 地下水相关路径总致癌风险与贡献率。
        result["CR_wn"] = (
            result["CR_iov3"] + result["CR_iiv2"] + result["CR_dgw"] + result["CR_cgw"]
        )
        result["PCR_iov3"] = self._safe_div(result["CR_iov3"], result["CR_wn"])
        result["PCR_iiv2"] = self._safe_div(result["CR_iiv2"], result["CR_wn"])
        result["PCR_dgw"] = self._safe_div(result["CR_dgw"], result["CR_wn"])
        result["PCR_cgw"] = self._safe_div(result["CR_cgw"], result["CR_wn"])
        result["PCR_wn"] = (
            result["PCR_iov3"]
            + result["PCR_iiv2"]
            + result["PCR_dgw"]
            + result["PCR_cgw"]
        )

        result["HI_wn"] = (
            result["HQ_iov3"] + result["HQ_iiv2"] + result["HQ_dgw"] + result["HQ_cgw"]
        )
        result["PHQ_iov3"] = self._safe_div(result["HQ_iov3"], result["HI_wn"])
        result["PHQ_iiv2"] = self._safe_div(result["HQ_iiv2"], result["HI_wn"])
        result["PHQ_dgw"] = self._safe_div(result["HQ_dgw"], result["HI_wn"])
        result["PHQ_cgw"] = self._safe_div(result["HQ_cgw"], result["HI_wn"])
        result["PHI_wn"] = (
            result["PHQ_iov3"]
            + result["PHQ_iiv2"]
            + result["PHQ_dgw"]
            + result["PHQ_cgw"]
        )

        # 反推土壤风险控制值。
        sfd = self._sfd(pollutant)
        sfi = self._sfi(par, pollutant)
        result["RCVS_n"] = self._safe_div(
            par.ACR,
            result["OISER_ca"] * pollutant.sfo
            + result["DCSER_ca"] * sfd
            + (
                result["PISER_ca"]
                + result["IOVER_ca1"]
                + result["IOVER_ca2"]
                + result["IIVER_ca1"]
            )
            * sfi,
        )
        rfdd = self._rfdd(pollutant)
        rfdi = self._rfdi(par, pollutant)
        rfdo = self._safe_div(result["OISER_nc"], pollutant.rfdo)
        rfdd_part = self._safe_div(result["DCSER_nc"], rfdd)
        rfdi_part = self._safe_div(
            result["PISER_nc"]
            + result["IOVER_nc1"]
            + result["IOVER_nc2"]
            + result["IIVER_nc1"],
            rfdi,
        )
        result["HCVS_n"] = self._safe_div(
            pollutant.saf * par.AHQ, rfdo + rfdd_part + rfdi_part
        )

        # 保护地下水的土壤控制值，需要重新计算土壤到地下水的稀释/迁移因子。
        theta = to_decimal(1) - self._safe_div(par.Rho_b, par.Rho_s)
        theta_ws = par.Rho_b * par.Pws
        theta_as = theta - theta_ws
        f_oc = par.fom / self.dianqi / 1000
        if pollutant_name == "汞（无机）":
            k_d = Decimal("52")
        elif pollutant_name == "氰化物":
            k_d = Decimal("9.9")
        elif pollutant_name == "次氯酸钠":
            k_d = Decimal("{:.3e}".format(10 ** (-0.207608310501746)))
        elif pollutant_name == "铀（可溶性盐）":
            k_d = Decimal("{:.3e}".format(10**3.47))
        else:
            k_d = pollutant.koc * f_oc
        k_sw = self._safe_div(
            theta_ws + k_d * par.Rho_b + pollutant.henry * theta_as, par.Rho_b
        )
        lf_sgw_gw = self._safe_div(
            1, 1 + self._safe_div(par.Ugw * par.Delta_gw, par.I * par.W)
        )
        lf_sgw1 = self._safe_div(lf_sgw_gw, k_sw)
        lf_sgw2 = self._safe_div(par.dsub * par.Rho_b, par.I * par.Tau)
        lf_sgw = self._safe_min(lf_sgw1, lf_sgw2)
        result["CVS_pgw"] = self._safe_div(
            concentration.groundwater_protection_concentration, lf_sgw
        )

        result["RCVG_n"] = self._safe_div(
            par.ACR,
            (result["IOVER_ca3"] + result["IIVER_ca2"]) * sfi
            + result["CGWER_ca"] * pollutant.sfo
            + result["DGWER_ca"] * sfd,
        )
        rfdi_part2 = self._safe_div(result["IOVER_nc3"] + result["IIVER_nc2"], rfdi)
        rfdo_part2 = self._safe_div(result["CGWER_nc"], pollutant.rfdo)
        rfdd_part2 = self._safe_div(result["DGWER_nc"], rfdd)
        result["HCVG_n"] = self._safe_div(
            par.AHQ * pollutant.saf, rfdi_part2 + rfdo_part2 + rfdd_part2
        )
        return result

    def _pick(self, source: dict[str, Decimal], *keys: str) -> dict[str, Decimal]:
        """从总状态表中挑出某张结果表需要的字段。"""
        return {key: source.get(key, ZERO) for key in keys}
