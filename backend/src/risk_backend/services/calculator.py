from __future__ import annotations

import math
from decimal import Decimal
from types import SimpleNamespace

from risk_backend.models.entities import AttributeMap, SelectedPollutant, SiteSelection, ZERO, to_decimal
from risk_backend.repositories.parameters import ParameterRepository


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


class RiskCalculator:
    def __init__(self, parameter_repository: ParameterRepository):
        self.parameter_repository = parameter_repository
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
        parameters = AttributeMap(self.parameter_repository.get_parameter_map(selection))
        return {
            item.workspace_number: self._calculate_single(selection, parameters, item, pathway_flags)
            for item in selected_pollutants
        }

    def _calculate_single(
        self,
        selection: SiteSelection,
        parameters: AttributeMap,
        item: SelectedPollutant,
        pathway_flags: dict[str, bool],
    ) -> dict[str, dict[str, Decimal]]:
        pollutant = item.pollutant
        concentration = item.concentration
        state = self._build_empty_state()

        if pollutant.henry == ZERO:
            self._run_nonvolatile(selection, parameters, pollutant, concentration, state, pathway_flags)
        else:
            gas = self._gaspd(parameters, pollutant, pollutant.name)
            state.update(gas)
            self._run_all_pathways(selection, parameters, pollutant, concentration, state, pathway_flags)

        summary = self._build_summaries(parameters, pollutant, concentration, state, pollutant.name)
        return {
            "db_exposure_ca": self._pick(
                summary,
                "OISER_ca", "DCSER_ca", "PISER_ca", "IOVER_ca1", "IOVER_ca2",
                "IIVER_ca1", "IOVER_ca3", "IIVER_ca2", "DGWER_ca", "CGWER_ca",
            ),
            "db_exposure_nc": self._pick(
                summary,
                "OISER_nc", "DCSER_nc", "PISER_nc", "IOVER_nc1", "IOVER_nc2",
                "IIVER_nc1", "IOVER_nc3", "IIVER_nc2", "DGWER_nc", "CGWER_nc",
            ),
            "db_cr": self._pick(
                summary,
                "CR_ois", "CR_dcs", "CR_pis", "CR_iov1", "CR_iov2", "CR_iiv1",
                "CR_sn", "CR_iov3", "CR_iiv2", "CR_dgw", "CR_cgw", "CR_wn",
            ),
            "db_hq": self._pick(
                summary,
                "HQ_ois", "HQ_dcs", "HQ_pis", "HQ_iov1", "HQ_iov2", "HQ_iiv1",
                "HI_sn", "HQ_iov3", "HQ_iiv2", "HQ_dgw", "HQ_cgw", "HI_wn",
            ),
            "db_pcr": self._pick(
                summary,
                "PCR_ois", "PCR_dcs", "PCR_pis", "PCR_iov1", "PCR_iov2", "PCR_iiv1",
                "PCR_sn", "PCR_iov3", "PCR_iiv2", "PCR_dgw", "PCR_cgw", "PCR_wn",
            ),
            "db_phq": self._pick(
                summary,
                "PHQ_ois", "PHQ_dcs", "PHQ_pis", "PHQ_iov1", "PHQ_iov2", "PHQ_iiv1",
                "PHI_sn", "PHQ_iov3", "PHQ_iiv2", "PHQ_dgw", "PHQ_cgw", "PHI_wn",
            ),
            "db_cv": self._pick(summary, "RCVS_n", "HCVS_n", "RCVG_n", "HCVG_n", "CVS_pgw"),
        }

    def _build_empty_state(self) -> dict[str, Decimal]:
        columns = [
            "OISER_ca", "OISER_nc", "CR_ois", "HQ_ois",
            "DCSER_ca", "DCSER_nc", "CR_dcs", "HQ_dcs",
            "PISER_ca", "PISER_nc", "CR_pis", "HQ_pis",
            "DGWER_ca", "DGWER_nc", "CR_dgw", "HQ_dgw",
            "CGWER_ca", "CGWER_nc", "CR_cgw", "HQ_cgw",
            "IOVER_ca1", "IOVER_nc1", "CR_iov1", "HQ_iov1",
            "IOVER_ca2", "IOVER_nc2", "CR_iov2", "HQ_iov2",
            "IIVER_ca1", "IIVER_nc1", "CR_iiv1", "HQ_iiv1",
            "IOVER_ca3", "IOVER_nc3", "CR_iov3", "HQ_iov3",
            "IIVER_ca2", "IIVER_nc2", "CR_iiv2", "HQ_iiv2",
            "VF_subia", "VF_suboa", "VF_suroa", "VF_gwia", "VF_gwoa",
            "Theta", "Theta_ws", "Theta_as", "D_eff_s", "D_eff_cap", "D_eff_gws",
            "D_eff_crack", "f_oc", "K_d", "K_sw", "DF_oa", "DF_ia", "Q_s",
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
        for key in ("ois", "dcs", "pis", "dgw", "cgw"):
            if pathways.get(key):
                getattr(self, f"_calc_{key}")(selection, par, pollutant, concentration, state)

    def _run_all_pathways(
        self,
        selection: SiteSelection,
        par: AttributeMap,
        pollutant,
        concentration,
        state: dict[str, Decimal],
        pathways: dict[str, bool],
    ) -> None:
        for key in PATHWAY_FLAGS:
            if pathways.get(key):
                getattr(self, f"_calc_{key}")(selection, par, pollutant, concentration, state)

    def _first_type(self, selection: SiteSelection) -> bool:
        return selection.area_type == "I"

    def _safe_div(self, numerator: Decimal, denominator: Decimal) -> Decimal:
        try:
            if denominator == ZERO:
                return ZERO
            return numerator / denominator
        except Exception:
            return ZERO

    def _safe_min(self, left: Decimal, right: Decimal) -> Decimal:
        try:
            return min(left, right)
        except Exception:
            return ZERO

    def _ln(self, value: Decimal) -> Decimal:
        try:
            return value.ln()
        except Exception:
            try:
                return Decimal(str(math.log(float(value))))
            except Exception:
                return ZERO

    def _pow_e(self, value: Decimal) -> Decimal:
        try:
            return Decimal(str(math.e ** float(value)))
        except Exception:
            return ZERO

    def _sfd(self, pollutant) -> Decimal:
        return self._safe_div(pollutant.sfo, pollutant.absgi)

    def _rfdd(self, pollutant) -> Decimal:
        return pollutant.rfdo * pollutant.absgi

    def _sfi(self, par: AttributeMap, pollutant) -> Decimal:
        return pollutant.iur * self._safe_div(par.BWa, par.DAIRa)

    def _rfdi(self, par: AttributeMap, pollutant) -> Decimal:
        return pollutant.rfc * self._safe_div(par.DAIRa, par.BWa)

    def _calc_ois(self, selection, par, pollutant, concentration, state):
        if self._first_type(selection):
            state["OISER_ca"] = (
                (par.OSIRc * par.EDc * par.EFc / par.BWc) +
                (par.OSIRa * par.EDa * par.EFa / par.BWa)
            ) * par.ABSo / par.ATca * self.dianliu
            state["OISER_nc"] = (
                par.OSIRc * par.EDc * par.EFc * par.ABSo / par.BWc / par.ATnc * self.dianliu
            )
        else:
            state["OISER_ca"] = par.OSIRa * par.EDa * par.EFa / par.BWa * par.ABSo / par.ATca * self.dianliu
            state["OISER_nc"] = par.OSIRa * par.EDa * par.EFa / par.BWa * par.ABSo / par.ATnc * self.dianliu
        state["CR_ois"] = state["OISER_ca"] * concentration.surface_concentration * pollutant.sfo
        state["HQ_ois"] = self._safe_div(
            state["OISER_nc"] * concentration.surface_concentration,
            pollutant.rfdo * pollutant.saf,
        )

    def _calc_dcs(self, selection, par, pollutant, concentration, state):
        if self._first_type(selection):
            state["DCSER_ca"] = (
                par.SAEc * par.SSARc * par.EFc * par.EDc * par.Ev * pollutant.absd * self.dianliu / par.BWc / par.ATca
                + par.SAEa * par.SSARa * par.EFa * par.EDa * par.Ev * pollutant.absd * self.dianliu / par.BWa / par.ATca
            )
            state["DCSER_nc"] = (
                par.SAEc * par.SSARc * par.EFc * par.EDc * par.Ev * pollutant.absd * self.dianliu / par.BWc / par.ATnc
            )
        else:
            state["DCSER_ca"] = (
                par.SAEa * par.SSARa * par.EFa * par.EDa * par.Ev * pollutant.absd * self.dianliu / par.BWa / par.ATca
            )
            state["DCSER_nc"] = (
                par.SAEa * par.SSARa * par.EFa * par.EDa * par.Ev * pollutant.absd * self.dianliu / par.BWa / par.ATnc
            )
        state["CR_dcs"] = state["DCSER_ca"] * concentration.surface_concentration * self._sfd(pollutant)
        state["HQ_dcs"] = self._safe_div(
            state["DCSER_nc"] * concentration.surface_concentration,
            self._rfdd(pollutant) * pollutant.saf,
        )

    def _calc_pis(self, selection, par, pollutant, concentration, state):
        if self._first_type(selection):
            state["PISER_ca"] = (
                par.PM10 * par.DAIRc * par.EDc * par.PIAF * (par.fspo * par.EFOc + par.fspi * par.EFIc) * self.dianliu / par.BWc / par.ATca
                + par.PM10 * par.DAIRa * par.EDa * par.PIAF * (par.fspo * par.EFOa + par.fspi * par.EFIa) * self.dianliu / par.BWa / par.ATca
            )
            state["PISER_nc"] = (
                par.PM10 * par.DAIRc * par.EDc * par.PIAF * (par.fspo * par.EFOc + par.fspi * par.EFIc) * self.dianliu / par.BWc / par.ATnc
            )
        else:
            state["PISER_ca"] = (
                par.PM10 * par.DAIRa * par.EDa * par.PIAF * (par.fspo * par.EFOa + par.fspi * par.EFIa) * self.dianliu / par.BWa / par.ATca
            )
            state["PISER_nc"] = (
                par.PM10 * par.DAIRa * par.EDa * par.PIAF * (par.fspo * par.EFOa + par.fspi * par.EFIa) * self.dianliu / par.BWa / par.ATnc
            )
        state["CR_pis"] = state["PISER_ca"] * concentration.surface_concentration * self._sfi(par, pollutant)
        state["HQ_pis"] = self._safe_div(
            state["PISER_nc"] * concentration.surface_concentration,
            self._rfdi(par, pollutant) * pollutant.saf,
        )

    def _calc_dgw(self, selection, par, pollutant, concentration, state):
        daec = pollutant.kp * concentration.groundwater_concentration * par.tc * self.diansan
        daea = pollutant.kp * concentration.groundwater_concentration * par.ta * self.diansan
        if self._first_type(selection):
            state["DGWER_ca"] = (
                par.SAEc * par.EFc * par.EDc * par.Ev * daec * self.dianliu / par.BWc / par.ATca
                + par.SAEa * par.EFa * par.EDa * par.Ev * daea * self.dianliu / par.BWa / par.ATca
            )
            state["DGWER_nc"] = par.SAEc * par.EFc * par.EDc * par.Ev * daec * self.dianliu / par.BWc / par.ATnc
        else:
            state["DGWER_ca"] = par.SAEa * par.EFa * par.EDa * par.Ev * daea * self.dianliu / par.BWa / par.ATca
            state["DGWER_nc"] = par.SAEa * par.EFa * par.EDa * par.Ev * daea * self.dianliu / par.BWa / par.ATnc
        state["CR_dgw"] = state["DGWER_ca"] * self._sfd(pollutant)
        state["HQ_dgw"] = self._safe_div(state["DGWER_nc"], self._rfdd(pollutant))

    def _calc_cgw(self, selection, par, pollutant, concentration, state):
        if self._first_type(selection):
            state["CGWER_ca"] = par.GWCRc * par.EFc * par.EDc / par.BWc / par.ATca + par.GWCRa * par.EFa * par.EDa / par.BWa / par.ATca
            state["CGWER_nc"] = par.GWCRc * par.EFc * par.EDc / par.BWc / par.ATnc
        else:
            state["CGWER_ca"] = par.GWCRa * par.EFa * par.EDa / par.BWa / par.ATca
            state["CGWER_nc"] = par.GWCRa * par.EFa * par.EDa / par.BWa / par.ATnc
        state["CR_cgw"] = state["CGWER_ca"] * concentration.groundwater_concentration * pollutant.sfo
        state["HQ_cgw"] = self._safe_div(
            state["CGWER_nc"] * concentration.groundwater_concentration,
            pollutant.rfdo * pollutant.saf,
        )

    def _gaspd(self, par: AttributeMap, pollutant, pollutant_name: str) -> dict[str, Decimal]:
        gas = self._build_empty_state()
        gas["Theta"] = to_decimal(1) - self._safe_div(par.Rho_b, par.Rho_s)
        gas["Theta_ws"] = par.Rho_b * par.Pws
        gas["Theta_as"] = gas["Theta"] - gas["Theta_ws"]
        gas["D_eff_s"] = (
            self._safe_div(pollutant.da * (gas["Theta_as"] ** self.diansansan), gas["Theta"] ** 2)
            + self._safe_div(pollutant.dw * (gas["Theta_ws"] ** self.diansansan), (gas["Theta"] ** 2) * pollutant.henry)
        )
        gas["D_eff_cap"] = (
            self._safe_div(pollutant.da * (par.Theta_acap ** self.diansansan), (par.Theta_acap + par.Theta_wcap) ** 2)
            + self._safe_div(
                pollutant.dw * (par.Theta_wcap ** self.diansansan),
                ((par.Theta_acap + par.Theta_wcap) ** 2) * pollutant.henry,
            )
        )
        gas["D_eff_gws"] = self._safe_div(par.Lgw, self._safe_div(par.hcap, gas["D_eff_cap"]) + self._safe_div(par.hv, gas["D_eff_s"]))
        gas["D_eff_crack"] = (
            self._safe_div(pollutant.da * (par.Theta_acrack ** self.diansansan), (par.Theta_acrack + par.Theta_wcrack) ** 2)
            + self._safe_div(
                pollutant.dw * (par.Theta_wcrack ** self.diansansan),
                ((par.Theta_acrack + par.Theta_wcrack) ** 2) * pollutant.henry,
            )
        )
        gas["f_oc"] = par.fom / self.dianqi / 1000
        if pollutant_name == "汞（无机）":
            gas["K_d"] = Decimal("52")
        elif pollutant_name == "氰化物":
            gas["K_d"] = Decimal("9.9")
        elif pollutant_name == "次氯酸钠":
            gas["K_d"] = Decimal("{:.3e}".format(10 ** (-0.207608310501746)))
        elif pollutant_name == "铀（可溶性盐）":
            gas["K_d"] = Decimal("{:.3e}".format(10 ** 3.47))
        else:
            gas["K_d"] = pollutant.koc * gas["f_oc"]
        gas["K_sw"] = self._safe_div(gas["Theta_ws"] + gas["K_d"] * par.Rho_b + pollutant.henry * gas["Theta_as"], par.Rho_b)
        gas["DF_oa"] = self._safe_div(par.Uair * par.W * par.Delta_air, par.A)
        gas["DF_ia"] = par.LB * par.ER / 86400
        denominator = self._ln(2 * par.Z_crack * par.X_crack / (par.Ab * par.Eit))
        gas["Q_s"] = self._safe_div(2 * self.pai * par.dP * par.K_v * par.X_crack, self.dianba * denominator)
        xxx = self._safe_div(gas["Q_s"] * par.Lcrack, par.Ab * gas["D_eff_crack"] * par.Eit)
        exp_x = self._pow_e(xxx)
        if par.dsub > 0:
            if gas["Q_s"] == ZERO:
                gas["VF_subia"] = self._safe_div(
                    1000,
                    self._safe_div(gas["K_sw"], pollutant.henry)
                    * (
                        1
                        + self._safe_div(gas["D_eff_s"], gas["DF_ia"] * par.LS)
                        + self._safe_div(gas["D_eff_s"] * par.Lcrack, gas["D_eff_crack"] * par.LS * par.Eit)
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
                        + self._safe_div(gas["D_eff_s"] * par.Ab * (exp_x - 1), gas["Q_s"] * par.LS)
                    )
                    * self._safe_div(gas["DF_ia"] * par.LS, gas["D_eff_s"] * exp_x),
                )
            vf_subia2 = par.dsub * par.Rho_b * 1000 / gas["DF_ia"] / par.Tau / 31536000
            gas["VF_subia"] = self._safe_min(gas["VF_subia"], vf_subia2)
            vf_suboa1 = self._safe_div(1, 1 + self._safe_div(gas["DF_oa"] * par.LS, gas["D_eff_s"])) * self._safe_div(pollutant.henry * 1000, gas["K_sw"])
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
                        + self._safe_div(gas["D_eff_s"] * par.Lcrack, gas["D_eff_crack"] * par.LS * par.Eit)
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
                        + self._safe_div(gas["D_eff_s"] * par.Ab * (exp_x - 1), gas["Q_s"] * par.LS)
                    )
                    * self._safe_div(gas["DF_ia"] * par.LS, gas["D_eff_s"] * exp_x),
                )
            gas["VF_suboa"] = self._safe_div(1, 1 + self._safe_div(gas["DF_oa"] * par.LS, gas["D_eff_s"])) * self._safe_div(pollutant.henry * 1000, gas["K_sw"])

        vf_suroa1 = self._safe_div(
            par.Rho_b,
            gas["DF_oa"],
        ) * (
            self._safe_div(4 * gas["D_eff_s"] * pollutant.henry, self.pai * par.Tau * 31536000 * gas["K_sw"] * par.Rho_b)
        ) ** self.dianwu * 1000
        vf_suroa2 = par.d * par.Rho_b / gas["DF_oa"] / par.Tau / 31536000 * 1000
        gas["VF_suroa"] = self._safe_min(vf_suroa1, vf_suroa2)

        if gas["Q_s"] == ZERO:
            gas["VF_gwia"] = self._safe_div(
                1000 * pollutant.henry * gas["D_eff_gws"],
                (
                    1
                    + self._safe_div(gas["D_eff_gws"], gas["DF_ia"] * par.Lgw)
                    + self._safe_div(gas["D_eff_gws"] * par.Lcrack, gas["D_eff_crack"] * par.Lgw * par.Eit)
                ) * gas["DF_ia"] * par.Lgw,
            )
        else:
            gas["VF_gwia"] = self._safe_div(
                1000 * pollutant.henry * gas["D_eff_gws"] * exp_x,
                (
                    1
                    + self._safe_div(gas["D_eff_gws"], gas["DF_ia"] * par.Lgw)
                    + self._safe_div(gas["D_eff_gws"] * par.Ab * (exp_x - 1), gas["Q_s"] * par.Lgw)
                ) * gas["DF_ia"] * par.Lgw,
            )
        gas["VF_gwoa"] = self._safe_div(1000 * pollutant.henry, 1 + self._safe_div(gas["DF_oa"] * par.Lgw, gas["D_eff_gws"]))
        return gas

    def _calc_iov3(self, selection, par, pollutant, concentration, state):
        if self._first_type(selection):
            state["IOVER_ca3"] = state["VF_gwoa"] * (
                par.DAIRc * par.EFOc * par.EDc / par.BWc / par.ATca
                + par.DAIRa * par.EFOa * par.EDa / par.BWa / par.ATca
            )
            state["IOVER_nc3"] = state["VF_gwoa"] * par.DAIRc * par.EFOc * par.EDc / par.BWc / par.ATnc
        else:
            state["IOVER_ca3"] = state["VF_gwoa"] * par.DAIRa * par.EFOa * par.EDa / par.BWa / par.ATca
            state["IOVER_nc3"] = state["VF_gwoa"] * par.DAIRa * par.EFOa * par.EDa / par.BWa / par.ATnc
        state["CR_iov3"] = state["IOVER_ca3"] * concentration.groundwater_concentration * self._sfi(par, pollutant)
        state["HQ_iov3"] = self._safe_div(
            state["IOVER_nc3"] * concentration.groundwater_concentration,
            self._rfdi(par, pollutant) * pollutant.saf,
        )

    def _calc_iiv2(self, selection, par, pollutant, concentration, state):
        if self._first_type(selection):
            state["IIVER_ca2"] = state["VF_gwia"] * (
                par.DAIRc * par.EFIc * par.EDc / par.BWc / par.ATca
                + par.DAIRa * par.EFIa * par.EDa / par.BWa / par.ATca
            )
            state["IIVER_nc2"] = state["VF_gwia"] * par.DAIRc * par.EFIc * par.EDc / par.BWc / par.ATnc
        else:
            state["IIVER_ca2"] = state["VF_gwia"] * par.DAIRa * par.EFIa * par.EDa / par.BWa / par.ATca
            state["IIVER_nc2"] = state["VF_gwia"] * par.DAIRa * par.EFIa * par.EDa / par.BWa / par.ATnc
        state["CR_iiv2"] = state["IIVER_ca2"] * concentration.groundwater_concentration * self._sfi(par, pollutant)
        state["HQ_iiv2"] = self._safe_div(
            state["IIVER_nc2"] * concentration.groundwater_concentration,
            self._rfdi(par, pollutant) * pollutant.saf,
        )

    def _calc_iov1(self, selection, par, pollutant, concentration, state):
        if self._first_type(selection):
            state["IOVER_ca1"] = state["VF_suroa"] * (
                par.DAIRc * par.EFOc * par.EDc / par.BWc / par.ATca
                + par.DAIRa * par.EFOa * par.EDa / par.BWa / par.ATca
            )
            state["IOVER_nc1"] = state["VF_suroa"] * par.DAIRc * par.EFOc * par.EDc / par.BWc / par.ATnc
        else:
            state["IOVER_ca1"] = state["VF_suroa"] * par.DAIRa * par.EFOa * par.EDa / par.BWa / par.ATca
            state["IOVER_nc1"] = state["VF_suroa"] * par.DAIRa * par.EFOa * par.EDa / par.BWa / par.ATnc
        state["CR_iov1"] = state["IOVER_ca1"] * concentration.surface_concentration * self._sfi(par, pollutant)
        state["HQ_iov1"] = self._safe_div(
            state["IOVER_nc1"] * concentration.surface_concentration,
            self._rfdi(par, pollutant) * pollutant.saf,
        )

    def _calc_iov2(self, selection, par, pollutant, concentration, state):
        if self._first_type(selection):
            state["IOVER_ca2"] = state["VF_suboa"] * (
                par.DAIRc * par.EFOc * par.EDc / par.BWc / par.ATca
                + par.DAIRa * par.EFOa * par.EDa / par.BWa / par.ATca
            )
            state["IOVER_nc2"] = state["VF_suboa"] * par.DAIRc * par.EFOc * par.EDc / par.BWc / par.ATnc
        else:
            state["IOVER_ca2"] = state["VF_suboa"] * par.DAIRa * par.EFOa * par.EDa / par.BWa / par.ATca
            state["IOVER_nc2"] = state["VF_suboa"] * par.DAIRa * par.EFOa * par.EDa / par.BWa / par.ATnc
        state["CR_iov2"] = state["IOVER_ca2"] * concentration.lower_soil_concentration * self._sfi(par, pollutant)
        state["HQ_iov2"] = self._safe_div(
            state["IOVER_nc2"] * concentration.lower_soil_concentration,
            self._rfdi(par, pollutant) * pollutant.saf,
        )

    def _calc_iiv1(self, selection, par, pollutant, concentration, state):
        if self._first_type(selection):
            state["IIVER_ca1"] = state["VF_subia"] * (
                par.DAIRc * par.EFIc * par.EDc / par.BWc / par.ATca
                + par.DAIRa * par.EFIa * par.EDa / par.BWa / par.ATca
            )
            state["IIVER_nc1"] = state["VF_subia"] * par.DAIRc * par.EFIc * par.EDc / par.BWc / par.ATnc
        else:
            state["IIVER_ca1"] = state["VF_subia"] * par.DAIRa * par.EFIa * par.EDa / par.BWa / par.ATca
            state["IIVER_nc1"] = state["VF_subia"] * par.DAIRa * par.EFIa * par.EDa / par.BWa / par.ATnc
        state["CR_iiv1"] = state["IIVER_ca1"] * concentration.lower_soil_concentration * self._sfi(par, pollutant)
        state["HQ_iiv1"] = self._safe_div(
            state["IIVER_nc1"] * concentration.lower_soil_concentration,
            self._rfdi(par, pollutant) * pollutant.saf,
        )

    def _build_summaries(self, par, pollutant, concentration, state, pollutant_name: str) -> dict[str, Decimal]:
        result = dict(state)

        result["CR_sn"] = result["CR_ois"] + result["CR_dcs"] + result["CR_pis"] + result["CR_iov1"] + result["CR_iov2"] + result["CR_iiv1"]
        result["PCR_ois"] = self._safe_div(result["CR_ois"], result["CR_sn"])
        result["PCR_dcs"] = self._safe_div(result["CR_dcs"], result["CR_sn"])
        result["PCR_pis"] = self._safe_div(result["CR_pis"], result["CR_sn"])
        result["PCR_iov1"] = self._safe_div(result["CR_iov1"], result["CR_sn"])
        result["PCR_iov2"] = self._safe_div(result["CR_iov2"], result["CR_sn"])
        result["PCR_iiv1"] = self._safe_div(result["CR_iiv1"], result["CR_sn"])
        result["PCR_sn"] = result["PCR_ois"] + result["PCR_dcs"] + result["PCR_pis"] + result["PCR_iov1"] + result["PCR_iov2"] + result["PCR_iiv1"]

        result["HI_sn"] = result["HQ_ois"] + result["HQ_dcs"] + result["HQ_pis"] + result["HQ_iov1"] + result["HQ_iov2"] + result["HQ_iiv1"]
        result["PHQ_ois"] = self._safe_div(result["HQ_ois"], result["HI_sn"])
        result["PHQ_dcs"] = self._safe_div(result["HQ_dcs"], result["HI_sn"])
        result["PHQ_pis"] = self._safe_div(result["HQ_pis"], result["HI_sn"])
        result["PHQ_iov1"] = self._safe_div(result["HQ_iov1"], result["HI_sn"])
        result["PHQ_iov2"] = self._safe_div(result["HQ_iov2"], result["HI_sn"])
        result["PHQ_iiv1"] = self._safe_div(result["HQ_iiv1"], result["HI_sn"])
        result["PHI_sn"] = result["PHQ_ois"] + result["PHQ_dcs"] + result["PHQ_pis"] + result["PHQ_iov1"] + result["PHQ_iov2"] + result["PHQ_iiv1"]

        result["CR_wn"] = result["CR_iov3"] + result["CR_iiv2"] + result["CR_dgw"] + result["CR_cgw"]
        result["PCR_iov3"] = self._safe_div(result["CR_iov3"], result["CR_wn"])
        result["PCR_iiv2"] = self._safe_div(result["CR_iiv2"], result["CR_wn"])
        result["PCR_dgw"] = self._safe_div(result["CR_dgw"], result["CR_wn"])
        result["PCR_cgw"] = self._safe_div(result["CR_cgw"], result["CR_wn"])
        result["PCR_wn"] = result["PCR_iov3"] + result["PCR_iiv2"] + result["PCR_dgw"] + result["PCR_cgw"]

        result["HI_wn"] = result["HQ_iov3"] + result["HQ_iiv2"] + result["HQ_dgw"] + result["HQ_cgw"]
        result["PHQ_iov3"] = self._safe_div(result["HQ_iov3"], result["HI_wn"])
        result["PHQ_iiv2"] = self._safe_div(result["HQ_iiv2"], result["HI_wn"])
        result["PHQ_dgw"] = self._safe_div(result["HQ_dgw"], result["HI_wn"])
        result["PHQ_cgw"] = self._safe_div(result["HQ_cgw"], result["HI_wn"])
        result["PHI_wn"] = result["PHQ_iov3"] + result["PHQ_iiv2"] + result["PHQ_dgw"] + result["PHQ_cgw"]

        sfd = self._sfd(pollutant)
        sfi = self._sfi(par, pollutant)
        result["RCVS_n"] = self._safe_div(
            par.ACR,
            result["OISER_ca"] * pollutant.sfo
            + result["DCSER_ca"] * sfd
            + (result["PISER_ca"] + result["IOVER_ca1"] + result["IOVER_ca2"] + result["IIVER_ca1"]) * sfi,
        )
        rfdd = self._rfdd(pollutant)
        rfdi = self._rfdi(par, pollutant)
        rfdo = self._safe_div(result["OISER_nc"], pollutant.rfdo)
        rfdd_part = self._safe_div(result["DCSER_nc"], rfdd)
        rfdi_part = self._safe_div(result["PISER_nc"] + result["IOVER_nc1"] + result["IOVER_nc2"] + result["IIVER_nc1"], rfdi)
        result["HCVS_n"] = self._safe_div(pollutant.saf * par.AHQ, rfdo + rfdd_part + rfdi_part)

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
            k_d = Decimal("{:.3e}".format(10 ** 3.47))
        else:
            k_d = pollutant.koc * f_oc
        k_sw = self._safe_div(theta_ws + k_d * par.Rho_b + pollutant.henry * theta_as, par.Rho_b)
        lf_sgw_gw = self._safe_div(1, 1 + self._safe_div(par.Ugw * par.Delta_gw, par.I * par.W))
        lf_sgw1 = self._safe_div(lf_sgw_gw, k_sw)
        lf_sgw2 = self._safe_div(par.dsub * par.Rho_b, par.I * par.Tau)
        lf_sgw = self._safe_min(lf_sgw1, lf_sgw2)
        result["CVS_pgw"] = self._safe_div(concentration.groundwater_protection_concentration, lf_sgw)

        result["RCVG_n"] = self._safe_div(
            par.ACR,
            (result["IOVER_ca3"] + result["IIVER_ca2"]) * sfi
            + result["CGWER_ca"] * pollutant.sfo
            + result["DGWER_ca"] * sfd,
        )
        rfdi_part2 = self._safe_div(result["IOVER_nc3"] + result["IIVER_nc2"], rfdi)
        rfdo_part2 = self._safe_div(result["CGWER_nc"], pollutant.rfdo)
        rfdd_part2 = self._safe_div(result["DGWER_nc"], rfdd)
        result["HCVG_n"] = self._safe_div(par.AHQ * pollutant.saf, rfdi_part2 + rfdo_part2 + rfdd_part2)
        return result

    def _pick(self, source: dict[str, Decimal], *keys: str) -> dict[str, Decimal]:
        return {key: source.get(key, ZERO) for key in keys}
