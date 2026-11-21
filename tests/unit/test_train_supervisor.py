"""The training supervisor must notice a silent worker, kill it and resume from a checkpoint."""

from __future__ import annotations

import os
import sys
import tarfile
import time
from pathlib import Path

import pytest
from training import proc
from training import train_visual as tv

FAR_FUTURE = 4_000_000_000.0


@pytest.fixture(autouse=True)
def _fast_polling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(proc, "POLL_SECONDS", 0.05)
    monkeypatch.setattr(proc, "DUMP_GRACE_SECONDS", 0.3)


def _python(code: str) -> list[str]:
    return [sys.executable, "-u", "-c", code]


def test_child_success_and_output_is_forwarded(capfd: pytest.CaptureFixture[str]) -> None:
    outcome = tv._run_child(_python("print('hello from worker')"), dict(os.environ), 30, FAR_FUTURE)
    assert outcome == "ok"
    assert "hello from worker" in capfd.readouterr().out


def test_child_failure_reports_exit_code() -> None:
    outcome = tv._run_child(_python("raise SystemExit(3)"), dict(os.environ), 30, FAR_FUTURE)
    assert outcome == "exit code 3"


def test_silent_child_is_dumped_and_killed(capfd: pytest.CaptureFixture[str]) -> None:
    code = (
        "import faulthandler, signal, time\n"
        "faulthandler.register(signal.SIGUSR1, all_threads=True)\n"
        "print('started', flush=True)\n"
        "time.sleep(120)\n"
    )
    began = time.time()
    outcome = tv._run_child(_python(code), dict(os.environ), 1.0, FAR_FUTURE)
    assert outcome.startswith("no output")
    assert time.time() - began < 30
    assert "most recent call first" in capfd.readouterr().out


def test_hard_time_limit_kills_a_talkative_child() -> None:
    code = "import time\nwhile True:\n    print('tick', flush=True)\n    time.sleep(0.05)\n"
    outcome = tv._run_child(_python(code), dict(os.environ), 30, time.time() + 0.5)
    assert outcome == "hard time limit"


def _args(tmp_path: Path, *extra: str) -> tuple[list[str], object]:
    argv = ["--ffpp-root", str(tmp_path), "--out", str(tmp_path / "out"), *extra]
    argv += ["--state-dir", str(tmp_path / "state"), "--max-restarts", "3"]
    return argv, tv.parse_args(argv)


def test_supervisor_resumes_until_the_worker_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    argv, args = _args(tmp_path)
    (tmp_path / "state").mkdir()
    calls: list[list[str]] = []

    def fake_child(cmd: list[str], env: dict[str, str], stall_s: float, kill_at: float) -> str:
        calls.append(cmd)
        (tmp_path / "state" / "last.pt").write_bytes(b"x" * len(calls))
        os.utime(tmp_path / "state" / "last.pt", (len(calls) * 100, len(calls) * 100))
        return "ok" if len(calls) == 3 else "no output for 15 min"

    monkeypatch.setattr(tv, "_run_child", fake_child)
    tv.supervise(argv, args)  # type: ignore[arg-type]
    assert len(calls) == 3
    assert "--resume" not in calls[0]
    assert "--resume" in calls[1] and calls[1][-1] == "1"
    assert all("--child" in c for c in calls)


def test_supervisor_stops_retrying_a_persistent_fault_and_evaluates_the_best(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    argv, args = _args(tmp_path)
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "best.pt").write_bytes(b"best")
    calls: list[list[str]] = []

    def fake_child(cmd: list[str], env: dict[str, str], stall_s: float, kill_at: float) -> str:
        calls.append(cmd)
        return "ok" if "--eval-only" in cmd else "exit code 1"

    monkeypatch.setattr(tv, "_run_child", fake_child)
    tv.supervise(argv, args)  # type: ignore[arg-type]
    assert len(calls) == 3  # two fruitless attempts, then the evaluation-only worker
    assert "--eval-only" in calls[-1]


def test_supervisor_fails_loudly_without_any_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    argv, args = _args(tmp_path)
    monkeypatch.setattr(tv, "_run_child", lambda *a: "exit code 1")
    with pytest.raises(SystemExit, match="giving up"):
        tv.supervise(argv, args)  # type: ignore[arg-type]


def test_faces_are_restored_from_an_archive(tmp_path: Path) -> None:
    source = tmp_path / "src" / "faces"
    (source / "train" / "original").mkdir(parents=True)
    (source / "train" / "original" / "000_00001.jpg").write_bytes(b"jpg")
    (source / "manifest.csv").write_text(
        "file,label,method,video,split\ntrain/original/000_00001.jpg,0,original,original/000,train\n"
    )
    archive = tmp_path / "faces.tar"
    with tarfile.open(archive, "w") as tar:
        tar.add(source, arcname="faces")
    _, args = _args(tmp_path, "--faces-tar", str(archive), "--faces-dir", str(tmp_path / "w" / "f"))
    rows = tv.prepare_faces(args)  # type: ignore[arg-type]
    assert [r.video for r in rows] == ["original/000"]
    assert (tmp_path / "w" / "f" / "train" / "original" / "000_00001.jpg").is_file()
