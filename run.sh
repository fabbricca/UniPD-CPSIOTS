#!/usr/bin/env bash
# Thin wrapper around docker compose, mirroring the drone-spoofing project.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

cmd="${1:-help}"; shift || true

case "$cmd" in
    build)   exec docker compose build "$@" ;;
    shell)   exec docker compose run --rm sim /bin/bash "$@" ;;
    version) exec docker compose run --rm sim cat /opt/VERSION.txt ;;
    make)    exec docker compose run --rm sim make -C firmware "$@" ;;
    cooja)   # GUI Cooja. Needs `xhost +local:docker` on the host first.
             exec docker compose run --rm sim \
                 bash -c 'cd $CONTIKI_NG/tools/cooja && ./gradlew --no-daemon run' ;;
    sim)     # Headless run: ./run.sh sim simulations/xxx.csc [seed]
             exec docker compose run --rm sim scripts/run_scenario.sh "$@" ;;
    test)    exec docker compose run --rm sim python -m pytest tests "$@" ;;
    gen)     exec docker compose run --rm sim python scripts/gen_scenario.py "$@" ;;
    parse)   exec docker compose run --rm sim python scripts/parse_logs.py "$@" ;;
    help|*)
        cat <<USAGE
Usage: ./run.sh <command> [args]

  build          Build the Docker image (clones pinned Contiki-NG, builds Cooja)
  version        Print the recorded toolchain/Contiki-NG versions
  shell          Interactive shell inside the container
  make [...]     Run make in rpl-ids/ inside the container (e.g. make TARGET=cooja)
  cooja          Launch the Cooja GUI (X11)
  sim <csc>      Run a Cooja scenario headless via scripts/run_scenario.sh
  test           Run host-side Python tests
  gen [...]      Generate a scenario (scripts/gen_scenario.py)
  parse <log>    Parse a run log into results/ CSVs (scripts/parse_logs.py)
USAGE
        ;;
esac
