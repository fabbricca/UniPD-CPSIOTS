# A Lightweight Distributed Anomaly-Based IDS for RPL Networks (Contiki-NG / Cooja)

Reproduction of *An Anomaly-Based IDS for Detecting Attacks in RPL-Based
Internet of Things* (Farzaneh, Montazeri, Jamali, ICWR 2019) on Contiki-NG,
plus an original comparison between the paper's fixed 5-minute detection
window and a sliding-window variant.

The full plan lives in [../PROJECT_PLAN.md](../PROJECT_PLAN.md).

## Quick start

```bash
./run.sh build                 # clone pinned Contiki-NG, apply patches, build Cooja (slow, once)
./run.sh version               # print recorded toolchain versions
./run.sh gen --nodes 10 --spacing 30 --seed 1 --duration 5 --window 60 \
             --out simulations/dev-10-baseline-s1.csc      # generate a scenario
./run.sh sim simulations/dev-10-baseline-s1.csc [seed]     # headless run -> logs/
./run.sh parse logs/dev-10-baseline-s1.log --summary       # CSV tables -> results/
./run.sh make TARGET=cooja     # build firmware by hand (Cooja builds it itself otherwise)
./run.sh test                  # host-side unit tests for threshold + metrics
```

The container starts as root and its entrypoint remaps the `user` account to
`LOCAL_UID`/`LOCAL_GID` (defaults: your host `id -u`/`id -g` via
`docker-compose.yml`) before dropping privileges, so files written into the
bind-mounted `logs/` and `results/` directories are owned by you.

## Layout

```
Dockerfile, docker-compose.yml, run.sh   reproducible toolchain
firmware/Makefile, project-conf.h        firmware build + every tunable (next to the
                                         sources because Cooja runs make there)
firmware/                                rpl-ids-root.c, rpl-ids-node.c, ids.c, attackers
include/ids.h                            IDS API and log record formats
patches/                                 0001: 2-line DIS/DIO hook in rpl-lite/rpl-icmp6.c
simulations/                             generated .csc scenarios (never hand-edited)
scripts/                                 gen_scenario.py, run_scenario.sh, parse_logs.py, ...
tests/                                   pytest for threshold and metric maths
logs/ results/                           generated data (git-ignored)
report/evidence/                         kept logs proving each checkpoint
```

## Log records

Cooja's control script writes every mote line as `<time_us>\t<mote_id>\t<msg>`.
Firmware records are tab separated with a leading tag (see `include/ids.h`):

| Tag | Emitted by | Fields |
|---|---|---|
| `EV` | ids.c, per received DIO/DIS | kind, neighbour id |
| `NBR` | ids.c, window end | window, neighbour id, dio, dis |
| `WIN` | ids.c, window end | window, neighbours heard, RPL neighbours, dio sum, dis sum |
| `PAR` | ids.c, parent switch | old parent, new parent, total changes |
| `TX` | node | sequence number |
| `STAT` | node, every 30 s | rank, parent, parent changes, tx, RPL nbrs, IDS nbrs |
| `RX` | root | sender id, sequence number |
| `RSTAT` | root, every 30 s | rx total, RPL nbrs, routes |

Node ids are the last 16 bits of the sender's IPv6 address, which equal the
Cooja mote id, so ground-truth joins on the host are exact.

## Build variants

`IDS_MODE`, `IDS_WINDOW_SEC` and `APP_SEND_INTERVAL_SEC` are passed to `make`
in the scenario's `<commands>` line. Because `make` ignores flag changes and
Cooja reuses `firmware/build/`, the Makefile keeps a variant stamp and
recompiles the three project objects whenever the variant string changes.

## Headless Cooja notes (learned in Phase 0)

* Invocation: `java -jar cooja.jar --no-gui --contiki=$CONTIKI_NG --logdir=DIR [--random-seed=N] file.csc`.
  `--no-gui` is a bare flag. The control script's `log.log()` output goes to
  `DIR/COOJA.testlog`; `log.testOK()` gives exit code 0, `log.testFailed()` 1.
* The control script body runs inside a function, but the `TIMEOUT(ms, action)`
  action is evaluated in global scope. Declare shared state with bare
  assignment (`senders = {}`), never `var`, or the action sees a ReferenceError.
