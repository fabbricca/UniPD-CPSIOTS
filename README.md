# UniPD — CPS & IoT Security

Course projects for *Cyber-Physical Systems and IoT Security* (MSc Computer Science,
University of Padova, 2025/26). Two independent reproductions of published attacks and
defences, each with its own Docker toolchain, experiment runner and written report.

| project | what it is | stack |
|---|---|---|
| [`rpl-ids/`](rpl-ids/) | **Distributed anomaly-based IDS for RPL.** Reproduction of Farzaneh, Montazeri & Jamali, *An Anomaly-Based IDS for Detecting Attacks in RPL-Based IoT* (ICWR 2019): DIO/DIS flooding attackers, the paper's z-score detector and blocking, plus an original fixed- vs sliding-window comparison and an analytical detection blind spot (Samuelson's bound) confirmed in simulation. DIS attack reproduces the paper exactly — TPR 100 %, FPR 0 %. | Contiki-NG v5.2 · Cooja (headless) · C · Python |
| [`drone-spoofing/`](drone-spoofing/) | **Adaptive GPS spoofing of a consumer drone.** Reproduction of Strategy C from Noh et al., *Tractor Beam: Safe-hijacking of Consumer Drones with Adaptive GPS Spoofing* (ACM TOPS 2019) against ArduCopter SITL: adaptive `GPS_INPUT` injection steers the vehicle 5.3° off its planned track while the EKF still believes it is on course. | ArduPilot SITL · MAVLink · Python |

Each directory has its own README with a quick start; both need only Docker.
The engineering log for the IDS project is in [`PROJECT_PLAN.md`](PROJECT_PLAN.md).

**Author:** Riccardo Fabbian
