#!/usr/bin/env python3
"""Generate a headless Cooja scenario (.csc) for the RPL IDS experiment.

Topology follows the paper's Fig. 6: the root (id 1) sits top-centre and the
other nodes fill a grid of `cols` columns below it with `spacing` metres
between neighbours. Attacker placement (section 4) will be drawn from `seed`.

Example:
  scripts/gen_scenario.py --nodes 10 --spacing 30 --duration 5 --seed 1 \
      --out simulations/dev-10-baseline-s1.csc
"""
import argparse
import math
import pathlib
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
# Experiment pass/fail is decided host-side by parse_logs.py.
SCRIPT = """/* rpl-ids control script (generated). Bare assignments on purpose: the
 * TIMEOUT action runs in global scope and cannot see `var` locals. */
TIMEOUT({timeout_ms}, log.log("SUMMARY end_us=" + time + "\\n"); log.testOK(););
while (true) {{
  YIELD();
  log.log(time + "\\t" + id + "\\t" + msg + "\\n");
}}
"""


def mote_xml(mid, x, y):
    return f"""      <mote>
        <interface_config>
          org.contikios.cooja.interfaces.Position
          <pos x="{x:.2f}" y="{y:.2f}" />
        </interface_config>
        <interface_config>
          org.contikios.cooja.contikimote.interfaces.ContikiMoteID
          <id>{mid}</id>
        </interface_config>
      </mote>
"""


def motetype_xml(desc, firmware, motes, make_vars):
    src = f"[CONFIG_DIR]/../firmware/{firmware}.c"
    cmd = f"$(MAKE) -j$(CPUS) {firmware}.cooja TARGET=cooja {make_vars}".rstrip()
    return (f"    <motetype>\n      org.contikios.cooja.contikimote.ContikiMoteType\n"
            f"      <description>{escape(desc)}</description>\n"
            f"      <source>{src}</source>\n      <commands>{escape(cmd)}</commands>\n"
            f"{INTERFACES}{''.join(motes)}    </motetype>\n")


def grid_positions(n_nodes, cols, spacing):
    """Root at top centre, remaining nodes row by row beneath it."""
    others = n_nodes - 1
    width = (cols - 1) * spacing
    pos = {1: (width / 2.0, 0.0)}
    for i in range(others):
        r, c = divmod(i, cols)
        pos[2 + i] = (c * spacing, (r + 1) * spacing)
    return pos


def build(args):
    cols = args.cols or (5 if args.nodes > 10 else 3)
    pos = grid_positions(args.nodes, cols, args.spacing)
    make_vars = " ".join(v for v in [
        f"IDS_MODE={args.mode.upper()}",
        f"IDS_WINDOW_SEC={args.window}" if args.window else "",
        f"APP_SEND_INTERVAL_SEC={args.send_interval}" if args.send_interval else "",
        f"IDS_DIS_THRESHOLD={args.dis_threshold}" if args.dis_threshold else "",
        f"IDS_WARMUP_WINDOWS={args.warmup}" if args.warmup else "",
    ] if v)
    root = [mote_xml(1, *pos[1])]
    nodes = [mote_xml(i, *pos[i]) for i in range(2, args.nodes + 1)]
    title = (f"rpl-ids {args.nodes} nodes, {args.spacing} m grid, baseline, "
             f"seed {args.seed}, {args.mode} detector, {args.duration} min")
    script = SCRIPT.format(timeout_ms=args.duration * 60 * 1000)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
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
{motetype_xml("RPL root + UDP sink", "rpl-ids-root", root, make_vars)}{motetype_xml("Normal node (UDP client + IDS)", "rpl-ids-node", nodes, make_vars)}  </simulation>
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


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--nodes", type=int, required=True, help="total motes including the root")
    ap.add_argument("--spacing", type=float, default=30.0, help="grid spacing in metres (paper: 20/30/40)")
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
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    out = pathlib.Path(args.out)
    out.write_text(build(args))
    print(f"wrote {out} ({args.nodes} motes, cols={args.cols or (5 if args.nodes > 10 else 3)}, seed={args.seed})")


if __name__ == "__main__":
    main()
