import test from "node:test";
import assert from "node:assert/strict";
import { checkForUpdates, isTrustedReleaseUrl } from "./updateService.js";

function giteeResponse(status, body = []) {
  return {
    status,
    ok: status >= 200 && status < 300,
    json: async () => body,
  };
}

test("Gitee 404 会被识别为暂无可读取的正式版本", async () => {
  let requestedUrl = "";
  let requestedOptions = null;
  const result = await checkForUpdates("0.1.0", async (url, options) => {
    requestedUrl = url;
    requestedOptions = options;
    return giteeResponse(404);
  });

  assert.equal(result.status, "unavailable");
  assert.match(
    requestedUrl,
    /^https:\/\/gitee\.com\/api\/v5\/repos\/CarsonClack030\/risk\/releases\?/,
  );
  assert.equal(requestedOptions.headers.Accept, "application/json");
});

test("更高的 Gitee Release 会触发更新确认", async () => {
  const result = await checkForUpdates("0.1.0", async () =>
    giteeResponse(200, [
      {
        tag_name: "v0.2.0",
        name: "Risk Studio 0.2.0",
        body: "更新说明",
        created_at: "2026-07-14T00:00:00+08:00",
        prerelease: false,
      },
    ]),
  );

  assert.equal(result.status, "available");
  assert.equal(result.latestVersion, "0.2.0");
  assert.equal(result.releaseName, "Risk Studio 0.2.0");
});

test("相同版本不会重复提示下载", async () => {
  const result = await checkForUpdates("0.1.0", async () =>
    giteeResponse(200, [{ tag_name: "v0.1.0", prerelease: false }]),
  );
  assert.equal(result.status, "current");
});

test("更新下载地址统一重建为当前仓库的可信地址", async () => {
  const result = await checkForUpdates("0.1.0", async () =>
    giteeResponse(200, [
      {
        tag_name: "v0.2.0",
        html_url: "https://attacker.example/download",
        prerelease: false,
      },
    ]),
  );

  assert.equal(result.releaseUrl, "https://gitee.com/CarsonClack030/risk/releases/tag/v0.2.0");
});

test("检查更新时跳过 Gitee 预发布版本", async () => {
  const result = await checkForUpdates("0.1.0", async () =>
    giteeResponse(200, [
      { tag_name: "v0.3.0-beta.1", prerelease: true },
      { tag_name: "v0.2.0", prerelease: false },
    ]),
  );

  assert.equal(result.status, "available");
  assert.equal(result.latestVersion, "0.2.0");
});

test("没有正式版本时返回暂无可用更新", async () => {
  const result = await checkForUpdates("0.1.0", async () =>
    giteeResponse(200, [{ tag_name: "v0.2.0-beta.1", prerelease: true }]),
  );

  assert.equal(result.status, "unavailable");
});

test("下载地址只信任当前 Gitee 仓库的版本页面", () => {
  assert.equal(
    isTrustedReleaseUrl("https://gitee.com/carsonclack030/risk/releases/tag/v1.1.4"),
    true,
  );
  assert.equal(
    isTrustedReleaseUrl("https://github.com/CarsonClack030/risk/releases/tag/v1.1.4"),
    false,
  );
  assert.equal(isTrustedReleaseUrl("https://gitee.com/attacker/risk/releases/tag/v1.1.4"), false);
  assert.equal(
    isTrustedReleaseUrl("https://gitee.com/CarsonClack030/risk/releases-evil/tag/v1.1.4"),
    false,
  );
  assert.equal(
    isTrustedReleaseUrl("https://gitee.com/CarsonClack030/risk/releases/download/v1.1.4/file.exe"),
    false,
  );
});
