#!/usr/bin/env python3
import argparse
import csv
import os
import time

from pymavlink import mavutil


DEFAULT_MASTER = "udp:127.0.0.1:14550"


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
                    "current": int(parts[1]),
                    "frame": int(parts[2]),
                    "command": int(parts[3]),
                    "param1": float(parts[4]),
                    "param2": float(parts[5]),
                    "param3": float(parts[6]),
                    "param4": float(parts[7]),
                    "x": float(parts[8]),
                    "y": float(parts[9]),
                    "z": float(parts[10]),
                    "autocontinue": int(parts[11]),
                }
            )
    return items


def upload_mission(mav, items, timeout_s=20):
    mav.mav.mission_clear_all_send(mav.target_system, mav.target_component)
    mav.mav.mission_count_send(mav.target_system, mav.target_component, len(items))

    sent = set()
    start = time.time()
    while len(sent) < len(items):
        if time.time() - start > timeout_s:
            raise TimeoutError("Timed out waiting for mission requests")
        msg = mav.recv_match(
            type=["MISSION_REQUEST", "MISSION_REQUEST_INT"],
            blocking=True,
            timeout=2,
        )
        if msg is None:
            continue
        seq = msg.seq
        if seq < 0 or seq >= len(items):
            continue
        item = items[seq]
        if msg.get_type() == "MISSION_REQUEST_INT":
            mav.mav.mission_item_int_send(
                mav.target_system,
                mav.target_component,
                seq,
                item["frame"],
                item["command"],
                item["current"],
                item["autocontinue"],
                item["param1"],
                item["param2"],
                item["param3"],
                item["param4"],
                int(item["x"] * 1e7),
                int(item["y"] * 1e7),
                item["z"],
            )
        else:
            mav.mav.mission_item_send(
                mav.target_system,
                mav.target_component,
                seq,
                item["frame"],
                item["command"],
                item["current"],
                item["autocontinue"],
                item["param1"],
                item["param2"],
                item["param3"],
                item["param4"],
                item["x"],
                item["y"],
                item["z"],
            )
        sent.add(seq)

    ack = mav.recv_match(type="MISSION_ACK", blocking=True, timeout=timeout_s)
    if ack is None:
        raise TimeoutError("Timed out waiting for mission ACK")


def set_mode(mav, mode):
    mapping = mav.mode_mapping()
    if mode not in mapping:
        raise ValueError(f"Mode {mode} not supported")
    mav.mav.set_mode_send(
        mav.target_system,
        mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
        mapping[mode],
    )


def arm(mav):
    mav.mav.command_long_send(
        mav.target_system,
        mav.target_component,
        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
        0,
        1,
        0,
        0,
        0,
        0,
        0,
        0,
    )


def takeoff(mav, altitude_m):
    mav.mav.command_long_send(
        mav.target_system,
        mav.target_component,
        mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        altitude_m,
    )


def set_param(mav, name, value, timeout_s=5):
    mav.mav.param_set_send(
        mav.target_system,
        mav.target_component,
        name.encode("utf-8"),
        float(value),
        mavutil.mavlink.MAV_PARAM_TYPE_REAL32,
    )
    start = time.time()
    while time.time() - start < timeout_s:
        msg = mav.recv_match(type="PARAM_VALUE", blocking=True, timeout=1)
        if msg is None:
            continue
        pid = msg.param_id
        if isinstance(pid, bytes):
            pid = pid.decode("utf-8")
        if pid.strip("\x00") == name:
            return True
    return False


