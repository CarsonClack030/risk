import { open, save } from "@tauri-apps/plugin-dialog";
import { readFile, writeFile } from "@tauri-apps/plugin-fs";
import { isTauriRuntime } from "./runtime";

const WORKSPACE_IMPORT_EXTENSIONS = [".xlsx", ".xls", ".csv", ".txt"];
const WORKSPACE_IMPORT_FILTER = {
  name: "污染物数据文件",
  extensions: ["xlsx", "xls", "csv", "txt"],
};
const EXCEL_EXPORT_FILTER = {
  name: "Excel 文件",
  extensions: ["xlsx"],
};
const EXCEL_MIME_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
const CSV_MIME_TYPE = "text/csv;charset=utf-8";
const PROJECT_FILTER = {
  name: "Risk Studio 项目",
  extensions: ["riskproj"],
};
const CSV_EXPORT_FILTER = {
  name: "CSV 文件",
  extensions: ["csv"],
};

function ensureProjectExtension(path) {
  const value = String(path || "");
  return value.toLowerCase().endsWith(".riskproj") ? value : `${value}.riskproj`;
}

export function hasSupportedImportExtension(filename) {
  const lower = String(filename || "").toLowerCase();
  return WORKSPACE_IMPORT_EXTENSIONS.some((extension) => lower.endsWith(extension));
}

// Tauri 返回完整路径，而后端只需要文件名来判断格式。
// Windows 使用反斜杠，macOS 使用正斜杠，因此这里同时兼容两种分隔符。
export function filenameFromPath(path) {
  return (
    String(path || "")
      .split(/[\\/]/)
      .pop() || ""
  );
}

// 浏览器 File 对象会自带 MIME 类型，但 Tauri readFile 返回的是 Uint8Array。
// 根据扩展名补齐类型后，两种环境就可以共用同一条后端上传接口。
export function importContentType(filename) {
  const lower = String(filename || "").toLowerCase();
  if (lower.endsWith(".xlsx")) {
    return EXCEL_MIME_TYPE;
  }
  if (lower.endsWith(".xls")) {
    return "application/vnd.ms-excel";
  }
  if (lower.endsWith(".csv")) {
    return "text/csv";
  }
  if (lower.endsWith(".txt")) {
    return "text/plain";
  }
  return "application/octet-stream";
}

// 桌面版打开系统文件选择器并读取用户选中的文件。
// 返回 null 表示用户取消；浏览器模式由 App.jsx 的 file input 兼容入口负责。
export async function pickWorkspaceImportFile() {
  const selectedPath = await open({
    multiple: false,
    directory: false,
    filters: [WORKSPACE_IMPORT_FILTER],
  });
  if (!selectedPath) {
    return null;
  }

  const path = Array.isArray(selectedPath) ? selectedPath[0] : selectedPath;
  const filename = filenameFromPath(path);
  return {
    filename,
    content: await readFile(path),
    contentType: importContentType(filename),
  };
}

// 启动页使用独立的项目文件选择器，项目文件本质上是经过校验的 SQLite 快照。
export async function pickProjectFile() {
  if (!isTauriRuntime()) {
    throw new Error("请使用桌面版打开 Risk Studio 项目文件");
  }
  const selectedPath = await open({
    multiple: false,
    directory: false,
    filters: [PROJECT_FILTER],
  });
  if (!selectedPath) {
    return null;
  }
  const path = Array.isArray(selectedPath) ? selectedPath[0] : selectedPath;
  return {
    path,
    filename: filenameFromPath(path),
    content: await readFile(path),
  };
}

// 新建项目时先让用户选择项目文件的完整保存位置。
// 保存对话框的默认文件名来自用户填写的项目名称，用户仍可以手动修改文件名。
export async function pickProjectSavePath(defaultName) {
  if (!isTauriRuntime()) {
    throw new Error("请使用桌面版选择 Risk Studio 项目的保存位置");
  }
  const targetPath = await save({
    defaultPath: ensureProjectExtension(defaultName),
    filters: [PROJECT_FILTER],
  });
  return targetPath ? ensureProjectExtension(targetPath) : null;
}

// 文件导出统一经过这个函数：
// - Tauri 桌面版使用系统“另存为”窗口；
// - 浏览器调试时优先使用 File System Access API；
// - 不支持该 API 的旧浏览器才回退到普通下载行为。
// 返回 null 表示用户取消，此时调用方不应显示“保存成功”。
export async function saveExcelBlob(blob, defaultPath) {
  if (isTauriRuntime()) {
    const targetPath = await save({
      defaultPath,
      filters: [EXCEL_EXPORT_FILTER],
    });
    if (!targetPath) {
      return null;
    }
    await writeFile(targetPath, new Uint8Array(await blob.arrayBuffer()));
    return targetPath;
  }

  if (typeof window.showSaveFilePicker === "function") {
    try {
      const handle = await window.showSaveFilePicker({
        suggestedName: defaultPath,
        types: [
          {
            description: EXCEL_EXPORT_FILTER.name,
            accept: { [EXCEL_MIME_TYPE]: [".xlsx"] },
          },
        ],
      });
      const writable = await handle.createWritable();
      await writable.write(blob);
      await writable.close();
      return handle.name;
    } catch (error) {
      if (error?.name === "AbortError") {
        return null;
      }
      throw error;
    }
  }

  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = defaultPath;
  anchor.style.display = "none";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
  return defaultPath;
}

// 导出文本日志时也使用系统“另存为”窗口，保证用户能决定 CSV 文件的保存位置。
export async function saveCsvBlob(blob, defaultPath) {
  if (isTauriRuntime()) {
    const targetPath = await save({
      defaultPath,
      filters: [CSV_EXPORT_FILTER],
    });
    if (!targetPath) {
      return null;
    }
    await writeFile(targetPath, new Uint8Array(await blob.arrayBuffer()));
    return targetPath;
  }

  if (typeof window.showSaveFilePicker === "function") {
    try {
      const handle = await window.showSaveFilePicker({
        suggestedName: defaultPath,
        types: [
          {
            description: CSV_EXPORT_FILTER.name,
            accept: { [CSV_MIME_TYPE]: [".csv"] },
          },
        ],
      });
      const writable = await handle.createWritable();
      await writable.write(blob);
      await writable.close();
      return handle.name;
    } catch (error) {
      if (error?.name === "AbortError") {
        return null;
      }
      throw error;
    }
  }

  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = defaultPath;
  anchor.style.display = "none";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
  return defaultPath;
}

// 保存项目快照。项目和 Excel 都由用户通过系统“另存为”窗口决定位置。
export async function saveProjectBlob(blob, defaultPath) {
  if (!isTauriRuntime()) {
    throw new Error("请使用桌面版保存 Risk Studio 项目文件");
  }
  const targetPath = await save({
    defaultPath,
    filters: [PROJECT_FILTER],
  });
  if (!targetPath) {
    return null;
  }
  const normalizedPath = ensureProjectExtension(targetPath);
  await writeFile(normalizedPath, new Uint8Array(await blob.arrayBuffer()));
  return normalizedPath;
}

// 自动保存使用已确定的项目路径，不再重复弹出保存窗口。
export async function writeProjectBlob(blob, targetPath) {
  if (!isTauriRuntime()) {
    throw new Error("请使用桌面版保存 Risk Studio 项目文件");
  }
  const normalizedPath = ensureProjectExtension(targetPath);
  await writeFile(normalizedPath, new Uint8Array(await blob.arrayBuffer()));
  return normalizedPath;
}
