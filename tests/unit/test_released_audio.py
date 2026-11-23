"""Deployment metadata must not silently remove the audio safety limit."""

from __future__ import annotations

import json
from pathlib import Path

from dfd.domain.entities import Verdict
from dfd.infrastructure.ml.cards import load_card, verify_weights

ROOT = Path(__file__).resolve().parents[2]


def test_released_audio_matches_measured_results_and_keeps_required_cap() -> None:
    card = load_card(ROOT / "weights" / "audio")
    metrics = json.loads((ROOT / "docs/metrics/audio_tk_metrics.json").read_text())
    assert card.metrics["tk_test_auc"] == metrics["tk_test"]["auc"]
    assert card.metrics["tk_test_eer"] == metrics["tk_test"]["eer"]
    assert card.temperature == metrics["temperature"]
    assert card.thresholds_for("audio").real_max == metrics["thresholds"]["real_max"]
    assert card.thresholds_for("audio").fake_min == metrics["thresholds"]["fake_min"]
    assert verify_weights(ROOT / "weights" / "audio", card).is_file()
    evaluated = [metrics["tk_test"], *metrics["tk_test_conditions"].values()]
    if any(result["verdicts"]["real"]["as_fake"] > metrics["max_error"] for result in evaluated):
        assert card.provisional, "Measured false alarms exceed the target; not a final model"
        assert card.max_verdict is Verdict.SUSPICIOUS
