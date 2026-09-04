#!/usr/bin/env python3
"""Parse a Cooja run log (time<TAB>mote<TAB>msg) into tidy CSV tables.

Record tags emitted by the firmware (see include/ids.h):
  EV, NBR, WIN, PAR (ids.c)   TX, STAT (node)   RX, RSTAT (root)
Lines without a known tag (Contiki log module output) are ignored.

Usage: parse_logs.py logs/<run>.log [--out results/] [--summary]
Writes results/<run>.<table>.csv and, with --summary, prints a human check:
join times, per-window DIO/DIS distribution, PDR.
"""
import argparse
import pathlib
import sys

import pandas as pd

SCHEMAS = {
    "EV":    ["kind", "nbr"],
    "NBR":   ["win", "nbr", "dio", "dis", "dropped", "bstate"],
    "DET":   ["win", "n", "mean_x1000", "sigma_x1000", "k_x1000", "thr_x1000"],
    "ALERT": ["win", "nbr", "kind", "count", "thr_x1000"],
    "BLOCK": ["nbr", "action", "block_count", "duration"],
    "WIN":   ["win", "n_heard", "n_rpl", "dio_sum", "dis_sum"],
    "PAR":   ["old", "new", "changes"],
    "TX":    ["seq"],
    "STAT":  ["rank", "parent", "parent_changes", "tx", "rpl_nbrs", "ids_nbrs"],
    "RX":    ["from", "seq"],
    "RSTAT": ["rx_total", "rpl_nbrs", "routes"],
    "IDS":   ["init", "window", "dis_thr", "block_thr", "temp_block", "warmup", "mode"],
}


def parse(path):
    rows = {tag: [] for tag in SCHEMAS}
    with open(path, errors="replace") as fh:
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 3:
                continue
            t, mote, tag = parts[0], parts[1], parts[2]
            if tag not in SCHEMAS or not t.isdigit():
                continue
            fields = parts[3:]
            if tag == "IDS":      # key=value fields -> values only
                fields = [f.split("=", 1)[1] if "=" in f else f for f in fields]
            cols = SCHEMAS[tag]
            fields = (fields + [None] * len(cols))[:len(cols)]
            rows[tag].append([int(t) / 1e6, int(mote)] + fields)
    tables = {}
    for tag, cols in SCHEMAS.items():
        df = pd.DataFrame(rows[tag], columns=["t", "mote"] + cols)
        for c in cols:
            if c not in ("kind", "action", "init", "mode"):
                df[c] = pd.to_numeric(df[c], errors="coerce")
        tables[tag] = df
    return tables


def summary(tables):
    out = []
    stat, tx, rx, nbr, win = (tables[k] for k in ("STAT", "TX", "RX", "NBR", "WIN"))
    out.append(f"motes seen: root=1, nodes={sorted(stat.mote.unique().tolist())}")
    joined = stat[stat["rank"] > 0].groupby("mote").t.min()
    out.append(f"first STAT with rank>0 (s): min={joined.min():.0f} max={joined.max():.0f} "
               f"missing={sorted(set(stat.mote.unique()) - set(joined.index))}")
    tx_n = tx.groupby("mote").size()
    rx_n = rx.groupby("from").size()
    pdr = (rx_n / tx_n).fillna(0)
    out.append(f"PDR per node: mean={pdr.mean():.3f} min={pdr.min():.3f} "
               f"(tx total={int(tx_n.sum())}, rx total={int(rx_n.sum())})")
    pc = stat.groupby("mote").parent_changes.max()
    out.append(f"parent changes per node: mean={pc.mean():.2f} max={int(pc.max())}")
    if len(nbr):
        g = nbr.groupby("win").dio
        out.append("per-window DIO count per (monitor, neighbour): "
                   + ", ".join(f"w{int(w)}: n={len(s)} mean={s.mean():.2f} sd={s.std(ddof=0):.2f} max={int(s.max())}"
                               for w, s in g))
        gd = nbr.groupby("win").dis
        out.append("per-window DIS count max: " + ", ".join(f"w{int(w)}={int(s.max())}" for w, s in gd))
        out.append("neighbours heard per monitor (last window): "
                   f"mean={win.groupby('mote').n_heard.last().mean():.1f}, "
                   f"RPL table: mean={win.groupby('mote').n_rpl.last().mean():.1f}")
    alert, det, block = tables["ALERT"], tables["DET"], tables["BLOCK"]
    if len(det):
        samples = nbr.groupby("win").size()
        per_win = alert.groupby("win").size() if len(alert) else {}
        out.append("alerts per window (samples = monitor x neighbour decisions): "
                   + ", ".join(f"w{int(w)}: {int(per_win.get(w, 0))}/{int(samples[w])}" for w in samples.index))
        out.append(f"alert kinds: {alert.kind.value_counts().to_dict() if len(alert) else {}}; "
                   f"blocks: {block.action.value_counts().to_dict() if len(block) else {}}")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("log")
    ap.add_argument("--out", default="results")
    ap.add_argument("--summary", action="store_true")
    a = ap.parse_args()
    name = pathlib.Path(a.log).stem
    tables = parse(a.log)
    outdir = pathlib.Path(a.out); outdir.mkdir(parents=True, exist_ok=True)
    for tag, df in tables.items():
        if len(df):
            df.to_csv(outdir / f"{name}.{tag.lower()}.csv", index=False)
    counts = {tag: len(df) for tag, df in tables.items() if len(df)}
    print(f"{name}: records {counts}")
    if a.summary:
        print(summary(tables))


if __name__ == "__main__":
    sys.exit(main())
