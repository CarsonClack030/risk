import test from "node:test";
import assert from "node:assert/strict";
import { checkForUpdates, isTrustedReleaseUrl } from "./updateService.js";

function githubResponse(status, body = {}) {
  return {
    status,
    ok: status >= 200 && status < 300,
    json: async () => body,
  };
}

test("GitHub 404 会被识别为暂无可读取的正式版本", async () => {
  const result = await checkForUpdates("0.1.0", async () => githubResponse(404));
  assert.equal(result.status, "unavailable");
});

test("更高的 GitHub Release 会触发更新确认", async () => {
  const result = await checkForUpdates("0.1.0", async () =>
    githubResponse(200, {
      tag_name: "v0.2.0",
      name: "Risk Studio 0.2.0",
      body: "更新说明",
      html_url: "https://github.com/CarsonClack030/risk/releases/tag/v0.2.0",
      published_at: "2026-07-14T00:00:00Z",
    }),
  );

  assert.equal(result.status, "available");
  assert.equal(result.latestVersion, "0.2.0");
  assert.equal(result.releaseName, "Risk Studio 0.2.0");
});

test("相同版本不会重复提示下载", async () => {
  const result = await checkForUpdates("0.1.0", async () =>
    githubResponse(200, {
      tag_name: "v0.1.0",
      html_url: "https://github.com/CarsonClack030/risk/releases/tag/v0.1.0",
    }),
  );
  assert.equal(result.status, "current");
});

test("更新下载地址统一重建为当前仓库的可信地址", async () => {
  const result = await checkForUpdates("0.1.0", async () =>
    githubResponse(200, {
      tag_name: "v0.2.0",
      html_url: "https://github.com/wangminglei030/risk/releases/tag/v0.2.0",
    }),
  );

  assert.equal(
    result.releaseUrl,
    "https://github.com/CarsonClack030/risk/releases/tag/v0.2.0",
  );
});

test("下载地址校验兼容用户名大小写和旧仓库别名", () => {
  assert.equal(
    isTrustedReleaseUrl("https://github.com/carsonclack030/risk/releases/tag/v1.1.1"),
    true,
  );
  assert.equal(
    isTrustedReleaseUrl("https://github.com/wangminglei030/risk/releases/tag/v1.1.1"),
    true,
  );
  assert.equal(
    isTrustedReleaseUrl("https://github.com/attacker/risk/releases/tag/v1.1.1"),
    false,
  );
  assert.equal(
    isTrustedReleaseUrl("https://github.com/CarsonClack030/risk/releases-evil/tag/v1.1.1"),
    false,
  );
});
