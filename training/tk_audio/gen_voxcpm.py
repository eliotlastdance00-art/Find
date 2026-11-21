"""Voice-cloning TTS: VoxCPM2 with the Anadil Turkmen LoRA adapter.

    python -m training.tk_audio.gen_voxcpm       (needs ``pip install voxcpm``)

Slow, so it works through a shuffled job list until its time budget (``TK_DEADLINE``) ends.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any

from training.proc import enable_stack_dumps
from training.tk_audio.common import Job, Sink, load, load_plan, run_generator, work_root, write_wav

MODEL = "openbmb/VoxCPM2 + Anadilorg/Anadil_Turkmen_TTS"


def main() -> None:
    enable_stack_dumps()
    from huggingface_hub import snapshot_download  # noqa: PLC0415

    repo = snapshot_download("Anadilorg/Anadil_Turkmen_TTS")
    sys.path.insert(0, repo)
    from inference import AnadilTurkmenTTS  # noqa: PLC0415

    tts = AnadilTurkmenTTS(repo=repo)
    rate = int(tts.sample_rate)
    reference = Path(tempfile.mkdtemp(prefix="voxcpm_")) / "reference.wav"

    def synth(job: Job) -> tuple[Any, int]:
        write_wav(reference, load(work_root() / "audio" / job["refs"][0]))
        audio = tts.model.generate(
            text=job["text"],
            reference_wav_path=str(reference),
            cfg_value=2.0,
            inference_timesteps=10,
            normalize=True,
            max_len=2000,
            min_len=2,
        )
        return audio, rate

    run_generator(
        Sink("tts_voxcpm_anadil", "tts-cloning", MODEL), load_plan("tts_voxcpm_anadil"), synth, 10
    )


if __name__ == "__main__":
    main()
