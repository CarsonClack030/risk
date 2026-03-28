// 这个文件专门存放“纯配置型数据”。
// 把这些常量集中管理有两个好处：
// 1. 界面渲染时不会把业务词典散落在各个组件里。
// 2. 后续如果要改显示名称、列顺序、表头文字，只需要在这里改一次。

// 暴露途径的 key 会直接和后端的计算标志对应。
// label 则是界面上给用户展示的中文说明。
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

// 管理员窗口里展示完整污染物库时使用的表头。
// 这里保留了全部参数列，方便教学时理解污染物数据库到底存了哪些字段。
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

// 主界面挑选污染物时只保留最核心的三列，避免用户被大量理化参数干扰。
export const CATALOG_PICKER_HEADERS = ["编号", "污染物名称", "英文名"];

// 工作区是“已经参与本次计算”的污染物列表。
// 这里的列会同时服务于浓度编辑、工作区浏览以及结果定位。
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

// 管理员维护污染物时的表单字段定义。
// key 对应后端接口字段，label 对应界面中文名称。
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

// 参数设置弹窗中的四类标准列。
// 这些 key 会直接映射到数据库参数表字段名。
export const PARAMETER_COLUMNS = [
  { key: "data_gi", label: "国家一类用地" },
  { key: "data_gii", label: "国家二类用地" },
  { key: "data_zi", label: "浙江一类用地" },
  { key: "data_zii", label: "浙江二类用地" },
];
