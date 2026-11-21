"""Fine-tune the audio detector (AASIST) jointly on ASVspoof 2019 LA and the Turkmen set.

Why: the official AASIST weights know only English studio speech and fail on Turkmen. Training
continues from those weights on a mix of ASVspoof 2019 LA (train) and the Turkmen set built by
``training.tk_audio.build``, so the model learns Turkmen without forgetting English.

Shortcuts the data would otherwise teach, and what is done about each:

* loudness (three Turkmen generators are 2-3x louder than real speech): every training clip
  of both classes gets a random level;
* compression history (real Turkmen speech comes from MP3/AAC/Opus, most fakes are clean):
  clips pass through a random lossy codec, fakes more often than real ones;
* class and generator size: batches are drawn evenly from real/fake and from each generator.

Evaluation uses the server's own windowing and aggregation. The model is selected on the mean
of the Turkmen-dev and LA-dev equal error rates; temperature and the verdict band come from
dev; the test split (with two generators never seen in training) and LA eval are only reported.

    python -m training.train_audio --out /kaggle/working --budget-min 240
"""

from __future__ import annotations

import argparse
import copy
import csv
import json
import math
import os
import random
import subprocess
import sys
import tarfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset

from dfd.domain.entities import Thresholds
from dfd.infrastructure.ml import metrics as M
from dfd.infrastructure.ml.audio import SAMPLE_RATE, WINDOW, build_aasist
from dfd.infrastructure.ml.cards import ModelCard, file_sha256, save_card
from training import proc
from training.eval_audio import (
    Item,
    Transform,
    fetch_weights,
    find_root,
    read_protocol,
    score,
    summarise,
    utterance_probs,
)
from training.tk_audio.common import HELD_OUT

Wave = np.ndarray
# (encoder, container, lowest kbit/s, highest kbit/s)
CODECS: tuple[tuple[str, str, int, int], ...] = (
    ("libmp3lame", "mp3", 24, 128),
    ("aac", "adts", 24, 96),
    ("libopus", "ogg", 12, 64),
)
# Calibration of the model deployed before this training (weights/audio/model_card.json):
# temperature, real_max, fake_min. Used only to report "before" verdict rates.
DEPLOYED = (1.4483817680682325, 0.029732425099099635, 0.9900958059668292)


# ----------------------------------------------------------------------------- signal helpers
def fit_length(wave: Wave, size: int) -> Wave:
    """Exactly ``size`` samples: cut the tail, or repeat a short clip (the server does both)."""
    if wave.size >= size:
        return wave[:size]
    return np.tile(wave, math.ceil(size / wave.size))[:size]


def random_crop(wave: Wave, size: int, rng: random.Random) -> Wave:
    if wave.size <= size:
        return fit_length(wave, size)
    start = rng.randrange(wave.size - size + 1)
    return wave[start : start + size]


def set_peak(wave: Wave, target: float) -> Wave:
    peak = float(np.abs(wave).max())
    return wave if peak < 1e-4 else (wave * (target / peak)).astype(np.float32)


