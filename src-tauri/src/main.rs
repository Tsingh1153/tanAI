// Prevent a second console window on Windows release builds.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

// tanAI desktop shell.
//
// The native window loads the bundled UI; this Rust core brings up everything
// the UI talks to: it starts Ollama if it is installed but not running, then
// starts the Python backend, creating a virtual environment and installing
// dependencies on first launch. All child processes are killed on quit. The UI
// polls the backend's health and shows its own "starting" state, so the window
// can appear immediately while this work happens on a background thread.

use std::net::{SocketAddr, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::Duration;

use tauri::{Manager, RunEvent};

/// Child processes we spawned, so we can terminate them when the app exits.
#[derive(Default)]
struct Spawned(Mutex<Vec<Child>>);

const BACKEND_PORT: u16 = 8000;
const OLLAMA_PORT: u16 = 11434;

/// PATH augmented with the usual Homebrew / system locations. GUI apps on macOS
/// launch with a minimal PATH that omits /opt/homebrew/bin, where `python3` and
/// `ollama` often live, so we add them back for every command we run.
fn augmented_path() -> String {
    let mut dirs = vec![
        "/opt/homebrew/bin".to_string(),
        "/usr/local/bin".to_string(),
        "/usr/bin".to_string(),
        "/bin".to_string(),
        "/usr/sbin".to_string(),
        "/sbin".to_string(),
    ];
    if let Ok(existing) = std::env::var("PATH") {
        for dir in existing.split(':') {
            if !dir.is_empty() && !dirs.iter().any(|d| d == dir) {
                dirs.push(dir.to_string());
            }
        }
    }
    dirs.join(":")
}

fn command<S: AsRef<std::ffi::OsStr>>(program: S) -> Command {
    let mut cmd = Command::new(program);
    cmd.env("PATH", augmented_path());
    cmd
}

fn port_open(port: u16) -> bool {
    let addr = SocketAddr::from(([127, 0, 0, 1], port));
    TcpStream::connect_timeout(&addr, Duration::from_millis(400)).is_ok()
}

fn python_ok(py: &Path) -> bool {
    command(py)
        .args([
            "-c",
            "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)",
        ])
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .map(|s| s.success())
        .unwrap_or(false)
}

/// Find a Python 3.10+ interpreter, checking Homebrew locations before PATH.
fn find_python() -> Option<PathBuf> {
    let names = ["python3.12", "python3.11", "python3.10", "python3"];
    let dirs = ["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin"];
    for name in names {
        for dir in dirs {
            let path = Path::new(dir).join(name);
            if path.exists() && python_ok(&path) {
                return Some(path);
            }
        }
        let bare = PathBuf::from(name);
        if python_ok(&bare) {
            return Some(bare);
        }
    }
    None
}

/// The backend source directory in the repo (used only in development).
fn dev_backend_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("backend")
}

#[cfg(unix)]
fn make_executable(path: &Path) {
    use std::os::unix::fs::PermissionsExt;
    if let Ok(meta) = std::fs::metadata(path) {
        let mut perms = meta.permissions();
        perms.set_mode(0o755);
        let _ = std::fs::set_permissions(path, perms);
    }
}

#[cfg(not(unix))]
fn make_executable(_path: &Path) {}

fn requirements_signature(req: &Path) -> String {
    std::fs::read_to_string(req).unwrap_or_default()
}

/// Reuse the repo's virtual environment in development; otherwise create and
/// populate an app-managed one under Application Support. Returns the Python
/// interpreter to launch the backend with.
fn ensure_venv(backend_dir: &Path, data_dir: &Path) -> Result<PathBuf, String> {
    let repo_venv = backend_dir.join(".venv").join("bin").join("python");
    if repo_venv.exists() && python_ok(&repo_venv) {
        return Ok(repo_venv);
    }

    let venv = data_dir.join("venv");
    let venv_py = venv.join("bin").join("python");

    if !venv_py.exists() || !python_ok(&venv_py) {
        let python = find_python().ok_or_else(|| {
            "No Python 3.10+ found. Install it (e.g. brew install python@3.12) and reopen tanAI."
                .to_string()
        })?;
        std::fs::remove_dir_all(&venv).ok();
        let created = command(&python)
            .arg("-m")
            .arg("venv")
            .arg(&venv)
            .status()
            .map(|s| s.success())
            .unwrap_or(false);
        if !created {
            return Err("Could not create the Python environment.".into());
        }
    }

    // Install dependencies on first run, or whenever requirements.txt changes.
    let req = backend_dir.join("requirements.txt");
    let marker = venv.join(".deps-ok");
    let current = requirements_signature(&req);
    let installed = std::fs::read_to_string(&marker).unwrap_or_default();
    if current != installed {
        command(&venv_py)
            .args(["-m", "pip", "install", "--upgrade", "pip"])
            .status()
            .ok();
        let ok = command(&venv_py)
            .args(["-m", "pip", "install", "-r"])
            .arg(&req)
            .status()
            .map(|s| s.success())
            .unwrap_or(false);
        if !ok {
            return Err("Could not install the backend dependencies.".into());
        }
        std::fs::write(&marker, current).ok();
    }

    Ok(venv_py)
}

