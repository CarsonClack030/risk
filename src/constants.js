export const PATHWAYS = [
  { key: "ois", label: "口摄入土壤颗粒物" },
  { key: "dcs", label: "皮肤接触土壤颗粒物" },
  { key: "pis", label: "吸入土壤颗粒物" },
  { key: "iov1", label: "吸入室外空气中来自表层土壤的气态污染物" },
  { key: "iov2", label: "吸入室外空气中来自下层土壤的气态污染物" },
  { key: "iiv1", label: "吸入室内空气中来自下层土壤的气态污染物" },
  { key: "iov3", label: "吸入室外空气中来自地下水的气态污染物" },
  { key: "iiv2", label: "吸入室内空气中来自地下水的气态污染物" },
  { key: "dgw", label: "皮肤接触地下水" },
  { key: "cgw", label: "饮用地下水" },
];

export const CATALOG_HEADERS = [
  "编号",
  "污染物名称",
  "英文名",
  "Henry",
  "Da",
  "Dw",
  "Koc",
  "S",
  "SFo",
  "IUR",
  "RfDo",
  "RfC",
  "ABSgi",
  "ABSd",
  "SAF",
  "Kp",
];

export const CATALOG_PICKER_HEADERS = ["编号", "污染物名称", "英文名"];

export const WORKSPACE_HEADERS = [
  "序号",
  "污染物编号",
  "污染物名称",
  "英文名",
  "地表浓度",
  "下层土壤浓度",
  "地下水浓度",
  "地下水保护浓度",
];

export const POLLUTANT_FORM_FIELDS = [
  { key: "name", label: "污染物名称" },
  { key: "english_name", label: "污染物英文名" },
  { key: "henry", label: "Henry" },
  { key: "da", label: "Da" },
  { key: "dw", label: "Dw" },
  { key: "koc", label: "Koc" },
  { key: "solubility", label: "S" },
  { key: "sfo", label: "SFo" },
  { key: "iur", label: "IUR" },
  { key: "rfdo", label: "RfDo" },
  { key: "rfc", label: "RfC" },
  { key: "absgi", label: "ABSgi" },
  { key: "absd", label: "ABSd" },
  { key: "saf", label: "SAF" },
  { key: "kp", label: "Kp" },
];

export const PARAMETER_COLUMNS = [
  { key: "data_gi", label: "国家一类用地" },
  { key: "data_gii", label: "国家二类用地" },
  { key: "data_zi", label: "浙江一类用地" },
  { key: "data_zii", label: "浙江二类用地" },
];
