import logging
import os
import subprocess
import shutil
import urllib.parse
import json
from pathlib import Path
from typing import Optional, Any

logger = logging.getLogger(__name__)

COMPOSE_TEMPLATE = """version: '3.8'

services:
  mineru-api:
    image: mineru:latest
    container_name: mineru-api
    restart: always
    ports:
      - "{port}:{port}"
    environment:
      - MINERU_MODEL_SOURCE={model_source}
    volumes:
      - "{config_file}:/root/magic-pdf.json"
      - "{models_dir}:/root/models"
    entrypoint: mineru-api
    command: --host 0.0.0.0 --port {port}
{gpu_config}
"""

GPU_CONFIG_TEMPLATE = """    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
"""

class MinerUManager:
    def __init__(self, settings: Any, api_url: str, gpu: bool = False, workers: int = 1):
        self.settings = settings
        self.data_dir = Path(settings.data_dir)
        self.runtime_dir = self.data_dir / "runtime" / "mineru"
        self.api_url = api_url
        self.gpu = gpu
        self.workers = workers
        self.process: Optional[subprocess.Popen] = None

        # Resolve mount paths from settings
        self.models_dir = Path(getattr(settings, "mineru_models_dir", self.data_dir / "models" / "mineru"))
        self.config_file = Path(getattr(settings, "mineru_config_file", self.data_dir / "mineru" / "magic-pdf.json"))

        # Parse host and port from api_url
        parsed = urllib.parse.urlparse(self.api_url)
        self.host = parsed.hostname or "127.0.0.1"
        self.port = parsed.port or 8000

    def get_compose_file_path(self) -> Path:
        return self.runtime_dir / "docker-compose.yml"

    def write_compose_file(self):
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. Ensure magic-pdf.json config file exists on host
        if not self.config_file.exists():
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            default_config = {
                "models-dir": "/root/models",
                "device-mode": "cuda" if self.gpu else "cpu"
            }
            try:
                self.config_file.write_text(json.dumps(default_config, indent=2), encoding="utf-8")
                logger.info(f"Generated default magic-pdf.json on host at: {self.config_file}")
            except Exception as e:
                logger.error(f"Failed to generate magic-pdf.json configuration: {e}")
                
        # 2. Ensure models directory exists on host
        self.models_dir.mkdir(parents=True, exist_ok=True)

        # 3. Format compose template
        gpu_config = GPU_CONFIG_TEMPLATE if self.gpu else ""
        model_source = os.getenv("MINERU_MODEL_SOURCE", "local")
        
        # Docker Compose requires absolute paths or relative to compose file
        # Convert path to absolute or relative to compose directory
        abs_config = str(self.config_file.resolve().as_posix())
        abs_models = str(self.models_dir.resolve().as_posix())

        content = COMPOSE_TEMPLATE.format(
            port=self.port,
            model_source=model_source,
            config_file=abs_config,
            models_dir=abs_models,
            gpu_config=gpu_config
        )
        compose_path = self.get_compose_file_path()
        compose_path.write_text(content, encoding="utf-8")
        logger.info(f"Wrote MinerU compose file to {compose_path}")

    def is_docker_available(self) -> bool:
        return shutil.which("docker") is not None

    def start_docker(self) -> bool:
        if not self.is_docker_available():
            raise RuntimeError("Docker command not found. Please install Docker or set MNEMOSYNE_MINERU_BACKEND=subprocess.")
        
        # Check if docker daemon is running and if the image exists locally
        try:
            img_check = subprocess.run(
                ["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"],
                capture_output=True, text=True, check=True
            )
            if "mineru:latest" not in img_check.stdout:
                raise RuntimeError(
                    "MinerU Docker image 'mineru:latest' was not found locally.\n"
                    "Since OpenDataLab does not host a pre-built image on Docker Hub, "
                    "you must build it locally first:\n\n"
                    "  wget https://gcore.jsdelivr.net/gh/opendatalab/MinerU@master/docker/global/Dockerfile\n"
                    "  docker build -t mineru:latest -f Dockerfile .\n"
                )
        except subprocess.CalledProcessError as e:
            err_msg = (e.stderr or "").lower()
            if "daemon" in err_msg or "connect" in err_msg or "context" in err_msg:
                raise RuntimeError("Docker daemon is not running. Please start the Docker service before launching managed containers.") from e
            logger.warning(f"Failed to check local Docker images: {e.stderr or e}")
        except Exception as e:
            logger.warning(f"Failed to check local Docker images: {e}")

        # Check GPU compatibility if GPU is requested
        if self.gpu:
            try:
                runtime_check = subprocess.run(
                    ["docker", "info", "--format", "{{json .Runtimes}}"],
                    capture_output=True, text=True, check=True
                )
                if "nvidia" not in runtime_check.stdout:
                    raise RuntimeError(
                        "NVIDIA Container Toolkit is not configured in Docker, but GPU acceleration was requested (--gpu or MNEMOSYNE_MINERU_GPU=true).\n"
                        "To use GPU acceleration inside Docker, you must configure the NVIDIA Container Toolkit:\n"
                        "  https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html"
                    )
            except subprocess.CalledProcessError as e:
                logger.warning(f"Failed to check Docker runtimes: {e.stderr or e}")
            except Exception as e:
                logger.warning(f"Failed to check Docker runtimes: {e}")

        self.write_compose_file()
        compose_file = self.get_compose_file_path()
        
        logger.info("Launching MinerU via Docker Compose...")
        cmd = ["docker", "compose", "-f", str(compose_file), "up", "-d"]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.info("Docker Compose output: " + res.stdout)
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to start Docker Compose: {e.stderr}")
            raise RuntimeError(f"Docker Compose failed: {e.stderr}")

    def stop_docker(self):
        compose_file = self.get_compose_file_path()
        if not compose_file.exists():
            return
        
        logger.info("Stopping MinerU via Docker Compose...")
        cmd = ["docker", "compose", "-f", str(compose_file), "down"]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except Exception as e:
            logger.error(f"Failed to stop Docker Compose: {e}")

    def start_subprocess(self, log_file: Path) -> int:
        cmd_path = shutil.which("mineru-api")
        if not cmd_path:
            raise RuntimeError("mineru-api executable not found on PATH. Please install MinerU locally.")
        
        logger.info(f"Launching MinerU via local subprocess: mineru-api --host {self.host} --port {self.port}")
        
        # Ensure log directory exists
        log_file.parent.mkdir(parents=True, exist_ok=True)
        log_fh = open(log_file, "a", encoding="utf-8")
        
        cmd = ["mineru-api", "--host", self.host, "--port", str(self.port)]
        
        # In Windows we might want to disable console window popping up
        creation_flags = 0
        if os.name == "nt":
            creation_flags = 0x08000000  # CREATE_NO_WINDOW
            
        self.process = subprocess.Popen(
            cmd,
            stdout=log_fh,
            stderr=log_fh,
            creationflags=creation_flags,
            text=True
        )
        return self.process.pid

    def stop_subprocess(self, pid: int):
        import psutil
        logger.info(f"Stopping MinerU subprocess PID {pid}...")
        try:
            proc = psutil.Process(pid)
            # Terminate process and children
            for child in proc.children(recursive=True):
                child.terminate()
            proc.terminate()
            # Wait a bit
            gone, alive = psutil.wait_procs([proc] + proc.children(), timeout=3)
            for p in alive:
                p.kill()
        except psutil.NoSuchProcess:
            logger.debug(f"PID {pid} not running.")
        except Exception as e:
            logger.error(f"Error stopping PID {pid}: {e}")
