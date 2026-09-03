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

## Adaptations from the paper (running list)

| Paper (Contiki 2.7) | This project (Contiki-NG) | Why |
|---|---|---|
| ContikiMAC duty cycling | CSMA, no radio duty cycling | ContikiMAC was removed from Contiki-NG |
| ContikiRPL | `rpl-lite` | Contiki-NG default; fits Tmote Sky memory |
| Ant-built Cooja | Gradle-built Cooja, run headless | Contiki-NG tooling |
| Attack start 75 s | Parameter, default 75 s | Later start used only for latency runs |
| Hook into RPL input | 2-line patch in `rpl-icmp6.c` | Contiki-NG allows one ICMPv6 handler per type/code |

Every entry above must be reflected in the report's Implementation section.
