# A Lightweight Distributed Anomaly-Based IDS for RPL Networks in Contiki-NG/Cooja

Reproduction of Farzaneh, Montazeri and Jamali, *An Anomaly-Based IDS for
Detecting Attacks in RPL-Based Internet of Things* (ICWR 2019), on Contiki-NG
v5.2 with the Cooja simulator, plus an original comparison between the paper's
fixed observation window and a sliding-window variant.

All results are reproducible from the commands in `README.md` and the pinned
toolchain in `Dockerfile` (Contiki-NG `release/v5.2`, commit `4ccd1a3b`).

---

## 1. Introduction

The Internet of Things connects large numbers of resource-constrained devices
over Low-Power and Lossy Networks (LLNs). Routing in LLNs uses RPL, the IPv6
Routing Protocol for Low-Power and Lossy Networks (RFC 6550), which builds a
Destination-Oriented Directed Acyclic Graph (DODAG) rooted at a border router.
RPL nodes exchange three control messages: DIO (DODAG Information Object) to
advertise and maintain the graph, DIS (DODAG Information Solicitation) to ask
for a DIO, and DAO (Destination Advertisement Object) to build downward routes.

Link-layer encryption protects an RPL network from outsiders but not from a
node that has already joined. Two internal attacks target the control plane
directly. In the **neighbour attack** a malicious node rebroadcasts DIOs so
that receivers add it to their parent set or reset their Trickle timers, and in
the **DIS attack** a node floods DIS messages, forcing neighbours to reset
Trickle and re-emit DIOs. Both waste energy and destabilise routing while using
only valid protocol messages.

This project implements the paper's distributed, threshold-based anomaly IDS,
reproduces its two attacks in Cooja, and evaluates detection quality, network
impact and resource cost. It then asks an original question: does a shorter,
sliding observation window detect faster, and at what cost in false positives?

## 2. Background

An LLN stack places IPv6 over 6LoWPAN over IEEE 802.15.4. RPL forms one or more
DODAGs per instance; each node holds a **rank** (its distance from the root
under an Objective Function) and a **preferred parent**. DIO emission is paced
by the **Trickle** algorithm, which sends often while the network is unstable
and exponentially less often once it converges, up to a maximum interval. This
is central to the detector: after convergence a node hears only a few DIOs per
neighbour per window, so an attacker that emits many stands out.

An **anomaly-based IDS** builds a profile of normal behaviour and flags
deviations. The paper's profile is the per-neighbour DIO count, modelled as
normally distributed across a node's neighbours, with a dynamic threshold
mean + k·sigma. It is **distributed and stand-alone**: every normal node
monitors its own neighbours and decides independently, with no central monitor.

## 3. Threat model

The network is a static IPv6 LLN using RPL with one root that also acts as UDP
sink. Attackers are internal nodes that have joined the DODAG and can send
valid DIO and DIS messages; they do not break link-layer security. The IDS runs
on every normal node and observes only the control traffic it can hear. Out of
scope, as in the paper: wormhole, sinkhole, selective forwarding, rank and
version-number attacks.

## 4. Reference paper

The paper's model has four phases per observation window: count DIOs per
neighbour; compute the neighbourhood mean and standard deviation and the
coefficient k from a polynomial in the neighbour count (its eq. 2); flag any
neighbour whose DIO count exceeds mean + k·sigma (Algorithm 1) or whose DIS
count exceeds a fixed threshold of 3 (Algorithm 2); and block flagged
neighbours temporarily, escalating to a permanent block after `block_threshold`
detections. Counters reset every 5 minutes; the temporary block lasts 1 minute;
`block_threshold` is 2. The paper reports DIS detection at 100% TPR and 0% FPR,
and neighbour detection at 94-100% TPR with 0.2-9.6% FPR, on Tmote Sky motes in
networks of 20, 30 and 40 nodes with 1, 20% and 30% attackers.

**Reproduced:** the profile, the dynamic threshold and its polynomial, the DIS
threshold, the four phases, temporary and permanent blocking, and the
20/30/40-node, 1/20%/30%-attacker matrix.

**Adapted for Contiki-NG v5.2** (full list in `README.md`): ContikiMAC no
longer exists, so CSMA without duty cycling is used; the routing layer is
`rpl-lite`; DIO/DIS reception is captured by a two-line patch to
`rpl-icmp6.c`; Cooja runs headless via a control script; and the experiments
run on the `cooja` mote because the instrumented node no longer fits the Sky
(section 8.3).

## 5. System design

