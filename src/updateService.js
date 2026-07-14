import { getVersion } from "@tauri-apps/api/app";
import { openUrl } from "@tauri-apps/plugin-opener";
import packageMetadata from "../package.json" with { type: "json" };
import { isTauriRuntime } from "./fileTransfers.js";
import { compareVersions } from "./versioning.js";

export const PACKAGE_VERSION = packageMetadata.version;
const GITHUB_LATEST_RELEASE_API =
  "https://api.github.com/repos/wangminglei030/risk/releases/latest";
const GITHUB_RELEASES_PATH = "/wangminglei030/risk/releases";

// 打包后的桌面应用从 Tauri 配置读取真实版本号。
// 纯浏览器联调没有 Tauri API，因此回退到当前项目版本。
export async function getCurrentAppVersion() {
  if (!isTauriRuntime()) {
    return PACKAGE_VERSION;
  }
  try {
    return await getVersion();
  } catch {
    return PACKAGE_VERSION;
  }
}

// GitHub 的 latest Release 接口只返回正式发布版本，不会把草稿和预发布版
// 错当成普通用户应该安装的稳定更新。
export async function checkForUpdates(currentVersion, request = fetch) {
  let response;
  try {
    response = await request(GITHUB_LATEST_RELEASE_API, {
      headers: {
        Accept: "application/vnd.github+json",
      },
    });
  } catch {
    throw new Error("无法连接 GitHub，请检查网络后重试。");
  }

  if (response.status === 404) {
    return {
      status: "unavailable",
      currentVersion,
    };
  }
  if (response.status === 403) {
    throw new Error("GitHub 暂时拒绝了更新查询，请稍后再试。");
  }
  if (!response.ok) {
    throw new Error(`检查更新失败，GitHub 返回状态码 ${response.status}。`);
  }

  const release = await response.json();
  const latestVersion = String(release.tag_name || "").replace(/^v/i, "");
  const comparison = compareVersions(currentVersion, latestVersion);
  const common = {
    currentVersion,
    latestVersion,
    releaseName: release.name || `v${latestVersion}`,
    releaseNotes: String(release.body || "").trim(),
    releaseUrl: release.html_url,
    publishedAt: release.published_at || "",
  };

  if (comparison < 0) {
    return { status: "available", ...common };
  }
  if (comparison > 0) {
    return { status: "ahead", ...common };
  }
  return { status: "current", ...common };
}

// 外部地址在调用 Tauri 插件前再校验一次，只允许打开本仓库的 Release 页面。
export async function openReleasePage(releaseUrl) {
  const url = new URL(releaseUrl);
  if (url.origin !== "https://github.com" || !url.pathname.startsWith(GITHUB_RELEASES_PATH)) {
    throw new Error("更新下载地址不是受信任的 GitHub Release 页面。");
  }

  if (isTauriRuntime()) {
    await openUrl(url.toString());
    return;
  }
  window.open(url.toString(), "_blank", "noopener,noreferrer");
}
