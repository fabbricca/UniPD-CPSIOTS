#!/usr/bin/env python3
"""Generate a headless Cooja scenario (.csc) and its ground-truth file.

Topology follows the paper's Fig. 6: the root (id 1) sits top-centre and the
other nodes fill a grid of `cols` columns below it with `spacing` metres
between neighbours. Attacker ids are chosen deterministically from `seed`
(overridable with --attacker-ids), so the same seed gives the same topology
and the same attacker placement across detector modes.

The generator writes <out>.truth.csv listing attacker ids, type and rate. The
analysis joins IDS alerts against this file and never infers ground truth from
IDS output.

Examples:
  gen_scenario.py --nodes 10 --spacing 30 --seed 1 --out simulations/dev-10-baseline-s1.csc
  gen_scenario.py --nodes 10 --attack neighbor --attackers 1 --attack-period-ms 5000 \
      --seed 1 --out simulations/dev-10-neighbor-a1-s1.csc
  gen_scenario.py --nodes 30 --attack dis --attackers 20% --seed 3 \
      --out simulations/final-30-dis-a20-s3.csc
"""
import argparse
import pathlib
import random
from xml.sax.saxutils import escape

INTERFACES = """      <moteinterface>org.contikios.cooja.interfaces.Position</moteinterface>
      <moteinterface>org.contikios.cooja.interfaces.Battery</moteinterface>
      <moteinterface>org.contikios.cooja.contikimote.interfaces.ContikiVib</moteinterface>
      <moteinterface>org.contikios.cooja.contikimote.interfaces.ContikiMoteID</moteinterface>
      <moteinterface>org.contikios.cooja.contikimote.interfaces.ContikiRS232</moteinterface>
      <moteinterface>org.contikios.cooja.contikimote.interfaces.ContikiBeeper</moteinterface>
      <moteinterface>org.contikios.cooja.interfaces.RimeAddress</moteinterface>
      <moteinterface>org.contikios.cooja.interfaces.IPAddress</moteinterface>
      <moteinterface>org.contikios.cooja.contikimote.interfaces.ContikiRadio</moteinterface>
      <moteinterface>org.contikios.cooja.contikimote.interfaces.ContikiButton</moteinterface>
      <moteinterface>org.contikios.cooja.contikimote.interfaces.ContikiPIR</moteinterface>
      <moteinterface>org.contikios.cooja.contikimote.interfaces.ContikiClock</moteinterface>
      <moteinterface>org.contikios.cooja.contikimote.interfaces.ContikiLED</moteinterface>
      <moteinterface>org.contikios.cooja.contikimote.interfaces.ContikiCFS</moteinterface>
      <moteinterface>org.contikios.cooja.interfaces.Mote2MoteRelations</moteinterface>
      <moteinterface>org.contikios.cooja.interfaces.MoteAttributes</moteinterface>
"""

# Generic control script: log everything, stop at the timeout, always TEST OK.
# Experiment pass/fail is decided host-side by parse_logs.py. Bare assignments:
# the TIMEOUT action runs in global scope and cannot see `var` locals.
SCRIPT = """/* rpl-ids control script (generated). */
TIMEOUT({timeout_ms}, log.log("SUMMARY end_us=" + time + "\\n"); log.testOK(););
while (true) {{
  YIELD();
  log.log(time + "\\t" + id + "\\t" + msg + "\\n");
}}
"""

FIRMWARE = {"neighbor": "neighbor-attacker", "dis": "dis-attacker"}


def mote_xml(mid, x, y):
    return (f"      <mote>\n"
            f"        <interface_config>\n"
            f"          org.contikios.cooja.interfaces.Position\n"
            f"          <pos x=\"{x:.2f}\" y=\"{y:.2f}\" />\n"
            f"        </interface_config>\n"
            f"        <interface_config>\n"
            f"          org.contikios.cooja.contikimote.interfaces.ContikiMoteID\n"
            f"          <id>{mid}</id>\n"
            f"        </interface_config>\n"
            f"      </mote>\n")


def motetype_xml(desc, firmware, ids, pos, make_vars):
    src = f"[CONFIG_DIR]/../firmware/{firmware}.c"
    cmd = f"$(MAKE) -j$(CPUS) {firmware}.cooja TARGET=cooja {make_vars}".rstrip()
    motes = "".join(mote_xml(i, *pos[i]) for i in ids)
    return (f"    <motetype>\n      org.contikios.cooja.contikimote.ContikiMoteType\n"
            f"      <description>{escape(desc)}</description>\n"
            f"      <source>{src}</source>\n      <commands>{escape(cmd)}</commands>\n"
            f"{INTERFACES}{motes}    </motetype>\n")


def grid_positions(n_nodes, cols, spacing):
    """Root (id 1) at top centre, remaining nodes row by row beneath it."""
    width = (cols - 1) * spacing
    pos = {1: (width / 2.0, 0.0)}
    for i in range(n_nodes - 1):
        r, c = divmod(i, cols)
        pos[2 + i] = (c * spacing, (r + 1) * spacing)
    return pos


def pick_attackers(args, node_ids):
    if args.attack == "baseline" or args.attackers in (None, "0"):
        return []
    if args.attacker_ids:
        ids = [int(x) for x in args.attacker_ids.split(",")]
        assert all(i in node_ids for i in ids), f"attacker id not a normal node: {ids}"
        return sorted(ids)
    spec = args.attackers
    if spec.endswith("%"):
        k = max(1, round(len(node_ids) * float(spec[:-1]) / 100.0))
    else:
        k = int(spec)
    rng = random.Random(args.seed)
    return sorted(rng.sample(node_ids, k))


