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

def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return False
        except socket.error:
            return True

def probe_health(url: str, endpoint: str = "") -> bool:
    probe_url = url.rstrip("/")
    if endpoint:
        probe_url = f"{probe_url}/{endpoint.lstrip('/')}"
    try:
        # Standard health check endpoint
        res = httpx.get(probe_url, timeout=1.5)
        # 200, 404, or 405 implies the HTTP server is alive and responding
        return res.status_code in (200, 301, 302, 307, 308, 404, 405)
    except Exception:
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
            emb_status = "running" if probe_health(emb_url, "health") else "stopped"
        elif emb_mode == "managed":
            is_alive = probe_health(emb_url, "health")
            state_info = state.get("embedding", {})
            if is_alive:
                emb_status = "running"
            elif state_info.get("pid"):
                # Check if process is still alive
                import psutil
                try:
                    p = psutil.Process(state_info["pid"])
                    if p.is_running():
                        emb_status = "starting"
                    else:
                        emb_status = "stopped"
                except Exception:
                    emb_status = "stopped"
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
            mineru_status = "running" if probe_health(mineru_url) else "stopped"
        elif mineru_mode == "off":
            mineru_status = "off"
        elif mineru_mode == "managed":
            is_alive = probe_health(mineru_url)
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
                import psutil
                try:
                    p = psutil.Process(state_info["pid"])
                    if p.is_running():
                        mineru_status = "starting"
                    else:
                        mineru_status = "stopped"
                except Exception:
                    mineru_status = "stopped"
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
        if probe_health(emb_url, "health"):
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
                "--device", settings.local_embedding_device
            ]
            
            logger.info(f"Starting managed local embedding server: {' '.join(cmd)}")
            creation_flags = 0
            if os.name == "nt":
                creation_flags = 0x08000000  # CREATE_NO_WINDOW
                
            env = os.environ.copy()
            env["MNEMOSYNE_LOCAL_EMBEDDING_MODEL"] = settings.local_embedding_model
            env["MNEMOSYNE_LOCAL_EMBEDDING_DEVICE"] = settings.local_embedding_device
            
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
            for _ in range(30):
                if probe_health(emb_url, "health"):
                    success = True
                    break
                time.sleep(1)
                
            if not success:
                # Terminate on timeout
                proc.terminate()
                raise RuntimeError(
                    "Local embedding server failed to respond within 30 seconds. "
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
        
        if probe_health(mineru_url):
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
                
            logger.info("Waiting for MinerU API to become responsive (this may take up to 90 seconds for model loading)...")
            success = False
            for _ in range(90):
                if probe_health(mineru_url):
                    success = True
                    break
                time.sleep(1)
                
            if not success:
                # Cleanup on failure
                if settings.mineru_backend == "docker":
                    manager.stop_docker()
                elif pid:
                    manager.stop_subprocess(pid)
                raise RuntimeError("MinerU API server failed to respond within 90 seconds.")
                
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
        import psutil
        logger.info(f"Stopping managed local embedding server (PID {pid})...")
        try:
            proc = psutil.Process(pid)
            proc.terminate()
            gone, alive = psutil.wait_procs([proc], timeout=3)
            for p in alive:
                p.kill()
        except psutil.NoSuchProcess:
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
