"""Train and evaluate the visual deepfake detector on FaceForensics++ c23.

Designed for a Kaggle GPU session (2 x T4) but runs anywhere, including a CPU smoke test:

    python -m training.train_visual --ffpp-root /data/ffpp --out out --smoke \\
        --arch test_efficientnet --size 160 --epochs 1

Outputs in ``--out``: weights.pth, model_card.json, metrics.json, history.csv, roc.png.

Robustness (a first full run froze in its last epoch and lost the model):

* the work runs in a child process; a supervisor restarts it with ``--resume`` when it has
  printed nothing for ``--stall-min`` minutes or exits with an error;
* every epoch writes a resumable checkpoint, and every improvement exports the best weights
  with a provisional model card, so an interrupted run still leaves a usable model;
* ``faces.tar`` is written right after face extraction and is picked up automatically from
  ``/kaggle/input`` by later runs, which then skip the extraction.
"""

from __future__ import annotations

import argparse
import csv
import faulthandler
import json
import math
import os
import random
import signal
import subprocess
import sys
import tarfile
import threading
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset

from dfd.domain.entities import Thresholds
from dfd.domain.scoring import aggregate_scores
from dfd.infrastructure.ml import metrics as M
from dfd.infrastructure.ml.cards import ModelCard, file_sha256, save_card
from dfd.infrastructure.ml.visual import build_backbone
from training.augment import augment
from training.ffpp import FaceRow, discover, extract_faces, find_root, read_manifest

IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--ffpp-root", type=Path, default=Path("/kaggle/input"))
    p.add_argument("--faces-dir", type=Path, default=Path("/tmp/dfd_faces"))
    p.add_argument("--out", type=Path, default=Path("/kaggle/working"))
    p.add_argument("--arch", default="tf_efficientnet_b4.ns_jft_in1k")
    p.add_argument("--name", default="effnet-b4-ffpp")
    p.add_argument("--version", default="1.0.0")
    p.add_argument("--size", type=int, default=288)
    p.add_argument("--store-size", type=int, default=320)
    p.add_argument("--epochs", type=int, default=12)
    p.add_argument("--batch", type=int, default=64)
    p.add_argument("--lr", type=float, default=2e-4)
    p.add_argument("--weight-decay", type=float, default=1e-2)
    p.add_argument("--frames-real", type=int, default=32)
    p.add_argument("--frames-fake", type=int, default=8)
    p.add_argument("--frames-eval", type=int, default=16)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--limit-videos", type=int, default=None, help="per method and split")
    p.add_argument("--time-budget-min", type=float, default=600.0)
    p.add_argument("--seed", type=int, default=20261120)
    p.add_argument("--smoke", action="store_true", help="ignore official splits (tiny test runs)")
    p.add_argument("--no-pretrained", action="store_true")
    p.add_argument("--save-faces", action="store_true", help="also write faces.tar to --out")
    p.add_argument("--faces-tar", type=Path, default=None, help="reuse faces from this archive")
    p.add_argument("--state-dir", type=Path, default=Path("/tmp/dfd_state"))
    p.add_argument("--stall-min", type=float, default=15.0, help="restart after this much silence")
    p.add_argument("--max-restarts", type=int, default=4)
    p.add_argument("--in-process", action="store_true", help="no supervisor (debugging)")
    p.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--resume", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--eval-only", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--attempt", type=int, default=0, help=argparse.SUPPRESS)
    return p.parse_args(argv)


class FaceDataset(Dataset[tuple[torch.Tensor, float]]):
    def __init__(
        self,
        rows: list[FaceRow],
        root: Path,
        size: int,
        mean: tuple[float, ...],
        std: tuple[float, ...],
        train: bool,
        seed: int,
    ) -> None:
        self.rows, self.root, self.size, self.train, self.seed = rows, root, size, train, seed
        self.mean = np.asarray(mean, dtype=np.float32)
        self.std = np.asarray(std, dtype=np.float32)
        self.epoch = 0

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, float]:
        row = self.rows[index]
        image = cv2.imread(str(self.root / row.file), cv2.IMREAD_COLOR)
        if image is None:
            raise FileNotFoundError(row.file)
        if self.train:
            rng = random.Random(hash((self.seed, self.epoch, index)))
            image = augment(image, self.size, rng)
        elif image.shape[0] != self.size:
            image = cv2.resize(image, (self.size, self.size), interpolation=cv2.INTER_AREA)
        array = (image[..., ::-1].astype(np.float32) / 255.0 - self.mean) / self.std
        return torch.from_numpy(array.transpose(2, 0, 1).copy()), float(row.label)


