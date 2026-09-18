# CPS and IoT Security Final Project Plan

## Project title

**A Lightweight Distributed Anomaly-Based IDS for RPL Networks in Contiki-NG/Cooja**

## Status

- 2026-09-03: plan reviewed against the paper and the host environment. `rpl-ids/` scaffold created with Docker toolchain, Makefile, `project-conf.h`, runner script, and directory layout. Contiki-NG pinned to `release/v5.2` (commit `4ccd1a3b`, Cooja `fabff3ee`; latest release; has `sky`, `cooja`, `rpl-udp`, exported DIO/DIS output API). Docker image builds and runs; toolchain is Java 25, msp430-gcc 4.7.4, arm-gcc 10.3 on Ubuntu 22.04. Corrections applied below: CSMA instead of ContikiMAC, `rpl-lite`, instrumentation patch, headless Cooja, scenario generator, explicit metric sample unit, 75 s attack start.

- 2026-09-03: **Phase 0 checkpoint passed.** Stock `examples/rpl-udp` built for the `cooja` target and ran headless for 5 simulated minutes (1 root + 9 clients, 30 m grid, UDGM 50/100 m, seed 1). All 9 clients were heard by the root, last join at 46 s; wall time under 1 s. Scenario: `rpl-ids/simulations/smoke-rpl-udp.csc`, runner: `rpl-ids/scripts/run_scenario.sh`, evidence: `rpl-ids/report/evidence/`. Cooja lessons recorded in `rpl-ids/README.md`.
- 2026-09-04: **Section 2 (Phases 1-2) checkpoint passed.** Root and node firmware, `ids.c` counters, the `rpl-icmp6.c` hook patch (baked into the image), scenario generator and log parser are in place. 10-node baseline, 60 s windows: all nodes join by 61 s, PDR 1.0, one parent change per node, per-neighbour DIO count per window falls from mean 3.9 (max 8) in the Trickle burst to 0.3 by the fourth window; DIS max 2 in the first window and 0 afterwards, consistent with the paper's normal maximum of 3. Evidence in `rpl-ids/report/evidence/`.
- 2026-09-04: **Section 3 (Phases 3 and 6) checkpoint passed.** Detector and blocking implemented in `ids.c` with integer arithmetic; `scripts/ids_model.py` is a bit-exact reference and 17 host tests pass, including a replay test that matches every firmware DET/ALERT record in the evidence logs. Baselines with the paper's 300 s window over 30 min: 2.8 % (10 nodes) and 0.9 % (30 nodes) of monitor-neighbour decisions raise a DIO alert, no permanent blocks, PDR 1.0. **Analytical finding:** because Algorithm 1 uses the population standard deviation including the attacker, Samuelson's inequality caps any neighbour's z-score at sqrt(n-1); a lone attacker is undetectable by the DIO rule whenever k(n) exceeds that, i.e. at 5-7 and 28-32 neighbours, regardless of rate. To be verified experimentally in section 4 and reported as a limitation of the paper's threshold.
- 2026-09-04: **Section 4 (Phases 4-5) checkpoint passed.** Neighbour and DIS attackers implemented (multicast DIO/DIS via rpl-lite output API, configurable rate/start/duration, ground-truth `.truth.csv` per scenario). `calculate_metrics.py` reports node-level (paper-comparable) and decision-level metrics. Both attacks detected at node TPR 1.0. **DIS reproduces the paper exactly: TPR 100%, FPR 0%, F1 1.0.** Neighbour attack decision-level FPR ~1% (paper: 0.2-9.6%). Detection latency equals one window (525 s at 300 s windows), motivating the sliding-window contribution. **Blind-spot prediction from section 3 confirmed experimentally:** of three monitors hearing a flooding attacker, only the one with 8 neighbours flagged it (7/7 windows); the two with 5 and 6 neighbours never did (0/7), matching sqrt(n-1) vs k(n). 28 host tests pass. Evidence in `rpl-ids/report/evidence/section4-*`.
- 2026-09-04: **Section 5 (analysis pipeline) checkpoint passed.** `run_matrix.py` (preset-driven, resumable), `aggregate.py` (Table III-style mean/std/min/max) and `plot_results.py` (per-run and matrix figures) complete and wired into `run.sh`. Dev matrix (10 nodes, 3 seeds, 9 runs) runs from one command in ~16 s: DIS TPR 100% FPR 0%, neighbour TPR 100%. Ten figures generated incl. threshold-vs-count (attacker above threshold at the detecting monitor) and TPR/FPR by size. Node-level FPR high at dev scale (small networks); decision-level ~1%. Final numbers come from the section 6 paper matrix.
- 2026-09-04: **Section 6 complete; all phases done.** Sliding-window detector added (shared detect_over, ring buffer). Full 42-run matrix (20/30/40 nodes x 1/20%/30% attackers x paper+sliding x 3 seeds) ran in 280 s. **DIS attack reproduces the paper at every size: 100% TPR, 0% FPR.** Neighbour attack: 100% TPR for a lone attacker, collapsing to 27.8% (20% attackers) and 2.8% (30%) as attackers mask each other (H3). **Sliding window (H4): mean latency 225 s -> ~25 s, mean node FPR 2.5% -> 13.5%, and mean TPR 72% -> 76% (it partly resists masking).** Two analytical findings: size-dependent blind spots (Samuelson bound, confirmed experimentally) and collusion masking. IDS module overhead ~2 KB ROM / 0.6 KB RAM on Sky; stock RPL+UDP fills 91% of Sky ROM under v5.2 so runs on cooja. Report in `rpl-ids/report/report.md`, figures in `report/figures/`, 28 host tests pass. **Definition of done: all 11 items satisfied.**
- 2026-09-05: **Gap closure.** Network-impact metrics (PDR, delay, DIO/DIS overhead, parent changes, blocks), topology figure, DIS-threshold sweep (2/3/5: insensitive, 5 adds latency), attack-rate sweep (1/5/10/30 s + random), repeatability (byte-identical), main matrix extended to 5 seeds, demo script `report/demo.md`. **Finding 3:** sliding mode misses DIS attackers slower than one per 20 s because the paper's fixed threshold of 3 assumes a 300 s window; and with the paper's blocking parameters it issues ~100 permanent blocks per run even with no attacker. PDR/delay unaffected by attacks under lossless UDGM; DIS attack multiplies DIO receptions x6-x13 and sliding halves that. Report, README and figures updated. Only Markdown report (no LaTeX/PDF toolchain in the image).

