import { invoke } from "@tauri-apps/api/core";
import { isTauriRuntime } from "./runtime";

// 这是前端和后端通信的“唯一入口”。
// 我们把 fetch、错误处理、URL 拼接都收口到这里，
// 这样 App.jsx 可以专心处理界面状态，不必重复写底层网络细节。

// 兜底地址只在两种场景下会被使用：
// 1. 纯 Web 调试时，通过 Vite 环境变量或固定地址访问本地后端。
// 2. Tauri 命令调用失败时，退回到默认本地地址。
const FALLBACK_API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:38911";
const FALLBACK_API_TOKEN = import.meta.env.VITE_API_TOKEN || "";
let resolvedApiBase = null;
let resolvingApiBasePromise = null;
let resolvedApiToken = null;
let resolvingApiTokenPromise = null;

// API 基地址解析的顺序很重要：
// 1. 如果运行在 Tauri 中，就向 Rust 壳询问真正的后端地址。
//    这样即使默认端口被占用，前端也能拿到自动回退后的实际端口。
// 2. 纯 Web 调试时才使用 VITE_API_BASE。
// 3. 如果以上都失败，再退回到默认本地地址。
//
// 这里仍然做缓存，但只缓存“可靠拿到的结果”：
// - Tauri 命令成功返回的真实地址
// - 显式配置的 VITE_API_BASE
// - 非 Tauri 环境下的固定 fallback
//
// 如果 Tauri 命令偶发失败，就先临时退回 fallback，
// 但不会把这个 fallback 永久缓存死。
// 这样后续请求还有机会重新拿到真正的动态端口。
async function resolveApiBase({ force = false } = {}) {
  if (!force && resolvedApiBase) {
    return resolvedApiBase;
  }
  if (!force && resolvingApiBasePromise) {
    return resolvingApiBasePromise;
  }

  resolvingApiBasePromise = (async () => {
    if (isTauriRuntime()) {
      try {
        const apiBase = await invoke("resolve_backend_api_base");
        resolvedApiBase = apiBase;
        return apiBase;
      } catch (error) {
        console.warn("Failed to resolve backend API base from Tauri, using fallback.", error);
      }
    }

    if (import.meta.env.VITE_API_BASE) {
      resolvedApiBase = import.meta.env.VITE_API_BASE;
      return resolvedApiBase;
    }

    resolvedApiBase = FALLBACK_API_BASE;
    return resolvedApiBase;
  })();

  try {
    return await resolvingApiBasePromise;
  } finally {
    resolvingApiBasePromise = null;
  }
}

async function resolveApiToken({ force = false } = {}) {
  if (!force && resolvedApiToken !== null) {
    return resolvedApiToken;
  }
  if (!force && resolvingApiTokenPromise) {
    return resolvingApiTokenPromise;
  }

  resolvingApiTokenPromise = (async () => {
    if (isTauriRuntime()) {
      try {
        resolvedApiToken = await invoke("resolve_backend_api_token");
        return resolvedApiToken;
      } catch (error) {
        console.warn("Failed to resolve backend API token from Tauri.", error);
      }
    }
    if (import.meta.env.VITE_API_TOKEN) {
      resolvedApiToken = import.meta.env.VITE_API_TOKEN;
      return resolvedApiToken;
    }
    resolvedApiToken = FALLBACK_API_TOKEN;
    return resolvedApiToken;
  })();

  try {
    return await resolvingApiTokenPromise;
  } finally {
    resolvingApiTokenPromise = null;
  }
}