@torch.no_grad()
def predict_logits(
    model: nn.Module, loader: DataLoader, device: torch.device, amp: bool
) -> np.ndarray:
    model.eval()
    chunks = []
    for images, _ in loader:
        images = images.to(device, non_blocking=True)  # noqa: PLW2901
        with torch.autocast(device_type=device.type, dtype=torch.float16, enabled=amp):
            chunks.append(model(images).float().reshape(-1).cpu())
    return torch.cat(chunks).numpy().astype(np.float64)


def sigmoid(z: np.ndarray, temperature: float = 1.0) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-z / temperature))


def video_level(rows: list[FaceRow], probs: np.ndarray) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Aggregate frame probabilities per video with the application's scoring rule."""
    grouped: dict[str, list[float]] = defaultdict(list)
    labels: dict[str, int] = {}
    for row, prob in zip(rows, probs, strict=True):
        grouped[row.video].append(float(prob))
        labels[row.video] = row.label
    keys = sorted(grouped)
    scores = np.array([aggregate_scores(grouped[k]) for k in keys])
    return np.array([labels[k] for k in keys]), scores, keys


def summarise(labels: np.ndarray, scores: np.ndarray) -> dict[str, float]:
    equal_error, _ = M.eer(labels, scores)
    return {
        "auc": M.auc(labels, scores),
        "eer": equal_error,
        "accuracy_at_0.5": M.accuracy(labels, scores, 0.5),
        "n_real": int((labels == 0).sum()),
        "n_fake": int((labels == 1).sum()),
    }


def per_method(rows: list[FaceRow], probs: np.ndarray) -> dict[str, dict[str, float]]:
    """AUC of real vs. each manipulation method, frame and video level."""
    out: dict[str, dict[str, float]] = {}
    methods = sorted({r.method for r in rows if r.label == 1})
    for method in methods:
        keep = [i for i, r in enumerate(rows) if r.label == 0 or r.method == method]
        sub_rows, sub_probs = [rows[i] for i in keep], probs[keep]
        frame_labels = np.array([r.label for r in sub_rows])
        v_labels, v_scores, _ = video_level(sub_rows, sub_probs)
        out[method] = {
            "frame_auc": M.auc(frame_labels, sub_probs),
            "video_auc": M.auc(v_labels, v_scores),
        }
    return out


def save_roc(path: Path, curves: dict[str, tuple[np.ndarray, np.ndarray]]) -> None:
    try:
        import matplotlib  # noqa: PLC0415

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt  # noqa: PLC0415
    except ImportError:
        return
    fig, ax = plt.subplots(figsize=(5.5, 5.5), dpi=140)
    for name, (labels, scores) in curves.items():
        fpr, tpr, _ = M.roc_curve(labels, scores)
        ax.plot(fpr, tpr, label=f"{name} (AUC {M.auc(labels, scores):.4f})")
    ax.plot([0, 1], [0, 1], "--", color="gray", linewidth=0.8)
    ax.set(xlabel="False positive rate", ylabel="True positive rate", title="ROC, FF++ c23 test")
    ax.legend(loc="lower right")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


TRAINED_ON = "FaceForensics++ c23 (Deepfakes, Face2Face, FaceSwap, NeuralTextures, FaceShifter)"
DEADLINE_ENV = "DFD_TRAIN_DEADLINE"
POLL_SECONDS = 5.0  # how often the supervisor looks at its worker
DUMP_GRACE_SECONDS = 10.0  # time the worker gets to print its stacks before it is killed


