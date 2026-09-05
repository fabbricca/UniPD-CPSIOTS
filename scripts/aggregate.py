#!/usr/bin/env python3
"""Aggregate results/matrix.csv into a per-configuration summary.

Groups rows by (nodes, attack, attackers, mode, window) and reports the mean,
min, max and standard deviation across seeds for the node-level TPR/FPR and
detection latency, in the layout of the paper's Table III. Writes
results/summary.csv and prints a readable table.

Usage: aggregate.py [results/matrix.csv] [--out results/summary.csv]
"""
import argparse
import pathlib

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
GROUP = ["nodes", "attack", "attackers", "mode", "window", "dis_threshold", "period_ms", "tag"]
AGG = {"node_TPR": "%", "node_FPR": "%", "dec_FPR": "%", "detection_latency_sec": "s",
       "pdr": "", "pdr_normal": "", "delay_mean_s": "s", "dio_rx_per_node_min": "/min",
       "dis_rx_per_node_min": "/min", "parent_changes_per_node": "", "blocks_temp": "",
       "blocks_perm": "", "temp_block_time_s": "s"}


def summarise(df):
    out = []
    for key, g in df.groupby(GROUP):
        row = dict(zip(GROUP, key))
        row["seeds"] = len(g)
        for col in AGG:
            s = g[col].dropna()
            row[f"{col}_mean"] = round(s.mean(), 4) if len(s) else float("nan")
            row[f"{col}_std"] = round(s.std(ddof=0), 4) if len(s) else float("nan")
            row[f"{col}_min"] = round(s.min(), 4) if len(s) else float("nan")
            row[f"{col}_max"] = round(s.max(), 4) if len(s) else float("nan")
        out.append(row)
    return pd.DataFrame(out).sort_values(GROUP)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("matrix", nargs="?", default=str(ROOT / "results" / "matrix.csv"))
    ap.add_argument("--out", default=str(ROOT / "results" / "summary.csv"))
    a = ap.parse_args()
    df = pd.read_csv(a.matrix)
    s = summarise(df)
    s.to_csv(a.out, index=False)
    # Compact console view (paper Table III style).
    show = s[GROUP + ["seeds", "node_TPR_mean", "node_FPR_mean", "node_FPR_std",
                      "detection_latency_sec_mean", "pdr_mean", "delay_mean_s_mean",
                      "dio_rx_per_node_min_mean", "parent_changes_per_node_mean",
                      "blocks_perm_mean"]].copy()
    show["TPR%"] = (show.pop("node_TPR_mean") * 100).round(1)
    show["FPR%"] = (show.pop("node_FPR_mean") * 100).round(2)
    show["FPRsd%"] = (show.pop("node_FPR_std") * 100).round(2)
    show["lat_s"] = show.pop("detection_latency_sec_mean").round(0)
    show["PDR"] = show.pop("pdr_mean").round(3)
    show["delay_s"] = show.pop("delay_mean_s_mean").round(3)
    show["DIO/node/min"] = show.pop("dio_rx_per_node_min_mean").round(2)
    show["par_chg"] = show.pop("parent_changes_per_node_mean").round(2)
    show["perm_blk"] = show.pop("blocks_perm_mean").round(1)
    with pd.option_context("display.width", 220, "display.max_columns", None):
        print(show.to_string(index=False))
    print(f"\nwrote {a.out}")


if __name__ == "__main__":
    main()
