import { invoke } from "@tauri-apps/api/core";

// 这是前端和后端通信的“唯一入口”。
// 我们把 fetch、错误处理、URL 拼接都收口到这里，
// 这样 App.jsx 可以专心处理界面状态，不必重复写底层网络细节。

// 兜底地址只在两种场景下会被使用：
// 1. 纯 Web 调试时，通过 Vite 环境变量或固定地址访问本地后端。
// 2. Tauri 命令调用失败时，退回到默认本地地址。
const FALLBACK_API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:38911";
let resolvedApiBasePromise = null;

// 只有在 Tauri 桌面壳里，window 上才会注入内部运行时对象。
// 这个判断用于区分“浏览器调试环境”和“桌面应用环境”。
function isTauriRuntime() {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

// API 基地址解析的顺序很重要：
// 1. 先尊重显式配置的 VITE_API_BASE，方便开发时手工指定后端。
// 2. 如果运行在 Tauri 中，就向 Rust 壳询问真正的后端地址。
//    这样即使默认端口被占用，前端也能拿到自动回退后的实际端口。
// 3. 如果以上都失败，再退回到默认本地地址。
//
// 这里用 Promise 做缓存，是为了避免每次请求都重复 invoke 一次 Tauri 命令。
async function resolveApiBase() {
  if (!resolvedApiBasePromise) {
    resolvedApiBasePromise = (async () => {
      if (import.meta.env.VITE_API_BASE) {
        return import.meta.env.VITE_API_BASE;
      }
      if (isTauriRuntime()) {
        try {
          return await invoke("resolve_backend_api_base");
        } catch (error) {
          console.warn("Failed to resolve backend API base from Tauri, using fallback.", error);
        }
      }
      return FALLBACK_API_BASE;
    })();
  }
  return resolvedApiBasePromise;
}

// 统一的请求封装：
// - 自动拼接基地址
// - 自动补 JSON 头
// - 自动把后端错误转换为前端可读的 Error
// - 自动区分 JSON 响应和二进制响应（例如 Excel 导出）
async function request(path, options = {}) {
  const apiBase = await resolveApiBase();
  const response = await fetch(`${apiBase}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
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
  resolveBaseUrl: resolveApiBase,
  health: () => request("/api/health"),
  listCatalog: (keyword = "") => request(`/api/catalog${qs({ keyword })}`),
  listWorkspace: () => request("/api/workspace"),
  downloadWorkspaceImportTemplate: () => request("/api/workspace/import-template"),
  addWorkspaceItem: (pollutantId) =>
    request("/api/workspace/add", {
      method: "POST",
      body: JSON.stringify({ pollutant_id: pollutantId }),
    }),
  importWorkspaceExcel: (file) =>
    request("/api/workspace/import-excel", {
      method: "POST",
      body: file,
      headers: {
        "Content-Type":
          file.type || "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
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
      headers: {},
    }),
  login: (username, password) =>
    request("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  updatePassword: (payload) =>
    request("/api/auth/password", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  addPollutant: (payload) =>
    request("/api/admin/pollutants", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updatePollutant: (pollutantId, payload) =>
    request(`/api/admin/pollutants/${pollutantId}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  deletePollutant: (pollutantId, keyword = "") =>
    request(`/api/admin/pollutants/${pollutantId}${qs({ keyword })}`, {
      method: "DELETE",
    }),
};
