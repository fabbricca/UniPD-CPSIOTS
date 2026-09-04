#!/usr/bin/env python3
"""Generate, run and score a matrix of scenarios, one metrics row per run.

A matrix is a list of scenario templates; each is expanded over a seed list
and, optionally, over detector modes. For every expanded run this driver:
  1. calls gen_scenario.py to write the .csc and .truth.csv,
  2. runs it headless via run_scenario.sh,
  3. parses the log and computes metrics with calculate_metrics.py,
  4. appends one row (config fields + metrics) to results/matrix.csv and writes
     results/<name>.metrics.json.
Runs are skipped when the metrics JSON already exists unless --force is given,
so an interrupted matrix resumes cheaply.

Presets (see PRESETS): "dev" (fast, 10-node, 3 seeds), "paper" (the plan's
final matrix, 20/30/40 nodes, 5 seeds). Select rows with --preset or point at
a JSON matrix file with --matrix.

Usage:
  run_matrix.py --preset dev
  run_matrix.py --preset dev --modes paper sliding
  run_matrix.py --matrix my.json --seeds 1 2 3 4 5
"""
import argparse
import csv
import json
import pathlib
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import parse_logs as pl          # noqa: E402
import calculate_metrics as cm   # noqa: E402

# Each template: nodes, spacing, attack, attackers, rate (period ms), duration
# (sim minutes), window (s). attack_period_ms/attack_start/attack_duration in s
# where relevant. Seeds and modes are applied by the driver.
PRESETS = {
    "dev": [
        dict(nodes=10, spacing=30, attack="baseline", attackers="0", duration=10, window=60),
        dict(nodes=10, spacing=30, attack="neighbor", attackers="1", period_ms=10000,
             attack_start=75, attack_duration=0, duration=10, window=60),
        dict(nodes=10, spacing=30, attack="dis", attackers="1", period_ms=10000,
             attack_start=75, attack_duration=0, duration=10, window=60),
    ],
    "paper": [
        dict(nodes=20, spacing=20, attack="baseline", attackers="0", duration=30, window=300),
        dict(nodes=20, spacing=20, attack="neighbor", attackers="1", period_ms=10000,
             attack_start=75, attack_duration=600, duration=30, window=300),
        dict(nodes=20, spacing=20, attack="dis", attackers="1", period_ms=10000,
             attack_start=75, attack_duration=600, duration=30, window=300),
        dict(nodes=30, spacing=20, attack="neighbor", attackers="20%", period_ms=10000,
             attack_start=75, attack_duration=600, duration=30, window=300),
        dict(nodes=30, spacing=20, attack="dis", attackers="20%", period_ms=10000,
             attack_start=75, attack_duration=600, duration=30, window=300),
        dict(nodes=40, spacing=20, attack="neighbor", attackers="30%", period_ms=5000,
             attack_start=75, attack_duration=600, duration=30, window=300),
        dict(nodes=40, spacing=20, attack="dis", attackers="30%", period_ms=5000,
             attack_start=75, attack_duration=600, duration=30, window=300),
    ],
}

CONFIG_FIELDS = ["name", "nodes", "spacing", "attack", "attackers", "seed", "mode",
                 "window", "period_ms", "duration"]
METRIC_FIELDS = ["attackers_detected", "node_TP", "node_FP", "node_FN", "node_TN",
                 "node_TPR", "node_FPR", "node_precision", "node_F1",
                 "dec_TP", "dec_FP", "dec_FN", "dec_TN", "dec_TPR", "dec_FPR",
                 "detection_latency_sec"]


def scenario_name(t, seed, mode):
    pct = t["attackers"].replace("%", "pct")
    a = "base" if t["attack"] == "baseline" else f"{t['attack']}-a{pct}"
    return f"m-{t['nodes']}-{a}-w{t['window']}-{mode}-s{seed}"


def gen_cmd(t, seed, mode, out):
    c = ["python", str(HERE / "gen_scenario.py"),
         "--nodes", str(t["nodes"]), "--spacing", str(t["spacing"]),
         "--seed", str(seed), "--duration", str(t["duration"]),
         "--window", str(t["window"]), "--mode", mode,
         "--attack", t["attack"], "--attackers", str(t["attackers"]), "--out", out]
    if t.get("period_ms") is not None:
        c += ["--attack-period-ms", str(t["period_ms"])]
    if t.get("attack_start") is not None:
        c += ["--attack-start", str(t["attack_start"])]
    if t.get("attack_duration") is not None:
        c += ["--attack-duration", str(t["attack_duration"])]
    return c


def run_one(t, seed, mode, force):
    name = scenario_name(t, seed, mode)
    csc = ROOT / "simulations" / f"{name}.csc"
    log = ROOT / "logs" / f"{name}.log"
    mjson = ROOT / "results" / f"{name}.metrics.json"
    if mjson.exists() and not force:
        return json.loads(mjson.read_text()), name, "cached"

    subprocess.run(gen_cmd(t, seed, mode, str(csc)), check=True,
                   stdout=subprocess.DEVNULL)
    r = subprocess.run([str(ROOT / "scripts" / "run_scenario.sh"), str(csc)],
                       capture_output=True, text=True)
    if not log.exists():
        raise RuntimeError(f"{name}: no log produced\n{r.stdout[-500:]}\n{r.stderr[-500:]}")
    tables = pl.parse(log)
    truth = cm.load_truth(csc.with_suffix(".truth.csv"))
    win = int(tables["IDS"].iloc[0]["window"]) if len(tables["IDS"]) else t["window"]
    m = cm.compute(tables, truth, win)
    mjson.parent.mkdir(parents=True, exist_ok=True)
    mjson.write_text(json.dumps(m, indent=2))
    return m, name, "ran"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--preset", choices=list(PRESETS), default="dev")
    ap.add_argument("--matrix", help="JSON file with a list of scenario templates")
    ap.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3])
    ap.add_argument("--modes", nargs="+", default=["paper"], choices=["paper", "sliding"])
    ap.add_argument("--force", action="store_true", help="re-run even if metrics exist")
    ap.add_argument("--out", default=str(ROOT / "results" / "matrix.csv"))
    a = ap.parse_args()

    templates = json.loads(pathlib.Path(a.matrix).read_text()) if a.matrix else PRESETS[a.preset]
    rows = []
    t0 = time.time()
    for t in templates:
        for mode in a.modes:
            for seed in a.seeds:
                m, name, how = run_one(t, seed, mode, a.force)
                row = {"name": name, "nodes": t["nodes"], "spacing": t["spacing"],
                       "attack": t["attack"], "attackers": t["attackers"], "seed": seed,
                       "mode": mode, "window": t["window"],
                       "period_ms": t.get("period_ms", 0), "duration": t["duration"]}
                for f in METRIC_FIELDS:
                    v = m.get(f)
                    row[f] = ";".join(map(str, v)) if isinstance(v, list) else v
                rows.append(row)
                print(f"[{how:5}] {name}: node_TPR={m['node_TPR']} node_FPR={m['node_FPR']:.3f} "
                      f"lat={m['detection_latency_sec']}")
    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CONFIG_FIELDS + METRIC_FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"\n{len(rows)} runs in {time.time()-t0:.0f}s -> {out}")


if __name__ == "__main__":
    main()
