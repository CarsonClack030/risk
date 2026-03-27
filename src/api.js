import { invoke } from "@tauri-apps/api/core";

const FALLBACK_API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:38911";
let resolvedApiBasePromise = null;

function isTauriRuntime() {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

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

export const api = {
  resolveBaseUrl: resolveApiBase,
  health: () => request("/api/health"),
  listCatalog: (keyword = "") => request(`/api/catalog${qs({ keyword })}`),
  listWorkspace: () => request("/api/workspace"),
  addWorkspaceItem: (pollutantId) =>
    request("/api/workspace/add", {
      method: "POST",
      body: JSON.stringify({ pollutant_id: pollutantId }),
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
