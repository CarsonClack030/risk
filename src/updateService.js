import { getVersion } from "@tauri-apps/api/app";
import { openUrl } from "@tauri-apps/plugin-opener";
import packageMetadata from "../package.json" with { type: "json" };
import { isTauriRuntime } from "./fileTransfers.js";
import { compareVersions } from "./versioning.js";

export const PACKAGE_VERSION = packageMetadata.version;
const GITHUB_REPOSITORY = "CarsonClack030/risk";
const GITHUB_LATEST_RELEASE_API =
  `https://api.github.com/repos/${GITHUB_REPOSITORY}/releases/latest`;
const TRUSTED_REPOSITORIES = new Set([
  GITHUB_REPOSITORY.toLowerCase(),
  "wangminglei030/risk",
]);

function canonicalReleaseUrl(tagName) {
  const encodedTag = encodeURIComponent(String(tagName || "").trim());
  return `https://github.com/${GITHUB_REPOSITORY}/releases/tag/${encodedTag}`;
}

// GitHub 用户名大小写不敏感，并且仓库迁移后旧用户名仍可能出现在缓存链接中。
// 这里按路径段精确判断仓库和 releases，避免简单 startsWith 放过伪造前缀。
export function isTrustedReleaseUrl(releaseUrl) {
  try {
    const url = new URL(releaseUrl);
    const segments = url.pathname.split("/").filter(Boolean);
    const repository = `${segments[0] || ""}/${segments[1] || ""}`.toLowerCase();
    return (
      url.protocol === "https:" &&
      url.hostname.toLowerCase() === "github.com" &&
      TRUSTED_REPOSITORIES.has(repository) &&
      segments[2]?.toLowerCase() === "releases"
    );
  } catch {
    return false;
  }
}

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
    // 下载页只由固定仓库地址和 GitHub 返回的 tag 组成，避免用户名迁移或大小写差异误报。
    releaseUrl: canonicalReleaseUrl(release.tag_name),
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
  if (!isTrustedReleaseUrl(releaseUrl)) {
    throw new Error("更新下载地址不是受信任的 GitHub Release 页面。");
  }
  const url = new URL(releaseUrl);

  if (isTauriRuntime()) {
    await openUrl(url.toString());
    return;
  }
  window.open(url.toString(), "_blank", "noopener,noreferrer");
}