## 1. Project goal

Implement an IoT network in Contiki-NG, generate RPL routing attacks in the Cooja simulator, and detect them with a lightweight anomaly-based intrusion detection system (IDS).

The project is based on the reference paper:

> *An Anomaly-Based IDS for Detecting Attacks in RPL-Based Internet of Things*

The implementation will reproduce the paper's main experiment for two attacks:

1. RPL neighbor attack.
2. RPL DIS attack.

The project will then add a small original comparison: evaluate the paper's fixed observation-window detector against a sliding-window variant and compare detection speed, true-positive rate, and false-positive rate.

The existing `drone-spoofing/` directory is a separate ArduPilot GPS-spoofing project. It should remain unchanged. The new experiment will be implemented in a separate `rpl-ids/` directory.

## 2. Research question and hypotheses

### Research question

Can a distributed, low-resource anomaly-based IDS detect RPL neighbor and DIS attacks using only local observations of neighboring nodes?

### Hypotheses

- H1: A malicious node transmitting excessive DIO messages can be detected because its DIO count deviates from the normal neighborhood profile.
- H2: A malicious node transmitting excessive DIS messages can be detected when its DIS count exceeds the normal per-window threshold.
- H3: Increasing the attacker percentage improves the amount of attack traffic but can also increase false positives and routing instability.
- H4: A sliding observation window reduces detection latency but may produce more false positives than the paper's longer fixed window.
- H5: The IDS introduces measurable memory, code-size, and communication overhead, but does not require centralized monitoring.

## 3. Reference-paper baseline

Use the following parameters first so that the results are comparable with the paper. Document every difference caused by using Contiki-NG instead of Contiki 2.7.

