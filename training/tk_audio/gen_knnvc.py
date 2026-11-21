"""Voice conversion with kNN-VC (WavLM features + HiFi-GAN), which is language independent.

    python -m training.tk_audio.gen_knnvc

Two uses: a real clip re-voiced as another real speaker (``vc_knnvc``), and MMS speech re-voiced
as a real speaker (``tts_mms_knnvc``), which gives the single-voice TTS many voices.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import torch

from training.proc import enable_stack_dumps
from training.tk_audio.common import (
    Job,
    generate,
    load,
    load_plan,
    work_root,
    write_wav,
)

MODEL = "bshall/knn-vc"


def main() -> None:
    enable_stack_dumps()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = torch.hub.load(
        MODEL, "knn_vc", prematched=True, trust_repo=True, pretrained=True, device=device
    )
    scratch = Path(tempfile.mkdtemp(prefix="knnvc_"))
    matching_cache: dict[tuple[str, ...], Any] = {}

    def as_wav(relative: str) -> str:
        """kNN-VC reads files itself; hand it plain 16 kHz WAV whatever the stored format is."""
        target = scratch / (relative.replace("/", "__") + ".wav")
        if not target.is_file():
            write_wav(target, load(work_root() / "audio" / relative))
        return str(target)

    def synth(job: Job) -> tuple[Any, int]:
        key = tuple(job["refs"])
        if key not in matching_cache:
            if len(matching_cache) > 64:
                matching_cache.clear()
            matching_cache[key] = model.get_matching_set([as_wav(ref) for ref in key])
        source = as_wav(job["src"])
        out = model.match(model.get_features(source), matching_cache[key], topk=4)
        Path(source).unlink(missing_ok=True)
        return out.float().cpu().numpy(), 16000

    results = []
    for name, kind in (("vc_knnvc", "voice-conversion"), ("tts_mms_knnvc", "tts+voice-conversion")):
        jobs = [j for j in load_plan(name) if (work_root() / "audio" / j["src"]).is_file()]
        results.append(generate(name, kind, MODEL, jobs, synth))
    if not all(results):
        raise SystemExit("kNN-VC generation failed")


if __name__ == "__main__":
    main()