def apply_pre_arm_params(mav, log):
    # DISARM_DELAY=60:  avoid auto-disarm if takeoff is delayed (default 10s).
    # ARMING_CHECK=0:   skip pre-arm checks for scripted SITL runs.
    # FS_GCS_ENABLE=0:  don't trigger GCS failsafe if pymavlink lags.
    # FS_EKF_THRESH=0:  disable EKF-variance failsafe. Modern ArduCopter checks
    #   compass+velocity+position+height variances (paper analyzed an older
    #   3DR Solo with velVar-only). The paper's adaptive-spoofing strategy
    #   keeps fail_count under 10 on the old check; on the modern check the
    #   position-variance always trips. Disabling matches the paper's intent:
    #   the drone *can* be steered by the spoofer without failsafing.
    # EK3_GLITCH_RAD=0:  Clip GPS innovations instead of rejecting them.
    #   Without this, a 20m spoofed-position offset trips the innovation gate
    #   ("EKF3 IMU0 stopped aiding") and the EKF falls back to IMU-only
    #   dead-reckoning — meaning our spoof is ignored. With GLITCH_RAD=0,
    #   the EKF state migrates toward the spoofed GPS, which is what lets
    #   the drone actually be steered (matches paper §7.3.1 assumption that
    #   the spoofed GPS reaches the EKF).
    # EK3_POS_I_GATE / EK3_VEL_I_GATE = 1000: maximum-permissive innovation
    #   gate (10 sigma instead of default 5). Lets larger spoofed offsets
    #   pass through the consistency check.
    # NOTE: EK3_POSNE_M_NSE/VELNE_M_NSE not bumped — raising those breaks
    #   pre-arm because the EKF reports its position estimate as too
    #   uncertain to safely arm.
    for name, value in (
        ("DISARM_DELAY", 60),
        ("ARMING_CHECK", 0),
        ("FS_GCS_ENABLE", 0),
        ("FS_EKF_THRESH", 0),
        ("EK3_GLITCH_RAD", 0),
        ("EK3_POS_I_GATE", 1000),
        ("EK3_VEL_I_GATE", 1000),
    ):
        # Raise loudly on failure: silent fall-through here means the EKF
        # gates / failsafes stay at defaults and the spoof later fails
        # without any visible error.
        if not set_param(mav, name, value):
            raise RuntimeError(f"Failed to set pre-arm param {name}={value}")


def wait_gps_fix(mav, timeout_s=30):
    start = time.time()
    while time.time() - start < timeout_s:
        msg = mav.recv_match(type="GPS_RAW_INT", blocking=True, timeout=2)
        if msg and msg.fix_type >= 3:
            return True
    return False


def wait_heartbeat(mav, timeout_s=30):
    start = time.time()
    while time.time() - start < timeout_s:
        msg = mav.recv_match(type="HEARTBEAT", blocking=True, timeout=2)
        if msg:
            return True
    return False


def wait_altitude(mav, altitude_m, timeout_s=120):
    start = time.time()
    while time.time() - start < timeout_s:
        msg = mav.recv_match(type="GLOBAL_POSITION_INT", blocking=True, timeout=2)
        if msg:
            rel_alt = msg.relative_alt / 1000.0
            if rel_alt >= altitude_m * 0.95:
                return True
    return False


def wait_disarmed(mav, timeout_s=120):
    start = time.time()
    while time.time() - start < timeout_s:
        msg = mav.recv_match(type="HEARTBEAT", blocking=True, timeout=2)
        if msg:
            if not (msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED):
                return True
    return False


def wait_armed(mav, timeout_s=20):
    start = time.time()
    while time.time() - start < timeout_s:
        msg = mav.recv_match(type="HEARTBEAT", blocking=True, timeout=2)
        if msg:
            if msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED:
                return True
    return False