| Parameter | Baseline value |
|---|---|
| Operating system | Contiki-NG |
| Simulator | Cooja |
| Mote platform | `cooja` native mote for development; `sky` (Tmote Sky, 48 KB ROM / 10 KB RAM) for final ROM/RAM measurement |
| Routing protocol | Contiki-NG `rpl-lite` (adaptation: paper used ContikiRPL on Contiki 2.7) |
| Link layer | IEEE 802.15.4 |
| MAC protocol | CSMA, no radio duty cycling (adaptation: ContikiMAC was removed from Contiki-NG) |
| Radio medium | UDGM |
| Transmission range | 50 m |
| Interference range | 100 m |
| Deployment area | 100 m x 100 m, grid with 20 m, 30 m, or 40 m spacing as in the paper |
| Number of nodes | 20, 30, and 40 |
| Number of sinks | 1 |
| Attack percentage | 1 attacker, 20%, and 30% |
| Traffic | Constant-bit-rate UDP |
| Simulation duration | 30 minutes for final runs |
| Attack start | 75 s after simulation start (paper); configurable, later start used only for latency measurements |
| IDS detection window | Start with 5 minutes for paper reproduction |
| DIS attacker rate | random 5 s to 60 s (paper), plus fixed low, medium, and high rates |
| DIS blocking threshold | 2 detections before permanent blocking, if supported by the implementation |
| Temporary block duration | 1 minute |

### Known Contiki-NG differences (record in the report)

- ContikiMAC does not exist in Contiki-NG; only CSMA and TSCH remain. All runs use CSMA without duty cycling, so energy and DIO timing differ from the paper.
- Contiki-NG ships two RPL implementations. `rpl-lite` (default, single parent, smaller) is used; `rpl-classic` is the descendant of the ContikiRPL used by the paper and is kept as a fallback if `rpl-lite` behaviour prevents reproduction.
- Neither implementation exposes a per-neighbor DIO/DIS receive callback, and Contiki-NG allows exactly one ICMPv6 handler per type/code. A two-line patch in `rpl-icmp6.c` adds a weak `ids_rpl_input()` hook that also serves as the blocking point.
- Cooja is built with Gradle and can run headless with a control script; this is required for the multi-seed matrix.
- The default neighbor table (16 entries) is too small for 40 nodes in a 100 m x 100 m area with 50 m range and is raised in `project-conf.h`.

During development, use 10 nodes and 5 minutes to keep iteration fast. Only use the full matrix after the detector works in the small scenario.

## 4. Threat model

### Network assumptions

- The network is an IPv6 Low-Power and Lossy Network using RPL.
- Nodes are static and have constrained memory and energy.
- One root acts as the sink and forms the DODAG.
- Normal nodes forward data toward the root.
- Attackers are internal RPL nodes that can send valid-looking RPL control messages.
- The IDS is distributed: every normal node monitors its neighbors independently.
- The attacker is not assumed to break link-layer encryption. The attacks exploit protocol behavior after the node has joined the network.

### Out of scope

Do not implement wormhole, sinkhole, selective forwarding, or GPS spoofing in the first version. They would expand the project beyond the paper's main contribution and make it harder to isolate the detector's behavior.

## 5. System architecture

```text
+------------------ Cooja simulation ------------------+
|                                                      |
|  RPL root          normal nodes          attackers    |
|      |                  |                  |          |
|      +---------- 802.15.4 / 6LoWPAN ---------------+
|                         |
|                    ContikiRPL
|                         |
|        local IDS running on every normal node
|        - neighbor table
|        - DIO counters
|        - DIS counters
|        - threshold calculation
|        - alert and block state
|                         |
|                    serial CSV logs
+------------------------------------------------------+
```

The detector should observe protocol behavior locally rather than receiving reports from a central IDS server. The root can collect result logs for analysis, but it must not make detection decisions on behalf of other nodes.

## 6. Repository structure to create

Create this structure at the workspace root:

```text
rpl-ids/
├── Dockerfile              # pinned Contiki-NG tag + prebuilt Cooja + toolchains
├── docker-compose.yml
├── run.sh                  # build / shell / make / sim / test wrapper
├── Makefile
├── README.md               # includes running list of adaptations from the paper
├── project-conf.h          # every tunable (window, thresholds, table sizes)
├── patches/
│   └── 0001-rpl-icmp6-ids-hook.patch
├── firmware/
│   ├── rpl-ids-node.c
│   ├── rpl-ids-root.c
│   ├── neighbor-attacker.c
│   ├── dis-attacker.c
│   └── ids.c
├── include/
│   └── ids.h
├── simulations/
│   ├── templates/          # .csc template with placeholders
│   ├── scenarios.md        # naming scheme and catalogue
│   └── *.csc               # generated, one per (nodes, attack, attackers, seed, mode)
├── scripts/
│   ├── gen_scenario.py     # deterministic grid topology + attacker placement by seed
│   ├── run_scenario.sh     # headless Cooja runner
│   ├── parse_logs.py
│   ├── calculate_metrics.py
│   └── plot_results.py
├── tests/                  # pytest: threshold maths, metric maths, parser edge cases
├── logs/
├── results/
└── report/
    ├── report.md
    └── figures/
```

