#!/usr/bin/env python3
import argparse
import csv
import math
import os

import matplotlib.pyplot as plt


STATE_COLORS = {
    "sync": "#ffcc00",
    "ramp": "#ff7f0e",
    "adaptive": "#d62728",
}


def read_path(path, prefer_true=False):
    # When prefer_true is set and the CSV carries true_lat/true_lon (added
    # by auto_mission.py from SIMSTATE), use those — that's the ground-truth
    # physics position. Otherwise fall back to lat/lon (the EKF estimate,
    # which can be spoofed).
    lats = []
    lons = []
    true_lats = []
    true_lons = []
    with open(path, "r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            lats.append(float(row["lat"]))
            lons.append(float(row["lon"]))
            tl = row.get("true_lat", "")
            tn = row.get("true_lon", "")
            if tl and tn:
                try:
                    true_lats.append(float(tl))
                    true_lons.append(float(tn))
                except ValueError:
                    pass
    if prefer_true and len(true_lats) == len(lats) and true_lats:
        return true_lats, true_lons
    return lats, lons


def read_spoof_log(path):
    rows = []
    with open(path, "r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            try:
                rows.append(
                    {
                        "timestamp": float(row["timestamp"]),
                        "state": row.get("state", ""),
                        "lat": float(row["lat"]),
                        "lon": float(row["lon"]),
                    }
                )
            except (KeyError, ValueError):
                continue
    return rows


def parse_polygon(poly_text):
    points = []
    if not poly_text:
        return points
    for chunk in poly_text.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        lat_str, lon_str = chunk.split(",")
        points.append((float(lat_str.strip()), float(lon_str.strip())))
    return points


def parse_circle(circle_text):
    if not circle_text:
        return None
    parts = [p.strip() for p in circle_text.split(",")]
    if len(parts) != 3:
        raise ValueError("Circle must be 'lat,lon,radius_m'")
    return float(parts[0]), float(parts[1]), float(parts[2])


def circle_points(center_lat, center_lon, radius_m, samples=64):
    points = []
    radius_deg_lat = radius_m / 6378137.0
    for i in range(samples + 1):
        angle = 2 * 3.141592653589793 * (i / samples)
        dlat = radius_deg_lat * math.cos(angle)
        dlon = radius_deg_lat * math.sin(angle) / math.cos(math.radians(center_lat))
        points.append((center_lat + math.degrees(dlat), center_lon + math.degrees(dlon)))
    return points


def overlay_spoof_segments(rows):
    if not rows:
        return
    legend_seen = set()
    segment_lats = [rows[0]["lat"]]
    segment_lons = [rows[0]["lon"]]
    segment_state = rows[0]["state"]
    for row in rows[1:]:
        if row["state"] == segment_state:
            segment_lats.append(row["lat"])
            segment_lons.append(row["lon"])
            continue
        color = STATE_COLORS.get(segment_state)
        if color is not None:
            label = f"spoof:{segment_state}" if segment_state not in legend_seen else None
            plt.plot(segment_lons, segment_lats, linewidth=2.0, color=color, label=label, alpha=0.7)
            legend_seen.add(segment_state)
        segment_lats = [row["lat"]]
        segment_lons = [row["lon"]]
        segment_state = row["state"]
    color = STATE_COLORS.get(segment_state)
    if color is not None:
        label = f"spoof:{segment_state}" if segment_state not in legend_seen else None
        plt.plot(segment_lons, segment_lats, linewidth=2.0, color=color, label=label, alpha=0.7)


def plot_paths(inputs, labels, polygon, circle, spoof_rows, output):
    plt.figure(figsize=(7, 7))

    # Explicit colors per run so true vs EKF traces are clearly distinct.
    # EKF traces use long dashes in a contrasting color so they don't blur
    # into the (true) trace at common scales.
    palette = [
        ("#1f77b4", "#17becf"),  # baseline: blue + cyan
        ("#2ca02c", "#d62728"),  # attack:   green + red
        ("#9467bd", "#8c564b"),  # extra:    purple + brown
        ("#e377c2", "#7f7f7f"),  # extra:    pink + gray
    ]
    for idx, path in enumerate(inputs):
        label = labels[idx] if labels and idx < len(labels) else os.path.basename(path)
        true_color, ekf_color = palette[idx % len(palette)]
        # For attack-style logs, plot the ground-truth (SIMSTATE) trace —
        # the EKF trace would show the planned mission completing cleanly
        # even when the drone is physically deflected.
        true_lats, true_lons = read_path(path, prefer_true=True)
        ekf_lats, ekf_lons = read_path(path, prefer_true=False)
        if true_lats != ekf_lats or true_lons != ekf_lons:
            plt.plot(true_lons, true_lats, linewidth=1.8, color=true_color,
                     label=f"{label} (true)")
            plt.plot(ekf_lons, ekf_lats, linewidth=1.4, color=ekf_color,
                     linestyle=(0, (8, 4)), label=f"{label} (EKF)")
        else:
            plt.plot(ekf_lons, ekf_lats, linewidth=1.5, color=true_color,
                     label=label)

    overlay_spoof_segments(spoof_rows)

    if polygon:
        poly_lats = [p[0] for p in polygon] + [polygon[0][0]]
        poly_lons = [p[1] for p in polygon] + [polygon[0][1]]
        plt.plot(poly_lons, poly_lats, linestyle="--", color="black", label="zone")
    elif circle:
        circle_pts = circle_points(*circle)
        circle_lats = [p[0] for p in circle_pts]
        circle_lons = [p[1] for p in circle_pts]
        plt.plot(circle_lons, circle_lats, linestyle="--", color="black", label="zone")

    plt.xlabel("Longitude")
    plt.ylabel("Latitude")
    plt.axis("equal")
    plt.grid(True, linestyle=":")
    if len(inputs) > 1 or polygon or circle or spoof_rows:
        plt.legend()

    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
    plt.tight_layout()
    plt.savefig(output, dpi=150)


def run():
    parser = argparse.ArgumentParser(description="Plot logged mission paths.")
    parser.add_argument("inputs", nargs="+", help="CSV logs from auto_mission.py")
    parser.add_argument("--labels", nargs="*", default=[])
    parser.add_argument("--zone", default="", help="Polygon: 'lat,lon; lat,lon; ...'")
    parser.add_argument("--zone-circle", default="", help="Circle: 'lat,lon,radius_m'")
    parser.add_argument(
        "--spoof-log",
        default="",
        help="Optional spoofing CSV; sync/ramp/adaptive segments are overlaid",
    )
    parser.add_argument("--out", default="plots/mission_path.png")
    args = parser.parse_args()

    polygon = parse_polygon(args.zone)
    circle = parse_circle(args.zone_circle)
    spoof_rows = read_spoof_log(args.spoof_log) if args.spoof_log and os.path.exists(args.spoof_log) else []
    plot_paths(args.inputs, args.labels, polygon, circle, spoof_rows, args.out)


if __name__ == "__main__":
    run()