def run():
    parser = argparse.ArgumentParser(description="Automate SITL mission and log GPS.")
    parser.add_argument(
        "--master",
        default=DEFAULT_MASTER,
        help="MAVLink connection string",
    )
    parser.add_argument(
        "--mission",
        required=True,
        help="Path to QGC WPL mission file",
    )
    parser.add_argument("--takeoff-alt", type=float, default=35.0)
    parser.add_argument("--arm-retries", type=int, default=3)
    parser.add_argument("--arm-timeout", type=float, default=20.0)
    parser.add_argument(
        "--enable-gps-input",
        action="store_true",
        help="Set GPS_TYPE=14 (MAVLink) to accept GPS_INPUT",
    )
    parser.add_argument("--land", action="store_true")
    parser.add_argument("--log", default="")
    parser.add_argument(
        "--max-runtime-s",
        type=float,
        default=0.0,
        help="Stop the mission loop after this many seconds (0 = no limit)",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    def log(message):
        if args.verbose:
            print(message, flush=True)

    log_path = args.log
    if not log_path:
        ts = time.strftime("%Y%m%d_%H%M%S")
        log_path = os.path.join("logs", f"mission_{ts}.csv")

    os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)

    with open(log_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "time_boot_ms",
                "lat",
                "lon",
                "rel_alt_m",
                "vx_mps",
                "vy_mps",
                "vz_mps",
                "mode",
                "true_lat",
                "true_lon",
            ]
        )
        handle.flush()

        log(f"Connecting to {args.master}...")
        mav = mavutil.mavlink_connection(args.master)
        log("Waiting for heartbeat...")
        if not wait_heartbeat(mav):
            raise RuntimeError("No heartbeat received")

        log("Applying pre-arm params (DISARM_DELAY=60, ARMING_CHECK=0, FS_GCS_ENABLE=0)...")
        apply_pre_arm_params(mav, log)

        if args.enable_gps_input:
            # GPS1 stays SITL-driven; GPS2 becomes a MAVLink GPS_INPUT sink so
            # the spoofer runs alongside the legitimate GPS until silenced.
            log("Setting GPS2_TYPE=14 for GPS_INPUT...")
            if not set_param(mav, "GPS2_TYPE", 14):
                raise RuntimeError("Failed to set GPS2_TYPE")

        log("Waiting for GPS fix...")
        if not wait_gps_fix(mav):
            raise RuntimeError("No GPS fix")

        items = parse_qgc_wpl(args.mission)
        log(f"Uploading mission ({len(items)} items)...")
        upload_mission(mav, items)
        log("Mission uploaded")

        log("Arming and taking off...")
        set_mode(mav, "GUIDED")

        armed = False
        for attempt in range(1, args.arm_retries + 1):
            arm(mav)
            if wait_armed(mav, timeout_s=args.arm_timeout):
                armed = True
                break
            log(f"Arm attempt {attempt} failed")

        if not armed:
            raise RuntimeError("Failed to arm")

        takeoff(mav, args.takeoff_alt)

        if not wait_altitude(mav, args.takeoff_alt):
            raise RuntimeError("Takeoff did not reach target altitude")

        log("Switching to AUTO and logging path...")
        set_mode(mav, "AUTO")

        last_seq = len(items) - 1
        reached_last = False

        # Track SIMSTATE (ground-truth physics) so the plot shows where the
        # drone *actually* is, not where its (potentially spoofed) EKF says
        # it is. Without this, a successful spoof produces a plot that looks
        # like a clean mission because the EKF tracks the planned path.
        last_true_lat = ""
        last_true_lon = ""

        mission_started = time.time()
        while not reached_last:
            if args.max_runtime_s > 0 and (time.time() - mission_started) >= args.max_runtime_s:
                log("Reached max runtime; ending mission loop")
                break
            msg = mav.recv_match(
                type=["GLOBAL_POSITION_INT", "SIMSTATE", "MISSION_ITEM_REACHED", "HEARTBEAT"],
                blocking=True,
                timeout=2,
            )
            if msg is None:
                continue

            if msg.get_type() == "SIMSTATE":
                last_true_lat = msg.lat / 1e7
                last_true_lon = msg.lng / 1e7
                continue

            if msg.get_type() == "GLOBAL_POSITION_INT":
                writer.writerow(
                    [
                        msg.time_boot_ms,
                        msg.lat / 1e7,
                        msg.lon / 1e7,
                        msg.relative_alt / 1000.0,
                        msg.vx / 100.0,
                        msg.vy / 100.0,
                        msg.vz / 100.0,
                        mav.flightmode,
                        last_true_lat,
                        last_true_lon,
                    ]
                )
                handle.flush()
            elif msg.get_type() == "MISSION_ITEM_REACHED":
                log(f"Reached mission item {msg.seq}")
                if msg.seq >= last_seq:
                    reached_last = True
            elif msg.get_type() == "HEARTBEAT":
                # Exit cleanly if the autopilot disarms (e.g. EKF failsafe
                # forced LAND mid-mission) — otherwise we'd loop forever
                # waiting for a MISSION_ITEM_REACHED that will never arrive.
                if not (msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED):
                    log("Disarmed before reaching final waypoint — ending mission loop")
                    break

        if args.land:
            log("Landing...")
            set_mode(mav, "LAND")
            wait_disarmed(mav)

    print(f"Mission complete. Log saved to {log_path}")


if __name__ == "__main__":
    run()
