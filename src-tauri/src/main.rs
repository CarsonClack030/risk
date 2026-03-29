#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

// 这是 Tauri 桌面壳的入口。
// 它主要做三件事：
// 1. 启动时挑一个可用的本地端口。
// 2. 拉起 Python 后端（开发时直接跑脚本，发布时跑 sidecar）。
// 3. 把真实的后端地址告诉前端，并在应用退出时清理子进程。

use std::io;
use std::net::TcpListener;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use tauri::{Manager, RunEvent};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

// BackendState 用来保存当前已经启动的后端进程句柄，
// 这样应用退出时可以把它干净地 kill 掉。
struct BackendState(Mutex<Option<BackendProcess>>);

// BackendConfig 用来保存前端真正应该访问的 API 地址。
// 由于端口现在支持自动回退，因此这个地址不能在前端写死。
struct BackendConfig {
    api_base: String,
}

// 开发态和发布态的后端进程类型不同：
// - 开发态：直接用 std::process::Child 启动 Python 脚本
// - 发布态：通过 Tauri sidecar 启动打包后的后端二进制
enum BackendProcess {
    Dev(Child),
    Sidecar(CommandChild),
}

// 优先尝试项目默认端口 38911。
// 如果被占用，就向系统申请一个随机空闲端口。
// 这样即使用户同时打开多个版本，也不会因为端口冲突直接启动失败。
fn resolve_backend_port() -> Result<u16, String> {
    const DEFAULT_PORT: u16 = 38911;
    if let Ok(listener) = TcpListener::bind(("127.0.0.1", DEFAULT_PORT)) {
        let port = listener
            .local_addr()
            .map_err(|error| error.to_string())?
            .port();
        drop(listener);
        return Ok(port);
    }

    let listener = TcpListener::bind(("127.0.0.1", 0)).map_err(|error| error.to_string())?;
    let port = listener
        .local_addr()
        .map_err(|error| error.to_string())?
        .port();
    eprintln!(
        "risk-backend: port {} is busy, falling back to {}",
        DEFAULT_PORT, port
    );
    drop(listener);
    Ok(port)
}

#[tauri::command]
fn resolve_backend_api_base(config: tauri::State<'_, BackendConfig>) -> String {
    // 前端通过 invoke("resolve_backend_api_base") 获取真实地址。
    config.api_base.clone()
}

fn spawn_backend(app: &tauri::AppHandle, port: u16) -> Result<BackendProcess, String> {
    // 开发态直接跑 backend/main.py，方便我们热调前后端。
    if cfg!(debug_assertions) {
        let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        let script_path = manifest_dir.join("../backend/main.py");
        let python_bin = std::env::var("RISK_PYTHON_BIN").unwrap_or_else(|_| "python3".to_string());
        let child = Command::new(python_bin)
            .arg(script_path)
            .arg("--host")
            .arg("127.0.0.1")
            .arg("--port")
            .arg(port.to_string())
            .stdout(Stdio::null())
            .stderr(Stdio::inherit())
            .spawn()
            .map_err(|error| error.to_string())?;
        return Ok(BackendProcess::Dev(child));
    }

    // 发布态通过 sidecar 启动已经打包好的 Python 后端可执行文件。
    let sidecar_command = app.shell().sidecar("risk-backend").map_err(|error| error.to_string())?;
    let port_arg = port.to_string();
    let (mut rx, child) = sidecar_command
        .args(["--host", "127.0.0.1", "--port", &port_arg])
        .spawn()
        .map_err(|error| error.to_string())?;

    // 把 sidecar 的 stdout/stderr 转发到桌面壳日志，方便排错。
    tauri::async_runtime::spawn(async move {
        while let Some(event) = rx.recv().await {
            match event {
                CommandEvent::Stdout(line) | CommandEvent::Stderr(line) => {
                    eprintln!("risk-backend: {}", String::from_utf8_lossy(&line));
                }
                _ => {}
            }
        }
    });

    Ok(BackendProcess::Sidecar(child))
}

fn stop_backend(process: BackendProcess) {
    // 无论开发态还是 sidecar，都统一在这里清理。
    match process {
        BackendProcess::Dev(mut child) => {
            let _ = child.kill();
        }
        BackendProcess::Sidecar(child) => {
            let _ = child.kill();
        }
    }
}

fn main() {
    // 先预留端口，再把这个真实地址交给前端和后端同时使用。
    let backend_port =
        resolve_backend_port().expect("failed to reserve a localhost port for the backend");
    let backend_api_base = format!("http://127.0.0.1:{backend_port}");
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_shell::init())
        .manage(BackendState(Mutex::new(None)))
        .manage(BackendConfig {
            api_base: backend_api_base,
        })
        .invoke_handler(tauri::generate_handler![resolve_backend_api_base])
        .setup(move |app| {
            // 应用启动阶段就拉起后端，确保前端打开后很快能完成健康检查。
            let child = spawn_backend(app.handle(), backend_port)
                .map_err(|message| io::Error::new(io::ErrorKind::Other, message))?;
            let state = app.state::<BackendState>();
            *state.0.lock().expect("failed to lock backend state") = Some(child);
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    app.run(|app_handle, event| {
        if matches!(event, RunEvent::Exit | RunEvent::ExitRequested { .. }) {
            // 窗口关闭时主动结束后端，避免残留监听端口。
            let state = app_handle.state::<BackendState>();
            let process = { state.0.lock().expect("failed to lock backend state").take() };
            if let Some(process) = process {
                stop_backend(process);
            }
        }
    });
}
