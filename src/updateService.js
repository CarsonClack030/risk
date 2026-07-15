import { getVersion } from "@tauri-apps/api/app";
import { openUrl } from "@tauri-apps/plugin-opener";
import packageMetadata from "../package.json" with { type: "json" };
import { isTauriRuntime } from "./runtime.js";
import { compareVersions } from "./versioning.js";

export const PACKAGE_VERSION = packageMetadata.version;
const GITEE_REPOSITORY = "CarsonClack030/risk";
const GITEE_RELEASES_API = `https://gitee.com/api/v5/repos/${GITEE_REPOSITORY}/releases?page=1&per_page=20&direction=desc`;

function canonicalReleaseUrl(tagName) {
  const encodedTag = encodeURIComponent(String(tagName || "").trim());
  return `https://gitee.com/${GITEE_REPOSITORY}/releases/tag/${encodedTag}`;
}

// 按主机名和每个路径段精确判断下载页，避免 startsWith 放过相似域名或伪造前缀。
export function isTrustedReleaseUrl(releaseUrl) {
  try {
    const url = new URL(releaseUrl);
    const segments = url.pathname.split("/").filter(Boolean);
    const repository = `${segments[0] || ""}/${segments[1] || ""}`.toLowerCase();
    return (
      url.protocol === "https:" &&
      url.hostname.toLowerCase() === "gitee.com" &&
      repository === GITEE_REPOSITORY.toLowerCase() &&
      segments[2]?.toLowerCase() === "releases" &&
      segments[3]?.toLowerCase() === "tag" &&
      Boolean(segments[4]) &&
      segments.length === 5
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

// Gitee 的 Release 列表可能同时包含正式版和预发布版，因此客户端主动选择
// 第一条正式版本，避免测试版本被普通用户误装。
export async function checkForUpdates(currentVersion, request = fetch) {
  let response;
  try {
    response = await request(GITEE_RELEASES_API, {
      headers: {
        Accept: "application/json",
      },
    });
  } catch {
    throw new Error("无法连接 Gitee，请检查网络后重试。");
  }

  if (response.status === 404) {
    return {
      status: "unavailable",
      currentVersion,
    };
  }
  if (response.status === 403) {
    throw new Error("Gitee 暂时拒绝了更新查询，请稍后再试。");
  }
  if (!response.ok) {
    throw new Error(`检查更新失败，Gitee 返回状态码 ${response.status}。`);
  }

  const releases = await response.json();
  const release = Array.isArray(releases)
    ? releases.find((item) => item && item.prerelease !== true)
    : null;
  if (!release) {
    return {
      status: "unavailable",
      currentVersion,
    };
  }
  const latestVersion = String(release.tag_name || "").replace(/^v/i, "");
  const comparison = compareVersions(currentVersion, latestVersion);
  const common = {
    currentVersion,
    latestVersion,
    releaseName: release.name || `v${latestVersion}`,
    releaseNotes: String(release.body || "").trim(),
    // 下载页只由固定 Gitee 仓库和 API 返回的 tag 组成，不信任响应中的任意外链。
    releaseUrl: canonicalReleaseUrl(release.tag_name),
    publishedAt: release.created_at || release.published_at || "",
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
    throw new Error("更新下载地址不是受信任的 Gitee Release 页面。");
  }
  const url = new URL(releaseUrl);

  if (isTauriRuntime()) {
    await openUrl(url.toString());
    return;
  }
  window.open(url.toString(), "_blank", "noopener,noreferrer");
}
