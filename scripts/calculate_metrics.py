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


def eval_period(tables):
    """Seconds represented by one window index: the detector's evaluation
    period. In sliding mode that is the bucket size (IDS init 'eval' field);
    in paper mode it equals the window."""
    ids = tables["IDS"]
    if len(ids) == 0:
        return 300
    row = ids.iloc[0]
    if "eval" in ids.columns and str(row.get("eval")) not in ("nan", "None", ""):
        try:
            return int(float(row["eval"]))
        except (ValueError, TypeError):
            pass
    return int(row["window"])


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


def network_metrics(tables, attackers):
    """Network-impact metrics (PROJECT_PLAN section 10) from one run.

    PDR and delay come from matching TX (node, seq) to RX (root, from, seq).
    Control-plane overhead is DIO/DIS *receptions* summed over all monitors'
    NBR records, normalised per monitor per minute. In sliding mode every
    message is counted in IDS_SLIDE_BUCKETS consecutive evaluations, so the sum
    is divided by that factor (6 for the default 6 x 10 s ring).
    """
    tx, rx, nbr, par, block, stat, ids, atk = (tables[k] for k in
        ("TX", "RX", "NBR", "PAR", "BLOCK", "STAT", "IDS", "ATK"))
    out = {}
    normals = set(stat.mote.unique()) - set(attackers)
    # Packet delivery ratio, all senders and normal senders only.
    tx_n = len(tx)
    rx_n = len(rx)
    out["tx_total"], out["rx_total"] = int(tx_n), int(rx_n)
    out["pdr"] = (rx_n / tx_n) if tx_n else float("nan")
    tx_norm = tx[tx.mote.isin(normals)]
    rx_norm = rx[rx["from"].isin(normals)]
    out["pdr_normal"] = (len(rx_norm) / len(tx_norm)) if len(tx_norm) else float("nan")
    # End-to-end delay via (sender, seq) join.
    if tx_n and rx_n:
        m = tx.rename(columns={"mote": "from", "t": "t_tx"})[["from", "seq", "t_tx"]].merge(
            rx.rename(columns={"t": "t_rx"})[["from", "seq", "t_rx"]], on=["from", "seq"])
        d = (m.t_rx - m.t_tx)
        d = d[d >= 0]
        out["delay_mean_s"] = float(d.mean()) if len(d) else float("nan")
        out["delay_p95_s"] = float(d.quantile(0.95)) if len(d) else float("nan")
    else:
        out["delay_mean_s"] = out["delay_p95_s"] = float("nan")
    # Control-plane overhead: receptions per monitor per minute.
    mode = str(ids.iloc[0]["mode"]) if len(ids) else "paper"
    factor = 6.0 if mode == "sliding" else 1.0
    run_min = (float(nbr.t.max()) / 60.0) if len(nbr) else float("nan")
    n_mon = nbr.mote.nunique() if len(nbr) else 0
    if n_mon and run_min:
        out["dio_rx_per_node_min"] = float(nbr.dio.sum()) / factor / n_mon / run_min
        out["dis_rx_per_node_min"] = float(nbr.dis.sum()) / factor / n_mon / run_min
    else:
        out["dio_rx_per_node_min"] = out["dis_rx_per_node_min"] = float("nan")
    # Routing churn and response.
    n_nodes = stat.mote.nunique() if len(stat) else 0
    out["parent_changes_per_node"] = (len(par) / n_nodes) if n_nodes else float("nan")
    out["blocks_temp"] = int((block.action == "temp").sum()) if len(block) else 0
    out["blocks_perm"] = int((block.action == "perm").sum()) if len(block) else 0
    out["blocked_pairs"] = int(block[block.action.isin(["temp", "perm"])]
                               .groupby(["mote", "nbr"]).ngroups) if len(block) else 0
    temp_sec = int(ids.iloc[0]["temp_block"]) if len(ids) else 60
    out["temp_block_time_s"] = out["blocks_temp"] * temp_sec
    out["attacker_injections"] = int((atk.action == "send").sum()) if len(atk) else 0
    return out


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
        # A window is scored if its time span overlaps the attack interval.
        # Window `win` spans (win*win_sec, (win+1)*win_sec]. Detection often
        # happens in the first overlapping window and then blocking suppresses
        # the attacker, so this must include that window rather than shift past
        # it. Baseline runs score the whole run.
        if no_attack:
            return True
        wstart, wend = win * window_sec, (win + 1) * window_sec
        return wstart < atk_end and wend > start

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
    net = network_metrics(tables, attackers)
    return {**net,
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
    win = eval_period(tables)
    m = compute(tables, truth, win)
    for k, v in m.items():
        print(f"{k:24} {v}")
    if a.json:
        pathlib.Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(a.json).write_text(json.dumps(m, indent=2))
        print(f"wrote {a.json}")


if __name__ == "__main__":
    main()
