"""Tests for LLM provider abstraction."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from knowcran.config import Settings
from knowcran.llm.base import LLMProviderError, LLMValidationError
from knowcran.llm.claw_provider import ClawLLMProvider, _extract_json
from knowcran.llm.fake_provider import FakeLLMProvider
from knowcran.llm.factory import create_provider


class TestExtractJson:
    """Tests for JSON extraction from LLM output."""

    def test_direct_json_parse(self):
        data = {"key": "value", "number": 42}
        assert _extract_json(json.dumps(data)) == data

    def test_json_with_surrounding_text(self):
        data = {"paper_id": "123", "is_relevant": True}
        text = f"Here is the result:\n{json.dumps(data)}\nDone."
        assert _extract_json(text) == data

    def test_json_with_markdown_fence(self):
        data = {"result": "ok"}
        text = f"```json\n{json.dumps(data)}\n```"
        # This should still find the JSON since { is present
        assert _extract_json(text) == data

    def test_no_json_raises_validation_error(self):
        with pytest.raises(LLMValidationError, match="No JSON object found"):
            _extract_json("This has no JSON at all")

    def test_non_dict_json_raises_validation_error(self):
        with pytest.raises(LLMValidationError, match="No JSON object found"):
            _extract_json('[1, 2, 3]')

    def test_malformed_json_raises_validation_error(self):
        with pytest.raises(LLMValidationError):
            _extract_json('{"key": "value", "broken":}')

    def test_nested_json_object(self):
        data = {"outer": {"inner": [1, 2, 3]}, "flag": True}
        assert _extract_json(json.dumps(data)) == data


class TestFakeLLMProvider:
    """Tests for FakeLLMProvider."""

    def test_is_available(self):
        provider = FakeLLMProvider()
        assert provider.is_available() is True

    def test_returns_configured_response(self):
        response = {"paper_id": "123", "is_relevant": True, "score": 0.9}
        provider = FakeLLMProvider(responses={"rerank": response})
        result = provider.call("some prompt", task_type="rerank")
        assert result == response

    def test_records_calls(self):
        provider = FakeLLMProvider()
        provider.call("prompt1", task_type="task1")
        provider.call("prompt2", task_type="task2")
        assert len(provider.calls) == 2
        assert provider.calls[0]["task_type"] == "task1"
        assert provider.calls[1]["prompt"] == "prompt2"

    def test_default_response_when_no_config(self):
        provider = FakeLLMProvider()
        result = provider.call("prompt", task_type="unknown")
        assert result["status"] == "ok"


class TestClawLLMProvider:
    """Tests for ClawLLMProvider (subprocess-based, no live calls)."""

    def test_command_construction(self):
        provider = ClawLLMProvider(
            claw_bin="/usr/bin/claw",
            model="sonnet",
            permission_mode="read-only",
        )
        cmd = provider._build_command("test prompt")
        assert cmd == [
            "/usr/bin/claw",
            "--model", "sonnet",
            "--permission-mode", "read-only",
            "--output-format", "json",
            "prompt", "test prompt",
        ]

    def test_is_available_with_existing_binary(self, tmp_path):
        fake_bin = tmp_path / "claw"
        fake_bin.write_text("#!/bin/sh")
        provider = ClawLLMProvider(claw_bin=str(fake_bin))
        assert provider.is_available() is True

    def test_is_available_with_missing_binary(self):
        provider = ClawLLMProvider(claw_bin="/nonexistent/path/claw")
        assert provider.is_available() is False

    def test_successful_call(self, tmp_path):
        fake_bin = tmp_path / "claw"
        fake_bin.write_text("#!/bin/sh")
        response = {"result": "ok", "paper_id": "abc"}

        provider = ClawLLMProvider(claw_bin=str(fake_bin), max_retries=0)

        with patch("knowcran.llm.claw_provider.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout=json.dumps(response), stderr=""
            )
            result = provider.call("test prompt")
            assert result == response
            assert mock_run.call_count == 1

    def test_nonzero_exit_raises_error(self, tmp_path):
        fake_bin = tmp_path / "claw"
        fake_bin.write_text("#!/bin/sh")

        provider = ClawLLMProvider(claw_bin=str(fake_bin), max_retries=0)

        with patch("knowcran.llm.claw_provider.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr="Error: API key invalid"
            )
            with pytest.raises(LLMProviderError, match="API key invalid"):
                provider.call("test")

    def test_timeout_raises_error(self, tmp_path):
        fake_bin = tmp_path / "claw"
        fake_bin.write_text("#!/bin/sh")

        provider = ClawLLMProvider(claw_bin=str(fake_bin), max_retries=0, timeout_seconds=5)

        with patch("knowcran.llm.claw_provider.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="claw", timeout=5)
            with pytest.raises(LLMProviderError, match="timed out"):
                provider.call("test")

    def test_malformed_json_raises_validation_error(self, tmp_path):
        fake_bin = tmp_path / "claw"
        fake_bin.write_text("#!/bin/sh")

        provider = ClawLLMProvider(claw_bin=str(fake_bin), max_retries=0)

        with patch("knowcran.llm.claw_provider.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="This is not JSON", stderr=""
            )
            with pytest.raises(LLMValidationError):
                provider.call("test")

    def test_empty_output_raises_error(self, tmp_path):
        fake_bin = tmp_path / "claw"
        fake_bin.write_text("#!/bin/sh")

        provider = ClawLLMProvider(claw_bin=str(fake_bin), max_retries=0)

        with patch("knowcran.llm.claw_provider.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )
            with pytest.raises(LLMProviderError, match="empty output"):
                provider.call("test")

    def test_retry_on_failure(self, tmp_path):
        fake_bin = tmp_path / "claw"
        fake_bin.write_text("#!/bin/sh")
        response = {"ok": True}

        provider = ClawLLMProvider(claw_bin=str(fake_bin), max_retries=2)

        with patch("knowcran.llm.claw_provider.subprocess.run") as mock_run, \
             patch("knowcran.llm.claw_provider.time.sleep"):
            # First two calls fail, third succeeds
            mock_run.side_effect = [
                subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="fail1"),
                subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="fail2"),
                subprocess.CompletedProcess(args=[], returncode=0, stdout=json.dumps(response), stderr=""),
            ]
            result = provider.call("test")
            assert result == response
            assert mock_run.call_count == 3


class TestCreateProvider:
    """Tests for the provider factory."""

    def test_none_provider_returns_none(self, monkeypatch):
        monkeypatch.delenv("MNEMOSYNE_LLM_PROVIDER", raising=False)
        monkeypatch.delenv("MNEMOSYNE_CLAW_BIN", raising=False)
        settings = Settings(llm_provider="none")
        assert create_provider(settings) is None

    def test_claw_provider_without_bin_raises(self):
        settings = Settings(llm_provider="claw", claw_bin=None)
        with pytest.raises(LLMProviderError, match="no Claw binary found"):
            create_provider(settings)

    def test_unknown_provider_raises(self):
        settings = Settings(llm_provider="unknown_provider")
        with pytest.raises(LLMProviderError, match="Unknown LLM provider"):
            create_provider(settings)