Keep generated logs and plots out of the firmware source. Every result file must identify the node count, attacker type, attacker count, random seed, radio range, window size, and detector version.

## 7. Implementation phases

### Phase 0: Environment and version record

1. Build the Docker image from `rpl-ids/Dockerfile`, which clones a pinned Contiki-NG tag into the official `contiker/contiki-ng` toolchain image and prebuilds Cooja with Gradle. Nothing is installed on the host apart from Docker.
2. Verify inside the container that Java, Gradle, msp430-gcc, and the host C compiler are available.
3. Record the exact Contiki-NG commit, Cooja commit, Java version, and compiler versions. The image writes these to `/opt/VERSION.txt`.
4. Compile the stock `examples/rpl-udp` for the `cooja` target and run it headless with a control script before writing IDS code.
5. Save a screenshot showing the Cooja topology and a log proving that nodes joined the same DODAG.

**Checkpoint:** a stock RPL network runs in Cooja and sends IPv6 traffic to the root.

### Phase 1: Build the normal IoT network

1. Create the root process.
2. Create the normal sensor-node process.
3. Configure a single RPL instance and one DODAG root.
4. Add a UDP client on normal nodes and a UDP server on the root.
5. Use a constant sending interval, initially 30 seconds or 60 seconds.
6. Print node ID, parent, rank, and packet counters periodically.
7. Configure the Cooja radio medium and node positions.
8. Verify that all nodes can reach the root without attackers.

**Checkpoint:** baseline runs produce stable DODAG formation, UDP packets reach the root, and the topology can be exported or reconstructed from logs.

### Phase 2: Add observability hooks

Add counters without detection logic first.

For each node and neighbor, record:

- Simulation time.
- Local node ID.
- Neighbor ID.
- DIO count.
- DIS count.
- Current RPL rank.
- Preferred parent.
- Number of parent changes.
- UDP packets sent, received, and lost.
- Radio-on or energy counters when available.

Use `RPL_CALLBACK_PARENT_SWITCH` and `RPL_CALLBACK_NEW_DIO_INTERVAL` from `rpl-lite` for parent and Trickle events. For DIO and DIS reception there is no exposed callback, so apply `patches/0001-rpl-icmp6-ids-hook.patch`, which calls `ids_rpl_input(code, from)` at the top of `dio_input()` and `dis_input()`. The hook returns whether to accept the message, which is also the blocking mechanism in Phase 6. Document the patch in `README.md`.

Do not use packet sniffing as the primary detector. Cooja's radio logging may be used for validation, but the IDS should operate from information available to a node.

**Checkpoint:** a normal run produces enough logs to calculate per-neighbor DIO and DIS distributions.

### Phase 3: Implement the normal profile

Implement the detector as a reusable module in `ids.c` and `ids.h`.

For every observation window:

1. Enumerate known neighbors.
2. Count DIO messages received from each neighbor.
3. Count DIS messages received from each neighbor.
4. Calculate the average DIO count:

   $$
   \mu = \frac{\sum_i c_i}{N}
   $$

   where $c_i$ is the DIO count for neighbor $i$ and $N$ is the number of neighbors.

5. Calculate the standard deviation of the neighbor counts.
6. Calculate the paper's coefficient using the current neighbor count $x$:

   $$
   k=-5\times10^{-5}x^4+0.0037x^3-0.0899x^2+0.9281x-0.7903
   $$

7. Calculate the neighbor-attack threshold:

   $$
   T_{neighbor}=\mu+k\sigma
   $$

8. Flag a neighbor if its DIO count is greater than the threshold.
9. Flag a neighbor for a DIS attack if its DIS count exceeds the configured DIS threshold.
10. Reset or rotate counters at the end of the window.

Use integer arithmetic only on the mote. The neighbor count $x$ is a small integer, so precompute $k$ scaled by 1000 for $x = 0 \ldots 40$ on the host and store it as a `const uint16_t` table. Use an integer square root for $\sigma$. Compare scaled counts with 32-bit arithmetic. The host-side Python analysis may use floating-point arithmetic and must include a test proving the table matches the polynomial.

