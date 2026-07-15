#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

// 桌面壳负责启动 Python 后端、向前端提供动态端口并在退出时清理进程。

use std::io::{self, Read, Write};
use std::net::{SocketAddr, TcpListener, TcpStream};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use tauri::{Manager, RunEvent};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

struct BackendState(Mutex<Option<ManagedBackend>>);

struct BackendConfig {
    api_base: String,
}

enum BackendProcess {
    Dev(Child),
    Sidecar(CommandChild),
}

// 除了进程句柄，还保存后端端口和一次性退出令牌。
// PyInstaller onefile 实际包含父子两层进程，只 kill 外层会留下真正的 HTTP 服务。
struct ManagedBackend {
    process: BackendProcess,
    port: u16,
    shutdown_token: String,
}

// 优先尝试项目默认端口 38911。
// 如果被占用，就向系统申请一个随机空闲端口。
// 这样即使用户同时打开多个版本，也不会因为端口冲突直接启动失败。
fn resolve_backend_port() -> Result<u16, String> {
    const DEFAULT_PORT: u16 = 38911;
    if let Ok(listener) = TcpListener::bind(("127.0.0.1", DEFAULT_PORT)) {
        drop(listener);
        return Ok(DEFAULT_PORT);
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

fn generate_shutdown_token() -> String {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos();
    format!("{:x}-{:x}", std::process::id(), nanos)
}

fn spawn_backend(
    app: &tauri::AppHandle,
    port: u16,
    shutdown_token: &str,
) -> Result<BackendProcess, String> {
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
            .env("RISK_SHUTDOWN_TOKEN", shutdown_token)
            .stdout(Stdio::null())
            .stderr(Stdio::inherit())
            .spawn()
            .map_err(|error| error.to_string())?;
        return Ok(BackendProcess::Dev(child));
    }

    // 发布态通过 sidecar 启动已经打包好的 Python 后端可执行文件。
    let sidecar_command = app
        .shell()
        .sidecar("risk-backend")
        .map_err(|error| error.to_string())?
        .env("RISK_SHUTDOWN_TOKEN", shutdown_token);
    let port_arg = port.to_string();
    let (mut rx, child) = sidecar_command
        .args(["--host", "127.0.0.1", "--port", &port_arg])
        .spawn()
        .map_err(|error| error.to_string())?;

    // 把 sidecar 的 stdout/stderr 转发到桌面壳日志，方便排错。
    tauri::async_runtime::spawn(async move {
        while let Some(event) = rx.recv().await {
            if let CommandEvent::Stdout(line) | CommandEvent::Stderr(line) = event {
                eprintln!("risk-backend: {}", String::from_utf8_lossy(&line));
            }
        }
    });

    Ok(BackendProcess::Sidecar(child))
}

fn request_backend_shutdown(port: u16, shutdown_token: &str) {
    let address = SocketAddr::from(([127, 0, 0, 1], port));
    let Ok(mut stream) = TcpStream::connect_timeout(&address, Duration::from_millis(300)) else {
        return;
    };
    let request = format!(
        "POST /api/shutdown HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nX-Risk-Shutdown-Token: {shutdown_token}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
    );
    let _ = stream.set_write_timeout(Some(Duration::from_millis(300)));
    let _ = stream.set_read_timeout(Some(Duration::from_millis(500)));
    if stream.write_all(request.as_bytes()).is_ok() {
        // 读到响应后，后端已经安排 shutdown；稍等片刻让 serve_forever 正常返回。
        let mut response = [0_u8; 64];
        let _ = stream.read(&mut response);
        std::thread::sleep(Duration::from_millis(120));
    }
}

fn stop_backend(backend: ManagedBackend) {
    request_backend_shutdown(backend.port, &backend.shutdown_token);
    // HTTP 服务优雅退出后再清理外层进程；若后端启动失败，这里仍能兜底 kill。
    match backend.process {
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
    let shutdown_token = generate_shutdown_token();
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        // opener 只负责把确认后的 Gitee Release 页面交给系统浏览器打开。
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_shell::init())
        .manage(BackendState(Mutex::new(None)))
        .manage(BackendConfig {
            api_base: backend_api_base,
        })
        .invoke_handler(tauri::generate_handler![resolve_backend_api_base])
        .setup(move |app| {
            // 应用启动阶段就拉起后端，确保前端打开后很快能完成健康检查。
            let child = spawn_backend(app.handle(), backend_port, &shutdown_token)
                .map_err(io::Error::other)?;
            let state = app.state::<BackendState>();
            *state.0.lock().expect("failed to lock backend state") = Some(ManagedBackend {
                process: child,
                port: backend_port,
                shutdown_token: shutdown_token.clone(),
            });
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