// 统一的请求封装：
// - 自动拼接基地址
// - 自动补 JSON 头
// - 自动把后端错误转换为前端可读的 Error
// - 自动区分 JSON 响应和二进制响应（例如 Excel 导出）
async function performRequest(apiBase, apiToken, path, options = {}) {
  const { headers: providedHeaders, ...requestOptions } = options;
  const headers = new Headers(providedHeaders);
  if (typeof requestOptions.body === "string" && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (apiToken) {
    headers.set("X-Risk-Api-Token", apiToken);
  }
  const response = await fetch(`${apiBase}${path}`, {
    ...requestOptions,
    headers,
  });

  if (!response.ok) {
    let message = `请求失败: ${response.status}`;
    try {
      const payload = await response.json();
      message = payload.error || message;
    } catch (_error) {
      message = response.statusText || message;
    }
    throw new Error(message);
  }

  const contentType = response.headers.get("Content-Type") || "";
  if (contentType.includes("application/json")) {
    return response.json();
  }
  return response.blob();
}

async function request(path, options = {}) {
  const [apiBase, apiToken] = await Promise.all([resolveApiBase(), resolveApiToken()]);
  try {
    return await performRequest(apiBase, apiToken, path, options);
  } catch (error) {
    // 如果最初拿到的是 fallback 地址，或者动态端口解析失败过，
    // 就再强制问一次 Rust 壳，看看是否能拿到真正的后端端口。
    if (isTauriRuntime() && error instanceof TypeError) {
      const refreshedApiBase = await resolveApiBase({ force: true });
      const refreshedApiToken = await resolveApiToken({ force: true });
      if (refreshedApiBase !== apiBase) {
        return performRequest(refreshedApiBase, refreshedApiToken, path, options);
      }
    }
    throw error;
  }
}

function adminHeaders(token) {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

// 把查询参数对象转成 URL 上的 ?a=1&b=2 形式。
// 空值会被自动忽略，避免产生多余参数。
function qs(params = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      query.set(key, value);
    }
  });
  const text = query.toString();
  return text ? `?${text}` : "";
}

// 这里暴露的是“面向业务语义”的 API，
// 而不是把 fetch 细节暴露给页面组件。
// 例如页面只需要知道“列出工作区”“计算结果”，不需要关心 HTTP 方法和路径。
export const api = {
  health: () => request("/api/health"),
  listCatalog: (keyword = "") => request(`/api/catalog${qs({ keyword })}`),
  listWorkspace: () => request("/api/workspace"),
  downloadWorkspaceImportTemplate: () => request("/api/workspace/import-template"),
  addWorkspaceItem: (pollutantId) =>
    request("/api/workspace/add", {
      method: "POST",
      body: JSON.stringify({ pollutant_id: pollutantId }),
    }),
  // 文件内容可能来自浏览器 File，也可能来自 Tauri readFile 返回的 Uint8Array。
  // 显式传入文件名和内容后，两种运行环境可以复用同一个上传接口。
  importWorkspaceFile: (filename, content, contentType = "application/octet-stream") =>
    request(`/api/workspace/import-file${qs({ filename })}`, {
      method: "POST",
      body: content,
      headers: {
        "Content-Type": contentType,
      },
    }),
  removeWorkspaceItem: (workspaceNumber) =>
    request(`/api/workspace/${workspaceNumber}`, { method: "DELETE" }),
  resetWorkspace: () => request("/api/workspace/reset", { method: "POST", body: "{}" }),
  updateConcentrations: (items) =>
    request("/api/workspace/concentrations", {
      method: "PUT",
      body: JSON.stringify({ items }),
    }),
  listParameters: () => request("/api/parameters"),
  resetParameters: () => request("/api/parameters/reset", { method: "POST", body: "{}" }),
  saveParameters: (groups) =>
    request("/api/parameters", {
      method: "PUT",
      body: JSON.stringify({ groups }),
    }),
  calculate: (payload) =>
    request("/api/calculate", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  listResults: () => request("/api/results"),
  exportResults: () =>
    request("/api/results/export", {
      method: "POST",
      body: "{}",
    }),
  login: (username, password) =>
    request("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  logout: (token) =>
    request("/api/auth/logout", {
      method: "POST",
      body: "{}",
      headers: adminHeaders(token),
    }),
  updatePassword: (payload, token) =>
    request("/api/auth/password", {
      method: "POST",
      body: JSON.stringify(payload),
      headers: adminHeaders(token),
    }),
  addPollutant: (payload, token) =>
    request("/api/admin/pollutants", {
      method: "POST",
      body: JSON.stringify(payload),
      headers: adminHeaders(token),
    }),
  updatePollutant: (pollutantId, payload, token) =>
    request(`/api/admin/pollutants/${pollutantId}`, {
      method: "PUT",
      body: JSON.stringify(payload),
      headers: adminHeaders(token),
    }),
  deletePollutant: (pollutantId, keyword = "", token) =>
    request(`/api/admin/pollutants/${pollutantId}${qs({ keyword })}`, {
      method: "DELETE",
      headers: adminHeaders(token),
    }),
};
