#!/usr/bin/env bash
# Input:  a checkout of this repo (run from anywhere inside it); PYTHON may name the interpreter (default python3)
# Output: runs the verification gate for software/sim and exits non-zero on the first failure
# Must never: modify tracked files, skip the URDF cross-check silently, or be read as hardware validation
#
# The gate, in order:
#   1. the upstream SO-101 URDF is checked out (otherwise the cross-check test would be skipped)
#   2. all simulator unit tests pass, with none skipped
#   3. a headless default run passes --check (nothing unreached, no spray blocked)
#   4. tools/blast-check.sh finds every Python file has its Input/Output/Must never contract
#
# Passing means the simulator agrees with itself and with the URDF. It says nothing about the real
# arm, the airbrush, paint, air pressure or safety; none of that has been measured yet.

set -euo pipefail

PY="${PYTHON:-python3}"
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

URDF="third_party/SO-ARM100/Simulation/SO101/so101_new_calib.urdf"
if [[ ! -f "$URDF" ]]; then
  echo "FAIL: $URDF is missing. Run: git submodule update --init" >&2
  exit 1
fi
echo "ok: upstream URDF present"

echo "== unit tests ($($PY --version 2>&1))"
LOG="$(mktemp)"
trap 'rm -f "$LOG"' EXIT
if ! (cd software/sim && "$PY" -m unittest discover -s tests 2>&1 | tee "$LOG"; exit "${PIPESTATUS[0]}"); then
  echo "FAIL: unit tests" >&2
  exit 1
fi
if grep -q "skipped=" "$LOG"; then
  echo "FAIL: some tests were skipped; the gate needs all of them to run" >&2
  exit 1
fi

echo "== headless run with --check"
(cd software/sim && "$PY" -B -m airbrush_sim run --shape circle --check)

echo "== contracts (tools/blast-check.sh, strict)"
BLAST_STRICT=1 bash tools/blast-check.sh software/sim

echo "verify.sh: all checks passed (simulation only, not hardware)"
