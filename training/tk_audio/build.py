"""Build the Turkmen bona fide / spoof speech set (designed for a Kaggle GPU session).

    python -m training.tk_audio.build --budget-min 210
    python -m training.tk_audio.build --out out --work work --ts-videos 3 --ts-per-video 2 \\
        --cv-parts dev --cv-per-speaker 3 --only sources,resynth,mms     # small CPU trial

Steps: download real speech -> plan the fakes -> run every generator -> check a sample with ASR
-> write ``manifest.csv``. Lessons from earlier lost runs are built in:

* every generator is a separate child process under a watchdog (``training.proc``), some in
  their own virtualenv, so one crash, hang or dependency conflict cannot take the others down;
* every clip is recorded the moment it is written and a restarted generator skips finished
  clips, so a failed step is simply run once more;
* each generator's audio is archived into the output directory as soon as that generator
  finishes, and the manifest and report are written even when the run is cut short.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import tarfile
import threading
import time
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

from training import proc
from training.tk_audio.common import HELD_OUT, SPLITS, read_jsonl
from training.tk_audio.plan import MMS_SCRATCH, PlanConfig, describe, make_plan

MANIFEST_COLUMNS = [
    *("id", "file", "label", "generator", "kind", "source", "group", "split", "parent"),
    *("ref_group", "duration", "native_sr", "rms", "peak", "text"),
]
PRODUCES = {  # stage -> generator directories it fills
    "sources": ("real_cv", "real_ts"),
    "resynth": ("rs_hifigan", "rs_univnet", "rs_encodec", "rs_dac", "rs_mimi"),
    "mms": ("tts_mms",),
    "knnvc": ("vc_knnvc", "tts_mms_knnvc"),
    "vocos": ("rs_vocos",),
    "voxcpm": ("tts_voxcpm_anadil",),
    "omnivoice": ("tts_omnivoice",),
}
EXTRA_PACKAGES = {
    "vocos": ["vocos"],
    "voxcpm": ["voxcpm", "safetensors", "soundfile"],
    "omnivoice": ["omnivoice"],
}
RESERVE_S = 8 * 60.0  # kept back for the manifest, the report and the last archives


class Builder:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.out: Path = args.out.resolve()
        self.work: Path = args.work.resolve()
        self.started = time.time()
        self.deadline = self.started + args.budget_min * 60.0
        self.only = {s for s in args.only.split(",") if s}
        self.lock = threading.Lock()
        self.report: dict[str, object] = {
            "started": time.strftime("%Y-%m-%d %H:%M:%S"),
            "args": {k: str(v) for k, v in vars(args).items()},
            "stages": {},
        }
        for path in (self.out / "logs", self.out / "meta", self.out / "plan", self.work / "audio"):
            path.mkdir(parents=True, exist_ok=True)
        self.env = {
            "HF_HOME": str(self.work / "hf"),
            "TORCH_HOME": str(self.work / "torch"),
            "TOKENIZERS_PARALLELISM": "false",
            "HF_HUB_DISABLE_PROGRESS_BARS": "1",
            **os.environ,
            "PYTHONPATH": os.pathsep.join(p for p in sys.path if p),
            "PYTHONUNBUFFERED": "1",
            "TK_OUT": str(self.out),
            "TK_WORK": str(self.work),
        }

    # --- running steps -------------------------------------------------------------------

    def wants(self, name: str) -> bool:
        return not self.only or name in self.only

    def save_report(self) -> None:
        with self.lock:
            self.report["elapsed_min"] = round((time.time() - self.started) / 60, 1)
            text = json.dumps(self.report, indent=1, ensure_ascii=False)
            (self.out / "report.json").write_text(text)

    def stage(
        self,
        name: str,
        cmd: list[str],
        minutes: float,
        gpu: int | None = None,
        retries: int = 1,
    ) -> bool:
        """Run one step under the watchdog; a failed step is resumed ``retries`` times."""
        outcome = "skipped: time budget"
        attempts: list[dict[str, object]] = []
        for attempt in range(retries + 1):
            now = time.time()
            soft = min(now + minutes * 60.0, self.deadline - RESERVE_S)
            if soft - now < 120:
                break
            env = {**self.env, "TK_DEADLINE": str(soft)}
            if gpu is not None:
                env["CUDA_VISIBLE_DEVICES"] = str(gpu)
            print(
                f"===== {name}: start (attempt {attempt}, {(soft - now) / 60:.0f} min)", flush=True
            )
            outcome = proc.run_watched(
                cmd,
                env,
                self.args.stall_min * 60.0,
                soft + 5 * 60.0,
                log=self.out / "logs" / f"{name}.txt",
                prefix=f"{name}| ",
            )
            took = round((time.time() - now) / 60, 1)
            attempts.append({"outcome": outcome, "minutes": took})
            print(f"===== {name}: {outcome} in {took} min", flush=True)
            if outcome in ("ok", "hard time limit"):  # out of time is not worth a retry
                break
        with self.lock:
            stages = self.report["stages"]
            assert isinstance(stages, dict)
            stages[name] = {"outcome": outcome, "attempts": attempts}
        self.save_report()
        return outcome == "ok"

    def module(self, name: str, python: str = sys.executable, *extra: str) -> list[str]:
        return [python, "-u", "-m", f"training.tk_audio.{name}", *extra]

    def virtualenv(self, name: str) -> str | None:
        """An environment that sees the image's packages; extras are installed into it only."""
        path = self.work / "venvs" / name
        python = str(path / "bin" / "python")
        create = [sys.executable, "-m", "venv", "--system-site-packages", str(path)]
        if not self.stage(f"venv_{name}", create, 5, retries=0):
            install = [sys.executable, "-m", "pip", "install", "-q", "virtualenv"]
            self.stage(f"virtualenv_{name}", install, 5, retries=0)
            create = [sys.executable, "-m", "virtualenv", "--system-site-packages", str(path)]
            if not self.stage(f"venv2_{name}", create, 5, retries=0):
                return None
        pip = [python, "-m", "pip", "install", "-q", "--no-input", *EXTRA_PACKAGES[name]]
        return python if self.stage(f"pip_{name}", pip, 25) else None

    def generate(self, name: str, minutes: float, gpu: int | None) -> None:
        if not self.wants(name):
            return
        python: str | None = sys.executable
        if name in EXTRA_PACKAGES:
            python = self.virtualenv(name)
        if python is not None:
            self.stage(name, self.module(f"gen_{name}", python), minutes, gpu)
        self.archive(name)

    def archive(self, stage: str) -> None:
        """Pack each finished generator directory into the output directory right away."""
        for name in PRODUCES[stage]:
            source = self.work / "audio" / name
            if not source.is_dir() or not any(source.iterdir()):
                continue
            partial = self.out / f"audio_{name}.tar.part"
            with tarfile.open(partial, "w") as tar:
                tar.add(source, arcname=name)
            partial.replace(self.out / f"audio_{name}.tar")
            size = (self.out / f"audio_{name}.tar").stat().st_size / 1e6
            print(f"[archive] audio_{name}.tar {size:.0f} MB", flush=True)

    # --- the build -----------------------------------------------------------------------

    def run(self) -> None:
        args = self.args
        gpus = _gpu_count()
        self.report["gpus"] = gpus
        print(f"[build] out={self.out} work={self.work} gpus={gpus}", flush=True)
        if self.wants("sources"):
            flags = ["--ts-videos", str(args.ts_videos), "--ts-per-video", str(args.ts_per_video)]
            flags += ["--cv-parts", args.cv_parts, "--cv-per-speaker", str(args.cv_per_speaker)]
            self.stage("sources", self.module("sources", sys.executable, *flags), 45)
            self.archive("sources")

        real = read_jsonl(self.out / "meta" / "real_cv.jsonl")
        real += read_jsonl(self.out / "meta" / "real_ts.jsonl")
        if not real:
            raise RuntimeError("no real speech was downloaded; nothing to build")
        plan = make_plan(real, PlanConfig())
        for name, jobs in plan.items():
            (self.out / "plan" / f"{name}.json").write_text(json.dumps(jobs, ensure_ascii=False))
        self.report["plan"] = describe(plan)
        self.report["plan_config"] = asdict(PlanConfig())
        print(f"[plan] {len(real)} real clips -> {json.dumps(describe(plan))}", flush=True)
        self.save_report()

        first = 0 if gpus else None
        second = 1 if gpus > 1 else first

        def fast_lane() -> None:
            self.generate("resynth", 70, first)
            self.generate("mms", 25, first)
            self.generate("knnvc", 50, first)
            self.generate("vocos", 15, first)

        def slow_lane() -> None:
            self.generate("voxcpm", args.voxcpm_min, second)
            self.generate("omnivoice", args.omnivoice_min, second)

        if gpus > 1:  # one lane per GPU; on a single device they would fight for memory
            lanes = [threading.Thread(target=lane) for lane in (fast_lane, slow_lane)]
            for lane in lanes:
                lane.start()
            for lane in lanes:
                lane.join()
        else:
            fast_lane()
            slow_lane()

        if self.wants("asr"):
            check = self.module("check_asr", sys.executable, "--per-generator", str(args.asr_n))
            self.stage("asr", check, 20, first, retries=0)

    def finish(self) -> None:
        """Manifest, summary and listening samples from whatever exists; safe to call any time."""
        rows = []
        for path in sorted((self.out / "meta").glob("*.jsonl")):
            if path.stem == MMS_SCRATCH:
                continue
            for row in read_jsonl(path):
                if (self.work / "audio" / row["file"]).is_file():
                    rows.append(row)
        with (self.out / "manifest.csv").open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=MANIFEST_COLUMNS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)

        table: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for row in rows:
            table[row["generator"]][row["split"]] += 1
            table[row["generator"]]["hours"] += row["duration"] / 3600
        summary = {
            name: {**{s: int(c[s]) for s in SPLITS}, "hours": round(c["hours"], 2)}
            for name, c in sorted(table.items())
        }
        leaked = [
            n for n in HELD_OUT if summary.get(n, {}).get("train") or summary.get(n, {}).get("dev")
        ]
        self.report["summary"] = summary
        self.report["clips"] = len(rows)
        self.report["held_out_leak"] = leaked
        check = self.out / "asr_check.json"
        if check.is_file():
            self.report["asr"] = json.loads(check.read_text()).get("scores")

        samples = self.out / "samples"
        seen: dict[str, int] = defaultdict(int)
        for row in rows:
            if seen[row["generator"]] < self.args.samples:
                seen[row["generator"]] += 1
                target = samples / row["file"]
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(self.work / "audio" / row["file"], target)
        self.save_report()
        print(f"[done] {len(rows)} clips; {json.dumps(summary)}", flush=True)
        if leaked:
            raise RuntimeError(f"held-out generators outside the test split: {leaked}")


