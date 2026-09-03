#!/usr/bin/env bash
# Run one Cooja scenario headless and collect its logs.
#
# Usage: scripts/run_scenario.sh <file.csc> [seed] [outdir]
#   seed    Cooja random seed (default: the one stored in the .csc)
#   outdir  where logs go (default: logs/)
#
# Output: <outdir>/<scenario>[-s<seed>].log   the control script's log.log() lines
#         <outdir>/<scenario>[-s<seed>].cooja.out  Cooja's own console output
# Exit code is Cooja's: 0 when the control script called log.testOK().
set -euo pipefail
CSC="${1:?usage: run_scenario.sh <file.csc> [seed] [outdir]}"
SEED="${2:-}"
OUT="${3:-logs}"
: "${CONTIKI_NG:?CONTIKI_NG must point to the Contiki-NG tree (set by the image)}"

COOJA_JAR="${CONTIKI_NG}/tools/cooja/build/libs/cooja.jar"
[ -f "$COOJA_JAR" ] || { echo "cooja.jar missing; run ./run.sh build" >&2; exit 1; }

NAME="$(basename "${CSC%.csc}")"
[ -n "$SEED" ] && NAME="${NAME}-s${SEED}"
mkdir -p "$OUT"
LOGDIR="$(mktemp -d "$OUT/.run-${NAME}.XXXX")"

ARGS=(--no-gui --contiki="$CONTIKI_NG" --logdir="$LOGDIR")
[ -n "$SEED" ] && ARGS+=(--random-seed="$SEED")

set +e
java -Djava.awt.headless=true -jar "$COOJA_JAR" "${ARGS[@]}" "$(realpath "$CSC")" \
    > "$OUT/$NAME.cooja.out" 2>&1
RC=$?
set -e

if [ -f "$LOGDIR/COOJA.testlog" ]; then
  mv "$LOGDIR/COOJA.testlog" "$OUT/$NAME.log"
else
  echo "no COOJA.testlog produced; see $OUT/$NAME.cooja.out" >&2
fi
rm -rf "$LOGDIR"
echo "cooja exit=$RC  log=$OUT/$NAME.log  console=$OUT/$NAME.cooja.out"
exit $RC
