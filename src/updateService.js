import { getVersion } from "@tauri-apps/api/app";
import { openUrl } from "@tauri-apps/plugin-opener";
import packageMetadata from "../package.json" with { type: "json" };
import { isTauriRuntime } from "./runtime.js";
import { compareVersions } from "./versioning.js";

export const PACKAGE_VERSION = packageMetadata.version;
const GITEE_REPOSITORY = "CarsonClack030/risk";
const GITEE_RELEASES_API = `https://gitee.com/api/v5/repos/${GITEE_REPOSITORY}/releases?page=1&per_page=20&direction=desc`;
const GITHUB_LATEST_RELEASE_API =
  "https://api.github.com/repos/CarsonClack030/risk/releases/latest";

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

async function fetchGiteeRelease(request) {
  let response;
  try {
    response = await request(GITEE_RELEASES_API, {
      headers: {
        Accept: "application/json",
      },
    });
  } catch (error) {
    throw new Error("无法连接 Gitee 更新服务。", { cause: error });
  }

  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    throw new Error(`Gitee 更新服务返回状态码 ${response.status}。`);
  }

  const releases = await response.json();
  return Array.isArray(releases) ? releases.find((item) => item && item.prerelease !== true) : null;
}

async function fetchGitHubRelease(request) {
  let response;
  try {
    response = await request(GITHUB_LATEST_RELEASE_API, {
      headers: {
        Accept: "application/vnd.github+json",
      },
    });
  } catch (error) {
    throw new Error("无法连接 GitHub 备用更新服务。", { cause: error });
  }

  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    throw new Error(`GitHub 备用更新服务返回状态码 ${response.status}。`);
  }

  const release = await response.json();
  return release && release.draft !== true && release.prerelease !== true ? release : null;
}

// Gitee 是国内用户的首选更新源。它的匿名 API 偶尔会因访问频率返回 403，
// 此时仅改用 GitHub 获取版本元数据；安装包下载页仍固定为可信的 Gitee Release。
export async function checkForUpdates(currentVersion, request = fetch) {
  let release;
  try {
    release = await fetchGiteeRelease(request);
  } catch (_giteeError) {
    try {
      release = await fetchGitHubRelease(request);
    } catch (_githubError) {
      throw new Error("暂时无法连接更新服务，请检查网络后稍后重试。");
    }
  }

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
    // 下载页只由固定 Gitee 仓库和版本 tag 组成，不信任响应中的任意外链。
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
