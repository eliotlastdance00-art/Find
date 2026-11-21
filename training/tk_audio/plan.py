"""Decide which fake is made from which real clip, before any model is loaded.

The plan is a pure function of the list of real clips, so it is reproducible and testable:

* every fake inherits the split of the real clip it is made from, and every reference voice
  comes from the same split, so no speaker, video or sentence crosses a split boundary;
* the held-out generators (``common.HELD_OUT``) appear in the test split only;
* budget-limited generators get their jobs in a shuffled order, so wherever a time limit stops
  them the finished part is still a fair sample of all splits.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from training.tk_audio.common import HELD_OUT, Job, stable_hash

SEEN_RESYNTH = ("rs_hifigan", "rs_univnet", "rs_encodec", "rs_dac", "rs_mimi")
ENCODEC_KBPS = (3.0, 6.0, 12.0)
MMS_SCRATCH = "_mms_tmp"  # intermediate TTS output that is then voice-converted; not a class


@dataclass(frozen=True)
class PlanConfig:
    resynth_per_clip: int = 2
    mms_fraction: float = 0.30
    mms_vc_fraction: float = 0.12
    knnvc_fraction: float = 0.35
    voxcpm_fraction: float = 0.35
    vc_references: int = 8


def _unit(salt: str, clip_id: str) -> float:
    return (stable_hash(f"{salt}:{clip_id}") % 100_000) / 100_000


def _fake(clip: Job, generator: str, **fields: object) -> Job:
    return {
        "id": f"{clip['id']}__{generator.lstrip('_')}",
        "parent": clip["id"],
        "source": clip["source"],
        "group": clip["group"],
        "split": clip["split"],
        "text": clip["text"],
        **fields,
    }


class _References:
    """Picks a reference voice for a clip: another group of the same split when there is one."""

    def __init__(self, real: list[Job]) -> None:
        self.by_group: dict[str, list[Job]] = defaultdict(list)
        self.groups: dict[str, list[str]] = defaultdict(list)
        for clip in sorted(real, key=lambda c: c["id"]):
            if clip["group"] not in self.by_group:
                self.groups[clip["split"]].append(clip["group"])
            self.by_group[clip["group"]].append(clip)

    def pick(self, clip: Job, salt: str, count: int) -> tuple[str, list[Job]]:
        others = [g for g in self.groups[clip["split"]] if g != clip["group"]]
        if others:
            group = others[stable_hash(f"{salt}:group:{clip['id']}") % len(others)]
            pool = self.by_group[group]
        else:  # a split with a single group (tiny smoke runs): use the speaker's other clips
            group = clip["group"]
            pool = [c for c in self.by_group[group] if c["id"] != clip["id"]]
        ranked = sorted(pool, key=lambda c: stable_hash(f"{salt}:{clip['id']}:{c['id']}"))
        return group, ranked[:count]


def make_plan(real: list[Job], config: PlanConfig | None = None) -> dict[str, list[Job]]:
    """Jobs per generator. ``real`` rows need: id, file, source, group, split, text."""
    config = config or PlanConfig()
    references = _References(real)
    plan: dict[str, list[Job]] = defaultdict(list)

    for clip in sorted(real, key=lambda c: c["id"]):
        code = stable_hash("resynth:" + clip["id"])
        first = code % len(SEEN_RESYNTH)
        step = 1 + (code // len(SEEN_RESYNTH)) % (len(SEEN_RESYNTH) - 1)
        for k in range(min(config.resynth_per_clip, len(SEEN_RESYNTH))):
            name = SEEN_RESYNTH[(first + k * step) % len(SEEN_RESYNTH)]
            params = {}
            if name == "rs_encodec":
                params = {"kbps": ENCODEC_KBPS[(code // 97) % len(ENCODEC_KBPS)]}
            plan[name].append(_fake(clip, name, src=clip["file"], params=params))
        if clip["split"] == "test":
            plan["rs_vocos"].append(_fake(clip, "rs_vocos", src=clip["file"], params={}))

        tts_params = {
            "noise_scale": round(0.45 + 0.4 * _unit("ns", clip["id"]), 3),
            "noise_scale_duration": round(0.6 + 0.4 * _unit("nd", clip["id"]), 3),
            "speaking_rate": round(0.85 + 0.3 * _unit("rate", clip["id"]), 3),
            "seed": stable_hash("seed:" + clip["id"]) % 2**31,
        }
        draw = _unit("mms", clip["id"])
        if draw < config.mms_fraction:
            plan["tts_mms"].append(_fake(clip, "tts_mms", params=tts_params))
        elif draw < config.mms_fraction + config.mms_vc_fraction:
            group, refs = references.pick(clip, "mmsvc", config.vc_references)
            if refs:
                scratch = _fake(clip, MMS_SCRATCH, params=tts_params)
                plan[MMS_SCRATCH].append(scratch)
                plan["tts_mms_knnvc"].append(
                    _fake(
                        clip,
                        "tts_mms_knnvc",
                        src=f"{MMS_SCRATCH}/{scratch['id']}.flac",
                        refs=[r["file"] for r in refs],
                        ref_group=group,
                        params={},
                    )
                )

        if _unit("knnvc", clip["id"]) < config.knnvc_fraction:
            group, refs = references.pick(clip, "knnvc", config.vc_references)
            if refs:
                plan["vc_knnvc"].append(
                    _fake(
                        clip,
                        "vc_knnvc",
                        src=clip["file"],
                        refs=[r["file"] for r in refs],
                        ref_group=group,
                        params={},
                    )
                )

        cloning = [("tts_voxcpm_anadil", _unit("voxcpm", clip["id"]) < config.voxcpm_fraction)]
        cloning.append(("tts_omnivoice", clip["split"] == "test"))
        for name, wanted in cloning:
            if not wanted:
                continue
            group, refs = references.pick(clip, name, 1)
            if refs:
                plan[name].append(
                    _fake(
                        clip,
                        name,
                        refs=[refs[0]["file"]],
                        ref_text=refs[0]["text"],
                        ref_group=group,
                        params={},
                    )
                )

    for name in ("tts_voxcpm_anadil", "tts_omnivoice"):
        plan[name].sort(key=lambda job: stable_hash("order:" + job["id"]))
    for name in HELD_OUT:
        assert all(job["split"] == "test" for job in plan[name]), name
    return dict(plan)


def describe(plan: dict[str, list[Job]]) -> dict[str, dict[str, int]]:
    table: dict[str, dict[str, int]] = {}
    for name, jobs in sorted(plan.items()):
        counts = {"train": 0, "dev": 0, "test": 0}
        for job in jobs:
            counts[job["split"]] += 1
        table[name] = counts
    return table