def build(args):
    cols = args.cols or (5 if args.nodes > 10 else 3)
    pos = grid_positions(args.nodes, cols, args.spacing)
    node_ids = list(range(2, args.nodes + 1))
    attackers = pick_attackers(args, node_ids)
    normal_ids = [i for i in node_ids if i not in attackers]

    ids_vars = " ".join(v for v in [
        f"IDS_MODE={args.mode.upper()}",
        f"IDS_WINDOW_SEC={args.window}" if args.window else "",
        f"APP_SEND_INTERVAL_SEC={args.send_interval}" if args.send_interval else "",
        f"IDS_DIS_THRESHOLD={args.dis_threshold}" if args.dis_threshold else "",
        f"IDS_WARMUP_WINDOWS={args.warmup}" if args.warmup else "",
    ] if v)
    atk_vars = " ".join(v for v in [
        f"ATTACK_START_SEC={args.attack_start}" if args.attack_start else "",
        f"ATTACK_DURATION_SEC={args.attack_duration}" if args.attack_duration is not None else "",
        f"ATTACK_PERIOD_MS={args.attack_period_ms}" if args.attack_period_ms is not None else "",
    ] if v)

    types = [motetype_xml("RPL root + UDP sink", "rpl-ids-root", [1], pos, ids_vars)]
    if normal_ids:
        types.append(motetype_xml("Normal node (UDP client + IDS)", "rpl-ids-node",
                                   normal_ids, pos, ids_vars))
    if attackers:
        types.append(motetype_xml(f"{args.attack} attacker", FIRMWARE[args.attack],
                                   attackers, pos, (ids_vars + " " + atk_vars).strip()))

    title = (f"rpl-ids {args.nodes} nodes, {args.spacing:g} m grid, {args.attack}, "
             f"attackers={attackers}, seed {args.seed}, {args.mode}, {args.duration} min")
    script = SCRIPT.format(timeout_ms=args.duration * 60 * 1000)
    csc = f"""<?xml version="1.0" encoding="UTF-8"?>
<simconf version="2022112801">
  <simulation>
    <title>{escape(title)}</title>
    <randomseed>{args.seed}</randomseed>
    <motedelay_us>1000000</motedelay_us>
    <radiomedium>
      org.contikios.cooja.radiomediums.UDGM
      <transmitting_range>{args.tx_range:.1f}</transmitting_range>
      <interference_range>{args.int_range:.1f}</interference_range>
      <success_ratio_tx>1.0</success_ratio_tx>
      <success_ratio_rx>1.0</success_ratio_rx>
    </radiomedium>
    <events>
      <logoutput>40000</logoutput>
    </events>
{''.join(types)}  </simulation>
  <plugin>
    org.contikios.cooja.plugins.ScriptRunner
    <plugin_config>
      <script>{escape(script)}</script>
      <active>true</active>
    </plugin_config>
    <bounds x="0" y="0" height="600" width="900" />
  </plugin>
</simconf>
"""
    period = args.attack_period_ms if args.attack_period_ms is not None else 0
    truth = ["attacker_id,attack_type,period_ms,start_sec,duration_sec"]
    for a in attackers:
        truth.append(f"{a},{args.attack},{period},"
                     f"{args.attack_start or 75},{args.attack_duration if args.attack_duration is not None else 600}")
    return csc, "\n".join(truth) + "\n", attackers


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--nodes", type=int, required=True, help="total motes including the root")
    ap.add_argument("--spacing", type=float, default=30.0, help="grid spacing m (paper: 20/30/40)")
    ap.add_argument("--cols", type=int, default=0, help="grid columns (default 5, or 3 for <=10 nodes)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--duration", type=int, default=5, help="simulated minutes")
    ap.add_argument("--tx-range", type=float, default=50.0)
    ap.add_argument("--int-range", type=float, default=100.0)
    ap.add_argument("--mode", choices=["paper", "sliding"], default="paper")
    ap.add_argument("--window", type=int, default=0, help="override IDS_WINDOW_SEC")
    ap.add_argument("--send-interval", type=int, default=0, help="override APP_SEND_INTERVAL_SEC")
    ap.add_argument("--dis-threshold", type=int, default=0, help="override IDS_DIS_THRESHOLD (paper: 3)")
    ap.add_argument("--warmup", type=int, default=0, help="override IDS_WARMUP_WINDOWS (paper: 0)")
    ap.add_argument("--attack", choices=["baseline", "neighbor", "dis"], default="baseline")
    ap.add_argument("--attackers", default="0", help="count (e.g. 1) or percentage (e.g. 20%%)")
    ap.add_argument("--attacker-ids", default="", help="comma list, overrides seed-based placement")
    ap.add_argument("--attack-start", type=int, default=0, help="ATTACK_START_SEC (paper: 75)")
    ap.add_argument("--attack-duration", type=int, default=None, help="ATTACK_DURATION_SEC (0=to end)")
    ap.add_argument("--attack-period-ms", type=int, default=None, help="ATTACK_PERIOD_MS (0=random 5-60s)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    csc, truth, attackers = build(args)
    out = pathlib.Path(args.out)
    out.write_text(csc)
    truth_path = out.with_suffix(".truth.csv")
    truth_path.write_text(truth)
    print(f"wrote {out} (nodes={args.nodes}, attack={args.attack}, attackers={attackers}, seed={args.seed})")
    print(f"wrote {truth_path}")


if __name__ == "__main__":
    main()
