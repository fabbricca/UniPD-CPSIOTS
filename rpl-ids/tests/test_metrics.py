"""Metric definitions on kept evidence logs (deterministic, no Cooja)."""
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import parse_logs as pl        # noqa: E402
import calculate_metrics as cm  # noqa: E402

EV = ROOT / "report" / "evidence"


def _metrics(stem):
    log = EV / f"{stem}.log"
    tf = EV / f"{stem}.truth.csv"
    truth = cm.load_truth(tf if tf.exists() else None)
    t = pl.parse(log)
    win = int(t["IDS"].iloc[0]["window"])
    return cm.compute(t, truth, win)


@pytest.mark.parametrize("stem", [
    "section4-dev-10-neighbor-a1-s1", "section4-dev-10-dis-a1-s1",
    "section4-dev-30-neighbor-a1-w300-s1", "section4-dev-30-dis-a1-w300-s1",
])
def test_attacker_always_detected_node_level(stem):
    m = _metrics(stem)
    assert m["attackers_heard"], stem
    assert m["node_TPR"] == 1.0 and m["node_FN"] == 0, stem
    assert m["attackers_detected"] == m["attackers_heard"], stem


@pytest.mark.parametrize("stem", ["section4-dev-10-dis-a1-s1",
                                  "section4-dev-30-dis-a1-w300-s1"])
def test_dis_attack_zero_false_positives(stem):
    m = _metrics(stem)
    assert m["node_FPR"] == 0.0 and m["dec_FPR"] == 0.0, stem


def test_baseline_has_no_attackers_and_low_decision_fpr():
    m = _metrics("section3-dev-30-baseline-w300-s1")
    assert m["attackers"] == [] and m["node_TP"] == 0
    assert m["dec_FPR"] < 0.05