def _gpu_count() -> int:
    if shutil.which("nvidia-smi") is None:
        return 0
    listing = subprocess.run(["nvidia-smi", "-L"], capture_output=True, text=True, check=False)
    return sum(line.startswith("GPU ") for line in listing.stdout.splitlines())


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    p.add_argument("--out", type=Path, default=Path("/kaggle/working/tkset"))
    p.add_argument("--work", type=Path, default=Path("/tmp/tkset"))
    p.add_argument("--budget-min", type=float, default=210.0, help="whole run, hard limit")
    p.add_argument("--stall-min", type=float, default=15.0, help="silence that counts as a hang")
    p.add_argument("--ts-videos", type=int, default=482)
    p.add_argument("--ts-per-video", type=int, default=10)
    p.add_argument("--cv-parts", default="train,dev,test,other")
    p.add_argument("--cv-per-speaker", type=int, default=120)
    p.add_argument("--voxcpm-min", type=float, default=60.0)
    p.add_argument("--omnivoice-min", type=float, default=35.0)
    p.add_argument("--asr-n", type=int, default=25, help="clips per generator in the ASR check")
    p.add_argument("--samples", type=int, default=3, help="listening samples per generator")
    p.add_argument("--only", default="", help="comma-separated steps to run (default: all)")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    builder = Builder(parse_args(argv))
    try:
        builder.run()
    finally:
        builder.finish()


if __name__ == "__main__":
    main()
