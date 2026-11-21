"""Run a child process under a watchdog.

Long Kaggle jobs have frozen and been killed without a trace before. Every long step therefore
runs as a child whose output is forwarded line by line; a child that stays silent for too long,
or outlives its deadline, gets its Python stacks dumped (``faulthandler`` on SIGUSR1) and is
killed together with its whole process group.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

POLL_SECONDS = 5.0  # how often the watchdog looks at the child
DUMP_GRACE_SECONDS = 10.0  # time the child gets to print its stacks before it is killed


def enable_stack_dumps() -> None:
    """Call in a child so the watchdog's SIGUSR1 prints every thread's stack instead of killing."""
    import faulthandler  # noqa: PLC0415

    faulthandler.register(signal.SIGUSR1, all_threads=True)


def run_watched(
    cmd: list[str],
    env: dict[str, str],
    stall_s: float,
    kill_at: float,
    *,
    cwd: str | None = None,
    log: Path | None = None,
    prefix: str = "",
) -> str:
    """Run ``cmd``; return "ok" or the reason it ended. Silence longer than ``stall_s`` is a stall.

    Output goes to stdout (each line prefixed with ``prefix``) and, if given, to ``log``.
    """
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
        bufsize=1,
        env=env,
        cwd=cwd,
        start_new_session=True,
    )
    last_output = [time.time()]
    handle = log.open("a") if log is not None else None

    def pump() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            sys.stdout.write(prefix + line)
            sys.stdout.flush()
            if handle is not None:
                handle.write(line)
                handle.flush()
            last_output[0] = time.time()

    reader = threading.Thread(target=pump, daemon=True)
    reader.start()
    reason = ""
    try:
        while proc.poll() is None:
            time.sleep(POLL_SECONDS)
            silent = time.time() - last_output[0]
            if silent > stall_s:
                reason = f"no output for {silent / 60:.0f} min"
            elif time.time() > kill_at:
                reason = "hard time limit"
            if reason:
                print(f"{prefix}[watchdog] {reason}: dumping stacks, then killing", flush=True)
                try:
                    os.kill(proc.pid, signal.SIGUSR1)
                    time.sleep(DUMP_GRACE_SECONDS)
                    os.killpg(proc.pid, signal.SIGKILL)  # the whole group: workers too
                except ProcessLookupError:
                    pass
                proc.wait()
        reader.join(timeout=10)
    finally:
        if handle is not None:
            handle.close()
    if reason:
        return reason
    return "ok" if proc.returncode == 0 else f"exit code {proc.returncode}"
