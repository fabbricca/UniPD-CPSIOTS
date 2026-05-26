#!/usr/bin/env python3
import argparse
import os
import signal
import subprocess
import sys
import time

from pymavlink import mavutil


DEFAULT_MASTER = "udp:127.0.0.1:14550"
SPOOFER_MASTER = "udp:127.0.0.1:14551"
DEFAULT_ARDUPILOT = os.environ.get("ARDUPILOT_ROOT", "/opt/ardupilot")
DEFAULT_MISSION = "missions/attacker_zone_mission.waypoints"


def derive_home_from_mission(mission_path, default="45.0,11.0,0,0"):
    # First non-empty line after the QGC header is the home/launch waypoint;
    # columns are: seq curr frame cmd p1 p2 p3 p4 lat lon alt autocont.
    try:
        with open(mission_path, "r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped or stripped.startswith("QGC"):
                    continue
                parts = stripped.split()
                if len(parts) < 12:
                    continue
                lat = float(parts[8])
                lon = float(parts[9])
                # Skip placeholder home rows where lat/lon are 0.
                if lat == 0.0 and lon == 0.0:
                    continue
                return f"{lat},{lon},0,0"
    except (OSError, ValueError):
        pass
    return default


def wait_for_heartbeat(master, timeout_s=60):
    start = time.time()
    while time.time() - start < timeout_s:
        mav = None
        try:
            mav = mavutil.mavlink_connection(master)
            mav.wait_heartbeat(timeout=2)
            return True
        except Exception:
            time.sleep(1)
        finally:
            if mav is not None:
                try:
                    mav.close()
                except Exception:
                    pass
    return False


def start_sitl(ardupilot_root, log_path, extra_args, wipe_eeprom, speedup, custom_location):
    sim_vehicle = os.path.join(ardupilot_root, "Tools", "autotest", "sim_vehicle.py")
    # mavproxy stays enabled (handles fan-out to UDP 14550 + 14551), but we
    # unload its `wp` module which intercepts MISSION_COUNT/REQUEST and stops
    # GCS-side mission uploads from reaching the autopilot.
    extra_param_file = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "missions", "sim_float_except_off.parm")
    )
    cmd = [
        sim_vehicle,
        "-v", "ArduCopter",
        "--no-rebuild",
        "--speedup", str(speedup),
        "--custom-location", custom_location,
        "--out", "udp:127.0.0.1:14551",
        "--add-param-file", extra_param_file,
        "--mavproxy-args",
        "--non-interactive --cmd \"module unload wp\"",
    ]
    if wipe_eeprom:
        cmd.append("-w")
    if extra_args:
        cmd.extend(extra_args)

    env = os.environ.copy()
    env.setdefault("CC", "clang")
    env.setdefault("CXX", "clang++")

    log_handle = open(log_path, "w", encoding="utf-8")
    proc = subprocess.Popen(
        cmd,
        cwd=ardupilot_root,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        env=env,
    )
    return proc, log_handle


def stop_process(proc, log_handle, timeout_s=10):
    if proc.poll() is None:
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                proc.wait(timeout=timeout_s)
            except subprocess.TimeoutExpired:
                proc.kill()
    log_handle.close()


def run_auto_mission(
    python,
    mission,
    master,
    takeoff_alt,
    log_path,
    enable_gps_input,
    max_runtime_s,
):
    cmd = [
        python,
        os.path.join("scripts", "auto_mission.py"),
        "--mission",
        mission,
        "--master",
        master,
        "--takeoff-alt",
        str(takeoff_alt),
        "--log",
        log_path,
        "--land",
        "--max-runtime-s",
        str(max_runtime_s),
        "--verbose",
    ]
    if enable_gps_input:
        cmd.append("--enable-gps-input")
    subprocess.run(cmd, check=True)