Known limits of the paper's detector, to be measured rather than hidden: with a single neighbor $\sigma = 0$ and nothing is ever flagged; when most neighbors are attackers the mean rises and attackers hide inside it. This is the expected mechanism behind H3.

For the first implementation, preserve the paper's algorithm exactly. Add an optional configuration switch for a sliding-window detector only after the reproduction detector is working.

**Checkpoint:** a normal run produces no persistent alerts, or any alerts are explainable by a documented warm-up or topology change.

### Phase 4: Implement the neighbor attack

Create `neighbor-attacker.c`.

The attacker should:

1. Join the RPL network as a normal node.
2. Continue sending enough normal traffic to appear operational.
3. Send additional DIO messages at a configurable rate.
4. Support at least three rates: normal, moderate, and aggressive.
5. Log each attack transmission with timestamp and attacker ID.

Keep the attack controlled and simulation-only. The goal is to test detection, not to create an uncontrolled broadcast storm.

Recommended parameters:

- Moderate: one additional DIO every 10 seconds.
- Aggressive: one additional DIO every 1–5 seconds.
- Start delay: 5 minutes, after normal RPL convergence.
- Attack duration: 10 minutes, followed by a quiet period.

If directly forcing a standard RPL DIO is difficult in the selected Contiki-NG version, implement the attacker around the supported RPL control-message API and clearly document the API adaptation.

**Checkpoint:** Cooja confirms that the attacker sends more DIO traffic than normal nodes and the IDS eventually identifies the attacker.

### Phase 5: Implement the DIS attack

Create `dis-attacker.c`.

The attacker should send valid RPL DIS messages using the Contiki-NG ICMPv6/RPL mechanism. Make the rate configurable:

- Low rate: every 30–60 seconds.
- Medium rate: every 5–10 seconds.
- High rate: every 1–5 seconds.

Start the attack only after RPL has converged. Log the attack start, every DIS transmission, and the expected attacker ID.

The detector should count DIS messages per neighbor within the current observation window and compare the count with the configured DIS threshold. The paper uses a maximum normal value of 3 as the detection threshold; begin with that value, then test sensitivity to thresholds 2, 3, and 5.

**Checkpoint:** the DIS attacker creates a measurable increase in DIS messages and is detected without incorrectly identifying normal nodes in the baseline run.

### Phase 6: Add response and blocking

When a node is flagged:

1. Write an IDS alert record immediately.
2. Increment the suspected neighbor's block counter.
3. Temporarily ignore or deprioritize the neighbor for the configured blocking period.
4. Allow the node to be reconsidered after the temporary period.
5. Permanently block only after the configured repeated-alert threshold is reached.
6. Record the response action and its duration.

Do not remove a neighbor from RPL's tables. Blocking is implemented at the `ids_rpl_input()` hook: DIO and DIS messages from a blocked neighbor are dropped before RPL processes them, so the neighbor cannot reset Trickle or become a parent through new DIOs. Document this exact semantics and note that an already-selected parent is only demoted when its DIOs stop arriving.

**Checkpoint:** blocking changes the routing behavior as intended and does not crash, deadlock, or corrupt the RPL neighbor table.

### Phase 7: Add the original comparison detector

Implement a second detector mode after the paper reproduction is complete.

Suggested comparison:

- Paper mode: fixed 5-minute observation windows.
- Sliding mode: 60-second window updated every 10 seconds.

Use the same counters and attack scenarios for both modes. Do not change attack rates, node positions, or random seeds between detector comparisons.

Compare:

- Time until first correct alert.
- TPR.
- FPR.
- FNR.
- Number of alerts per normal node.
- Packet delivery ratio.
- Routing changes.
- Memory and communication overhead.

The contribution is not to claim that the sliding window is universally better. Explain the trade-off between faster detection and increased sensitivity to normal RPL control traffic.

## 8. Cooja scenario design

Scenarios are generated by `scripts/gen_scenario.py` from a template, never hand-edited. Nodes are placed on a grid with 20 m, 30 m, or 40 m spacing as in the paper's Fig. 6, the root at the top, and attacker positions chosen deterministically from the seed. The generator writes the attacker ground-truth file alongside the `.csc`. Each `.csc` embeds a Cooja control script with the simulation timeout so it runs headless.

### Baseline scenario