Every normal node runs the detector in `ids.c`. It keeps its own neighbour
table, independent of RPL's, keyed by the 16-bit node id taken from the
sender's IPv6 address. On each received DIO or DIS the patched `rpl-icmp6.c`
calls `ids_rpl_input()`, which increments the per-neighbour counter and, if the
neighbour is blocked, drops the message before RPL processes it. At each window
end the node computes the profile and threshold in **integer arithmetic scaled
by 1000** (a precomputed k table and an integer square root; no floating point
on the mote), logs the decision, and blocks flagged neighbours. The root runs
no detector; the paper's IDS is fully distributed.

Blocking never touches RPL's neighbour table. A blocked neighbour's control
messages are dropped at the hook, so it cannot reset Trickle or be re-selected
as a parent through new DIOs, which keeps RPL's invariants intact.

## 6. Implementation

The firmware is four Contiki-NG processes: root, normal node, neighbour
attacker and DIS attacker. Attackers are normal nodes plus a timer that injects
multicast DIO or DIS through rpl-lite's own output functions, at a configurable
rate, start and duration; the paper's random 5-60 s DIS cadence is the default.
Every injection and every detector decision is logged as a tab-separated CSV
record over the serial line. Scenarios and their attacker ground-truth files
are generated deterministically from a seed by `gen_scenario.py`; the analysis
joins alerts to ground truth and never infers it from IDS output.

The detector arithmetic has a bit-exact Python twin (`ids_model.py`); a test
replays every kept run log and asserts that each firmware profile and alert
record matches the model, so the host analysis and the mote agree exactly.

## 7. Experimental methodology

