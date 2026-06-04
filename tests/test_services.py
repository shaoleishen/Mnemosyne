import json
import socket
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import httpx

from knowcran.config import Settings
from knowcran.services.manager import (
    is_port_in_use,
    probe_health,
    probe_embedding_health,
    probe_mineru_health,
    start_services,
    stop_services,
    get_services_status,
    get_state_file_path,
)
from knowcran.embeddings import EmbeddingProvider

def test_is_port_in_use():
    # Find an open port
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    
    # It should not be in use
    assert not is_port_in_use(port)
    
    # Now keep it open and check again
    s2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s2.bind(("127.0.0.1", port))
    s2.listen(1)
    assert is_port_in_use(port)
    s2.close()

@patch("httpx.get")
def test_probe_health(mock_get):
    mock_get.return_value = MagicMock(status_code=200)
    assert probe_health("http://localhost:8010", "health")
    mock_get.assert_called_with("http://localhost:8010/health", timeout=1.5)

    mock_get.return_value = MagicMock(status_code=500)
    assert not probe_health("http://localhost:8010", "health")

    mock_get.side_effect = Exception("error")
    assert not probe_health("http://localhost:8010", "health")

@patch("httpx.get")
def test_probe_embedding_health_strips_openai_v1_base(mock_get):
    mock_get.return_value = MagicMock(status_code=200)
    assert probe_embedding_health("http://localhost:8010/v1")
    mock_get.assert_called_with("http://localhost:8010/health", timeout=1.5)

@patch("httpx.get")
def test_probe_mineru_health_requires_mineru_endpoint(mock_get):
    health_response = MagicMock(status_code=404)
    openapi_response = MagicMock(status_code=200)
    openapi_response.json.return_value = {"paths": {"/file_parse": {}}}
    mock_get.side_effect = [health_response, openapi_response]

    assert probe_mineru_health("http://localhost:8000")

@patch("subprocess.run")
@patch("knowcran.services.manager.probe_mineru_health")
@patch("knowcran.services.manager.is_port_in_use")
def test_start_mineru_docker(mock_in_use, mock_probe, mock_run, tmp_path):
    settings = Settings(
        data_dir=tmp_path,
        pdf_parser="mineru",
        mineru_mode="managed",
        mineru_backend="docker",
        mineru_api_url="http://127.0.0.1:8000",
        embedding_provider="none",  # Avoid starting embedding server in this test
        mineru_gpu=False,
    )
    
    mock_in_use.return_value = False
    # Mock probe: false initially, then true on second call
    mock_probe.side_effect = [False, True]
    
    # Configure mock_run for docker images check and docker compose up
    mock_img_check = MagicMock()
    mock_img_check.stdout = "mineru:latest"
    mock_compose_up = MagicMock()
    mock_compose_up.stdout = "success"
    mock_run.side_effect = [mock_img_check, mock_compose_up]
    
    # We mock shutil.which to say docker exists
    with patch("shutil.which", return_value="/usr/bin/docker"):
        start_services(settings)
        
    # Check that compose file was generated
    compose_file = tmp_path / "runtime" / "mineru" / "docker-compose.yml"
    assert compose_file.exists()
    content = compose_file.read_text()
    assert "image: mineru:latest" in content
    assert "container_name: mineru-api" in content

    # Check subprocess command
    assert mock_run.call_count == 2
    args = mock_run.call_args_list[1][0][0]
    assert args == ["docker", "compose", "-f", str(compose_file), "up", "-d"]

@patch("subprocess.Popen")
@patch("knowcran.services.manager.probe_embedding_health")
@patch("knowcran.services.manager.is_port_in_use")
def test_start_embedding_managed(mock_in_use, mock_probe, mock_popen, tmp_path):
    settings = Settings(
        data_dir=tmp_path,
        embedding_provider="local",
        local_embedding_mode="managed",
        local_embedding_url="http://127.0.0.1:8010/v1",
        mineru_mode="off",  # Avoid starting MinerU server in this test
    )
    
    mock_in_use.return_value = False
    mock_probe.side_effect = [False, True]
    
    mock_proc = MagicMock()
    mock_proc.pid = 9999
    mock_popen.return_value = mock_proc
    
    start_services(settings)
    
    # Verify state saved
    state_file = get_state_file_path(settings)
    assert state_file.exists()
    state = json.loads(state_file.read_text())
    assert state["embedding"]["pid"] == 9999
    assert state["embedding"]["url"] == "http://127.0.0.1:8010/v1"

@patch("psutil.Process")
def test_stop_services(mock_process, tmp_path):
    settings = Settings(
        data_dir=tmp_path,
        embedding_provider="local",
        local_embedding_mode="managed",
        local_embedding_url="http://127.0.0.1:8010/v1"
    )
    
    # Create services state file
    state_file = get_state_file_path(settings)
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps({
        "embedding": {
            "mode": "managed",
            "pid": 9999,
            "url": "http://127.0.0.1:8010/v1",
            "status": "running"
        }
    }))
    
    mock_proc = MagicMock()
    mock_process.return_value = mock_proc
    
    stop_services(settings)
    
    mock_proc.terminate.assert_called_once()
    assert not state_file.exists()