def _worker_init(_: int) -> None:
    # OpenCV's own thread pool inside forked DataLoader workers is a known source of deadlocks.
    cv2.setNumThreads(0)
    torch.set_num_threads(1)


def _atomic_save(payload: object, path: Path) -> None:
    tmp = path.with_name(path.name + ".tmp")
    torch.save(payload, tmp)
    tmp.replace(path)


def find_faces_tar(explicit: Path | None) -> Path | None:
    if explicit is not None:
        return explicit if explicit.is_file() else None
    root = Path("/kaggle/input")
    return next(iter(sorted(root.rglob("faces.tar"))), None) if root.is_dir() else None


def prepare_faces(args: argparse.Namespace) -> list[FaceRow]:
    """Reuse cropped faces (directory, then archive) or crop them from the videos."""
    manifest = args.faces_dir / "manifest.csv"
    if manifest.is_file():
        rows = read_manifest(manifest)
        print(f"[data] reusing {len(rows)} faces from {args.faces_dir}", flush=True)
        return rows
    archive = find_faces_tar(args.faces_tar)
    if archive is not None:
        print(f"[data] unpacking {archive}", flush=True)
        parent = args.faces_dir.parent
        parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive) as tar:
            tar.extractall(parent, filter="data")
        unpacked = parent / "faces"
        if unpacked != args.faces_dir:
            if args.faces_dir.is_dir():
                args.faces_dir.rmdir()
            unpacked.rename(args.faces_dir)
        rows = read_manifest(manifest)
        print(f"[data] {len(rows)} faces from the archive", flush=True)
        return rows

    root = find_root(args.ffpp_root)
    videos = discover(root, args.limit_videos, args.smoke)
    counts: dict[str, int] = defaultdict(int)
    for video in videos:
        counts[f"{video.split}/{video.method}"] += 1
    print(f"[data] root={root} videos={len(videos)} {dict(sorted(counts.items()))}", flush=True)
    args.faces_dir.mkdir(parents=True, exist_ok=True)
    rows = extract_faces(
        videos,
        args.faces_dir,
        args.frames_real,
        args.frames_fake,
        args.frames_eval,
        args.store_size,
        args.workers,
    )
    found = {r.video for r in rows}
    missing = sorted(v.key for v in videos if v.key not in found)
    print(f"[data] {len(rows)} faces; videos without any face: {len(missing)}", flush=True)
    (args.out / "videos_without_faces.json").write_text(json.dumps(missing, indent=1))
    if args.save_faces:
        # Written now, not at the end: a later crash must not cost the extraction again.
        print("[data] writing faces.tar", flush=True)
        target = args.out / "faces.tar"
        partial = args.out / "faces.tar.part"
        with tarfile.open(partial, "w") as tar:
            tar.add(args.faces_dir, arcname="faces")
        partial.replace(target)
        print(f"[data] faces.tar {target.stat().st_size / 1e6:.0f} MB", flush=True)
    return rows


def calibrate(
    rows: list[FaceRow], logits: np.ndarray
) -> tuple[float, tuple[float, float], tuple[float, float]]:
    """Temperature and the image/video decision bands from validation logits."""
    labels = np.array([r.label for r in rows])
    temperature = M.fit_temperature(logits, labels)
    probs = sigmoid(logits, temperature)
    v_labels, v_scores, _ = video_level(rows, probs)
    return temperature, M.decision_band(labels, probs), M.decision_band(v_labels, v_scores)


