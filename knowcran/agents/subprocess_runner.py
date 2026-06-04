"""Shared subprocess runner with idle timeout support."""

from __future__ import annotations

import logging
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SubprocessResult:
    """Result from a subprocess execution."""
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False
    idle_timed_out: bool = False


def run_with_idle_timeout(
    cmd: list[str],
    idle_timeout_seconds: int = 300,
    hard_timeout_seconds: int = 0,
    env: dict[str, str] | None = None,
    input_data: str | None = None,
) -> SubprocessResult:
    """Run a subprocess with idle timeout support.

    Instead of killing after a fixed wall-clock duration, this tracks
    when the process last produced output. If no output is received
    for `idle_timeout_seconds`, the process is killed.

    Args:
        cmd: Command to run.
        idle_timeout_seconds: Kill if no output for this many seconds.
        hard_timeout_seconds: Optional upper bound (0 = disabled).
        env: Environment variables.
        input_data: Data to send via stdin.

    Returns:
        SubprocessResult with stdout, stderr, and timeout status.
    """
    start_time = time.time()
    last_activity = time.time()
    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []
    stdout_lock = threading.Lock()
    stderr_lock = threading.Lock()

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE if input_data else None,
            env=env,
            text=True,
        )
    except Exception as e:
        return SubprocessResult(
            returncode=-1,
            stdout="",
            stderr=str(e),
        )

    def read_stdout():
        nonlocal last_activity
        try:
            while True:
                line = proc.stdout.readline()  # type: ignore
                if not line:
                    break
                with stdout_lock:
                    stdout_chunks.append(line)
                last_activity = time.time()
        except Exception:
            pass

    def read_stderr():
        nonlocal last_activity
        try:
            while True:
                line = proc.stderr.readline()  # type: ignore
                if not line:
                    break
                with stderr_lock:
                    stderr_chunks.append(line)
                last_activity = time.time()
        except Exception:
            pass

    stdout_thread = threading.Thread(target=read_stdout, daemon=True)
    stderr_thread = threading.Thread(target=read_stderr, daemon=True)
    stdout_thread.start()
    stderr_thread.start()

    # Send input data if provided
    if input_data and proc.stdin:
        try:
            proc.stdin.write(input_data)
            proc.stdin.close()
        except Exception:
            pass

    # Monitor for timeout
    while proc.poll() is None:
        time.sleep(0.5)
        now = time.time()

        # Check idle timeout
        if idle_timeout_seconds > 0 and (now - last_activity) > idle_timeout_seconds:
            logger.warning("Process idle for %ds, killing", idle_timeout_seconds)
            _kill_process_tree(proc)
            stdout_thread.join(timeout=2)
            stderr_thread.join(timeout=2)
            return SubprocessResult(
                returncode=-1,
                stdout="".join(stdout_chunks),
                stderr="".join(stderr_chunks) + "\n[Idle timeout]",
                idle_timed_out=True,
            )

        # Check hard timeout
        if hard_timeout_seconds > 0 and (now - start_time) > hard_timeout_seconds:
            logger.warning("Process exceeded hard timeout of %ds, killing", hard_timeout_seconds)
            _kill_process_tree(proc)
            stdout_thread.join(timeout=2)
            stderr_thread.join(timeout=2)
            return SubprocessResult(
                returncode=-1,
                stdout="".join(stdout_chunks),
                stderr="".join(stderr_chunks) + "\n[Hard timeout]",
                timed_out=True,
            )

    # Process finished
    stdout_thread.join(timeout=5)
    stderr_thread.join(timeout=5)

    return SubprocessResult(
        returncode=proc.returncode or 0,
        stdout="".join(stdout_chunks),
        stderr="".join(stderr_chunks),
    )


def _kill_process_tree(proc: subprocess.Popen) -> None:
    """Kill a process and all its children."""
    try:
        import signal
        import os

        if os.name == "nt":
            # Windows: use taskkill to kill process tree
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                timeout=5,
            )
        else:
            # Unix: kill process group
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            time.sleep(1)
            if proc.poll() is None:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