/// Start Ollama with the same speedups the shell launcher uses, but only if it
/// is installed and not already serving. If it is missing, onboarding guides the
/// user to install it, so we stay quiet here.
fn ensure_ollama(spawned: &Spawned) {
    if port_open(OLLAMA_PORT) {
        return;
    }
    let installed = command("ollama")
        .arg("--version")
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .map(|s| s.success())
        .unwrap_or(false);
    if !installed {
        return;
    }
    if let Ok(child) = command("ollama")
        .arg("serve")
        .env("OLLAMA_FLASH_ATTENTION", "1")
        .env("OLLAMA_KV_CACHE_TYPE", "q8_0")
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
    {
        spawned.0.lock().unwrap().push(child);
    }
}

/// Origins the webview may use, so the backend's CORS accepts the UI's requests.
const CORS_ORIGINS: &str = "[\"tauri://localhost\",\"http://tauri.localhost\",\"https://tauri.localhost\",\"http://localhost:3000\",\"http://127.0.0.1:3000\"]";

/// Start the FastAPI backend. In a packaged app this launches the frozen,
/// self-contained executable (no Python required on the machine). In development
/// it runs the backend from source in a virtualenv. Either way the working
/// directory is a writable folder under Application Support.
fn ensure_backend(app: &tauri::AppHandle, spawned: &Spawned) -> Result<(), String> {
    if port_open(BACKEND_PORT) {
        return Ok(()); // already running (e.g. started separately in dev)
    }

    let data_dir = app.path().app_data_dir().map_err(|e| e.to_string())?;
    std::fs::create_dir_all(&data_dir).ok();

    // 1) Packaged app: the frozen backend bundled as a resource.
    if let Ok(res) = app.path().resource_dir() {
        let exe = res.join("backend-bin").join("tanai-backend");
        if exe.exists() {
            make_executable(&exe);
            let child = command(&exe)
                .current_dir(&data_dir)
                .env("PYTHONUNBUFFERED", "1")
                .env("LOCALMIND_CORS_ORIGINS", CORS_ORIGINS)
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .spawn()
                .map_err(|e| e.to_string())?;
            spawned.0.lock().unwrap().push(child);
            return Ok(());
        }
    }

    // 2) Development: run from source using a virtualenv.
    let backend_dir = dev_backend_dir();
    if !backend_dir.exists() {
        return Err(format!("Backend not found at {}.", backend_dir.display()));
    }
    let venv_py = ensure_venv(&backend_dir, &data_dir)?;
    let child = command(&venv_py)
        .args([
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
        ])
        .current_dir(&data_dir)
        .env("PYTHONPATH", &backend_dir)
        .env("PYTHONUNBUFFERED", "1")
        .env("LOCALMIND_CORS_ORIGINS", CORS_ORIGINS)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|e| e.to_string())?;
    spawned.0.lock().unwrap().push(child);
    Ok(())
}

fn kill_all(app: &tauri::AppHandle) {
    if let Some(spawned) = app.try_state::<Spawned>() {
        for child in spawned.0.lock().unwrap().iter_mut() {
            let _ = child.kill();
        }
    }
}

fn main() {
    tauri::Builder::default()
        .manage(Spawned::default())
        .setup(|app| {
            let handle = app.handle().clone();
            // Bring services up off the UI thread so the window shows at once.
            std::thread::spawn(move || {
                let spawned = handle.state::<Spawned>();
                ensure_ollama(spawned.inner());
                if let Err(err) = ensure_backend(&handle, spawned.inner()) {
                    eprintln!("tanAI: backend did not start: {err}");
                }
            });
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("failed to start tanAI")
        .run(|app, event| {
            if matches!(event, RunEvent::ExitRequested { .. } | RunEvent::Exit) {
                kill_all(app);
            }
        });
}