def export_model(
    args: argparse.Namespace,
    state: dict[str, torch.Tensor],
    mean: tuple[float, ...],
    std: tuple[float, ...],
    temperature: float,
    image_band: tuple[float, float],
    video_band: tuple[float, float],
    metrics: dict[str, float],
    note: str | None,
) -> None:
    """Write weights.pth (half precision) and its model card; ``note`` marks an interim export."""
    weights = args.out / "weights.pth"
    _atomic_save({k: v.half() if v.is_floating_point() else v for k, v in state.items()}, weights)
    extra = {
        "face_margin": 1.3,
        "face_detector": "yunet_2023mar",
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    if note:
        extra["note"] = note
    card = ModelCard(
        name=args.name,
        version=args.version,
        kind="visual",
        arch=args.arch,
        weights_file=weights.name,
        sha256=file_sha256(weights),
        thresholds={"image": Thresholds(*image_band), "video": Thresholds(*video_band)},
        temperature=temperature,
        input_size=args.size,
        mean=(mean[0], mean[1], mean[2]),
        std=(std[0], std[1], std[2]),
        provisional=bool(note or args.smoke or args.limit_videos),
        trained_on=TRAINED_ON,
        metrics=metrics,
        extra=extra,
    )
    save_card(args.out, card)


def run(args: argparse.Namespace) -> None:
    """The actual work: faces, training with checkpoints, calibration, evaluation, export."""
    faulthandler.register(signal.SIGUSR1, all_threads=True)
    started = time.time()
    deadline = float(os.environ.get(DEADLINE_ENV, started + args.time_budget_min * 60.0))
    random.seed(args.seed + args.attempt)
    np.random.seed((args.seed + args.attempt) % (2**32))
    torch.manual_seed(args.seed + args.attempt)
    args.out.mkdir(parents=True, exist_ok=True)
    args.state_dir.mkdir(parents=True, exist_ok=True)
    last_path, best_path = args.state_dir / "last.pt", args.state_dir / "best.pt"
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    amp = device.type == "cuda"
    print(
        f"[env] torch {torch.__version__} device={device} gpus={torch.cuda.device_count()} "
        f"attempt={args.attempt}",
        flush=True,
    )

    # 1. Faces ---------------------------------------------------------------------------
    rows = prepare_faces(args)
    by_split = {s: [r for r in rows if r.split == s] for s in ("train", "val", "test")}
    leak = {r.video.split("/")[1].split("_")[0] for r in by_split["train"]} & {
        r.video.split("/")[1].split("_")[0] for r in by_split["val"] + by_split["test"]
    }
    if leak and not args.smoke:
        raise RuntimeError(f"identity leakage between splits: {sorted(leak)[:5]}")
    data_stats = {
        split: {
            "faces_real": sum(r.label == 0 for r in part),
            "faces_fake": sum(r.label == 1 for r in part),
            "videos": len({r.video for r in part}),
        }
        for split, part in by_split.items()
    }
    print(f"[data] {json.dumps(data_stats)}", flush=True)

    # 2. Model ---------------------------------------------------------------------------
    model = build_backbone(
        args.arch, pretrained=not args.no_pretrained, drop_rate=0.3, drop_path_rate=0.2
    )
    cfg = getattr(model, "pretrained_cfg", {}) or {}
    mean = tuple(float(v) for v in cfg.get("mean", IMAGENET_MEAN))
    std = tuple(float(v) for v in cfg.get("std", IMAGENET_STD))
    # NCHW on purpose: channels_last + AMP + DataParallel crashes with "CUDA error: misaligned
    # address" on Kaggle's torch 2.11/cu130 T4 image (verified with a diagnostic kernel).
    model = model.to(device)
    net: nn.Module = nn.DataParallel(model) if torch.cuda.device_count() > 1 else model

    def loader(split: str, train: bool) -> DataLoader:
        # A different augmentation stream after a restart, so a restart never replays the
        # exact batch sequence that preceded a stall.
        dataset = FaceDataset(
            by_split[split],
            args.faces_dir,
            args.size,
            mean,
            std,
            train,
            args.seed + 7919 * args.attempt,
        )
        return DataLoader(
            dataset,
            batch_size=args.batch if train else args.batch * 2,
            shuffle=train,
            num_workers=args.workers,
            pin_memory=amp,
            drop_last=train,
            persistent_workers=False,
            worker_init_fn=_worker_init if args.workers else None,
            timeout=600 if args.workers else 0,  # a stuck worker becomes an error, not a hang
        )

    train_loader, val_loader, test_loader = (
        loader("train", True),
        loader("val", False),
        loader("test", False),
    )
    n_real, n_fake = data_stats["train"]["faces_real"], data_stats["train"]["faces_fake"]
    criterion = nn.BCEWithLogitsLoss(
        pos_weight=torch.tensor(n_real / max(1, n_fake), device=device)
    )
    optimizer = torch.optim.AdamW(net.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    total_steps = max(1, args.epochs * len(train_loader))
    warmup = min(500, total_steps // 10)

    def lr_factor(step: int) -> float:
        if step < warmup:
            return (step + 1) / warmup
        progress = (step - warmup) / max(1, total_steps - warmup)
        return 0.01 + 0.99 * 0.5 * (1.0 + math.cos(math.pi * progress))

    scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lr_factor)
    scaler = torch.amp.GradScaler(device.type, enabled=amp)
    val_labels = np.array([r.label for r in by_split["val"]])

    # 3. Training ------------------------------------------------------------------------
    history: list[dict[str, float]] = []
    best_score, start_epoch, minutes_before = -1.0, 0, 0.0
    if args.resume and last_path.is_file():
        saved = torch.load(last_path, map_location="cpu", weights_only=True)
        model.load_state_dict(saved["model"])
        optimizer.load_state_dict(saved["optimizer"])
        scheduler.load_state_dict(saved["scheduler"])
        scaler.load_state_dict(saved["scaler"])
        history, best_score = saved["history"], saved["best_score"]
        start_epoch, minutes_before = saved["epoch"], saved["minutes"]
        print(
            f"[resume] continuing after epoch {start_epoch} (best score {best_score:.4f})",
            flush=True,
        )
        del saved
    elif args.resume:
        print("[resume] no checkpoint yet, starting from the beginning", flush=True)

    if args.eval_only:
        print("[train] skipped: evaluating the best checkpoint only", flush=True)
        start_epoch = args.epochs
    for epoch in range(start_epoch, args.epochs):
        net.train()
        train_loader.dataset.epoch = epoch  # type: ignore[attr-defined]
        running, seen, tick = 0.0, 0, time.time()
        for step, (images, labels) in enumerate(train_loader):
            images = images.to(device, non_blocking=True)  # noqa: PLW2901
            labels = labels.to(device, non_blocking=True).float()  # noqa: PLW2901
            with torch.autocast(device_type=device.type, dtype=torch.float16, enabled=amp):
                loss = criterion(net(images).float().reshape(-1), labels)
            optimizer.zero_grad(set_to_none=True)
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            nn.utils.clip_grad_norm_(net.parameters(), 2.0)
            scaler.step(optimizer)
            scaler.update()
            scheduler.step()
            running += loss.item() * labels.numel()
            seen += labels.numel()
            if step % 100 == 0:
                rate = seen / (time.time() - tick)
                print(
                    f"[train] epoch {epoch + 1} step {step}/{len(train_loader)} "
                    f"loss {running / seen:.4f} {rate:.0f} img/s",
                    flush=True,
                )
        print(f"[train] epoch {epoch + 1} finished, validating", flush=True)
        val_logits = predict_logits(net, val_loader, device, amp)
        val_probs = sigmoid(val_logits)
        v_labels, v_scores, _ = video_level(by_split["val"], val_probs)
        minutes = minutes_before + (time.time() - started) / 60.0
        record = {
            "epoch": epoch + 1,
            "train_loss": running / max(1, seen),
            "val_frame_auc": M.auc(val_labels, val_probs),
            "val_video_auc": M.auc(v_labels, v_scores),
            "minutes": minutes,
        }
        history.append(record)
        print(f"[val] {json.dumps(record)}", flush=True)
        with (args.out / "history.csv").open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(history[0]))
            writer.writeheader()
            writer.writerows(history)

        score = record["val_video_auc"] + 1e-3 * record["val_frame_auc"]
        if score > best_score:
            best_score = score
            state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            _atomic_save({"model": state, "epoch": epoch + 1}, best_path)
            try:  # an interim export must never be the reason a run dies
                temperature, image_band, video_band = calibrate(by_split["val"], val_logits)
                export_model(
                    args,
                    state,
                    mean,
                    std,
                    temperature,
                    image_band,
                    video_band,
                    {
                        "val_frame_auc": record["val_frame_auc"],
                        "val_video_auc": record["val_video_auc"],
                    },
                    note=f"interim export after epoch {epoch + 1}; not evaluated on the test split",
                )
                print(f"[checkpoint] best so far: epoch {epoch + 1}, exported", flush=True)
            except Exception as error:
                print(f"[checkpoint] interim export failed: {error!r}", flush=True)
            del state
        _atomic_save(
            {
                "model": model.state_dict(),
                "optimizer": optimizer.state_dict(),
                "scheduler": scheduler.state_dict(),
                "scaler": scaler.state_dict(),
                "history": history,
                "best_score": best_score,
                "epoch": epoch + 1,
                "minutes": minutes,
            },
            last_path,
        )
        if time.time() > deadline:
            print("[train] time budget reached, stopping early", flush=True)
            break

    # 4. Calibration and evaluation ------------------------------------------------------
    if not best_path.is_file():
        raise RuntimeError("no epoch finished; nothing to evaluate")
    best_state = torch.load(best_path, map_location="cpu", weights_only=True)["model"]
    model.load_state_dict(best_state)
    print("[eval] scoring validation and test splits with the best weights", flush=True)
    val_logits = predict_logits(net, val_loader, device, amp)
    test_logits = predict_logits(net, test_loader, device, amp)
    temperature, image_band, video_band = calibrate(by_split["val"], val_logits)
    val_probs, test_probs = sigmoid(val_logits, temperature), sigmoid(test_logits, temperature)
    test_labels = np.array([r.label for r in by_split["test"]])
    val_v_labels, val_v_scores, _ = video_level(by_split["val"], val_probs)
    test_v_labels, test_v_scores, _ = video_level(by_split["test"], test_probs)

    best_epoch = max(history, key=lambda h: h["val_video_auc"] + 1e-3 * h["val_frame_auc"])
    report = {
        "dataset": "FaceForensics++ c23, official video-level splits",
        "data": data_stats,
        "best_epoch": best_epoch["epoch"],
        "temperature": temperature,
        "validation": {
            "frame": summarise(val_labels, val_probs),
            "video": summarise(val_v_labels, val_v_scores),
        },
        "test": {
            "frame": summarise(test_labels, test_probs),
            "video": summarise(test_v_labels, test_v_scores),
            "per_method": per_method(by_split["test"], test_probs),
            "verdicts_frame": M.verdict_rates(test_labels, test_probs, *image_band),
            "verdicts_video": M.verdict_rates(test_v_labels, test_v_scores, *video_band),
        },
        "thresholds": {
            "image": {"real_max": image_band[0], "fake_min": image_band[1]},
            "video": {"real_max": video_band[0], "fake_min": video_band[1]},
        },
        "history": history,
        "restarts": args.attempt,
        "args": {k: str(v) for k, v in vars(args).items()},
        "minutes_total": minutes_before + (time.time() - started) / 60.0,
    }
    (args.out / "metrics.json").write_text(json.dumps(report, indent=2))
    save_roc(
        args.out / "roc.png",
        {
            "frame": (test_labels, test_probs),
            "video": (test_v_labels, test_v_scores),
        },
    )

    # 5. Export --------------------------------------------------------------------------
    test = report["test"]
    export_model(
        args,
        best_state,
        mean,
        std,
        temperature,
        image_band,
        video_band,
        {
            "test_frame_auc": test["frame"]["auc"],
            "test_video_auc": test["video"]["auc"],
            "test_video_eer": test["video"]["eer"],
        },
        note=None,
    )
    print(
        f"[done] {json.dumps({k: report[k] for k in ('best_epoch', 'temperature', 'thresholds')})}"
    )
    print(f"[done] test {json.dumps(test['frame'])} video {json.dumps(test['video'])}")
    print(f"[done] per-method {json.dumps(test['per_method'])}", flush=True)


def _run_child(cmd: list[str], env: dict[str, str], stall_s: float, kill_at: float) -> str:
    """Run one worker; return "ok" or the reason it ended. Silence counts as a stall."""
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
        start_new_session=True,
    )
    last_output = [time.time()]

    def pump() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            last_output[0] = time.time()

    reader = threading.Thread(target=pump, daemon=True)
    reader.start()
    reason = ""
    while proc.poll() is None:
        time.sleep(POLL_SECONDS)
        silent = time.time() - last_output[0]
        if silent > stall_s:
            reason = f"no output for {silent / 60:.0f} min"
        elif time.time() > kill_at:
            reason = "hard time limit"
        if reason:
            print(f"[supervisor] {reason}: dumping stacks, then killing the worker", flush=True)
            try:
                os.kill(proc.pid, signal.SIGUSR1)  # faulthandler prints every thread's stack
                time.sleep(DUMP_GRACE_SECONDS)
                os.killpg(proc.pid, signal.SIGKILL)  # the whole group: DataLoader workers too
            except ProcessLookupError:
                pass
            proc.wait()
    reader.join(timeout=10)
    if reason:
        return reason
    return "ok" if proc.returncode == 0 else f"exit code {proc.returncode}"


