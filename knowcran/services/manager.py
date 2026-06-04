import logging
import os
import sys
import json
import shutil
import socket
import time
import subprocess
import urllib.parse
from pathlib import Path
from typing import Dict, Any

import httpx

from knowcran.config import Settings
from knowcran.services.mineru import MinerUManager

logger = logging.getLogger(__name__)


def _openai_base_to_service_root(url: str) -> str:
    """Return the service root for an OpenAI-compatible base URL."""
    parsed = urllib.parse.urlparse(url.rstrip("/"))
    path = parsed.path.rstrip("/")
    if path == "/v1":
        parsed = parsed._replace(path="")
    return urllib.parse.urlunparse(parsed).rstrip("/")


def _pid_running(pid: int | str | None) -> bool:
    if not pid:
        return False
    try:
        pid_int = int(pid)
    except (TypeError, ValueError):
        return False

    try:
        import psutil
        return psutil.Process(pid_int).is_running()
    except ImportError:
        try:
            os.kill(pid_int, 0)
            return True
        except OSError:
            return False
    except Exception:
        return False


def _terminate_pid(pid: int | str, timeout: float = 3.0) -> None:
    pid_int = int(pid)
    try:
        import psutil
        proc = psutil.Process(pid_int)
        proc.terminate()
        gone, alive = psutil.wait_procs([proc], timeout=timeout)
        for p in alive:
            p.kill()
        return
    except ImportError:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid_int), "/T", "/F"], check=False, capture_output=True)
            return
        try:
            os.kill(pid_int, 15)
        except ProcessLookupError:
            return
    except Exception:
        raise


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return False
        except socket.error:
            return True

def probe_health(url: str, endpoint: str = "", timeout: float = 1.5) -> bool:
    probe_url = url.rstrip("/")
    if endpoint:
        probe_url = f"{probe_url}/{endpoint.lstrip('/')}"
    try:
        res = httpx.get(probe_url, timeout=timeout)
        return res.status_code in (200, 204, 301, 302, 307, 308)
    except Exception:
        return False


def probe_embedding_health(openai_base_url: str) -> bool:
    """Probe the managed embedding service health endpoint.

    The embedding API base is OpenAI-compatible and usually ends with /v1, while
    the service health endpoint is mounted at /health on the service root.
    """
    return probe_health(_openai_base_to_service_root(openai_base_url), "health")


def probe_mineru_health(api_url: str) -> bool:
    """Probe MinerU without accepting arbitrary HTTP servers as healthy."""
    root = api_url.rstrip("/")
    if probe_health(root, "health"):
        return True

    try:
        res = httpx.get(f"{root}/openapi.json", timeout=1.5)
        if res.status_code == 200:
            spec = res.json()
            paths = spec.get("paths", {}) if isinstance(spec, dict) else {}
            if any("file_parse" in path or "parse" in path for path in paths):
                return True
    except Exception:
        pass

    try:
        res = httpx.get(root, timeout=1.5)
        if res.status_code == 200 and "mineru" in res.text.lower():
            return True
    except Exception:
        pass
    return False


def get_state_file_path(settings: Settings) -> Path:
    return settings.data_dir / "runtime" / "services.json"

def load_services_state(settings: Settings) -> Dict[str, Any]:
    path = get_state_file_path(settings)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

def save_services_state(settings: Settings, state: Dict[str, Any]):
    path = get_state_file_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")

