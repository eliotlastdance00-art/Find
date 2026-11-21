"""Copy-synthesis: real audio -> features or codes -> neural vocoder or codec -> audio.

    python -m training.tk_audio.gen_resynth [rs_hifigan rs_univnet rs_encodec rs_dac rs_mimi]

The words and the voice stay those of the real clip; only the waveform is machine-made. This is
the cheapest way to show the detector the fingerprints of neural audio decoders.
"""

from __future__ import annotations

import gc
import sys
from collections.abc import Callable
from typing import Any

import torch

from training.proc import enable_stack_dumps
from training.tk_audio.common import Job, Synth, generate, load, load_plan, work_root

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


def _source(job: Job, rate: int) -> Any:
    return load(work_root() / "audio" / job["src"], rate)


def hifigan() -> Synth:
    from transformers import SpeechT5FeatureExtractor, SpeechT5HifiGan  # noqa: PLC0415

    extractor = SpeechT5FeatureExtractor.from_pretrained("microsoft/speecht5_tts")
    vocoder = SpeechT5HifiGan.from_pretrained("microsoft/speecht5_hifigan").eval().to(DEVICE)

    def synth(job: Job) -> tuple[Any, int]:
        wav = _source(job, 16000)
        mel = extractor(audio_target=wav, sampling_rate=16000, return_tensors="pt")
        out = vocoder(mel["input_values"].to(DEVICE))
        return out.squeeze().float().cpu().numpy(), 16000

    return synth


def univnet() -> Synth:
    from transformers import UnivNetFeatureExtractor, UnivNetModel  # noqa: PLC0415

    extractor = UnivNetFeatureExtractor.from_pretrained("dg845/univnet-dev")
    vocoder = UnivNetModel.from_pretrained("dg845/univnet-dev").eval().to(DEVICE)

    def synth(job: Job) -> tuple[Any, int]:
        wav = _source(job, 24000)
        inputs = extractor(wav, sampling_rate=24000, pad_end=True, return_tensors="pt")
        out = vocoder(**{k: v.to(DEVICE) for k, v in inputs.items()}).waveforms
        return out.squeeze().float().cpu().numpy()[: len(wav)], 24000

    return synth


def encodec() -> Synth:
    from transformers import AutoProcessor, EncodecModel  # noqa: PLC0415

    processor = AutoProcessor.from_pretrained("facebook/encodec_24khz")
    model = EncodecModel.from_pretrained("facebook/encodec_24khz").eval().to(DEVICE)

    def synth(job: Job) -> tuple[Any, int]:
        wav = _source(job, 24000)
        inputs = processor(raw_audio=wav, sampling_rate=24000, return_tensors="pt")
        values, mask = inputs["input_values"].to(DEVICE), inputs["padding_mask"].to(DEVICE)
        encoded = model.encode(values, mask, bandwidth=float(job["params"]["kbps"]))
        out = model.decode(encoded.audio_codes, encoded.audio_scales, mask)[0]
        return out.squeeze().float().cpu().numpy()[: len(wav)], 24000

    return synth


def dac() -> Synth:
    from transformers import AutoProcessor, DacModel  # noqa: PLC0415

    processor = AutoProcessor.from_pretrained("descript/dac_16khz")
    model = DacModel.from_pretrained("descript/dac_16khz").eval().to(DEVICE)

    def synth(job: Job) -> tuple[Any, int]:
        wav = _source(job, 16000)
        inputs = processor(raw_audio=wav, sampling_rate=16000, return_tensors="pt")
        encoded = model.encode(inputs["input_values"].to(DEVICE))
        out = model.decode(encoded.quantized_representation).audio_values
        return out.squeeze().float().cpu().numpy()[: len(wav)], 16000

    return synth


def mimi() -> Synth:
    from transformers import AutoFeatureExtractor, MimiModel  # noqa: PLC0415

    extractor = AutoFeatureExtractor.from_pretrained("kyutai/mimi")
    model = MimiModel.from_pretrained("kyutai/mimi").eval().to(DEVICE)

    def synth(job: Job) -> tuple[Any, int]:
        wav = _source(job, 24000)
        inputs = extractor(raw_audio=wav, sampling_rate=24000, return_tensors="pt")
        encoded = model.encode(inputs["input_values"].to(DEVICE))
        out = model.decode(encoded.audio_codes)[0]
        return out.squeeze().float().cpu().numpy()[: len(wav)], 24000

    return synth


def _lazy(setup: Callable[[], Synth]) -> Synth:
    """Load the model on the first clip, so a generator with nothing left to do loads nothing."""
    loaded: list[Synth] = []

    def synth(job: Job) -> tuple[Any, int]:
        if not loaded:
            loaded.append(setup())
        return loaded[0](job)

    return synth


GENERATORS: dict[str, tuple[Callable[[], Synth], str, str]] = {
    "rs_hifigan": (hifigan, "vocoder", "microsoft/speecht5_hifigan"),
    "rs_univnet": (univnet, "vocoder", "dg845/univnet-dev"),
    "rs_encodec": (encodec, "codec", "facebook/encodec_24khz"),
    "rs_dac": (dac, "codec", "descript/dac_16khz"),
    "rs_mimi": (mimi, "codec", "kyutai/mimi"),
}


def main(argv: list[str] | None = None) -> None:
    enable_stack_dumps()
    torch.set_grad_enabled(False)
    names = list(sys.argv[1:] if argv is None else argv) or list(GENERATORS)
    failed = []
    for name in names:
        setup, kind, model = GENERATORS[name]
        jobs = load_plan(name)
        if not generate(name, kind, model, jobs, _lazy(setup)):
            failed.append(name)
        gc.collect()
        if DEVICE == "cuda":
            torch.cuda.empty_cache()
    if failed:
        raise SystemExit(f"failed generators: {failed}")


if __name__ == "__main__":
    main()