def supervise(argv: list[str], args: argparse.Namespace) -> None:
    """Run the work in a child process and restart it from its checkpoint when it fails.

    A stall or crash is retried from the last finished epoch. Two failures in a row without
    a new checkpoint mean the fault is not transient: training stops there and, if a best
    checkpoint exists, one last worker calibrates and tests it so the run still ends with a
    measured model.
    """
    begun = time.time()
    train_deadline = begun + args.time_budget_min * 60.0
    kill_at = train_deadline + 60 * 60.0
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(p for p in sys.path if p),
        "PYTHONUNBUFFERED": "1",
        DEADLINE_ENV: str(train_deadline),
    }
    base = [sys.executable, "-u", "-m", "training.train_visual", *argv, "--child"]
    last_path, best_path = args.state_dir / "last.pt", args.state_dir / "best.pt"

    def progress() -> float:
        return last_path.stat().st_mtime if last_path.is_file() else 0.0

    def attempt_once(number: int, extra: list[str]) -> str:
        print(f"[supervisor] starting worker, attempt {number} {' '.join(extra)}", flush=True)
        flags = [*extra, "--attempt", str(number)]
        outcome = _run_child(base + flags, env, args.stall_min * 60.0, kill_at)
        minutes = (time.time() - begun) / 60
        print(f"[supervisor] worker ended: {outcome} ({minutes:.0f} min)", flush=True)
        return outcome

    outcome, fruitless = "not started", 0
    for attempt in range(args.max_restarts + 1):
        before = progress()
        outcome = attempt_once(attempt, ["--resume"] if attempt else [])
        if outcome == "ok":
            return
        fruitless = 0 if progress() > before else fruitless + 1
        if outcome == "hard time limit" or fruitless >= 2:
            break
    if best_path.is_file() and time.time() < kill_at + 30 * 60.0:
        print("[supervisor] training could not finish; evaluating the best checkpoint", flush=True)
        kill_at = max(kill_at, time.time() + 45 * 60.0)
        final = _run_child(
            [*base, "--resume", "--eval-only", "--attempt", str(args.max_restarts + 1)],
            env,
            args.stall_min * 60.0,
            kill_at,
        )
        print(f"[supervisor] evaluation worker ended: {final}", flush=True)
        if final == "ok":
            print(f"[supervisor] finished with a partial training run ({outcome})", flush=True)
            return
    raise SystemExit(f"[supervisor] giving up after: {outcome}")


def main(argv: list[str] | None = None) -> None:
    arguments = list(sys.argv[1:] if argv is None else argv)
    args = parse_args(arguments)
    if args.child or args.in_process:
        run(args)
    else:
        supervise(arguments, args)


if __name__ == "__main__":
    main()
