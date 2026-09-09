#!/usr/bin/env python3
"""Replay every run log through the Python reference model of the detector.

For each (monitor, window) the NBR records give the per-neighbour counts. The
model in ids_model.py must reproduce the firmware's DET line (n, mean, sigma,
k, threshold) exactly and produce exactly the same set of ALERT lines. Any
mismatch means the mote arithmetic and the host analysis have diverged.

Deliberately plain-Python: the pandas parser in parse_logs.py is convenient but
far too slow to sweep the whole logs/ directory, and this check is only useful
if it is cheap enough to run over all of it rather than a curated sample.
"""
import argparse
import collections
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import ids_model as m  # noqa: E402


def replay(log):
    """Return (decisions_checked, list of mismatch descriptions) for one log."""
    nbr = collections.defaultdict(list)
    det = {}
    alert = collections.defaultdict(lambda: (set(), set()))
    dis_thr = 3
    with open(log, errors="replace") as fh:
        for line in fh:
            p = line.rstrip("\n").split("\t")
            if len(p) < 4:
                continue
            tag = p[2]
            if tag == "NBR":
                nbr[(int(p[1]), int(p[3]))].append((int(p[4]), int(p[5]), int(p[6])))
            elif tag == "DET":
                det[(int(p[1]), int(p[3]))] = tuple(int(v) for v in p[4:9])
            elif tag == "ALERT":
                dio_set, dis_set = alert[(int(p[1]), int(p[3]))]
                (dio_set if p[5] == "DIO" else dis_set).add(int(p[4]))
            elif tag == "IDS":
                for f in p[3:]:
                    if f.startswith("dis_thr="):
                        dis_thr = int(f.split("=", 1)[1])
    if not det:
        # Pre-dates the DET record (early development logs). There is nothing
        # to compare against, which is not the same as a disagreement.
        return 0, [], True
    checked, bad = 0, []
    for key, rows in sorted(nbr.items()):
        rows.sort()
        ids = [r[0] for r in rows]
        dio = [r[1] for r in rows]
        dis = [r[2] for r in rows]
        got, exp = m.profile(dio), det.get(key)
        if got != exp:
            bad.append(f"{log}:{key} profile model={got} firmware={exp}")
            continue
        got_dio, got_dis = alert.get(key, (set(), set()))
        exp_dio = {ids[i] for i in m.dio_alerts(dio)}
        exp_dis = {ids[i] for i in m.dis_alerts(dis, dis_thr)}
        if got_dio != exp_dio or got_dis != exp_dis:
            bad.append(f"{log}:{key} alerts firmware={sorted(got_dio)}/{sorted(got_dis)} "
                       f"model={sorted(exp_dio)}/{sorted(exp_dis)}")
            continue
        checked += 1
    return checked, bad, False


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("logs", nargs="*", default=None,
                    help="log files (default: every logs/*.log)")
    ap.add_argument("--out", default=str(ROOT / "results" / "replay_check.txt"))
    a = ap.parse_args()
    logs = [pathlib.Path(x) for x in a.logs] or sorted((ROOT / "logs").glob("*.log"))
    total, files, skipped, bad = 0, 0, 0, []
    for log in logs:
        c, b, no_det = replay(log)
        if no_det:
            skipped += 1
            continue
        if c or b:
            files += 1
        total += c
        bad += b
    lines = [f"logs replayed:            {files}",
             f"logs skipped (no DET records, pre-dating the format): {skipped}",
             f"(monitor, window) decisions checked: {total}",
             f"mismatches:               {len(bad)}"]
    lines += ["", "FAILURES:"] + bad[:20] if bad else []
    text = "\n".join(lines) + "\n"
    print(text, end="")
    if a.out:
        out = pathlib.Path(a.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("Bit-exact replay of firmware/ids.c against scripts/ids_model.py\n"
                       "===============================================================\n" + text)
        print(f"wrote {a.out}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