def through_codec(wave: Wave, encoder: str, container: str, kbps: int) -> Wave | None:
    """Encode and decode with ffmpeg; None when ffmpeg fails (the caller keeps the original)."""
    raw = ["-f", "s16le", "-ar", str(SAMPLE_RATE), "-ac", "1"]
    ffmpeg = ["ffmpeg", "-v", "quiet"]
    pcm = (np.clip(wave, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()
    encode = [
        *ffmpeg,
        *raw,
        "-i",
        "-",
        "-c:a",
        encoder,
        "-b:a",
        f"{kbps}k",
        "-f",
        container,
        "-",
    ]
    decode = [*ffmpeg, "-i", "-", *raw, "-"]
    try:
        packed = subprocess.run(encode, input=pcm, capture_output=True, timeout=30, check=False)
        plain = subprocess.run(
            decode, input=packed.stdout, capture_output=True, timeout=30, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    data = plain.stdout[: len(plain.stdout) // 2 * 2]
    decoded = np.frombuffer(data, dtype="<i2").astype(np.float32) / 32768.0
    if decoded.size < wave.size // 2:
        return None
    return fit_length(decoded, wave.size)


def as_mp3(wave: Wave) -> Wave:
    coded = through_codec(wave, "libmp3lame", "mp3", 64)
    return wave if coded is None else coded


def available_codecs() -> tuple[tuple[str, str, int, int], ...]:
    """The codecs this machine's ffmpeg can really round-trip."""
    tone = (0.3 * np.sin(np.arange(SAMPLE_RATE) * 2 * np.pi * 440 / SAMPLE_RATE)).astype(np.float32)
    return tuple(c for c in CODECS if through_codec(tone, c[0], c[1], c[3]) is not None)


def augment(
    wave: Wave,
    rng: random.Random,
    codecs: tuple[tuple[str, str, int, int], ...],
    codec_p: float,
    noise_p: float,
) -> Wave:
    """Random codec, random noise, then a random level (always, for both classes)."""
    if codecs and rng.random() < codec_p:
        encoder, container, low, high = rng.choice(codecs)
        coded = through_codec(wave, encoder, container, rng.randint(low, high))
        wave = wave if coded is None else coded
    if rng.random() < noise_p:
        rms = float(np.sqrt(np.mean(np.square(wave)))) + 1e-8
        noise = np.random.default_rng(rng.getrandbits(32)).standard_normal(wave.size)
        wave = wave + (noise * rms / 10 ** (rng.uniform(15.0, 40.0) / 20)).astype(np.float32)
    target = math.exp(rng.uniform(math.log(0.02), math.log(0.99)))
    return np.ascontiguousarray(set_peak(wave, target), dtype=np.float32)


def read_clip(path: Path) -> Wave:
    import soundfile  # noqa: PLC0415

    samples, rate = soundfile.read(str(path), dtype="int16", always_2d=True)
    if rate != SAMPLE_RATE:
        raise ValueError(f"unexpected sample rate {rate}: {path}")
    mono: Wave = (samples.astype(np.float32) / 32768.0).mean(axis=1)
    return mono


def lr_at(progress: float, high: float, low: float) -> float:
    """Cosine decay from ``high`` to ``low`` over training progress 0..1."""
    return low + 0.5 * (high - low) * (1.0 + math.cos(math.pi * min(max(progress, 0.0), 1.0)))


# ------------------------------------------------------------------------------------- data
@dataclass(frozen=True)
class Bucket:
    """One slice of the training mix; ``groups`` are generators (or attacks) drawn evenly."""

    name: str
    label: int  # 1 = spoof
    weight: float
    codec_p: float
    groups: tuple[tuple[Path, ...], ...]


def make_buckets(tk_train: list[Item], la_train: list[Item], tk_share: float) -> list[Bucket]:
    def grouped(items: list[Item], label: int) -> tuple[tuple[Path, ...], ...]:
        groups: dict[str, list[Path]] = {}
        for _name, path, item_label, group in items:
            if item_label == label:
                groups.setdefault(group, []).append(path)
        return tuple(tuple(paths) for _, paths in sorted(groups.items()))

    buckets = [
        # Real Turkmen speech already went through a lossy codec once, most fakes did not.
        Bucket("tk_real", 0, tk_share / 2, 0.3, grouped(tk_train, 0)),
        Bucket("tk_fake", 1, tk_share / 2, 0.7, grouped(tk_train, 1)),
        Bucket("la_real", 0, (1 - tk_share) / 2, 0.5, grouped(la_train, 0)),
        Bucket("la_fake", 1, (1 - tk_share) / 2, 0.5, grouped(la_train, 1)),
    ]
    return [bucket for bucket in buckets if bucket.groups]


class TrainClips(Dataset[tuple[torch.Tensor, int]]):
    """An endless, seeded mix: item ``i`` of epoch ``e`` is always the same clip and crop."""

    def __init__(
        self,
        buckets: list[Bucket],
        length: int,
        seed: int,
        epoch: int,
        codecs: tuple[tuple[str, str, int, int], ...],
        noise_p: float,
    ) -> None:
        self.buckets, self.length, self.seed, self.epoch = buckets, length, seed, epoch
        self.codecs, self.noise_p = codecs, noise_p
        self.weights = [bucket.weight for bucket in buckets]

    def __len__(self) -> int:
        return self.length

    def __getitem__(self, index: int) -> tuple[torch.Tensor, int]:
        rng = random.Random(f"{self.seed}/{self.epoch}/{index}")
        for _ in range(5):  # an unreadable file must not end a long run
            bucket = rng.choices(self.buckets, weights=self.weights)[0]
            path = rng.choice(rng.choice(bucket.groups))
            try:
                wave = random_crop(read_clip(path), WINDOW, rng)
            except Exception as error:
                print(f"[data] skipped {path}: {error}", flush=True)
                continue
            wave = augment(wave, rng, self.codecs, bucket.codec_p, self.noise_p)
            return torch.from_numpy(wave), bucket.label
        raise RuntimeError("five unreadable clips in a row")


def prepare_tk(data: Path, work: Path) -> dict[str, list[Item]]:
    """Unpack the Turkmen set (``audio_*.tar`` + ``manifest.csv``) and list it per split."""
    manifests = [m for m in sorted(data.rglob("manifest.csv")) if any(m.parent.glob("audio_*.tar"))]
    if not manifests:
        raise SystemExit(f"Turkmen set (manifest.csv with audio_*.tar) not found under {data}")
    source, target = manifests[0].parent, work / "tk"
    target.mkdir(parents=True, exist_ok=True)
    for archive in sorted(source.glob("audio_*.tar")):
        marker = target / f".{archive.stem}.done"
        if not marker.exists():
            with tarfile.open(archive) as tar:
                tar.extractall(target, filter="data")
            marker.touch()
            print(f"[data] unpacked {archive.name}", flush=True)
    splits: dict[str, list[Item]] = {"train": [], "dev": [], "test": []}
    missing = 0
    with manifests[0].open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            path = target / row["file"]
            if not path.is_file():
                missing += 1
                continue
            splits[row["split"]].append((row["id"], path, int(row["label"]), row["generator"]))
    total = sum(len(items) for items in splits.values())
    print(f"[data] Turkmen set: {total} clips, {missing} missing files", flush=True)
    if missing > 0.01 * max(total, 1):
        raise SystemExit("too many Turkmen clips are missing")
    return splits


def subset(items: list[Item], limit: int, seed: int = 0) -> list[Item]:
    if not limit or len(items) <= limit:
        return items
    chosen = list(items)
    random.Random(seed).shuffle(chosen)
    return chosen[:limit]


# ------------------------------------------------------------------------------- evaluation
class Scorer:
    def __init__(self, model: nn.Module, device: torch.device, batch: int, workers: int) -> None:
        self.model, self.device, self.batch, self.workers = model, device, batch, workers

    def logits(self, items: list[Item], transform: Transform | None = None) -> list[list[float]]:
        self.model.eval()
        return score(self.model, items, self.device, self.batch, self.workers, transform)


def labels_of(items: list[Item]) -> np.ndarray:
    return np.asarray([item[2] for item in items])


def quick(items: list[Item], logits: list[list[float]]) -> dict[str, float]:
    labels, probs = labels_of(items), utterance_probs(logits, 1.0)
    return {"eer": M.eer(labels, probs)[0], "auc": M.auc(labels, probs)}


def breakdown(items: list[Item], probs: np.ndarray, band: tuple[float, float]) -> dict[str, Any]:
    """Per generator: EER against all real clips and how its fakes are judged; real by source."""
    labels = labels_of(items)
    names = np.asarray([item[3] for item in items])
    out: dict[str, Any] = {"fake": {}, "real": {}}
    for name in sorted(set(names[labels == 1])):
        mask = names == name
        chosen = (labels == 0) | mask
        out["fake"][name] = {
            "n": int(mask.sum()),
            "held_out": name in HELD_OUT,
            "eer": M.eer(labels[chosen], probs[chosen])[0] if (labels == 0).any() else None,
            "as_fake": float(np.mean(probs[mask] >= band[1])),
            "as_real": float(np.mean(probs[mask] <= band[0])),
        }
    for name in sorted(set(names[labels == 0])):
        mask = names == name
        out["real"][name] = {
            "n": int(mask.sum()),
            "as_real": float(np.mean(probs[mask] <= band[0])),
            "as_fake": float(np.mean(probs[mask] >= band[1])),
        }
    return out


def keep(items: list[Item], logits: list[list[float]], held_out: bool) -> tuple[list[Item], Any]:
    """Real clips plus only the held-out (or only the seen) generators."""
    picked = [
        i for i, item in enumerate(items) if item[2] == 0 or (item[3] in HELD_OUT) == held_out
    ]
    return [items[i] for i in picked], [logits[i] for i in picked]


# --------------------------------------------------------------------------------- training
def fitting_batch(model: nn.Module, device: torch.device, wanted: int) -> int:
    """The largest batch (``wanted``, or halved down to 4) whose training step fits in memory."""
    if device.type != "cuda":
        return wanted
    batch = wanted
    untouched = copy.deepcopy(model.state_dict())  # the probe must not move BatchNorm statistics
    while batch > 4:
        try:
            model.train()
            _, output = model(torch.randn(batch, WINDOW, device=device) * 0.1, Freq_aug=True)
            output.sum().backward()
            model.zero_grad(set_to_none=True)
            peak = torch.cuda.max_memory_allocated(device) / 2**30
            print(f"[env] batch {batch} fits: peak {peak:.1f} GB", flush=True)
            break
        except torch.cuda.OutOfMemoryError:
            model.zero_grad(set_to_none=True)
            torch.cuda.empty_cache()
            print(f"[env] batch {batch} does not fit in GPU memory, halving", flush=True)
            batch //= 2
    model.load_state_dict(untouched)
    return batch


def work(args: argparse.Namespace) -> None:
    if hasattr(os, "killpg"):
        proc.enable_stack_dumps()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    torch.manual_seed(args.seed)
    args.out.mkdir(parents=True, exist_ok=True)
    args.state_dir.mkdir(parents=True, exist_ok=True)
    print(f"[env] torch {torch.__version__} device={device}", flush=True)

    la_root = find_root(args.data)
    la = {part: read_protocol(la_root, part) for part in ("train", "dev", "eval")}
    if not la["train"][0][1].is_file():
        raise SystemExit(f"ASVspoof 2019 LA train audio not found: {la['train'][0][1]}")
    tk = prepare_tk(args.data, args.work)
    if args.limit:
        la = {part: subset(items, args.limit) for part, items in la.items()}
        tk = {part: subset(items, args.limit) for part, items in tk.items()}
    la_dev = subset(la["dev"], args.la_dev, seed=1)
    la_eval = subset(la["eval"], args.la_eval, seed=2)
    parts = {"la train": la["train"], "la dev": la_dev, "la eval": la_eval}
    parts |= {f"tk {part}": items for part, items in tk.items()}
    for name, items in parts.items():
        print(f"[data] {name}: {len(items)} clips, {sum(i[2] for i in items)} fake", flush=True)
    leaked = sorted({i[3] for i in tk["train"] + tk["dev"]} & set(HELD_OUT))
    if leaked:
        raise SystemExit(f"held-out generators in train/dev: {leaked}")

    codecs = available_codecs()
    print(f"[aug] codecs: {[c[0] for c in codecs] or 'NONE (ffmpeg missing)'}", flush=True)
    buckets = make_buckets(tk["train"], la["train"], args.tk_share)
    for bucket in buckets:
        sizes = [len(group) for group in bucket.groups]
        print(f"[mix] {bucket.name}: weight {bucket.weight:.2f}, groups {sizes}", flush=True)

    official = fetch_weights(args.state_dir / "official" / "AASIST.pth")
    model = build_aasist()
    model.load_state_dict(torch.load(official, map_location="cpu", weights_only=True))
    model = model.to(device)
    batch = fitting_batch(model, device, args.batch)
    steps = args.steps * args.batch // batch  # the same number of clips per epoch
    scorer = Scorer(model, device, args.eval_batch, args.workers)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    criterion = nn.CrossEntropyLoss()
    last_path, best_path = args.state_dir / "last.pt", args.state_dir / "best.pt"
    baseline_path = args.out / "baseline.json"

    def dev_scores() -> dict[str, Any]:
        tk_dev, la_dev_ = (
            quick(tk["dev"], scorer.logits(tk["dev"])),
            quick(la_dev, scorer.logits(la_dev)),
        )
        return {"tk_dev": tk_dev, "la_dev": la_dev_, "score": (tk_dev["eer"] + la_dev_["eer"]) / 2}

    if not baseline_path.is_file():  # the official weights, before any training
        temperature, *old_band = DEPLOYED
        test_logits = scorer.logits(tk["test"])
        test_probs = utterance_probs(test_logits, temperature)
        baseline = {
            **dev_scores(),
            "tk_test": summarise(labels_of(tk["test"]), test_probs, (old_band[0], old_band[1])),
            "tk_test_breakdown": breakdown(tk["test"], test_probs, (old_band[0], old_band[1])),
        }
        baseline_path.write_text(json.dumps(baseline, indent=2) + "\n")
        print(
            f"[baseline] {json.dumps({k: baseline[k] for k in ('tk_dev', 'la_dev')})}", flush=True
        )
        print(f"[baseline] tk test {json.dumps(baseline['tk_test'])}", flush=True)

    history: list[dict[str, Any]] = []
    epoch, total_epochs, best, spent = 0, args.epochs, float("inf"), 0.0
    if args.resume and last_path.is_file():
        state = torch.load(last_path, map_location="cpu", weights_only=False)
        model.load_state_dict(state["model"])
        optimizer.load_state_dict(state["optimizer"])
        history, epoch, total_epochs = state["history"], state["epoch"], state["total_epochs"]
        best, spent = state["best"], state["spent"]
        print(f"[resume] after epoch {epoch} of {total_epochs}, best {best:.4f}", flush=True)

    budget = args.budget_min * 60.0
    while epoch < total_epochs and spent < budget:
        began = time.time()
        loader = DataLoader(
            TrainClips(buckets, steps * batch, args.seed, epoch, codecs, args.noise_p),
            batch_size=batch,
            num_workers=args.workers,
            drop_last=True,
        )
        model.train()
        running, seen = 0.0, 0
        for step, (clips, labels) in enumerate(loader):
            rate = lr_at((epoch * steps + step) / (total_epochs * steps), args.lr, args.lr_min)
            for group in optimizer.param_groups:
                group["lr"] = rate
            _, output = model(clips.to(device), Freq_aug=True)
            loss = criterion(output, (1 - labels).to(device))  # output index 0 is "spoof"
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
            running, seen = running + loss.item() * len(labels), seen + len(labels)
            if step % 50 == 0:
                speed = seen / max(time.time() - began, 1e-6)
                print(
                    f"[train] epoch {epoch + 1}/{total_epochs} step {step}/{steps} "
                    f"loss {running / seen:.4f} lr {rate:.2e} {speed:.0f} clips/s",
                    flush=True,
                )
        scores = dev_scores()
        epoch += 1
        took = time.time() - began
        spent += took
        if len(history) == 0:  # now the real speed is known: plan only what fits the budget
            total_epochs = max(2, min(args.epochs, int(budget // took)))
        entry = {"epoch": epoch, "loss": running / max(seen, 1), "minutes": took / 60, **scores}
        history.append(entry)
        print(f"[epoch] {json.dumps(entry)} (planned epochs: {total_epochs})", flush=True)
        (args.out / "history.json").write_text(json.dumps(history, indent=2) + "\n")
        if scores["score"] < best:
            best = scores["score"]
            torch.save(model.state_dict(), best_path)
            torch.save(model.state_dict(), args.out / "AASIST.best-so-far.pth")
        torch.save(
            {"model": model.state_dict(), "optimizer": optimizer.state_dict(), "history": history,
             "epoch": epoch, "total_epochs": total_epochs, "best": best, "spent": spent},
            last_path,
        )  # fmt: skip

    if not best_path.is_file():
        raise SystemExit("no epoch finished: nothing to evaluate")
    finish(args, scorer, tk, la_dev, la_eval, best_path, history, codecs)


def finish(
    args: argparse.Namespace,
    scorer: Scorer,
    tk: dict[str, list[Item]],
    la_dev: list[Item],
    la_eval: list[Item],
    best_path: Path,
    history: list[dict[str, Any]],
    codecs: tuple[tuple[str, str, int, int], ...],
) -> None:
    """Calibrate the best checkpoint on dev, measure it on the test data, write the model."""
    scorer.model.load_state_dict(torch.load(best_path, map_location="cpu", weights_only=True))
    dev_items = tk["dev"] + la_dev
    dev_logits = scorer.logits(dev_items)
    dev_labels = labels_of(dev_items)
    window_logits = np.asarray([v for values in dev_logits for v in values])
    window_labels = np.asarray(
        [label for label, values in zip(dev_labels, dev_logits, strict=True) for _ in values]
    )
    temperature = M.fit_temperature(window_logits, window_labels)
    band = M.decision_band(dev_labels, utterance_probs(dev_logits, temperature), args.max_error)
    print(f"[calibration] temperature={temperature:.3f} band={band}", flush=True)

    def measured(items: list[Item], logits: list[list[float]]) -> dict[str, Any]:
        return summarise(labels_of(items), utterance_probs(logits, temperature), band)

    test = tk["test"]
    test_logits = scorer.logits(test)
    eval_logits = scorer.logits(la_eval)
    report: dict[str, Any] = {
        "temperature": temperature,
        "thresholds": {"real_max": band[0], "fake_min": band[1]},
        "max_error": args.max_error,
        "dev": measured(dev_items, dev_logits),
        "tk_test": measured(test, test_logits),
        "tk_test_seen_generators": measured(*keep(test, test_logits, held_out=False)),
        "tk_test_held_out_generators": measured(*keep(test, test_logits, held_out=True)),
        "tk_test_breakdown": breakdown(test, utterance_probs(test_logits, temperature), band),
        "la_eval": measured(la_eval, eval_logits),
        "la_eval_breakdown": breakdown(la_eval, utterance_probs(eval_logits, temperature), band),
        "codecs_used_in_training": [c[0] for c in codecs],
        "history": history,
    }
    # Robustness: the same test clips, all made quiet, all made loud, all sent through MP3.
    conditions: dict[str, Transform] = {
        "quiet_peak_0.05": lambda wave: set_peak(wave, 0.05),
        "loud_peak_0.99": lambda wave: set_peak(wave, 0.99),
    }
    if any(c[0] == "libmp3lame" for c in codecs):
        conditions["mp3_64k"] = as_mp3
    report["tk_test_conditions"] = {
        name: measured(test, scorer.logits(test, transform))
        for name, transform in conditions.items()
    }

    weights = args.out / "AASIST.pth"
    torch.save({k: v.cpu() for k, v in scorer.model.state_dict().items()}, weights)
    (args.out / "AASIST.best-so-far.pth").unlink(missing_ok=True)
    (args.out / "metrics.json").write_text(json.dumps(report, indent=2) + "\n")
    card = ModelCard(
        name="aasist-tk",
        version="2.0.0",
        kind="audio",
        arch="AASIST",
        weights_file=weights.name,
        sha256=file_sha256(weights),
        thresholds={"audio": Thresholds(*band)},
        temperature=temperature,
        provisional=bool(args.limit),
        trained_on=(
            "ASVspoof 2019 LA train + Turkmen set (Common Voice and broadcast speech; 9 seen "
            "generators), fine-tuned from the official AASIST weights (clovaai/aasist, MIT)"
        ),
        metrics={
            "eval_auc": report["la_eval"]["auc"],
            "eval_eer": report["la_eval"]["eer"],
            "dev_eer": report["dev"]["eer"],
            "tk_test_auc": report["tk_test"]["auc"],
            "tk_test_eer": report["tk_test"]["eer"],
            "tk_held_out_eer": report["tk_test_held_out_generators"]["eer"],
        },
        extra={
            "calibrated_on": "Turkmen dev + ASVspoof 2019 LA dev subset",
            "evaluated_on": "Turkmen test (incl. 2 unseen generators) and ASVspoof 2019 LA eval",
            "epochs": len(history),
            "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        },
    )
    save_card(args.out, card)
    for key in [k for k, v in report.items() if isinstance(v, dict) and "n_real" in v]:
        print(f"[done] {key} {json.dumps(report[key])}", flush=True)
    print(f"[done] conditions {json.dumps(report['tk_test_conditions'])}", flush=True)
    print(f"[done] breakdown {json.dumps(report['tk_test_breakdown'])}", flush=True)


def supervise(argv: list[str], args: argparse.Namespace) -> None:
    """Run the work in a child process; a stalled or crashed child resumes from its checkpoint."""
    kill_at = time.time() + (args.budget_min + 100.0) * 60.0
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(p for p in sys.path if p),
        "PYTHONUNBUFFERED": "1",
    }
    base = [sys.executable, "-u", "-m", "training.train_audio", *argv, "--child"]
    for attempt in range(args.max_restarts + 1):
        print(f"[supervisor] starting worker, attempt {attempt}", flush=True)
        outcome = proc.run_watched(
            base + (["--resume"] if attempt else []), env, args.stall_min * 60.0, kill_at
        )
        print(f"[supervisor] worker ended: {outcome}", flush=True)
        if outcome == "ok":
            return
        if outcome == "hard time limit":
            break
    raise SystemExit("training did not finish")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    p.add_argument("--data", type=Path, default=Path("/kaggle/input"))
    p.add_argument("--out", type=Path, default=Path("/kaggle/working"))
    p.add_argument("--work", type=Path, default=Path("/tmp/train_audio"))
    p.add_argument("--state-dir", type=Path, default=Path("/kaggle/working/state"))
    p.add_argument("--budget-min", type=float, default=240.0, help="time for the epochs")
    p.add_argument("--epochs", type=int, default=30)
    p.add_argument("--steps", type=int, default=1000, help="batches per epoch")
    p.add_argument("--batch", type=int, default=24)
    p.add_argument("--eval-batch", type=int, default=48)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--lr", type=float, default=1e-4)
    p.add_argument("--lr-min", type=float, default=5e-6)
    p.add_argument("--weight-decay", type=float, default=1e-4)
    p.add_argument("--tk-share", type=float, default=0.6, help="share of Turkmen clips in a batch")
    p.add_argument("--noise-p", type=float, default=0.3)
    p.add_argument("--la-dev", type=int, default=2500, help="LA dev clips used (0 = all)")
    p.add_argument("--la-eval", type=int, default=0, help="LA eval clips used (0 = all)")
    p.add_argument("--max-error", type=float, default=0.05)
    p.add_argument("--limit", type=int, default=0, help="clips per partition (smoke test)")
    p.add_argument("--seed", type=int, default=20261121)
    p.add_argument("--stall-min", type=float, default=15.0)
    p.add_argument("--max-restarts", type=int, default=3)
    p.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--resume", action="store_true", help=argparse.SUPPRESS)
    arguments = list(sys.argv[1:] if argv is None else argv)
    args = p.parse_args(arguments)
    if args.child:
        work(args)
    else:
        supervise(arguments, args)


if __name__ == "__main__":
    main()
