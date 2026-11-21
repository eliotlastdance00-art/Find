"""Text-to-speech with Meta MMS (VITS) for Turkmen.

    python -m training.tk_audio.gen_mms

MMS has a single built-in voice, so its prosody is varied per clip (noise scales, speaking rate)
and part of its output is only an intermediate that kNN-VC later turns into other voices.
"""

from __future__ import annotations

from typing import Any

import torch

from training.proc import enable_stack_dumps
from training.tk_audio.common import Job, generate, load_plan
from training.tk_audio.plan import MMS_SCRATCH

MODEL = "facebook/mms-tts-tuk-script_latin"


def main() -> None:
    enable_stack_dumps()
    from transformers import AutoTokenizer, VitsModel  # noqa: PLC0415

    device = "cuda" if torch.cuda.is_available() else "cpu"
    tokenizer = AutoTokenizer.from_pretrained(MODEL)
    model = VitsModel.from_pretrained(MODEL).eval().to(device)

    def synth(job: Job) -> tuple[Any, int]:
        params = job["params"]
        model.noise_scale = params["noise_scale"]
        model.noise_scale_duration = params["noise_scale_duration"]
        model.speaking_rate = params["speaking_rate"]
        torch.manual_seed(params["seed"])
        inputs = tokenizer(job["text"], return_tensors="pt").to(device)
        if inputs["input_ids"].shape[-1] < 2:
            raise ValueError("text has no characters the tokenizer knows")
        with torch.no_grad():
            wav = model(**inputs).waveform[0]
        return wav.float().cpu().numpy(), int(model.config.sampling_rate)

    results = [
        generate(name, "tts", MODEL, load_plan(name), synth) for name in ("tts_mms", MMS_SCRATCH)
    ]
    if not all(results):
        raise SystemExit("MMS generation failed")


if __name__ == "__main__":
    main()
