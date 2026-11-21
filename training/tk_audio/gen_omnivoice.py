"""Zero-shot voice-cloning TTS: OmniVoice. Held out: test split only.

python -m training.tk_audio.gen_omnivoice    (needs ``pip install omnivoice``)
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import torch

from training.proc import enable_stack_dumps
from training.tk_audio.common import Job, Sink, load, load_plan, run_generator, work_root, write_wav

MODEL = "k2-fsa/OmniVoice"


def main() -> None:
    enable_stack_dumps()
    from omnivoice import OmniVoice  # noqa: PLC0415

    cuda = torch.cuda.is_available()
    model = OmniVoice.from_pretrained(
        MODEL,
        device_map="cuda:0" if cuda else "cpu",
        dtype=torch.float16 if cuda else torch.float32,
    )
    rate = int(
        getattr(model, "sampling_rate", None) or getattr(model, "sample_rate", None) or 24000
    )
    reference = Path(tempfile.mkdtemp(prefix="omnivoice_")) / "reference.wav"

    def synth(job: Job) -> tuple[Any, int]:
        write_wav(reference, load(work_root() / "audio" / job["refs"][0]))
        audio = model.generate(
            text=job["text"], ref_audio=str(reference), ref_text=job["ref_text"], language="tk"
        )
        return audio[0], rate

    run_generator(
        Sink("tts_omnivoice", "tts-cloning", MODEL), load_plan("tts_omnivoice"), synth, 10
    )


if __name__ == "__main__":
    main()
