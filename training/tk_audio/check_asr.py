"""Intelligibility check of a sample of the generated clips.

    python -m training.tk_audio.check_asr --per-generator 25

Each sampled fake and the real clip with the same words are transcribed with MMS ASR (Turkmen
adapter). The score is the character error rate between the two transcripts, so the recogniser's
own mistakes largely cancel out; a generator that produces noise instead of speech stands out.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict

import torch

from training.proc import enable_stack_dumps
from training.tk_audio.common import Job, load, out_root, read_jsonl, stable_hash, work_root

MODEL = "facebook/mms-1b-all"
LANGUAGE = "tuk-script_latin"


def cer(reference: str, hypothesis: str) -> float | None:
    """Character error rate (Levenshtein distance over the reference length)."""
    if not reference:
        return None
    previous = list(range(len(hypothesis) + 1))
    for i, a in enumerate(reference, 1):
        current = [i]
        for j, b in enumerate(hypothesis, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (a != b)))
        previous = current
    return previous[-1] / len(reference)


def main(argv: list[str] | None = None) -> None:
    enable_stack_dumps()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--per-generator", type=int, default=25)
    args = parser.parse_args(argv)
    from transformers import AutoProcessor, Wav2Vec2ForCTC  # noqa: PLC0415

    rows: dict[str, list[Job]] = {}
    for path in sorted((out_root() / "meta").glob("*.jsonl")):
        if not path.stem.startswith("_"):
            rows[path.stem] = read_jsonl(path)
    real = {r["id"]: r for name, items in rows.items() if name.startswith("real_") for r in items}
    sample = {
        name: sorted(
            (r for r in items if r["parent"] in real), key=lambda r: stable_hash("asr:" + r["id"])
        )[: args.per_generator]
        for name, items in rows.items()
        if not name.startswith("real_")
    }

    device = "cuda" if torch.cuda.is_available() else "cpu"
    processor = AutoProcessor.from_pretrained(MODEL, target_lang=LANGUAGE)
    model = Wav2Vec2ForCTC.from_pretrained(
        MODEL, target_lang=LANGUAGE, ignore_mismatched_sizes=True
    )
    model = model.eval().to(device)
    cache: dict[str, str] = {}

    def transcribe(row: Job) -> str:
        if row["id"] not in cache:
            wav = load(work_root() / "audio" / row["file"])
            inputs = processor(wav, sampling_rate=16000, return_tensors="pt").to(device)
            with torch.no_grad():
                ids = model(**inputs).logits.argmax(-1)[0]
            cache[row["id"]] = processor.decode(ids)
        return cache[row["id"]]

    report: dict[str, dict[str, object]] = {}
    examples: dict[str, list[dict[str, str]]] = defaultdict(list)
    for name, items in sample.items():
        scores = []
        for row in items:
            reference, hypothesis = transcribe(real[row["parent"]]), transcribe(row)
            score = cer(reference, hypothesis)
            if score is not None:
                scores.append(score)
            if len(examples[name]) < 3:
                examples[name].append({"id": row["id"], "real": reference, "fake": hypothesis})
        mean = round(sum(scores) / len(scores), 4) if scores else None
        report[name] = {"n": len(scores), "mean_cer_vs_real_asr": mean}
        print(f"[asr] {name}: n={len(scores)} CER={mean}", flush=True)
        payload = {"scores": report, "examples": examples}
        (out_root() / "asr_check.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=1)
        )


if __name__ == "__main__":
    main()