Topology is the paper's grid: root at top centre, nodes on a 20 m grid in a
100 m x 100 m area, UDGM radio with 50 m transmit and 100 m interference range.
Traffic is constant-bit-rate UDP to the root every 30 s. Attacks start 75 s
after boot (paper value) and last 10 minutes. The final matrix covers 20, 30
and 40 nodes with 1, 20% and 30% attackers, each in both detector modes, over
5 independent seeds. Two sweeps (DIS threshold 2/3/5; attack period 1, 5, 10,
30 s and the paper's random 5-60 s) use 3 seeds. Cooja is deterministic per
seed: the same scenario run twice gave byte-identical logs
(`results/repeatability.txt`), so seed-to-seed spread reflects attacker
placement and timer jitter, not run noise. Development used 10-node, 5-minute
runs.

The **sample unit** matters. Node-level metrics classify each node once (the
paper's Table III view): an attacker is a true positive if any monitor raises
the attack's own rule during the attack; a normal node is a false positive if
any monitor raises that rule on it. Decision-level metrics score every
monitor-neighbour-window decision separately and expose the blind spots below.

## 8. Results

### 8.1 Baseline and DIS attack

Baseline runs form a stable DODAG (all nodes joined within ~60 s), deliver
every UDP packet (PDR 1.0) and average one parent change per node. Per-neighbour
DIO counts fall from the Trickle startup burst to 0-1 per window after
convergence, and the per-neighbour DIS count never exceeds 2, below the paper's
threshold of 3.

The **DIS attack reproduces the paper exactly**: at 20, 30 and 40 nodes and at
1, 20% and 30% attackers, node-level TPR is 100% and FPR is 0%. The DIS rule
fires on every DIS attacker and on no normal node, because normal DIS traffic
stays at or below the threshold.

### 8.2 Neighbour attack and two findings

A **single** neighbour attacker is detected at 100% TPR (20 nodes). But TPR
**collapses as the attacker fraction grows**: with 20% attackers it falls to
33% (30 nodes, 20% attackers) and to 5% (40 nodes, 30% attackers), mean over 5 seeds (Table 1).
Two mechanisms explain this, both rooted in the same statistics.

**Finding 1 - single-attacker blind spots.** Algorithm 1 divides by the
neighbour count, so it uses the *population* standard deviation, and the
attacker is one of the neighbours. By Samuelson's inequality the largest
z-score any member of a sample of n can have is sqrt(n-1). A lone attacker is
therefore detectable only where sqrt(n-1) > k(n). Because the paper fitted k to
the maximum normal z-score, k(n) tracks that bound and crosses it twice, so a
lone attacker is undetectable at 5-7 and at 28-32 neighbours, at any attack
rate. This was confirmed experimentally: of three monitors that hear a flooding
attacker (13-14 DIOs/window vs ~1 normal), only the one with 8 neighbours
flagged it (every window); the two with 5 and 6 neighbours never did, exactly
as predicted.

**Finding 2 - multiple attackers mask each other.** With several attackers in
one neighbourhood the mean and standard deviation both rise, so no single
attacker exceeds mean + k·sigma. This is the same bound with k outliers and it
drives the TPR collapse at 20% and 30%. The paper reports 94-99% TPR here; the
larger drop measured in this reproduction is attributed to attacker placement
(attackers clustered within radio range share monitors) and to the fixed-flood
attacker used here versus the paper's rebroadcast-on-receipt behaviour. It is
reported as a limitation of the published threshold under collusion.

False positives on the neighbour rule are the integer-quantisation alerts seen
in the baseline: a normal neighbour with 2-3 DIOs in a window where others sent
0-1. At the paper's scale the node-level rate is a few per cent, consistent with
the paper's 0.2-9.6%.

### 8.3 Resource overhead

Measured with `msp430-size` on the Tmote Sky (Contiki-NG v5.2):

| Component | ROM | RAM |
|---|---|---|
| IDS module `ids.o` (paper mode) | 1988 B | 588 B |
| Stock RPL-lite + UDP node baseline | 44578 / 49152 B (91%) | 7036 / 10240 B (69%) |

The detector itself is small (~2 KB ROM, ~0.6 KB RAM; sliding mode adds ~0.5 KB
RAM for the ring buffers). However, stock RPL-lite plus UDP already fills 91% of
the Sky's ROM under v5.2, so the instrumented node overflows ROM by ~10 KB and
the experiments run on the `cooja`/native mote. The paper used the same Sky
hardware but on Contiki 2.7, whose smaller RPL left far more free ROM. A
deployed detector without the verbose CSV logging is Sky-viable; the
instrumentation is a measurement artefact.

### 8.4 Fixed vs sliding window (original contribution)

Both modes use identical counters, attacks, topology and seeds; only the
evaluation cadence differs. The paper mode evaluates once per 300 s window; the
sliding mode keeps a 60 s window as six 10 s buckets and evaluates every 10 s.

On the same single-neighbour-attacker scenario the sliding window **more than
halved detection latency** (95 s vs 225 s) because it does not wait for a full
300 s window to elapse. The cost is a higher node-level false-positive rate,
because it makes many more decisions and so gives each normal node more chances
to be flagged once; the per-decision false-positive rate is comparable between
the modes. This confirms hypothesis H4: the sliding window trades sensitivity
to normal control traffic for faster detection. The contribution is not that
one window is universally better, but that the trade-off is explicit and
measurable, and that faster detection matters most exactly where the fixed
window is slowest (large windows chosen to suppress false positives).

**Table 1. Main matrix, node-level, mean over 5 seeds** (`results/summary.csv`).
FPR is mean ± sd across seeds; DIO is receptions per node per minute (baseline
4.6); perm = permanent blocks issued network-wide in 30 min.

| nodes | attack | attackers | mode | seeds | TPR % | FPR % | latency s | DIO/node/min | perm blocks |
|---|---|---|---|---|---|---|---|---|---|
| 20 | DIS | 1 | paper | 5 | 100.0 | 0.0 ± 0.0 | 225 | 27.4 | 13 |
| 20 | DIS | 1 | sliding | 5 | 100.0 | 0.0 ± 0.0 | 45 | 7.1 | 94 |
| 30 | DIS | 20% | paper | 5 | 100.0 | 0.0 ± 0.0 | 225 | 41.9 | 62 |
| 30 | DIS | 20% | sliding | 5 | 100.0 | 0.0 ± 0.0 | 45 | 15.3 | 126 |
| 40 | DIS | 30% | paper | 5 | 100.0 | 0.0 ± 0.0 | 225 | 61.0 | 112 |
| 40 | DIS | 30% | sliding | 5 | 100.0 | 0.0 ± 0.0 | 15 | 23.6 | 170 |
| 20 | neighbour | 1 | paper | 5 | 100.0 | 7.4 ± 7.1 | 225 | 6.2 | 11 |
| 20 | neighbour | 1 | sliding | 5 | 100.0 | 52.6 ± 26.4 | 29 | 5.4 | 92 |
| 30 | neighbour | 20% | paper | 5 | 33.3 | 1.7 ± 3.3 | 225 | 11.5 | 3 |
| 30 | neighbour | 20% | sliding | 5 | 46.7 | 12.5 ± 7.0 | 25 | 9.8 | 103 |
| 40 | neighbour | 30% | paper | 5 | 5.0 | 0.0 ± 0.0 | 225 | 24.3 | 2 |
| 40 | neighbour | 30% | sliding | 5 | 13.3 | 1.4 ± 2.9 | 11 | 20.5 | 105 |

Averaged over the six attack configurations, the sliding window cuts mean
detection latency from 225 s to 28 s, raises mean node-level FPR from 1.5% to
11.1%, and raises mean TPR from 73% to 77%: the shorter window captures an
attacker's burst before the other attackers' counts accumulate into the mean,
so it partly resists the masking of finding 2. It also **halves the DIO storm
caused by DIS attacks** (e.g. 61 to 24 receptions/node/min at 40 nodes, 30%
attackers) because it blocks the flooders sooner, before they trigger further
Trickle resets. Figures: `matrix.mode_comparison.png`, `matrix.tpr_fpr_by_size.png`.

Two costs are equally clear. First, node-level baseline FPR reaches 100% in
sliding mode (41% in paper mode): evaluating every 10 s gives each normal node
~180 chances per run to be flagged once by integer quantisation. Second, and
more serious, sliding mode issues **~100 permanent blocks per run even with no
attacker**, versus 0 for the paper mode, because the paper's blocking parameters
(two temporary blocks, then permanent) were calibrated for one decision per 5
minutes, not 30 per 5 minutes. A sliding detector must therefore raise the
block threshold or require consecutive confirmations; with the paper's values
it over-blocks the network. The per-decision FPR is close between the modes.

### 8.5 Network impact

Measured on the paper-mode matrix (`matrix.network_impact.png`):

| nodes | attack | PDR | mean delay ms | DIO rx/node/min | parent changes/node |
|---|---|---|---|---|---|
| 20 | baseline | 1.000 | 38 | 4.6 | 1.00 |
| 20 | neighbour, 1 | 1.000 | 38 | 6.2 | 1.06 |
| 20 | DIS, 1 | 1.000 | 38 | 27.4 | 1.06 |
| 30 | neighbour, 20% | 1.000 | 50 | 11.5 | 1.26 |
| 30 | DIS, 20% | 1.000 | 51 | 41.9 | 1.27 |
| 40 | neighbour, 30% | 1.000 | 63 | 24.3 | 1.44 |
| 40 | DIS, 30% | 1.000 | 64 | 61.0 | 1.44 |

Packet delivery stays at 1.0 and end-to-end delay is unchanged by the attacks:
UDGM with success ratio 1.0 and one 30 s datagram per node leaves the channel
far from saturation, so these attacks cost energy and stability rather than
delivery in this setting (a lossy radio model would change that). The damage
shows in the control plane: a single DIS attacker multiplies DIO receptions
sixfold, and 30% DIS attackers by thirteen, because each DIS resets every
receiver's Trickle timer. Parent changes rise from 1.0 to 1.44 per node. The
neighbour attack is cheaper for the network, adding mainly its own DIOs.

### 8.6 DIS threshold sensitivity

Paper mode, 20 nodes, one DIS attacker at the paper's random 5-60 s rate, 3
seeds each:

| DIS threshold | TPR % | FPR % (DIS rule) | latency s |
|---|---|---|---|
| 2 | 100 | 0.0 | 225 |
| 3 (paper) | 100 | 0.0 | 225 |
| 5 | 100 | 0.0 | 325 |

Detection is insensitive to the threshold in this range because normal nodes
never exceed 2 DIS per 5-minute window and the attacker sends about 10.
Threshold 5 only delays detection when a window happens to hold few attacker
DIS. The paper's choice of 3 is well placed.

### 8.7 Attack-rate sweep

20 nodes, one attacker, 3 seeds; cells are TPR / mean latency
(`matrix.latency_by_rate.png`):

| attack | period | paper mode | sliding mode | DIO rx/node/min |
|---|---|---|---|---|
| DIS | 1 s | 100 % / 225 s | 100 % / 5 s | 33.4 |
| DIS | 5 s | 100 % / 225 s | 100 % / 25 s | 33.0 |
| DIS | 10 s | 100 % / 225 s | 100 % / 45 s | 25.1 |
| DIS | 30 s | 100 % / 225 s | **0 %** / - | 17.5 |
| DIS | random 5-60 s | 100 % / 225 s | **33 %** / 575 s | 15.7 |
| neighbour | 1 s | 100 % / 225 s | 100 % / 5 s | 19.5 |
| neighbour | 5 s | 100 % / 225 s | 100 % / 22 s | 7.5 |
| neighbour | 10 s | 100 % / 225 s | 100 % / 28 s | 6.0 |
| neighbour | 30 s | 100 % / 225 s | 100 % / 55 s | 5.0 |
| neighbour | random 5-60 s | 100 % / 225 s | 100 % / 38 s | 4.9 |

The paper mode detects every rate with the same one-window latency. Sliding
latency scales with the attack period, down to 5 s for an aggressive attacker.
But sliding mode **misses slow DIS attackers**: a DIS every 30 s puts at most
two in a 60 s window, never above the fixed threshold of 3 that the paper
calibrated on 5-minute windows, so the random 5-60 s attacker is caught in only
one seed in three and the 30 s attacker never. **Finding 3:** a fixed count
threshold must scale with the window length; the sliding variant needs either
a threshold of ~1 per 60 s (with the false-positive risk that implies) or a
rate-based rule. The neighbour rule, being relative to the neighbourhood, has
no such dependence and is detected at every rate in both modes.

## 9. Discussion

The detector is effective and cheap where the paper's assumptions hold: the DIS
attack is caught perfectly, a single neighbour attacker is caught whenever a
non-blind monitor hears it, and false positives are the small, explainable
residue of integer quantisation over sparse Trickle traffic. Its weaknesses are
structural, not incidental: the population-standard-deviation threshold has
built-in blind spots at particular neighbourhood sizes and degrades sharply
under multiple colluding attackers. Detection latency is bounded below by the
window length, which the sliding variant addresses at a quantified cost: much
higher node-level false positives, over-blocking with the paper's response
parameters, and blindness to slow DIS attackers under a fixed count threshold.
Its unexpected benefits are partial resistance to masking and a halved DIO
storm under DIS attack, because flooders are blocked before they reset many
Trickle timers. Network impact in this lossless simulation is confined to the
control plane; delivery is unaffected.

## 10. Limitations and future work

The evaluation is simulation-only with static nodes, a known-ground-truth
configuration, and the two control-plane attacks of the paper. The radio model is
lossless, so delivery and delay impacts are lower bounds. The multi-attacker
TPR gap versus the paper deserves a controlled study of attacker placement and
of the rebroadcast-on-receipt attacker. Future work: window-scaled or rate-based DIS thresholds and confirmation-based
blocking for the sliding detector; a mitigation for the
masking effect (for example a robust/median-based dispersion estimate, or
excluding already-suspected neighbours from the profile), mobility, and real
Tmote Sky or nRF hardware once logging is trimmed to fit.

## 11. Conclusion

A distributed, low-resource anomaly IDS can detect RPL neighbour and DIS attacks
from purely local observations: the DIS attack is detected with 100% TPR and 0%
FPR, and a single neighbour attacker is reliably detected, reproducing the
paper on Contiki-NG. The reproduction also exposes two limits of the published
threshold - size-dependent blind spots and masking under collusion - and shows
that a sliding observation window cuts detection latency by an order of
magnitude and halves the DIS-induced DIO storm, at the cost of far more false
positives, over-blocking unless the response parameters are re-tuned, and a
fixed DIS threshold that no longer matches the window. The research question is answered: yes, with
the caveat that the dynamic threshold's statistics bound both which lone
attackers and how many simultaneous attackers it can catch.

---

## Appendix: figures and files

| figure | file |
|---|---|
| topology, 40 nodes, 30% attackers (paper Fig. 6 layout) | `report/figures/topology-m-40-neighbor-a30pct-w300-paper-s1.png` |
| DIO and DIS per neighbour over time | `report/figures/m-10-*-dio_over_time.png`, `*-dis_over_time.png` |
| threshold vs attacker count at the detecting monitor | `report/figures/m-20-neighbor-a1-w300-paper-s1.threshold_vs_count.png` |
| alerts on the timeline | `report/figures/m-10-neighbor-a1-w60-paper-s1.alerts_timeline.png` |
| TPR and FPR by network size | `report/figures/matrix.tpr_fpr_by_size.png` |
| latency and TPR by attack rate | `report/figures/matrix.latency_by_rate.png` |
| PDR and DIO overhead, baseline vs attacks | `report/figures/matrix.network_impact.png` |
| paper vs sliding detector | `report/figures/matrix.mode_comparison.png` |

Data: `results/matrix.csv` (one row per run), `results/summary.csv` (per
configuration, mean/sd/min/max), `results/overhead.txt`,
`results/repeatability.txt`. Kept run logs: `report/evidence/`. Demo script:
`report/demo.md`.