def get_services_status(settings: Settings) -> Dict[str, Any]:
    state = load_services_state(settings)
    
    # 1. Check Embedding Server
    emb_mode = settings.local_embedding_mode
    emb_url = settings.local_embedding_url
    emb_status = "stopped"
    
    if settings.embedding_provider == "local":
        if emb_mode == "external":
            emb_status = "running" if probe_embedding_health(emb_url) else "stopped"
        elif emb_mode == "managed":
            is_alive = probe_embedding_health(emb_url)
            state_info = state.get("embedding", {})
            if is_alive:
                emb_status = "running"
            elif state_info.get("pid"):
                emb_status = "starting" if _pid_running(state_info["pid"]) else "stopped"
            else:
                emb_status = "stopped"
    else:
        emb_status = "off"

    # 2. Check MinerU
    mineru_mode = settings.mineru_mode
    mineru_url = settings.mineru_api_url
    mineru_status = "stopped"
    
    if settings.pdf_parser == "mineru" or settings.pdf_parser == "auto":
        if mineru_mode == "external":
            mineru_status = "running" if probe_mineru_health(mineru_url) else "stopped"
        elif mineru_mode == "off":
            mineru_status = "off"
        elif mineru_mode == "managed":
            is_alive = probe_mineru_health(mineru_url)
            state_info = state.get("mineru", {})
            if is_alive:
                mineru_status = "running"
            elif settings.mineru_backend == "docker":
                # Check if container is running
                if shutil.which("docker"):
                    try:
                        res = subprocess.run(
                            ["docker", "ps", "--filter", "name=mineru-api", "--format", "{{.Names}}"],
                            capture_output=True, text=True, check=True
                        )
                        if "mineru-api" in res.stdout:
                            mineru_status = "starting"
                        else:
                            mineru_status = "stopped"
                    except Exception:
                        mineru_status = "stopped"
                else:
                    mineru_status = "stopped"
            elif state_info.get("pid"):
                mineru_status = "starting" if _pid_running(state_info["pid"]) else "stopped"
            else:
                mineru_status = "stopped"
    else:
        mineru_status = "off"

    return {
        "embedding": {
            "mode": emb_mode if settings.embedding_provider == "local" else "openai/none",
            "status": emb_status,
            "url": emb_url,
            "pid": state.get("embedding", {}).get("pid"),
            "model": settings.local_embedding_model,
            "device": settings.local_embedding_device
        },
        "mineru": {
            "mode": mineru_mode,
            "status": mineru_status,
            "url": mineru_url,
            "backend": settings.mineru_backend,
            "gpu": settings.mineru_gpu,
            "pid": state.get("mineru", {}).get("pid")
        }
    }

