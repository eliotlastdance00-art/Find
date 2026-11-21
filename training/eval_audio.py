"""Calibrate and evaluate the audio detector (AASIST) on ASVspoof 2019 LA.

The network weights are the official ones published with the AASIST paper; nothing is
trained here. What this script does, with the *same* windowing and aggregation code the
server uses:

* dev partition  -> temperature (calibration) and the three-way decision band;
* eval partition -> AUC, EER and verdict rates, overall and per attack (never used to tune).

Outputs ``AASIST.pth``, ``model_card.json`` and ``metrics.json`` into ``--out``.

    python -m training.eval_audio --out /kaggle/working
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import time
import urllib.request
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch.utils.data import DataLoader, Dataset

from dfd.domain.entities import Thresholds
from dfd.domain.scoring import aggregate_scores
from dfd.infrastructure.media.audio import windows
from dfd.infrastructure.ml import metrics as M
from dfd.infrastructure.ml.audio import SAMPLE_RATE, WINDOW, build_aasist, spoof_logit
from dfd.infrastructure.ml.cards import ModelCard, save_card

WEIGHTS_URL = "https://github.com/clovaai/aasist/raw/main/models/weights/AASIST.pth"
WEIGHTS_SHA256 = "51d2d9cf0738172f61e2a384ec50a54a55363240f67c971ed55a92435bc1a1c0"
PROTOCOL = "ASVspoof2019.LA.cm.{part}.{kind}.txt"  # kind: "trn" for train, else "trl"

Item = tuple[str, Path, int, str]  # utterance id, path, label (1 = spoof), attack id
Transform = Callable[[np.ndarray], np.ndarray]


def fetch_weights(target: Path) -> Path:
    if not target.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(WEIGHTS_URL, target)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    if digest != WEIGHTS_SHA256:
        raise SystemExit(f"AASIST.pth checksum mismatch: {digest}")
    return target


def find_root(search: Path) -> Path:
    hits = sorted(search.rglob(PROTOCOL.format(part="dev", kind="trl")))
    if not hits:
        raise SystemExit(f"ASVspoof 2019 LA protocols not found under {search}")
    return hits[0].parent.parent


def read_protocol(root: Path, part: str) -> list[Item]:
    kind = "trn" if part == "train" else "trl"
    protocol = root / "ASVspoof2019_LA_cm_protocols" / PROTOCOL.format(part=part, kind=kind)
    folder = root / f"ASVspoof2019_LA_{part}" / "flac"
    items: list[Item] = []
    for line in protocol.read_text().splitlines():
        _speaker, name, _, attack, label = line.split()
        items.append((name, folder / f"{name}.flac", int(label == "spoof"), attack))
    return items


class Utterances(Dataset[tuple[int, torch.Tensor]]):
    def __init__(self, items: list[Item], transform: Transform | None = None) -> None:
        self.items = items
        self.transform = transform  # applied to the whole clip (robustness checks)

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, index: int) -> tuple[int, torch.Tensor]:
        import soundfile  # noqa: PLC0415

        samples, rate = soundfile.read(str(self.items[index][1]), dtype="int16", always_2d=True)
        if rate != SAMPLE_RATE:
            raise ValueError(f"unexpected sample rate {rate}")
        # Same conversion as the server's read_wav(): 16-bit PCM -> mono float32.
        mono = (samples.astype(np.float32) / 32768.0).mean(axis=1)
        if self.transform is not None:
            mono = self.transform(mono)
        batch, _ = windows(mono, rate, WINDOW, WINDOW // 2)
        return index, torch.from_numpy(batch)


def collate(samples: list[tuple[int, torch.Tensor]]) -> tuple[torch.Tensor, torch.Tensor]:
    owners = torch.cat([torch.full((len(w),), i, dtype=torch.long) for i, w in samples])
    return owners, torch.cat([w for _, w in samples])


@torch.inference_mode()
def score(
    model: torch.nn.Module,
    items: list[Item],
    device: torch.device,
    batch: int,
    workers: int,
    transform: Transform | None = None,
) -> list[list[float]]:
    """Raw spoof logits of every window of every utterance."""
    loader = DataLoader(
        Utterances(items, transform), batch_size=batch, num_workers=workers, collate_fn=collate
    )
    logits: list[list[float]] = [[] for _ in items]
    started, done = time.time(), 0
    for step, (owners, clips) in enumerate(loader):
        values: list[float] = []
        for offset in range(0, len(clips), batch):
            chunk = clips[offset : offset + batch].to(device)
            values += spoof_logit(model, chunk).float().cpu().tolist()
        for owner, value in zip(owners.tolist(), values, strict=True):
            logits[owner].append(value)
        done += len(set(owners.tolist()))
        if step % 50 == 0:
            rate = done / max(time.time() - started, 1e-6)
            print(f"[score] {done}/{len(items)} utterances, {rate:.0f}/s", flush=True)
    return logits


def utterance_probs(logits: list[list[float]], temperature: float) -> np.ndarray:
    def sigmoid(values: list[float]) -> list[float]:
        return (1.0 / (1.0 + np.exp(-np.asarray(values) / temperature))).tolist()

    return np.asarray([aggregate_scores(sigmoid(values)) for values in logits])


def summarise(labels: np.ndarray, probs: np.ndarray, band: tuple[float, float]) -> dict[str, Any]:
    eer, _ = M.eer(labels, probs)
    return {
        "auc": M.auc(labels, probs),
        "eer": eer,
        "accuracy_at_0.5": M.accuracy(labels, probs),
        "n_real": int((labels == 0).sum()),
        "n_fake": int((labels == 1).sum()),
        "verdicts": M.verdict_rates(labels, probs, *band),
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, default=Path("/kaggle/input"))
    parser.add_argument("--out", type=Path, default=Path("/kaggle/working"))
    parser.add_argument("--limit", type=int, default=0, help="utterances per partition (smoke)")
    parser.add_argument("--batch", type=int, default=48)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-error", type=float, default=0.05)
    args = parser.parse_args(argv)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[env] torch {torch.__version__} device={device}", flush=True)
    args.out.mkdir(parents=True, exist_ok=True)
    weights = fetch_weights(args.out / "AASIST.pth")
    model = build_aasist()
    model.load_state_dict(torch.load(weights, map_location="cpu", weights_only=True))
    model = model.to(device).eval()

    root = find_root(args.data)
    parts: dict[str, list[Item]] = {}
    for part in ("dev", "eval"):
        items = read_protocol(root, part)
        if args.limit:
            random.Random(0).shuffle(items)
            items = items[: args.limit]
        parts[part] = items
        spoofed = sum(item[2] for item in items)
        print(f"[data] {part}: {len(items)} utterances, {spoofed} spoof", flush=True)

    dev_logits = score(model, parts["dev"], device, args.batch, args.workers)
    dev_labels = np.asarray([item[2] for item in parts["dev"]])
    window_logits = np.asarray([v for values in dev_logits for v in values])
    window_labels = np.asarray(
        [label for label, values in zip(dev_labels, dev_logits, strict=True) for _ in values]
    )
    temperature = M.fit_temperature(window_logits, window_labels)
    dev_probs = utterance_probs(dev_logits, temperature)
    band = M.decision_band(dev_labels, dev_probs, args.max_error)
    print(f"[calibration] temperature={temperature:.3f} band={band}", flush=True)

    eval_logits = score(model, parts["eval"], device, args.batch, args.workers)
    eval_labels = np.asarray([item[2] for item in parts["eval"]])
    eval_probs = utterance_probs(eval_logits, temperature)

    by_attack: dict[str, list[int]] = defaultdict(list)
    for index, item in enumerate(parts["eval"]):
        by_attack[item[3]].append(index)
    real = by_attack.pop("-", [])
    per_attack = {}
    for attack, indices in sorted(by_attack.items()):
        chosen = np.asarray(real + indices)
        if real and indices:
            eer, _ = M.eer(eval_labels[chosen], eval_probs[chosen])
            per_attack[attack] = {"eer": eer, "n_fake": len(indices)}

    report = {
        "temperature": temperature,
        "thresholds": {"real_max": band[0], "fake_min": band[1]},
        "max_error": args.max_error,
        "dev": summarise(dev_labels, dev_probs, band),
        "eval": summarise(eval_labels, eval_probs, band),
        "eval_per_attack": per_attack,
        "windows_per_utterance": float(np.mean([len(v) for v in eval_logits])),
    }
    (args.out / "metrics.json").write_text(json.dumps(report, indent=2) + "\n")

    card = ModelCard(
        name="aasist",
        version="1.0.0",
        kind="audio",
        arch="AASIST",
        weights_file=weights.name,
        sha256=WEIGHTS_SHA256,
        thresholds={"audio": Thresholds(*band)},
        temperature=temperature,
        provisional=bool(args.limit),
        trained_on="ASVspoof 2019 LA train (official AASIST weights, clovaai/aasist, MIT)",
        metrics={
            "eval_auc": report["eval"]["auc"],
            "eval_eer": report["eval"]["eer"],
            "dev_eer": report["dev"]["eer"],
        },
        extra={
            "calibrated_on": "ASVspoof 2019 LA dev",
            "evaluated_on": "ASVspoof 2019 LA eval",
            "source": WEIGHTS_URL,
            "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        },
    )
    save_card(args.out, card)
    print(f"[done] {json.dumps({k: report[k] for k in ('temperature', 'thresholds')})}")
    print(f"[done] dev {json.dumps(report['dev'])}")
    print(f"[done] eval {json.dumps(report['eval'])}")
    print(f"[done] per-attack {json.dumps(per_attack)}", flush=True)


if __name__ == "__main__":
    main()