- One root.
- Normal nodes only.
- No attacker process.
- Constant UDP traffic.
- At least 5 minutes of warm-up before measuring false positives.

### Neighbor-attack scenario

- Same topology and seed as baseline.
- One or more neighbor attackers.
- Attack begins after RPL convergence.
- Run both moderate and aggressive attack rates.

### DIS-attack scenario

- Same topology and seed as baseline.
- One or more DIS attackers.
- Run low, medium, and high DIS rates.

### Network sizes

Run development tests with 10 nodes. Run final experiments with 20, 30, and 40 nodes. For every size, test:

- One attacker.
- 20% attackers where meaningful.
- 30% attackers where meaningful.

A minimum final matrix is:

| Scenario | Nodes | Attackers | Detector modes |
|---|---:|---:|---|
| Baseline | 20 | 0 | Paper, sliding |
| Neighbor | 20 | 1 | Paper, sliding |
| DIS | 20 | 1 | Paper, sliding |
| Neighbor | 30 | 20% | Paper, sliding |
| DIS | 30 | 20% | Paper, sliding |
| Stress | 40 | 30% | Paper, sliding |

Run each final configuration with at least 5 independent seeds. If runtime is limited, use 3 seeds and explicitly state this limitation.

## 9. Logging format

Use machine-readable CSV or structured serial output. Every record should include:

```text
timestamp,scenario,seed,local_id,neighbor_id,event,
 dio_count,dis_count,neighbor_count,mean,stddev,k,threshold,
 rank,parent,alert,action
```

Attackers should produce separate ground-truth logs:

```text
timestamp,attacker_id,attack_type,event,rate
```

The analysis scripts must join IDS alerts with the ground-truth attacker list. Do not infer ground truth from the IDS output itself.

## 10. Metrics and analysis

### Detection metrics

The sample unit is one decision by one monitor about one neighbor at the end of one observation window. This is the only definition consistent with the paper's fractional FPR values and it must be stated in the report. For each sample, classify:

- **TP:** attacker correctly identified.
- **FP:** normal node incorrectly identified.
- **FN:** attacker not identified during the attack interval.
- **TN:** normal node remains unflagged.

Calculate:

$$
TPR=\frac{TP}{TP+FN}
$$

$$
FPR=\frac{FP}{FP+TN}
$$

Also calculate precision, F1 score, and detection latency where possible.

### Network metrics

Calculate:

- Packet delivery ratio.
- End-to-end delay.
- UDP throughput.
- DIO and DIS overhead.
- Number of parent changes.
- Number of rank changes.
- Number of blocked neighbors.
- Time spent in temporary blocking.
- Radio-on time or energy consumption if supported.

### Required plots

Produce at least:

1. Cooja topology and DODAG structure.
2. DIO count per neighbor over time.
3. DIS count per neighbor over time.
4. Threshold and observed count on the same graph.
5. Alerts over the simulation timeline.
6. TPR and FPR by network size.
7. Detection latency by attack rate.
8. Packet delivery ratio for baseline and attacks.
9. Paper detector versus sliding detector.

## 11. Validation strategy

Use these checks in order:

1. **Compilation:** all firmware targets compile with no warnings caused by the project code.
2. **RPL formation:** every normal node eventually receives a valid rank and parent.
3. **Traffic:** baseline UDP packets reach the root.
4. **Instrumentation:** DIO and DIS counters increase when the corresponding control messages are observed.
5. **No-attack behavior:** baseline does not generate repeated alerts.
6. **Single-attack behavior:** one known attacker is detected.
7. **Multiple-attacker behavior:** the detector can identify more than one attacker.
8. **Response behavior:** blocking is logged and expires as configured.
9. **Repeatability:** repeated runs with the same seed produce similar results.
10. **Resource check:** report ROM, RAM, and runtime overhead of the IDS.

Add host-side tests for the threshold and metric calculations. At minimum, test:

- Zero neighbors.
- One neighbor.
- Equal DIO counts.
- A single high-count outlier.
- DIS count exactly at the threshold.
- DIS count one above the threshold.
- Empty or incomplete log records.

## 12. Report outline

### 1. Introduction

Explain IoT LLNs, why RPL control traffic matters, and the project objective.

### 2. Background

Describe 6LoWPAN, IEEE 802.15.4, RPL, DIO, DIS, DODAGs, ranks, and anomaly-based IDSs.

