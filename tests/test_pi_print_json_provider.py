"""Tests for Pi print/JSON agent provider."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from knowcran.agents.base import AgentSchemaError
from knowcran.agents.pi_print_json_provider import PiPrintJsonProvider, _extract_json, _unwrap_envelope
from knowcran.agents.schemas import AgentTask


class TestExtractJson:
    def test_direct_json(self):
        data = {"key": "value", "number": 42}
        assert _extract_json(json.dumps(data)) == data

    def test_json_with_surrounding_text(self):
        data = {"result": "ok"}
        text = f"Here is the result:\n{json.dumps(data)}\nDone."
        assert _extract_json(text) == data

    def test_markdown_fenced_json(self):
        data = {"result": "ok"}
        text = f"```json\n{json.dumps(data)}\n```"
        assert _extract_json(text) == data

    def test_no_json_raises(self):
        with pytest.raises(AgentSchemaError, match="No JSON object found"):
            _extract_json("No JSON here")

    def test_malformed_json_raises(self):
        with pytest.raises(AgentSchemaError):
            _extract_json('{"key": "value", "broken":}')


class TestUnwrapEnvelope:
    def test_direct_data(self):
        data = {"decisions": []}
        assert _unwrap_envelope(data) == data

    def test_message_envelope(self):
        inner = {"decisions": [{"paper_id": "p1"}]}
        envelope = {"message": json.dumps(inner)}
        assert _unwrap_envelope(envelope) == inner

    def test_assistant_content_envelope(self):
        inner = {"decisions": []}
        envelope = {"assistant": {"content": json.dumps(inner)}}
        assert _unwrap_envelope(envelope) == inner

    def test_content_envelope(self):
        inner = {"decisions": []}
        envelope = {"content": json.dumps(inner)}
        assert _unwrap_envelope(envelope) == inner

    def test_non_string_message_returns_as_is(self):
        data = {"message": 42}
        assert _unwrap_envelope(data) == data


class TestPiPrintJsonProvider:
    def test_name(self):
        p = PiPrintJsonProvider(pi_bin="/usr/bin/pi")
        assert p.name == "pi-print-json"

    def test_capabilities(self):
        p = PiPrintJsonProvider()
        assert "structured_json" in p.capabilities()
        assert "subprocess" in p.capabilities()

    def test_is_available_with_existing_binary(self, tmp_path):
        fake_bin = tmp_path / "pi"
        fake_bin.write_text("#!/bin/sh")
        p = PiPrintJsonProvider(pi_bin=str(fake_bin))
        assert p.is_available() is True

    def test_is_available_with_missing_binary(self):
        p = PiPrintJsonProvider(pi_bin="/nonexistent/pi")
        assert p.is_available() is False

    def test_command_construction(self):
        p = PiPrintJsonProvider(pi_bin="/usr/bin/pi", model="gemini-2.0-flash")
        cmd = p._build_command()
        assert cmd[0] == "/usr/bin/pi"
        assert "-p" in cmd
        assert "--mode" in cmd
        assert "json" in cmd
        assert "--no-session" in cmd
        assert "--no-tools" in cmd
        assert "--model" in cmd
        assert "gemini-2.0-flash" in cmd

    def test_successful_call(self, tmp_path):
        fake_bin = tmp_path / "pi"
        fake_bin.write_text("#!/bin/sh")
        response = {"decisions": [{"paper_id": "p1", "is_relevant": True, "score": 0.9}]}

        p = PiPrintJsonProvider(pi_bin=str(fake_bin), max_retries=0)

        with patch("knowcran.agents.pi_print_json_provider.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout=json.dumps(response), stderr=""
            )
            task = AgentTask(
                task_id="t1",
                task_type="relevance_rerank",
                topic="ICH",
                input_json={"papers": []},
            )
            result = p.run(task)
            assert result.status == "ok"
            assert result.output_json == response
            assert result.provider_mode == "pi_print_json"

    def test_json_envelope_unwrapped(self, tmp_path):
        fake_bin = tmp_path / "pi"
        fake_bin.write_text("#!/bin/sh")
        inner = {"decisions": []}
        envelope = {"message": json.dumps(inner)}

        p = PiPrintJsonProvider(pi_bin=str(fake_bin), max_retries=0)

        with patch("knowcran.agents.pi_print_json_provider.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout=json.dumps(envelope), stderr=""
            )
            task = AgentTask(task_id="t1", task_type="health_check")
            result = p.run(task)
            assert result.status == "ok"
            assert result.output_json == inner

    def test_nonzero_exit_returns_error(self, tmp_path):
        fake_bin = tmp_path / "pi"
        fake_bin.write_text("#!/bin/sh")

        p = PiPrintJsonProvider(pi_bin=str(fake_bin), max_retries=0)

        with patch("knowcran.agents.pi_print_json_provider.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr="Error: model not found"
            )
            task = AgentTask(task_id="t1", task_type="health_check")
            result = p.run(task)
            assert result.status == "error"
            assert "model not found" in result.error

    def test_timeout_returns_error(self, tmp_path):
        fake_bin = tmp_path / "pi"
        fake_bin.write_text("#!/bin/sh")

        p = PiPrintJsonProvider(pi_bin=str(fake_bin), max_retries=0, timeout_seconds=5)

        with patch("knowcran.agents.pi_print_json_provider.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="pi", timeout=5)
            task = AgentTask(task_id="t1", task_type="health_check")
            result = p.run(task)
            assert result.status == "error"
            assert "timed out" in result.error

    def test_malformed_json_returns_schema_error(self, tmp_path):
        fake_bin = tmp_path / "pi"
        fake_bin.write_text("#!/bin/sh")

        p = PiPrintJsonProvider(pi_bin=str(fake_bin), max_retries=0)

        with patch("knowcran.agents.pi_print_json_provider.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="Not JSON at all", stderr=""
            )
            task = AgentTask(task_id="t1", task_type="health_check")
            result = p.run(task)
            assert result.status == "error"

    def test_retry_on_failure(self, tmp_path):
        fake_bin = tmp_path / "pi"
        fake_bin.write_text("#!/bin/sh")
        response = {"status": "ok"}

        p = PiPrintJsonProvider(pi_bin=str(fake_bin), max_retries=2)

        with patch("knowcran.agents.pi_print_json_provider.subprocess.run") as mock_run, \
             patch("knowcran.agents.pi_print_json_provider.time.sleep"):
            mock_run.side_effect = [
                subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="fail1"),
                subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="fail2"),
                subprocess.CompletedProcess(args=[], returncode=0, stdout=json.dumps(response), stderr=""),
            ]
            task = AgentTask(task_id="t1", task_type="health_check")
            result = p.run(task)
            assert result.status == "ok"
            assert mock_run.call_count == 3

    def test_empty_output_returns_error(self, tmp_path):
        fake_bin = tmp_path / "pi"
        fake_bin.write_text("#!/bin/sh")

        p = PiPrintJsonProvider(pi_bin=str(fake_bin), max_retries=0)

        with patch("knowcran.agents.pi_print_json_provider.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )
            task = AgentTask(task_id="t1", task_type="health_check")
            result = p.run(task)
            assert result.status == "error"
            assert "empty" in result.error
