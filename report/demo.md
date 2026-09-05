# Live demonstration script (target: 8-10 minutes)

Everything runs from the pinned Docker image; nothing is installed on the host.
If Docker or the network is unavailable, use the fallback material in section F.

## A. Setup (before the session)

```bash
cd rpl-ids
./run.sh build          # once; ~5 min (clones Contiki-NG v5.2, builds Cooja)
./run.sh version        # show the recorded toolchain: Contiki-NG commit, Java, msp430-gcc
./run.sh test           # 28 host tests, ~2 s
```

## B. Show the network and the detector working (3 min)

```bash
./run.sh gen --nodes 10 --spacing 30 --seed 1 --attack neighbor --attackers 1 \
    --attack-period-ms 10000 --attack-start 75 --attack-duration 0 --duration 10 \
    --window 60 --out simulations/demo.csc
./run.sh sim simulations/demo.csc            # ~2 s wall time for 10 simulated minutes
./run.sh parse logs/demo.log --summary       # joins, PDR, per-window DIO distribution, alerts
./run.sh metrics logs/demo.log               # node-level + decision-level TPR/FPR, latency
```

Talking points: all nodes join within ~60 s; PDR 1.0; attacker id in
`simulations/demo.truth.csv`; monitors that flag it vs monitors that cannot
(blind spot, section D).

## C. The two figures (1 min)

```bash
./run.sh plot run logs/demo.log
```

Open `report/figures/demo.threshold_vs_count.png` (attacker above the
dynamic threshold at the detecting monitor) and `demo.alerts_timeline.png`
(filled = true positives, hollow = quantisation false positives).

## D. The blind spot in 30 seconds

Algorithm 1 uses the population standard deviation and the attacker is in the
sample, so max z = sqrt(n-1) (Samuelson). Show `include/ids-k-table.h`: k(5) =
2.03 > sqrt(4) = 2, k(6) = 2.28 > sqrt(5) = 2.24. Then in the demo log:

```bash
grep -P "\tALERT\t" logs/demo.log | cut -f2 | sort | uniq -c     # which monitors flag
```

Only the monitor(s) with >= 8 neighbours flag the attacker; those with 5-7 never do.

## E. The contribution: fixed vs sliding window (2 min)

Pre-run (section A) or show `results/summary.csv` and
`report/figures/matrix.mode_comparison.png`: latency 225 s -> ~25 s, node FPR
2.5% -> 13.5%, TPR 72% -> 76%. Explain the trade-off and why sliding partly
resists multi-attacker masking.

## F. Fallback if Cooja cannot run

* `report/report.md` (full write-up), `results/summary.csv` (Table 1).
* `report/figures/*.png`: topology, threshold vs count, alert timeline, TPR/FPR
  by size, latency by rate, network impact, mode comparison.
* `report/evidence/*.log`: the kept run logs; `./run.sh parse` and
  `./run.sh metrics` work on them without a simulator.

## G. Likely questions

* *Why Contiki-NG and not 2.7?* Maintained, but ContikiMAC is gone and RPL is
  larger: the instrumented node no longer fits the Sky (IDS itself is ~2 KB).
* *Why is FPR higher than the paper's?* Integer quantisation over sparse
  Trickle traffic in small neighbourhoods; decision-level FPR ~1% is in the
  paper's band; node-level "flagged once in a run" is the pessimistic view.
* *Why does neighbour TPR collapse at 20-30% attackers?* Attackers inflate the
  mean and sigma and mask each other (same bound, k outliers).