def start_services(settings: Settings, gpu: bool = False):
    """Start local managed services if configured and stopped."""
    state = load_services_state(settings)
    
    # Apply GPU override configurations
    if gpu:
        settings.mineru_gpu = True
        settings.local_embedding_device = "cuda"
        os.environ["MNEMOSYNE_MINERU_GPU"] = "true"
        os.environ["MNEMOSYNE_LOCAL_EMBEDDING_DEVICE"] = "cuda"

    # Ensure directories exist
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    logs_dir = settings.data_dir / "runtime" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    # 1. Start Local Embedding Server (if provider=local, mode=managed)
    if settings.embedding_provider == "local" and settings.local_embedding_mode == "managed":
        emb_url = settings.local_embedding_url
        parsed = urllib.parse.urlparse(emb_url)
        emb_host = parsed.hostname or "127.0.0.1"
        emb_port = parsed.port or 8010
        
        # Check if already running
        if probe_embedding_health(emb_url):
            logger.info(f"Local embedding server is already running at {emb_url}. Reusing it.")
        else:
            if is_port_in_use(emb_port, emb_host):
                raise RuntimeError(
                    f"Port {emb_port} is already in use by another process. "
                    "Cannot start local embedding server."
                )
            
            # Start uvicorn server in subprocess using current python interpreter
            log_file = logs_dir / "embedding.log"
            log_fh = open(log_file, "a", encoding="utf-8")
            
            cmd = [
                sys.executable, "-m", "knowcran.cli", "embedding-server",
                "--host", emb_host,
                "--port", str(emb_port),
                "--model", settings.local_embedding_model,
                "--device", settings.local_embedding_device,
                "--batch-size", str(settings.local_embedding_batch_size),
            ]
            
            logger.info(f"Starting managed local embedding server: {' '.join(cmd)}")
            creation_flags = 0
            if os.name == "nt":
                creation_flags = 0x08000000  # CREATE_NO_WINDOW
                
            env = os.environ.copy()
            env["MNEMOSYNE_LOCAL_EMBEDDING_MODEL"] = settings.local_embedding_model
            env["MNEMOSYNE_LOCAL_EMBEDDING_DEVICE"] = settings.local_embedding_device
            env["MNEMOSYNE_LOCAL_EMBEDDING_BATCH_SIZE"] = str(settings.local_embedding_batch_size)
            
            proc = subprocess.Popen(
                cmd,
                stdout=log_fh,
                stderr=log_fh,
                env=env,
                creationflags=creation_flags
            )
            
            # Wait for startup
            logger.info("Waiting for local embedding server to become responsive...")
            success = False
            startup_timeout = max(1, int(settings.local_embedding_startup_timeout_seconds))
            for _ in range(startup_timeout):
                if probe_embedding_health(emb_url):
                    success = True
                    break
                time.sleep(1)
                
            if not success:
                # Terminate on timeout
                proc.terminate()
                raise RuntimeError(
                    f"Local embedding server failed to respond within {startup_timeout} seconds. "
                    f"Check logs in {log_file} for details."
                )
                
            logger.info("Local embedding server is online.")
            state["embedding"] = {
                "mode": "managed",
                "pid": proc.pid,
                "url": emb_url,
                "status": "running"
            }
            save_services_state(settings, state)

    # 2. Start MinerU Service (if parser=mineru/auto, mode=managed)
    if (settings.pdf_parser in ("mineru", "auto")) and settings.mineru_mode == "managed":
        mineru_url = settings.mineru_api_url
        parsed = urllib.parse.urlparse(mineru_url)
        mineru_host = parsed.hostname or "127.0.0.1"
        mineru_port = parsed.port or 8000
        
        if probe_mineru_health(mineru_url):
            logger.info(f"MinerU API is already running at {mineru_url}. Reusing it.")
        else:
            if is_port_in_use(mineru_port, mineru_host):
                raise RuntimeError(
                    f"Port {mineru_port} is already in use by another process. "
                    "Cannot start MinerU API server."
                )
                
            manager = MinerUManager(
                settings=settings,
                api_url=mineru_url,
                gpu=settings.mineru_gpu,
                workers=settings.mineru_workers
            )
            
            pid = None
            if settings.mineru_backend == "docker":
                manager.start_docker()
            elif settings.mineru_backend == "subprocess":
                log_file = logs_dir / "mineru.log"
                pid = manager.start_subprocess(log_file)
            else:
                raise ValueError(f"Unknown MinerU backend: {settings.mineru_backend}")
                
            startup_timeout = max(1, int(settings.mineru_startup_timeout_seconds))
            logger.info(f"Waiting for MinerU API to become responsive (timeout: {startup_timeout}s)...")
            success = False
            for _ in range(startup_timeout):
                if probe_mineru_health(mineru_url):
                    success = True
                    break
                time.sleep(1)
                
            if not success:
                # Cleanup on failure
                if settings.mineru_backend == "docker":
                    manager.stop_docker()
                elif pid:
                    manager.stop_subprocess(pid)
                raise RuntimeError(f"MinerU API server failed to respond within {startup_timeout} seconds.")
                
            logger.info("MinerU API is online.")
            state["mineru"] = {
                "mode": "managed",
                "backend": settings.mineru_backend,
                "url": mineru_url,
                "status": "running"
            }
            if pid:
                state["mineru"]["pid"] = pid
            save_services_state(settings, state)

def stop_services(settings: Settings):
    """Stop any managed local services that are running."""
    state = load_services_state(settings)
    
    # 1. Stop Embedding Server
    emb_info = state.get("embedding", {})
    if emb_info.get("mode") == "managed" and emb_info.get("pid"):
        pid = emb_info["pid"]
        logger.info(f"Stopping managed local embedding server (PID {pid})...")
        try:
            _terminate_pid(pid)
        except ProcessLookupError:
            pass
        except Exception as e:
            logger.error(f"Error stopping embedding server: {e}")
            
    # 2. Stop MinerU Service
    mineru_info = state.get("mineru", {})
    if mineru_info.get("mode") == "managed":
        backend = mineru_info.get("backend", settings.mineru_backend)
        if backend == "docker":
            manager = MinerUManager(
                settings=settings,
                api_url=mineru_info.get("url", settings.mineru_api_url),
                gpu=settings.mineru_gpu
            )
            manager.stop_docker()
        elif backend == "subprocess" and mineru_info.get("pid"):
            manager = MinerUManager(
                settings=settings,
                api_url=mineru_info.get("url", settings.mineru_api_url),
                gpu=settings.mineru_gpu
            )
            manager.stop_subprocess(mineru_info["pid"])

    # Clear state file
    state_path = get_state_file_path(settings)
    if state_path.exists():
        try:
            state_path.unlink()
        except Exception:
            pass
    logger.info("All managed local services stopped.")

def ensure_services(settings: Settings, gpu: bool = False):
    """Ensure that required managed local services are running."""
    # This automatically invokes start_services, which reuses active runs
    start_services(settings, gpu=gpu)
