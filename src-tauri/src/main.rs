#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::io;
use std::net::TcpListener;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use tauri::{Manager, RunEvent};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

struct BackendState(Mutex<Option<BackendProcess>>);
struct BackendConfig {
    api_base: String,
}

enum BackendProcess {
    Dev(Child),
    Sidecar(CommandChild),
}

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
    config.api_base.clone()
}

fn spawn_backend(app: &tauri::AppHandle, port: u16) -> Result<BackendProcess, String> {
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

    let sidecar_command = app.shell().sidecar("risk-backend").map_err(|error| error.to_string())?;
    let port_arg = port.to_string();
    let (mut rx, child) = sidecar_command
        .args(["--host", "127.0.0.1", "--port", &port_arg])
        .spawn()
        .map_err(|error| error.to_string())?;

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
    let backend_port =
        resolve_backend_port().expect("failed to reserve a localhost port for the backend");
    let backend_api_base = format!("http://127.0.0.1:{backend_port}");
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(BackendState(Mutex::new(None)))
        .manage(BackendConfig {
            api_base: backend_api_base,
        })
        .invoke_handler(tauri::generate_handler![resolve_backend_api_base])
        .setup(move |app| {
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
            let state = app_handle.state::<BackendState>();
            let process = { state.0.lock().expect("failed to lock backend state").take() };
            if let Some(process) = process {
                stop_backend(process);
            }
        }
    });
}