def run_spoofer(
    python,
    master,
    zone_circle,
    mission,
    target_latlon,
    land_target_latlon,
    land_radius_m,
    fake_final_s,
    log_path,
    profile,
    max_offset_m,
    ramp_time_s,
    exit_decay_s,
    bearing_deg,
    leash_length_m,
    gps_update_hz,
    max_velocity_mps,
    ainit_offset_m,
    jump_cooldown_s,
    sync_duration_s,
    ramp_ticks,
    final_wp_min_dist_m,
):
    cmd = [
        python,
        os.path.join("scripts", "spoof_gps.py"),
        "--master",
        master,
        "--profile",
        profile,
        "--zone-circle",
        zone_circle,
        "--mission",
        mission,
        "--land-target-latlon",
        land_target_latlon,
        "--land-radius-m",
        str(land_radius_m),
        "--fake-final-s",
        str(fake_final_s),
        "--gps-update-hz",
        str(gps_update_hz),
        "--max-velocity-mps",
        str(max_velocity_mps),
        "--leash-length-m",
        str(leash_length_m),
        "--ainit-offset-m",
        str(ainit_offset_m),
        "--jump-cooldown-s",
        str(jump_cooldown_s),
        "--final-wp-min-dist-m",
        str(final_wp_min_dist_m),
        "--log",
        log_path,
        "--max-offset-m",
        str(max_offset_m),
        "--ramp-time-s",
        str(ramp_time_s),
        "--exit-decay-s",
        str(exit_decay_s),
        "--offset-bearing-deg",
        str(bearing_deg),
        "--sync-duration-s",
        str(sync_duration_s),
        "--ramp-ticks",
        str(ramp_ticks),
        "--verbose",
    ]
    if target_latlon:
        cmd.extend(["--target-latlon", target_latlon])
    return subprocess.Popen(cmd)


def plot_paths(python, baseline_log, attack_log, spoof_log, zone_circle, output_path):
    # Default plot: just the two flown paths. The spoofing log is still
    # written to disk and can be overlaid manually with
    #   python analysis/plot_path.py --spoof-log ... ...
    cmd = [
        python,
        os.path.join("analysis", "plot_path.py"),
        baseline_log,
        attack_log,
        "--labels",
        "baseline",
        "attack",
        "--zone-circle",
        zone_circle,
        "--out",
        output_path,
    ]
    subprocess.run(cmd, check=True)


