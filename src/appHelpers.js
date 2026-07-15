import { PATHWAYS } from "./constants.js";

export const CATALOG_DISPLAY_LIMIT = 20;
export const CATALOG_SUGGESTION_LIMIT = 8;

export function cloneData(value) {
  return typeof structuredClone === "function"
    ? structuredClone(value)
    : JSON.parse(JSON.stringify(value));
}

export function createEmptyPollutantForm() {
  return {
    name: "",
    english_name: "",
    henry: 0,
    da: 0,
    dw: 0,
    koc: 0,
    solubility: 0,
    sfo: 0,
    iur: 0,
    rfdo: 0,
    rfc: 0,
    absgi: 0,
    absd: 0,
    saf: 1,
    kp: 0,
  };
}

export function createEmptyPathways(selected = false) {
  return Object.fromEntries(PATHWAYS.map(({ key }) => [key, selected]));
}

export function countSelectedPathways(pathways) {
  return PATHWAYS.filter(({ key }) => pathways[key]).length;
}

export function normalizeLoadError(error) {
  if (error?.message === "Load failed") {
    return new Error("后端启动稍慢或连接暂时失败，请稍后再试一次。");
  }
  return error instanceof Error ? error : new Error(String(error));
}

export function pollutantToAdminForm(pollutant) {
  return Object.fromEntries(
    Object.keys(createEmptyPollutantForm()).map((key) => [key, pollutant[key]]),
  );
}

export function workspaceToConcentrationDraft(items) {
  return items.map(({ workspace_number, concentration }) => ({
    workspace_number,
    pollutant_id: concentration.pollutant_id,
    name: concentration.name,
    english_name: concentration.english_name,
    surface_concentration: concentration.surface_concentration,
    lower_soil_concentration: concentration.lower_soil_concentration,
    groundwater_concentration: concentration.groundwater_concentration,
    groundwater_protection_concentration: concentration.groundwater_protection_concentration,
  }));
}

export function catalogRows(items) {
  return items.map((item) => ({
    key: item.id,
    cells: [item.id, item.name, item.english_name],
  }));
}

export function workspaceRows(items) {
  return items.map((item) => ({
    key: item.workspace_number,
    cells: [
      item.workspace_number,
      item.pollutant.id,
      item.pollutant.name,
      item.pollutant.english_name,
      item.concentration.surface_concentration,
      item.concentration.lower_soil_concentration,
      item.concentration.groundwater_concentration,
      item.concentration.groundwater_protection_concentration,
    ],
  }));
}

export function adminRows(items) {
  return items.map((item) => ({
    key: item.id,
    cells: [
      item.id,
      item.name,
      item.english_name,
      item.henry,
      item.da,
      item.dw,
      item.koc,
      item.solubility,
      item.sfo,
      item.iur,
      item.rfdo,
      item.rfc,
      item.absgi,
      item.absd,
      item.saf,
      item.kp,
    ],
  }));
}
