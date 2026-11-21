"""Copy-synthesis with Vocos (mel -> waveform, 24 kHz). Held out: test split only.

python -m training.tk_audio.gen_vocos        (needs ``pip install vocos``)
"""

from __future__ import annotations

from typing import Any

import torch

from training.proc import enable_stack_dumps
from training.tk_audio.common import Job, Sink, load, load_plan, run_generator, work_root

MODEL = "charactr/vocos-mel-24khz"


def main() -> None:
    enable_stack_dumps()
    from vocos import Vocos  # noqa: PLC0415

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = Vocos.from_pretrained(MODEL).eval().to(device)

    def synth(job: Job) -> tuple[Any, int]:
        wav = load(work_root() / "audio" / job["src"], 24000)
        with torch.no_grad():
            out = model(torch.from_numpy(wav)[None].to(device))
        return out.squeeze().float().cpu().numpy()[: len(wav)], 24000

    run_generator(Sink("rs_vocos", "vocoder", MODEL), load_plan("rs_vocos"), synth)


if __name__ == "__main__":
    main()
