#!/usr/bin/env bash
# Run one Cooja scenario headless and collect its log.
# Usage: scripts/run_scenario.sh simulations/<scenario>.csc [outdir]
# Requires a ScriptRunner plugin inside the .csc with a TIMEOUT and log.log().
set -euo pipefail
CSC="${1:?usage: run_scenario.sh <file.csc> [outdir]}"
OUT="${2:-logs}"
NAME="$(basename "${CSC%.csc}")"
mkdir -p "$OUT"
COOJA_JAR="${CNG_PATH}/tools/cooja/build/libs/cooja.jar"
[ -f "$COOJA_JAR" ] || { echo "cooja.jar missing; run ./run.sh build" >&2; exit 1; }
cd "$(dirname "$CSC")"
java -Djava.awt.headless=true -jar "$COOJA_JAR" --no-gui="$(basename "$CSC")" \
    --contiki="$CNG_PATH" 2>&1 | tee "../$OUT/$NAME.cooja.out"
# Cooja writes COOJA.testlog next to the .csc when the script calls log.log().
[ -f COOJA.testlog ] && mv COOJA.testlog "../$OUT/$NAME.log"
echo "log written to $OUT/$NAME.log"
