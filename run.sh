#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

cmd="${1:-help}"
shift || true

case "$cmd" in
    build)
        exec docker compose build "$@"
        ;;
    shell)
        exec docker compose run --rm --entrypoint /bin/bash sim "$@"
        ;;
    run)
        exec docker compose run --rm sim python /work/scripts/run_scenarios.py "$@"
        ;;
    sitl)
        exec docker compose run --rm --service-ports sim \
            python /opt/ardupilot/Tools/autotest/sim_vehicle.py -v ArduCopter --console "$@"
        ;;
    plot)
        exec docker compose run --rm sim python /work/analysis/plot_path.py "$@"
        ;;
    help|*)
        cat <<EOF
Usage: ./run.sh <command> [args]

Commands:
  build           Build the Docker image
  shell           Open an interactive bash shell inside the container
  sitl [...]     Launch sim_vehicle.py inside the container (publishes 14550/udp)
  run [...]      Run scripts/run_scenarios.py inside the container
  plot [...]     Run analysis/plot_path.py inside the container

Examples:
  ./run.sh build
  # Paper §7.3.3 / Fig. 12 reproduction: single-segment mission with the
  # attacker zone in the middle of the track and p_target perpendicular to
  # it, so a_init (Eq. 1) deflects the drone northward off the planned
  # east-bound segment.
  ./run.sh run --zone-circle 45.0000000,11.0040000,80 \\
               --target-latlon 45.0006000,11.0040000 \\
               --ainit-offset-m 30 \\
               --attack-max-runtime-s 90 \\
               --profile tractorbeam
  ./run.sh shell
EOF
        ;;
esac
