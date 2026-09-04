#!/usr/bin/env python3
"""Detection metrics for one run, joined against its ground-truth file.

Two aggregations are reported. Ground truth (attacker ids, type, interval)
comes only from the .truth.csv written by gen_scenario.py, never from IDS
output. A DIO alert scores against a neighbour attacker, a DIS alert against a
DIS attacker; the wrong kind for the attacker type is not a true positive.
Only windows active during the attack are scored (window end within
[start+win, atk_end+win], so the first scored window fully contains attack
traffic).

Node-level (primary, comparable with the paper's Table III): each node the
network can hear is classified once. An attacker is TP if at least one monitor
raised the correct-kind alert in an active window, else FN. A normal node is
FP if any monitor raised the attack's own rule on it in an active window (a
DIO alert for a neighbour attack, a DIS alert for a DIS attack), else TN, so
the columns line up with the paper's per-attack FPR. This matches the
paper's per-node samples and its "TPR 100%, FPR 0%" for the DIS attack.

Decision-level (secondary, PROJECT_PLAN section 10): one decision by one
monitor about one neighbour at one window end. Finer grained; exposes the
single-attacker blind spots (a monitor with 5-7 or 28-32 neighbours cannot
flag a lone attacker regardless of rate).

Usage: calculate_metrics.py logs/<run>.log [--truth simulations/<run>.truth.csv]
                            [--json results/<run>.metrics.json]
"""
import argparse
import json
import pathlib
import sys

import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import parse_logs as pl  # noqa: E402


def default_truth(log):
    stem = pathlib.Path(log).stem
    for c in (pathlib.Path(log).with_suffix(".truth.csv"),
              pathlib.Path("simulations") / f"{stem}.truth.csv"):
        if c.exists():
            return c
    return None


def load_truth(path):
    if path is None or not pathlib.Path(path).exists():
        return pd.DataFrame(columns=["attacker_id", "attack_type", "period_ms",
                                     "start_sec", "duration_sec"])
    return pd.read_csv(path)


def compute(tables, truth, window_sec):
    nbr, alert = tables["NBR"], tables["ALERT"]
    attackers = set(truth.attacker_id.astype(int)) if len(truth) else set()
    atype = truth.attack_type.iloc[0] if len(truth) else None
    start = int(truth.start_sec.iloc[0]) if len(truth) else 0
    dur = int(truth.duration_sec.iloc[0]) if len(truth) else 0
    run_end = float(nbr.t.max()) if len(nbr) else 0.0
    atk_end = start + dur if dur > 0 else run_end
    alert_kind = {"neighbor": "DIO", "dis": "DIS"}.get(atype, "DIO")
    no_attack = len(truth) == 0

    # Windows whose whole span lies after the attack has started and before it
    # ends: window w covers ((w)*win, (w+1)*win] in seconds of sim time. We
    # score a window as "attack active" if its end time is within the attack.
    def active(win):
        if no_attack:
            return True          # baseline: score false positives over the whole run
        wend = (win + 1) * window_sec
        return start + window_sec <= wend <= atk_end + window_sec

    # Alerts indexed by (monitor, win, neighbour) -> set of kinds.
    ak = {}
    for _, r in alert.iterrows():
        ak.setdefault((int(r.mote), int(r.win), int(r.nbr)), set()).add(r.kind)

    # Decision-level counters and per-node flag aggregation.
    d_tp = d_fp = d_fn = d_tn = 0
    node_flagged_correct = {}   # node id -> earliest active-window end it was correctly flagged
    node_flagged_any = set()    # nodes flagged (any kind) in an active window
    nodes_heard = set()
    first_tp_t = None
    for _, r in nbr.iterrows():
        mon, win, neigh = int(r.mote), int(r.win), int(r.nbr)
        nodes_heard.add(neigh)
        kinds = ak.get((mon, win, neigh), set())
        is_attacker = neigh in attackers
        in_attack = active(win)
        if is_attacker and in_attack:
            if alert_kind in kinds:
                d_tp += 1
                t = (win + 1) * window_sec
                first_tp_t = t if first_tp_t is None else min(first_tp_t, t)
                node_flagged_correct[neigh] = min(node_flagged_correct.get(neigh, t), t)
            else:
                d_fn += 1
        elif not is_attacker and in_attack:
            # Score false positives against the attack's own rule only, so the
            # numbers line up with the paper's per-attack FPR columns.
            if alert_kind in kinds:
                d_fp += 1
                node_flagged_any.add(neigh)
            else:
                d_tn += 1

    # Node-level (paper-comparable).
    heard_attackers = [a for a in attackers if a in nodes_heard]
    heard_normals = [n for n in nodes_heard if n not in attackers]
    n_tp = sum(1 for a in heard_attackers if a in node_flagged_correct)
    n_fn = len(heard_attackers) - n_tp
    n_fp = sum(1 for n in heard_normals if n in node_flagged_any)
    n_tn = len(heard_normals) - n_fp

    def rates(tp, fp, fn, tn):
        tpr = tp / (tp + fn) if (tp + fn) else float("nan")
        fpr = fp / (fp + tn) if (fp + tn) else 0.0
        prec = tp / (tp + fp) if (tp + fp) else float("nan")
        f1 = (2 * prec * tpr / (prec + tpr)) if (tp and prec == prec and tpr == tpr) else 0.0
        return tpr, fpr, prec, f1

    n_tpr, n_fpr, n_prec, n_f1 = rates(n_tp, n_fp, n_fn, n_tn)
    d_tpr, d_fpr, d_prec, d_f1 = rates(d_tp, d_fp, d_fn, d_tn)
    latency = (first_tp_t - start) if first_tp_t is not None else None
    return {
        "attack_type": atype, "attackers": sorted(attackers),
        "attackers_heard": sorted(heard_attackers),
        "attackers_detected": sorted(node_flagged_correct),
        "window_sec": window_sec, "attack_start_sec": start, "attack_end_sec": round(atk_end, 1),
        # node-level (primary)
        "node_TP": n_tp, "node_FP": n_fp, "node_FN": n_fn, "node_TN": n_tn,
        "node_TPR": n_tpr, "node_FPR": n_fpr, "node_precision": n_prec, "node_F1": n_f1,
        # decision-level (secondary)
        "dec_TP": d_tp, "dec_FP": d_fp, "dec_FN": d_fn, "dec_TN": d_tn,
        "dec_TPR": d_tpr, "dec_FPR": d_fpr, "dec_precision": d_prec, "dec_F1": d_f1,
        "detection_latency_sec": latency,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("log")
    ap.add_argument("--truth", default=None)
    ap.add_argument("--json", default=None)
    a = ap.parse_args()
    tables = pl.parse(a.log)
    truth = load_truth(a.truth or default_truth(a.log))
    win = int(tables["IDS"].iloc[0]["window"]) if len(tables["IDS"]) else 300
    m = compute(tables, truth, win)
    for k, v in m.items():
        print(f"{k:24} {v}")
    if a.json:
        pathlib.Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(a.json).write_text(json.dumps(m, indent=2))
        print(f"wrote {a.json}")


if __name__ == "__main__":
    main()