def run():
    parser = argparse.ArgumentParser(description="Run baseline and attack scenarios.")
    parser.add_argument("--ardupilot-root", default=DEFAULT_ARDUPILOT)
    parser.add_argument("--mission", default=DEFAULT_MISSION)
    parser.add_argument("--master", default=DEFAULT_MASTER)
    parser.add_argument("--takeoff-alt", type=float, default=35.0)
    parser.add_argument("--zone-circle", required=True, help="lat,lon,radius_m")
    parser.add_argument("--profile", choices=["tractorbeam", "ramp"], default="tractorbeam")
    parser.add_argument("--target-latlon", default="")
    parser.add_argument("--land-target-latlon", default="")
    parser.add_argument("--land-radius-m", type=float, default=5.0)
    parser.add_argument("--fake-final-s", type=float, default=2.0)
    parser.add_argument("--leash-length-m", type=float, default=13.0)
    parser.add_argument(
        "--gps-update-hz",
        type=float,
        default=0.0,
        help="Override observed GPS rate (0 = let spoofer measure f_obs)",
    )
    parser.add_argument("--max-velocity-mps", type=float, default=500.0)
    parser.add_argument("--ainit-offset-m", type=float, default=20.0)
    parser.add_argument("--jump-cooldown-s", type=float, default=1.0)
    parser.add_argument("--max-offset-m", type=float, default=50.0)
    parser.add_argument("--final-wp-min-dist-m", type=float, default=0.0)
    parser.add_argument("--ramp-time-s", type=float, default=20.0)
    parser.add_argument("--exit-decay-s", type=float, default=5.0)
    parser.add_argument("--offset-bearing-deg", type=float, default=90.0)
    parser.add_argument("--sync-duration-s", type=float, default=1.5)
    parser.add_argument("--ramp-ticks", type=int, default=30)
    parser.add_argument(
        "--attack-max-runtime-s",
        type=float,
        default=0.0,
        help="Stop the attack mission loop after this many seconds (0 = no limit)",
    )
    parser.add_argument("--speedup", type=int, default=4)
    parser.add_argument("--plot-out", default="plots/mission_path.png")
    parser.add_argument("--no-plot", action="store_true")
    parser.add_argument("--sitl-args", nargs="*", default=[])
    parser.add_argument(
        "--home",
        default="",
        help="SITL home as 'lat,lon,alt,hdg' (default: derived from mission first WP)",
    )
    args = parser.parse_args()

    os.makedirs("logs", exist_ok=True)
    os.makedirs("plots", exist_ok=True)

    ts = time.strftime("%Y%m%d_%H%M%S")
    baseline_log = os.path.join("logs", f"baseline_{ts}.csv")
    attack_log = os.path.join("logs", f"attack_{ts}.csv")
    spoof_log = os.path.join("logs", f"spoofing_{ts}.csv")

    python = sys.executable

    home = args.home or derive_home_from_mission(args.mission)
    print(f"SITL home: {home}")

    print("Starting baseline SITL...")
    base_sitl_log = os.path.join("logs", f"sitl_baseline_{ts}.log")
    base_proc, base_handle = start_sitl(
        args.ardupilot_root, base_sitl_log, args.sitl_args, wipe_eeprom=True,
        speedup=args.speedup, custom_location=home,
    )
    try:
        if not wait_for_heartbeat(args.master, timeout_s=120):
            raise RuntimeError("SITL heartbeat timeout")
        run_auto_mission(
            python,
            args.mission,
            args.master,
            args.takeoff_alt,
            baseline_log,
            enable_gps_input=False,
            max_runtime_s=0.0,
        )
    finally:
        stop_process(base_proc, base_handle)

    print("Starting attack SITL...")
    attack_sitl_log = os.path.join("logs", f"sitl_attack_{ts}.log")
    attack_proc, attack_handle = start_sitl(
        args.ardupilot_root, attack_sitl_log, args.sitl_args, wipe_eeprom=True,
        speedup=args.speedup, custom_location=home,
    )
    spoofer_proc = None
    try:
        if not wait_for_heartbeat(args.master, timeout_s=120):
            raise RuntimeError("SITL heartbeat timeout")
        spoofer_proc = run_spoofer(
            python,
            SPOOFER_MASTER,
            args.zone_circle,
            args.mission,
            args.target_latlon,
            args.land_target_latlon,
            args.land_radius_m,
            args.fake_final_s,
            spoof_log,
            args.profile,
            args.max_offset_m,
            args.ramp_time_s,
            args.exit_decay_s,
            args.offset_bearing_deg,
            args.leash_length_m,
            args.gps_update_hz,
            args.max_velocity_mps,
            args.ainit_offset_m,
            args.jump_cooldown_s,
            args.sync_duration_s,
            args.ramp_ticks,
            args.final_wp_min_dist_m,
        )
        run_auto_mission(
            python,
            args.mission,
            args.master,
            args.takeoff_alt,
            attack_log,
            enable_gps_input=True,
            max_runtime_s=args.attack_max_runtime_s,
        )
    finally:
        if spoofer_proc and spoofer_proc.poll() is None:
            spoofer_proc.terminate()
            try:
                spoofer_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                spoofer_proc.kill()
        stop_process(attack_proc, attack_handle)

    if not args.no_plot:
        plot_paths(python, baseline_log, attack_log, spoof_log, args.zone_circle, args.plot_out)
        print(f"Plot saved to {args.plot_out}")

    print(f"Baseline log: {baseline_log}")
    print(f"Attack log: {attack_log}")
    print(f"Spoofing log: {spoof_log}")


if __name__ == "__main__":
    run()
