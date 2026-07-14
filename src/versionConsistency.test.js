import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import packageMetadata from "../package.json" with { type: "json" };

// 发布版本同时存在于 JavaScript、Tauri 和 Rust 配置中。
// 这条测试可防止升级版本时漏改其中一个文件，导致界面与安装包显示不同版本。
test("前端、Tauri 与 Rust 的软件版本保持一致", () => {
  const tauriConfig = JSON.parse(readFileSync(new URL("../src-tauri/tauri.conf.json", import.meta.url)));
  const cargoManifest = readFileSync(new URL("../src-tauri/Cargo.toml", import.meta.url), "utf8");
  const cargoVersion = cargoManifest.match(/^version\s*=\s*"([^"]+)"/m)?.[1];

  assert.equal(tauriConfig.version, packageMetadata.version);
  assert.equal(cargoVersion, packageMetadata.version);
});
