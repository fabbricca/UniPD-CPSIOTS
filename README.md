# A Lightweight Distributed Anomaly-Based IDS for RPL Networks (Contiki-NG / Cooja)

Reproduction of *An Anomaly-Based IDS for Detecting Attacks in RPL-Based
Internet of Things* (Farzaneh, Montazeri, Jamali, ICWR 2019) on Contiki-NG,
plus an original comparison between the paper's fixed 5-minute detection
window and a sliding-window variant.

The full plan lives in [../PROJECT_PLAN.md](../PROJECT_PLAN.md).

## Quick start

```bash
./run.sh build                 # clone pinned Contiki-NG, build Cooja (slow, once)
./run.sh version               # print recorded toolchain versions
./run.sh make TARGET=cooja     # build the four firmware images
./run.sh sim simulations/dev-10-baseline.csc   # headless run -> logs/
./run.sh test                  # host-side unit tests for threshold + metrics
```

The container starts as root and its entrypoint remaps the `user` account to
`LOCAL_UID`/`LOCAL_GID` (defaults: your host `id -u`/`id -g` via
`docker-compose.yml`) before dropping privileges, so files written into the
bind-mounted `logs/` and `results/` directories are owned by you.

## Layout

```
Dockerfile, docker-compose.yml, run.sh   reproducible toolchain
Makefile, project-conf.h                 firmware build + all tunables
firmware/                                root, node, two attackers, ids.c
include/ids.h                            detector API
patches/                                 minimal Contiki-NG instrumentation patch
simulations/                             .csc scenarios + generator template
scripts/                                 run, parse, metrics, plots
tests/                                   pytest for threshold and metric maths
logs/ results/ report/                   generated data (git-ignored) and report
```

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

## Adaptations from the paper (running list)

| Paper (Contiki 2.7) | This project (Contiki-NG) | Why |
|---|---|---|
| ContikiMAC duty cycling | CSMA, no radio duty cycling | ContikiMAC was removed from Contiki-NG |
| ContikiRPL | `rpl-lite` | Contiki-NG default; fits Tmote Sky memory |
| Ant-built Cooja | Gradle-built Cooja, run headless | Contiki-NG tooling |
| Attack start 75 s | Parameter, default 75 s | Later start used only for latency runs |
| Hook into RPL input | 2-line patch in `rpl-icmp6.c` | Contiki-NG allows one ICMPv6 handler per type/code |

Every entry above must be reflected in the report's Implementation section.
