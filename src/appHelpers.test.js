import test from "node:test";
import assert from "node:assert/strict";

import {
  createEmptyPathways,
  createEmptyPollutantForm,
  normalizeLoadError,
  workspaceRows,
} from "./appHelpers.js";

test("表单和暴露途径工厂每次返回独立对象", () => {
  const firstForm = createEmptyPollutantForm();
  const secondForm = createEmptyPollutantForm();
  firstForm.name = "已修改";

  assert.equal(secondForm.name, "");
  assert.ok(Object.values(createEmptyPathways(true)).every(Boolean));
});

test("工作区表格保留工作区序号和重复污染物编号", () => {
  const concentration = {
    surface_concentration: 1,
    lower_soil_concentration: 2,
    groundwater_concentration: 3,
    groundwater_protection_concentration: 4,
  };
  const rows = workspaceRows([
    {
      workspace_number: 1,
      pollutant: { id: 17, name: "苯", english_name: "Benzene" },
      concentration,
    },
    {
      workspace_number: 2,
      pollutant: { id: 17, name: "苯", english_name: "Benzene" },
      concentration,
    },
  ]);

  assert.deepEqual(
    rows.map((row) => row.key),
    [1, 2],
  );
  assert.deepEqual(
    rows.map((row) => row.cells.slice(0, 2)),
    [
      [1, 17],
      [2, 17],
    ],
  );
});

test("后端连接失败会转换成可读提示", () => {
  assert.equal(
    normalizeLoadError(new TypeError("Load failed")).message,
    "后端启动稍慢或连接暂时失败，请稍后再试一次。",
  );
});