### 3. Threat model

Define the attacker capabilities, neighbor attack, DIS attack, and assumptions.

### 4. Reference paper

Explain the paper's distributed architecture, normal profile, dynamic threshold, DIS threshold, and temporary blocking. Clearly identify what is reproduced and what is changed.

### 5. System design

Describe node roles, data flow, IDS state, counters, windows, thresholds, alerts, and blocking.

### 6. Implementation

Describe Contiki-NG processes, Cooja configurations, logging, and any version-specific adaptations.

### 7. Experimental methodology

Give topology, radio model, node counts, attacker percentages, seeds, traffic, simulation duration, and detector modes.

### 8. Results

Present detection and network-performance metrics with confidence intervals or variation across seeds where possible.

### 9. Discussion

Discuss false positives, detection latency, overhead, topology dependence, resource limits, and differences from the paper.

### 10. Limitations and future work

Mention that the evaluation uses simulation, static nodes, a limited attack set, and a known ground-truth configuration. Future work may consider sinkhole, selective forwarding, mobility, or real hardware.

### 11. Conclusion

Answer the research question directly using the measured results.

## 13. Suggested execution schedule

### Session 1: Environment and baseline

- Build the Docker image and record versions.
- Run a stock RPL example headless.
- Create the 10-node baseline.
- Commit or archive the working baseline configuration.

### Session 2: Instrumentation

- Add DIO, DIS, rank, parent, and UDP counters.
- Export logs.
- Write the first parser and plots.

### Session 3: Detector reproduction

- Implement the paper threshold.
- Test it against saved normal logs.
- Add alert logging.

### Session 4: Attacks

- Implement the neighbor attacker.
- Implement the DIS attacker.
- Validate attack ground truth with Cooja logs.

### Session 5: Response and comparison

- Add temporary blocking.
- Add the sliding-window detector.
- Run controlled comparisons.

### Session 6: Final experiments

- Run the full experiment matrix with multiple seeds.
- Generate all tables and figures.
- Measure resource overhead.

### Session 7: Report and presentation

- Write the report from measured data.
- Prepare a short live demonstration.
- Prepare fallback screenshots and logs in case Cooja is unavailable during the exam.

## 14. Definition of done

The project is complete when all of the following are true:

- A Cooja simulation contains one RPL root, normal nodes, and configurable attackers.
- Baseline UDP traffic works before attacks are enabled.
- The IDS runs locally on normal nodes.
- Neighbor and DIS attacks are implemented and separately controllable.
- DIO and DIS behavior is logged with attacker ground truth.
- The paper's threshold detector identifies attacks in controlled scenarios.
- False positives are measured using attack-free runs.
- TPR, FPR, detection latency, and network impact are reported.
- The fixed-window and sliding-window detectors are compared.
- Results are reproducible from documented commands, versions, seeds, and scenario files.
- The report distinguishes paper reproduction, implementation adaptations, and original contribution.

## 15. Main technical risks and mitigations

| Risk | Mitigation |
|---|---|
| Contiki-NG APIs differ from Contiki 2.7 | Record the version, isolate compatibility code, and document every adaptation. |
| Direct RPL control-message injection is difficult | Start from supported RPL/ICMPv6 APIs and validate traffic in Cooja before adding IDS logic. |
| Five-minute windows make development slow | Use 10-node, 1-minute development runs; reserve 30-minute runs for final evaluation. |
| Normal Trickle behavior causes false positives | Ignore the RPL convergence period and evaluate after warm-up. |
| Blocking breaks RPL internals | Initially mark nodes suspicious and alter parent selection only through supported APIs. |
| Results vary between seeds | Run multiple seeds and report mean, minimum, maximum, and standard deviation. |
| Paper does not provide every implementation detail | Treat undocumented choices as experimental parameters and justify them explicitly. |
| Cooja or Java is unavailable during presentation | Keep final screenshots, logs, plots, and a short recorded demonstration. |

## 16. First concrete actions

1. Build the Docker image (`./run.sh build`) and record versions (`./run.sh version`).
2. Run the stock `rpl-udp` example headless on the `cooja` target.
3. Compile a minimal root and node firmware from `rpl-ids/`.
4. Reproduce a 10-node baseline topology.
5. Add UDP traffic and verify delivery.
6. Add logging before implementing any attack or detector.
7. Implement the detector only after the normal DIO/DIS distributions are visible.
