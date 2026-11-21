"""The Turkmen audio set: its plan must keep splits clean and its sinks must survive restarts."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest
from training.tk_audio import common
from training.tk_audio.plan import MMS_SCRATCH, SEEN_RESYNTH, PlanConfig, describe, make_plan


def _real(groups: int = 30, per_group: int = 6) -> list[common.Job]:
    clips = []
    for g in range(groups):
        source = "cv" if g % 2 else "ts"
        group = f"{source}_group{g:03d}"
        for k in range(per_group):
            clip_id = f"{source}_{g:03d}_{k}"
            clips.append(
                {
                    "id": clip_id,
                    "file": f"real_{source}/{clip_id}.flac",
                    "source": source,
                    "group": group,
                    "split": common.split_of(group),
                    "text": f"sözlem {g} {k}",
                }
            )
    return clips


def test_split_is_deterministic_and_roughly_70_15_15() -> None:
    counts = Counter(common.split_of(f"group{i}") for i in range(4000))
    assert common.split_of("group7") == common.split_of("group7")
    assert 0.66 < counts["train"] / 4000 < 0.74
    assert 0.12 < counts["dev"] / 4000 < 0.18
    assert 0.12 < counts["test"] / 4000 < 0.18


def test_plan_is_reproducible() -> None:
    real = _real()
    assert make_plan(real) == make_plan(list(reversed(real)))


def test_fakes_and_their_reference_voices_never_cross_a_split() -> None:
    real = _real()
    split = {clip["id"]: clip["split"] for clip in real}
    group_split = {clip["group"]: clip["split"] for clip in real}
    file_split = {clip["file"]: clip["split"] for clip in real}
    plan = make_plan(real)
    assert set(plan) >= {*SEEN_RESYNTH, "tts_mms", "vc_knnvc", "tts_voxcpm_anadil"}
    for name, jobs in plan.items():
        for job in jobs:
            assert job["split"] == split[job["parent"]], name
            if job.get("ref_group"):
                assert group_split[job["ref_group"]] == job["split"], name
                assert job["ref_group"] != job["group"], name
            for ref in job.get("refs", []):
                assert file_split[ref] == job["split"], name


def test_held_out_generators_exist_only_in_the_test_split() -> None:
    table = describe(make_plan(_real()))
    for name in common.HELD_OUT:
        assert table[name]["test"] > 0
        assert table[name]["train"] == table[name]["dev"] == 0
    assert table["rs_hifigan"]["train"] > 0


def test_every_real_clip_gets_two_different_seen_resynthesis_generators() -> None:
    real = _real()
    plan = make_plan(real)
    per_clip: dict[str, list[str]] = {}
    for name in SEEN_RESYNTH:
        for job in plan[name]:
            per_clip.setdefault(job["parent"], []).append(name)
    assert set(per_clip) == {clip["id"] for clip in real}
    assert all(len(names) == 2 and len(set(names)) == 2 for names in per_clip.values())
    used = Counter(name for names in per_clip.values() for name in names)
    assert min(used.values()) > 0.5 * max(used.values())  # no generator is starved


def test_voice_converted_tts_reads_the_scratch_file_planned_for_it() -> None:
    plan = make_plan(_real())
    scratch = {f"{MMS_SCRATCH}/{job['id']}.flac" for job in plan[MMS_SCRATCH]}
    assert plan["tts_mms_knnvc"]
    assert {job["src"] for job in plan["tts_mms_knnvc"]} == scratch
    ids = [job["id"] for jobs in plan.values() for job in jobs]
    assert len(ids) == len(set(ids))


def test_voice_conversion_reuses_one_reference_set_per_voice() -> None:
    plan = make_plan(_real(per_group=30), PlanConfig(knnvc_fraction=1.0, vc_references=20))
    sets: dict[str, set[tuple[str, ...]]] = {}
    for job in plan["vc_knnvc"]:
        sets.setdefault(job["ref_group"], set()).add(tuple(job["refs"]))
        assert len(job["refs"]) == 20
    assert all(len(variants) == 1 for variants in sets.values())
    cloning = plan["tts_voxcpm_anadil"]
    assert len({job["refs"][0] for job in cloning}) > len({job["ref_group"] for job in cloning})


def test_a_split_with_one_group_falls_back_to_the_same_speakers_other_clips() -> None:
    real = _real(1, 4)
    plan = make_plan(real, PlanConfig(knnvc_fraction=1.0))
    assert len(plan["vc_knnvc"]) == 4
    for job in plan["vc_knnvc"]:
        assert job["src"] not in job["refs"]


def test_sink_records_each_clip_and_a_restart_skips_finished_ones(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    np = pytest.importorskip("numpy")
    pytest.importorskip("soundfile")
    pytest.importorskip("scipy")
    monkeypatch.setenv("TK_OUT", str(tmp_path / "out"))
    monkeypatch.setenv("TK_WORK", str(tmp_path / "work"))
    jobs = [
        {"id": f"c{i}", "source": "ts", "group": "g", "split": "train", "text": "x", "parent": "p"}
        for i in range(4)
    ]
    tone = (0.5 * np.sin(np.linspace(0, 2000, 24000 * 2))).astype("float32")
    calls: list[str] = []

    def synth(job: common.Job) -> tuple[object, int]:
        calls.append(job["id"])
        if job["id"] == "c1":
            raise RuntimeError("one bad clip")
        if job["id"] == "c2":
            return tone * 3.0, 24000  # overshoots full scale
        return tone, 24000

    assert common.generate("gen", "vocoder", "model", jobs, synth)
    rows = common.read_jsonl(tmp_path / "out" / "meta" / "gen.jsonl")
    assert [row["id"] for row in rows] == ["c0", "c2", "c3"]
    assert all(row["label"] == 1 and row["native_sr"] == 24000 for row in rows)
    assert abs(rows[0]["duration"] - 2.0) < 0.01
    loud, _ = common.read_audio(tmp_path / "work" / "audio" / "gen" / "c2.flac")
    assert float(abs(loud).max()) <= 0.991

    with (tmp_path / "out" / "meta" / "gen.jsonl").open("a") as handle:
        handle.write('{"id": "c9", "file": ')  # a record cut off by a kill
    calls.clear()
    assert common.generate("gen", "vocoder", "model", jobs, synth)
    assert calls == ["c1"]  # only the clip that is still missing is tried again


def test_sink_rejects_silence_and_broken_audio(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    np = pytest.importorskip("numpy")
    pytest.importorskip("soundfile")
    monkeypatch.setenv("TK_OUT", str(tmp_path / "out"))
    monkeypatch.setenv("TK_WORK", str(tmp_path / "work"))
    sink = common.Sink("gen", "tts", "model")
    job = {"id": "a", "source": "cv", "group": "g", "split": "dev", "text": ""}
    assert not sink.save(job, np.zeros(32000, dtype="float32"), 16000)
    assert not sink.save(job, np.full(32000, np.nan, dtype="float32"), 16000)
    assert not sink.save(job, np.ones(100, dtype="float32") * 0.1, 16000)
    assert sink.rejected == 3 and not sink.done
    assert json.dumps(common.read_jsonl(sink.meta)) == "[]"