* `TIMEOUT` takes milliseconds; `time` inside the script is microseconds.
* 10 `cooja` motes simulate 5 minutes in under a second of wall time, so the
  development loop is fast; `sky` motes are much slower.
* Phase 0 evidence: `report/evidence/phase0-smoke-rpl-udp-seed1.log` (stock
  `rpl-udp`, 1 root + 9 clients, 30 m grid, all clients heard by the root within 46 s).

## Detector (section 3)

`firmware/ids.c` implements the paper's Algorithms 1 and 2 at every window end,
in integer arithmetic scaled by 1000. `scripts/ids_model.py` is a bit-exact
Python reference; `tests/test_firmware_consistency.py` replays the kept
evidence logs and asserts that every firmware `DET` and `ALERT` record equals
the model's output. `include/ids-k-table.h` is generated from the paper's
polynomial by `scripts/gen_k_table.py` (k x 1000, clamped at 0).

Blocking: a flagged neighbour is blocked for `IDS_TEMP_BLOCK_SEC` (60 s) while
its `block_count` is below `IDS_BLOCK_THRESHOLD` (2), then permanently. Its
DIS/DIO are dropped in the `rpl-icmp6.c` hook, so they can neither reset
Trickle nor make it a parent. Counting continues while blocked, which is what
lets repeated detections escalate as in the paper. Expiry is evaluated lazily
on the next message from that neighbour, so the `BLOCK expire` line is stamped
at that message, not at the exact 60 s mark.

### Analytical finding: single-attacker blind spots

Algorithm 1 uses the population standard deviation over the neighbour list,
and the attacker is part of that list. By Samuelson's inequality the largest
z-score any member of a sample of n can have is sqrt(n-1). A lone attacker
is therefore detectable only where sqrt(n-1) > k(n):

| neighbours n | sqrt(n-1) | k(n) | lone attacker detectable |
|---|---|---|---|
| 2-4 | 1.00-1.73 | 0.74-1.71 | yes (barely at 4) |
| 5-7 | 2.00-2.45 | 2.03-2.45 | **no** |
| 8-27 | 2.65-5.10 | 2.57-4.99 | yes |
| 28-32 | 5.20-5.57 | 5.21-5.66 | **no** |
| 33-40 | 5.66-6.24 | 1.29-5.61 | yes |

This holds for any attack rate. It is a property of the published threshold,
not of this implementation, and is encoded in `tests/test_threshold.py`.

### Baseline false positives (seed 1, paper 300 s windows, 30 min)

| Topology | decisions | DIO alerts | rate | permanent blocks |
|---|---|---|---|---|
| 10 nodes, 30 m | 215 | 6 | 2.8 % | 0 |
| 30 nodes, 20 m | 1860 | 17 | 0.9 % | 0 |

Every alert is a normal neighbour with 2-3 DIOs in a window where the others
sent 0-1: with Trickle at its maximum interval a 5-minute window holds only
0-4 DIOs per neighbour, so integer quantisation alone produces z-scores above
k for small neighbourhoods. The paper reports 0.2-9.6 % FPR for the same
reason.

## Adaptations from the paper (running list)

| Paper (Contiki 2.7) | This project (Contiki-NG) | Why |
|---|---|---|
| ContikiMAC duty cycling | CSMA, no radio duty cycling | ContikiMAC was removed from Contiki-NG |
| ContikiRPL | `rpl-lite` | Contiki-NG default; fits Tmote Sky memory |
| Ant-built Cooja | Gradle-built Cooja, run headless | Contiki-NG tooling |
| Attack start 75 s | Parameter, default 75 s | Later start used only for latency runs |
| Hook into RPL input | 2-line patch in `rpl-icmp6.c` | Contiki-NG allows one ICMPv6 handler per type/code |
| Neighbour set for the profile | Every node heard sending DIO/DIS (own table) | Paper's "neighbor list" is unspecified; RPL's table size is also logged for comparison |
| Server echo replies | Disabled | Keeps upstream CBR traffic the only application flow, so PDR is unambiguous |
| Parent-change count | `RPL_CALLBACK_PARENT_SWITCH` | Free in rpl-lite; not available in Contiki 2.7 |

Every entry above must be reflected in the report's Implementation section.
