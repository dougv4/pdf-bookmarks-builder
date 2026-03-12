#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use rfd::FileDialog;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::io::Write;
use std::path::PathBuf;
use std::process::{Command, Stdio};
use tauri::{AppHandle, Manager};

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct SimpleDialogPayload {
    last_dir: Option<String>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct OutputDialogPayload {
    input_path: Option<String>,
    suggested_name: Option<String>,
    last_dir: Option<String>,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
struct ValidationPayload {
    structured_toc: String,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
struct ProcessPdfPayload {
    input_pdf: String,
    output_pdf: String,
    structured_toc: String,
    optimize: bool,
    color_dpi: u32,
    gray_dpi: u32,
    jpeg_quality: u32,
}

#[derive(Debug)]
struct BackendProgram {
    executable: PathBuf,
    args: Vec<String>,
    current_dir: Option<PathBuf>,
}

#[tauri::command]
fn pick_input_pdf(payload: SimpleDialogPayload) -> Result<Option<String>, String> {
    let mut dialog = FileDialog::new().add_filter("PDF", &["pdf"]);
    if let Some(last_dir) = payload.last_dir {
        let path = PathBuf::from(last_dir);
        if path.exists() {
            dialog = dialog.set_directory(path);
        }
    }
    Ok(dialog.pick_file().map(|path| path.to_string_lossy().to_string()))
}

#[tauri::command]
fn pick_output_pdf(payload: OutputDialogPayload) -> Result<Option<String>, String> {
    let mut dialog = FileDialog::new().add_filter("PDF", &["pdf"]);
    if let Some(last_dir) = payload.last_dir {
        let path = PathBuf::from(last_dir);
        if path.exists() {
            dialog = dialog.set_directory(path);
        }
    } else if let Some(input_path) = payload.input_path {
        let path = PathBuf::from(input_path);
        if let Some(parent) = path.parent() {
            dialog = dialog.set_directory(parent);
        }
    }
    if let Some(name) = payload.suggested_name {
        dialog = dialog.set_file_name(&name);
    }
    Ok(dialog.save_file().map(|path| path.to_string_lossy().to_string()))
}

#[tauri::command]
async fn validate_preview(app: AppHandle, payload: ValidationPayload) -> Result<Value, String> {
    run_backend_command(app, "validate-preview", serde_json::to_value(payload).map_err(|err| err.to_string())?).await
}

#[tauri::command]
async fn process_pdf(app: AppHandle, payload: ProcessPdfPayload) -> Result<Value, String> {
    run_backend_command(app, "process-pdf", serde_json::to_value(payload).map_err(|err| err.to_string())?).await
}

async fn run_backend_command(app: AppHandle, subcommand: &'static str, payload: Value) -> Result<Value, String> {
    tauri::async_runtime::spawn_blocking(move || run_backend_command_blocking(&app, subcommand, payload))
        .await
        .map_err(|err| err.to_string())?
}

fn run_backend_command_blocking(app: &AppHandle, subcommand: &str, payload: Value) -> Result<Value, String> {
    let backend = resolve_backend_program(app)?;
    let mut command = Command::new(&backend.executable);
    command.args(&backend.args).arg(subcommand);
    if let Some(current_dir) = backend.current_dir {
        command.current_dir(current_dir);
    }

    let env_overrides = resolve_pdf_binary_envs(app);
    for (key, value) in env_overrides {
        command.env(key, value);
    }

    command.stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::piped());

    let mut child = command.spawn().map_err(|err| format!("Falha ao iniciar backend Python: {err}"))?;
    let payload_text = serde_json::to_string(&payload).map_err(|err| err.to_string())?;
    if let Some(stdin) = child.stdin.as_mut() {
        stdin.write_all(payload_text.as_bytes()).map_err(|err| format!("Falha ao enviar JSON ao backend: {err}"))?;
    }

    let output = child.wait_with_output().map_err(|err| format!("Falha aguardando backend: {err}"))?;
    let stdout = String::from_utf8(output.stdout).map_err(|err| format!("Saida invalida do backend: {err}"))?;
    let stderr = String::from_utf8_lossy(&output.stderr).to_string();

    if stdout.trim().is_empty() {
        return Err(if stderr.trim().is_empty() {
            "Backend nao retornou JSON.".to_string()
        } else {
            stderr
        });
    }

    serde_json::from_str::<Value>(stdout.trim()).map_err(|err| format!("JSON invalido do backend: {err}. Stderr: {stderr}"))
}

fn resolve_backend_program(app: &AppHandle) -> Result<BackendProgram, String> {
    if let Ok(explicit_path) = std::env::var("PDF_BUILDER_BACKEND_PATH") {
        let path = PathBuf::from(explicit_path);
        if path.exists() {
            return Ok(BackendProgram {
                executable: path,
                args: Vec::new(),
                current_dir: None,
            });
        }
    }

    if let Some(resource_dir) = app.path().resource_dir().ok() {
        let sidecar = resource_dir.join("binaries").join(platform_key()).join(executable_name("pdf-bookmarks-backend"));
        if sidecar.exists() {
            return Ok(BackendProgram {
                executable: sidecar,
                args: Vec::new(),
                current_dir: None,
            });
        }
    }

    let tauri_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let desktop_dir = tauri_dir.parent().ok_or("Nao foi possivel localizar o diretorio desktop.")?;
    let repo_root = desktop_dir.parent().ok_or("Nao foi possivel localizar a raiz do repositorio.")?;
    let entrypoint = desktop_dir.join("backend_entrypoint.py");
    if !entrypoint.exists() {
        return Err(format!("Backend de desenvolvimento nao encontrado em {}", entrypoint.display()));
    }

    Ok(BackendProgram {
        executable: PathBuf::from("python3"),
        args: vec![entrypoint.to_string_lossy().to_string()],
        current_dir: Some(repo_root.to_path_buf()),
    })
}

fn resolve_pdf_binary_envs(app: &AppHandle) -> Vec<(String, String)> {
    let mut envs = Vec::new();
    if let Some(resource_dir) = app.path().resource_dir().ok() {
        let base_dir = resource_dir.join("binaries").join(platform_key());
        let gs_path = base_dir.join(executable_name("gs"));
        let qpdf_path = base_dir.join(executable_name("qpdf"));
        let gs_resource_path = resource_dir.join("ghostscript").join(platform_key());
        if gs_path.exists() {
            envs.push(("PDF_BUILDER_GS_PATH".to_string(), gs_path.to_string_lossy().to_string()));
        }
        if qpdf_path.exists() {
            envs.push(("PDF_BUILDER_QPDF_PATH".to_string(), qpdf_path.to_string_lossy().to_string()));
        }
        if gs_resource_path.exists() {
            envs.push((
                "PDF_BUILDER_GS_RESOURCE_PATH".to_string(),
                gs_resource_path.to_string_lossy().to_string(),
            ));
        }
    }
    envs
}

fn executable_name(base: &str) -> String {
    if cfg!(target_os = "windows") {
        format!("{base}.exe")
    } else {
        base.to_string()
    }
}

fn platform_key() -> &'static str {
    #[cfg(all(target_os = "macos", target_arch = "aarch64"))]
    {
        return "macos-arm64";
    }
    #[cfg(all(target_os = "macos", target_arch = "x86_64"))]
    {
        return "macos-x64";
    }
    #[cfg(target_os = "windows")]
    {
        return "windows-x64";
    }
    #[cfg(not(any(target_os = "windows", target_os = "macos")))]
    {
        return "linux-x64";
    }
}

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            pick_input_pdf,
            pick_output_pdf,
            process_pdf,
            validate_preview,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
