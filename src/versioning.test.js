import test from "node:test";
import assert from "node:assert/strict";
import { compareVersions } from "./versioning.js";

test("版本比较支持 v 前缀和缺省补零", () => {
  assert.equal(compareVersions("v0.1.0", "0.1"), 0);
  assert.equal(compareVersions("0.1.0", "0.1.1"), -1);
  assert.equal(compareVersions("1.2.0", "1.1.9"), 1);
});

test("正式版本高于同版本号的预发布版本", () => {
  assert.equal(compareVersions("1.0.0-beta.2", "1.0.0-beta.10"), -1);
  assert.equal(compareVersions("1.0.0", "1.0.0-rc.1"), 1);
});

test("非法版本号会给出明确错误", () => {
  assert.throws(() => compareVersions("开发版", "1.0.0"), /无法识别版本号/);
});
