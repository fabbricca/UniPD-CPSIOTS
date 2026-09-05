#!/usr/bin/env python3
"""Produce the figures required by PROJECT_PLAN section 10.

Two groups:
  per-run   from one run log: DIO/DIS counts over time, threshold vs observed
            count for the attacker's monitor, alerts on the timeline.
  matrix    from results/matrix.csv: TPR and FPR by network size, detection
            latency by attack rate, PDR baseline vs attack.

Usage:
  plot_results.py run  logs/<run>.log [--truth ...] [--outdir report/figures]
  plot_results.py matrix [results/matrix.csv] [--outdir report/figures]
  plot_results.py topology simulations/<scenario>.csc [--outdir report/figures]
"""
import argparse
import pathlib
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt   # noqa: E402
import pandas as pd               # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import parse_logs as pl           # noqa: E402
import calculate_metrics as cm    # noqa: E402

FIGS = ROOT / "report" / "figures"


def _save(fig, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    print(f"wrote {path}")


def plot_run(log, truth_path, outdir):
    stem = pathlib.Path(log).stem
    t = pl.parse(log)
    nbr, det, alert = t["NBR"], t["DET"], t["ALERT"]
    truth = cm.load_truth(truth_path or (pathlib.Path("simulations") / f"{stem}.truth.csv"))
    attackers = set(truth.attacker_id.astype(int)) if len(truth) else set()

    # 1. DIO count per neighbour over time, attacker highlighted.
    if len(nbr):
        fig, ax = plt.subplots(figsize=(8, 4))
        for nid, g in nbr.groupby("nbr"):
            g = g.sort_values("win")
            is_atk = int(nid) in attackers
            ax.plot(g.win, g.dio, marker="o", ms=3, lw=2 if is_atk else 0.8,
                    color="crimson" if is_atk else "0.7",
                    label=f"attacker {nid}" if is_atk else None, zorder=3 if is_atk else 1)
        ax.set_xlabel("observation window"); ax.set_ylabel("DIO count")
        ax.set_title(f"DIO per neighbour over time - {stem}")
        if attackers:
            ax.legend()
        _save(fig, outdir / f"{stem}.dio_over_time.png")

        # 2. DIS count per neighbour over time.
        fig, ax = plt.subplots(figsize=(8, 4))
        for nid, g in nbr.groupby("nbr"):
            g = g.sort_values("win")
            is_atk = int(nid) in attackers
            ax.plot(g.win, g.dis, marker="o", ms=3, lw=2 if is_atk else 0.8,
                    color="crimson" if is_atk else "0.7",
                    label=f"attacker {nid}" if is_atk else None, zorder=3 if is_atk else 1)
        ax.set_xlabel("observation window"); ax.set_ylabel("DIS count")
        ax.set_title(f"DIS per neighbour over time - {stem}")
        if attackers:
            ax.legend()
        _save(fig, outdir / f"{stem}.dis_over_time.png")

    # 3. Threshold vs observed count for the monitor that best sees the attacker.
    if len(det) and attackers:
        atk = min(attackers)
        seers = nbr[nbr.nbr == atk].mote.unique()
        if len(seers):
            # Prefer a monitor that actually flags the attacker (shows the
            # count crossing the threshold); fall back to the one that hears it
            # loudest, which illustrates a blind spot.
            flaggers = alert[(alert.nbr == atk)].mote.value_counts()
            if len(flaggers):
                mon = flaggers.idxmax()
            else:
                mon = nbr[(nbr.nbr == atk)].groupby("mote").dio.max().idxmax()
            d = det[det.mote == mon].sort_values("win")
            obs = nbr[(nbr.mote == mon) & (nbr.nbr == atk)].sort_values("win")
            fig, ax = plt.subplots(figsize=(8, 4))
            ax.plot(d.win, d.thr_x1000 / 1000.0, "k--", label="threshold mean+k sigma")
            ax.plot(d.win, d.mean_x1000 / 1000.0, color="0.6", label="neighbourhood mean")
            ax.plot(obs.win, obs.dio, "crimson", marker="o", label=f"attacker {atk} DIO")
            ax.set_xlabel("observation window"); ax.set_ylabel("DIO count")
            ax.set_title(f"threshold vs attacker at monitor {mon} - {stem}")
            ax.legend()
            _save(fig, outdir / f"{stem}.threshold_vs_count.png")

    # 4. Alerts on the timeline (monitor on y, window on x).
    if len(alert):
        fig, ax = plt.subplots(figsize=(8, 4))
        for kind, mk, col in (("DIO", "o", "crimson"), ("DIS", "s", "darkorange")):
            a = alert[alert.kind == kind]
            atk_mask = a.nbr.isin(attackers)
            ax.scatter(a[atk_mask].win, a[atk_mask].mote, marker=mk, color=col,
                       label=f"{kind} on attacker", zorder=3)
            ax.scatter(a[~atk_mask].win, a[~atk_mask].mote, marker=mk, facecolors="none",
                       edgecolors=col, label=f"{kind} false positive", zorder=2)
        ax.set_xlabel("observation window"); ax.set_ylabel("monitor id")
        ax.set_title(f"alerts on the timeline - {stem}")
        ax.legend(fontsize=8)
        _save(fig, outdir / f"{stem}.alerts_timeline.png")


def plot_topology(csc, outdir, show_range=True):
    """Node placement and roles read from a generated .csc (plan fig. 1)."""
    import xml.etree.ElementTree as ET
    root = ET.parse(csc).getroot()
    tx_range = float(root.findtext(".//radiomedium/transmitting_range") or 50)
    roles = {}  # id -> (x, y, role)
    for mt in root.iter("motetype"):
        desc = (mt.findtext("description") or "").lower()
        role = "attacker" if "attacker" in desc else ("root" if "root" in desc else "normal")
        for mote in mt.iter("mote"):
            pos = mote.find(".//pos")
            mid = int(mote.findtext(".//id"))
            roles[mid] = (float(pos.get("x")), float(pos.get("y")), role)
    fig, ax = plt.subplots(figsize=(6.5, 6.5))
    style = {"root": ("limegreen", "s", 160), "normal": ("gold", "o", 110),
             "attacker": ("mediumpurple", "o", 130)}
    for role in ("normal", "attacker", "root"):
        pts = [(x, y) for x, y, r in roles.values() if r == role]
        if pts:
            ax.scatter(*zip(*pts), c=style[role][0], marker=style[role][1], s=style[role][2],
                       edgecolors="k", label=role, zorder=3)
    for mid, (x, y, _) in roles.items():
        ax.annotate(str(mid), (x, y), ha="center", va="center", fontsize=7, zorder=4)
    if show_range:
        first_atk = next((k for k, v in roles.items() if v[2] == "attacker"), 1)
        x, y, _ = roles[first_atk]
        ax.add_patch(plt.Circle((x, y), tx_range, fill=False, ls="--", color="0.5",
                                label=f"{tx_range:g} m tx range of node {first_atk}"))
    ax.set_aspect("equal"); ax.invert_yaxis()
    ax.set_xlabel("x (m)"); ax.set_ylabel("y (m)")
    ax.set_title(f"topology - {pathlib.Path(csc).stem}")
    ax.legend(loc="lower right", fontsize=8)
    _save(fig, outdir / f"topology-{pathlib.Path(csc).stem}.png")


def plot_matrix(matrix, outdir):
    df = pd.read_csv(matrix)
    atk = df[df.attack != "baseline"]

    # 5. TPR and FPR by network size (node-level), per attack.
    if len(atk):
        fig, axes = plt.subplots(1, 2, figsize=(11, 4))
        for attack, g in atk.groupby("attack"):
            by = g.groupby("nodes")
            axes[0].errorbar(by.node_TPR.mean().index, by.node_TPR.mean() * 100,
                             yerr=by.node_TPR.std(ddof=0).fillna(0) * 100, marker="o",
                             capsize=3, label=attack)
            axes[1].errorbar(by.node_FPR.mean().index, by.node_FPR.mean() * 100,
                             yerr=by.node_FPR.std(ddof=0).fillna(0) * 100, marker="o",
                             capsize=3, label=attack)
        axes[0].set_ylabel("node TPR (%)"); axes[1].set_ylabel("node FPR (%)")
        for ax in axes:
            ax.set_xlabel("number of nodes"); ax.legend()
        fig.suptitle("detection rate by network size")
        _save(fig, outdir / "matrix.tpr_fpr_by_size.png")

    # 6. Detection latency by attack rate (period_ms).
    # Use the dedicated rate sweep (tag p<period>) when present so one topology
    # and attacker count are held fixed; otherwise fall back to all attack rows.
    tags = df["tag"].fillna("").astype(str) if "tag" in df.columns else None
    sweep = atk[tags.loc[atk.index].str.startswith("p")] if tags is not None else atk
    if len(sweep) == 0:
        sweep = atk
    if len(sweep):
        order = sorted(sweep.period_ms.unique(), key=lambda pm: (pm == 0, pm))  # random last
        def rate_label(pm):
            return "random\n5-60s" if int(pm) == 0 else f"{int(pm)/1000:g}s"
        xs_all = [rate_label(pm) for pm in order]
        fig, axes = plt.subplots(1, 2, figsize=(12, 4))
        for (attack, mode), g in sweep.groupby(["attack", "mode"]):
            by = g.groupby("period_ms")
            tpr = by.node_TPR.mean().reindex(order)
            lat_m = by.detection_latency_sec.mean().reindex(order)
            lat_s = by.detection_latency_sec.std(ddof=0).reindex(order).fillna(0)
            axes[0].errorbar(xs_all, lat_m, yerr=lat_s, marker="o", capsize=3,
                             label=f"{attack} / {mode}")
            axes[1].plot(xs_all, tpr * 100, marker="o", label=f"{attack} / {mode}")
        axes[0].set_ylabel("detection latency (s)  [missing = not detected]")
        axes[1].set_ylabel("node TPR (%)"); axes[1].set_ylim(-5, 105)
        for ax in axes:
            ax.set_xlabel("attack period"); ax.legend(fontsize=7)
        fig.suptitle("detection latency and TPR by attack rate (20 nodes, 1 attacker)")
        _save(fig, outdir / "matrix.latency_by_rate.png")

    # 6b. Network impact: PDR and DIO overhead, baseline vs attacks, per mode.
    if "pdr" in df.columns and df.pdr.notna().any():
        fig, axes = plt.subplots(1, 2, figsize=(11, 4))
        g = df.groupby(["attack", "mode"])
        labels = [f"{a}\n{m}" for a, m in g.groups]
        axes[0].bar(labels, g.pdr.mean() * 100, yerr=g.pdr.std(ddof=0).fillna(0) * 100, capsize=3)
        axes[0].set_ylabel("PDR (%)"); axes[0].set_ylim(0, 105)
        axes[0].set_title("packet delivery ratio")
        axes[1].bar(labels, g.dio_rx_per_node_min.mean(),
                    yerr=g.dio_rx_per_node_min.std(ddof=0).fillna(0), capsize=3)
        axes[1].set_ylabel("DIO receptions / node / min")
        axes[1].set_title("control-plane overhead")
        for ax in axes:
            ax.tick_params(axis="x", labelsize=8)
        fig.suptitle("network impact: baseline vs attacks")
        _save(fig, outdir / "matrix.network_impact.png")

    # 7. Mode comparison if both present: TPR/FPR/latency paper vs sliding.
    if df["mode"].nunique() > 1 and len(atk):
        fig, axes = plt.subplots(1, 3, figsize=(13, 4))
        for mode, g in atk.groupby("mode"):
            axes[0].bar(mode, g.node_TPR.mean() * 100)
            axes[1].bar(mode, g.node_FPR.mean() * 100)
            axes[2].bar(mode, g.detection_latency_sec.dropna().mean())
        axes[0].set_title("node TPR (%)"); axes[1].set_title("node FPR (%)")
        axes[2].set_title("mean latency (s)")
        fig.suptitle("paper (fixed) vs sliding detector")
        _save(fig, outdir / "matrix.mode_comparison.png")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run"); r.add_argument("log"); r.add_argument("--truth", default=None)
    r.add_argument("--outdir", default=str(FIGS))
    m = sub.add_parser("matrix"); m.add_argument("matrix", nargs="?",
                                                 default=str(ROOT / "results" / "matrix.csv"))
    m.add_argument("--outdir", default=str(FIGS))
    t = sub.add_parser("topology"); t.add_argument("csc"); t.add_argument("--outdir", default=str(FIGS))
    a = ap.parse_args()
    outdir = pathlib.Path(a.outdir)
    if a.cmd == "run":
        plot_run(a.log, a.truth, outdir)
    elif a.cmd == "topology":
        plot_topology(a.csc, outdir)
    else:
        plot_matrix(a.matrix, outdir)


if __name__ == "__main__":
    main()
