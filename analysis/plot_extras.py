import argparse
import csv
import math
import os
import matplotlib.pyplot as plt

def read_data(path):
    times = []
    alts = []
    vels = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            times.append(float(row["time_boot_ms"])/1000.0)
            alts.append(float(row["rel_alt_m"]))
            vx, vy, vz = float(row["vx_mps"]), float(row["vy_mps"]), float(row["vz_mps"])
            vels.append(math.sqrt(vx*vx + vy*vy + vz*vz))
    if times:
        t0 = times[0]
        times = [t - t0 for t in times]
    return times, alts, vels

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--attack", required=True)
    parser.add_argument("--outdir", required=True)
    args = parser.parse_args()

    b_times, b_alts, b_vels = read_data(args.baseline)
    a_times, a_alts, a_vels = read_data(args.attack)

    os.makedirs(args.outdir, exist_ok=True)

    # Plot Altitude
    plt.figure(figsize=(7, 4))
    plt.plot(b_times, b_alts, label="Baseline", color="#1f77b4", linewidth=1.5)
    plt.plot(a_times, a_alts, label="Attack", color="#d62728", linewidth=1.5, linestyle="--")
    plt.xlabel("Time (s)")
    plt.ylabel("Relative Altitude (m)")
    plt.title("Altitude vs Time")
    plt.legend()
    plt.grid(True, linestyle=":")
    plt.tight_layout()
    plt.savefig(os.path.join(args.outdir, "altitude_vs_time.png"), dpi=150)

    # Plot Velocity
    plt.figure(figsize=(7, 4))
    plt.plot(b_times, b_vels, label="Baseline", color="#1f77b4", linewidth=1.5)
    plt.plot(a_times, a_vels, label="Attack", color="#d62728", linewidth=1.5, linestyle="--")
    plt.xlabel("Time (s)")
    plt.ylabel("Velocity (m/s)")
    plt.title("Total Velocity vs Time")
    plt.legend()
    plt.grid(True, linestyle=":")
    plt.tight_layout()
    plt.savefig(os.path.join(args.outdir, "velocity_vs_time.png"), dpi=150)

if __name__ == "__main__":
    main()
