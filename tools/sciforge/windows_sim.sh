#!/usr/bin/env bash
# Runs SciForge's Static Stress checks with FreeCAD for Windows (on a Windows machine, in Git
# Bash): the hand calculations (SciForgeTests/headless/sim_benchmarks.py) and the QA's own
# (sim_accuracy_qa.py), meshed by the gmsh.exe and solved by the ccx.exe FreeCAD ships.
#
#   tools/sciforge/windows_sim.sh --stock DIR OUT
#       the official FreeCAD for Windows (downloaded and unpacked into DIR when it is not
#       there yet) with SciForge added as an add-on, like the quick update on Luca's PC
#   tools/sciforge/windows_sim.sh --built DIR OUT
#       a SciForge build unpacked in DIR (SciForge built in, bin/SciForgeCmd.exe)
#
# Writes OUT/sim-benchmarks.json / .md and OUT/sim-accuracy-qa.json / .md; exit 1 when a
# check fails.
#
# Why: Luca runs SciForge on Windows, where the solve goes through other programs (ccx.exe,
# gmsh.exe), other paths and another file system than the Linux tests see.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VERSION="${FREECAD_VERSION:-1.1.4}"
MODE="${1:-}"
DIR="${2:-}"
OUT="${3:-}"
if [ -z "${MODE}" ] || [ -z "${DIR}" ] || [ -z "${OUT}" ]; then
    echo "usage: $0 --stock|--built DIR OUT" >&2
    exit 2
fi
case "${MODE}" in
    --stock | --built) ;;
    *) echo "the first argument must be --stock or --built" >&2; exit 2 ;;
esac

if [ "${MODE}" = "--stock" ] && ! ls "${DIR}"/*/bin/freecadcmd.exe >/dev/null 2>&1; then
    NAME="FreeCAD_${VERSION}-Windows-x86_64-py311.7z"
    echo "[SciForge] downloading ${NAME}"
    mkdir -p "${DIR}"
    curl -fsSL --retry 4 -o "${DIR}/${NAME}" \
        "https://github.com/FreeCAD/FreeCAD/releases/download/${VERSION}/${NAME}"
    7z x -y -o"${DIR}" "${DIR}/${NAME}" >/dev/null
    rm -f "${DIR}/${NAME}"
fi

exe="$(ls "${DIR}"/bin/SciForgeCmd.exe "${DIR}"/*/bin/SciForgeCmd.exe \
    "${DIR}"/bin/freecadcmd.exe "${DIR}"/*/bin/freecadcmd.exe 2>/dev/null | head -1 || true)"
if [ -z "${exe}" ]; then
    echo "[SciForge] no bin/SciForgeCmd.exe or bin/freecadcmd.exe in ${DIR}" >&2
    exit 1
fi
echo "[SciForge] FreeCAD: ${exe}"
ls "$(dirname "${exe}")"/ccx.exe "$(dirname "${exe}")"/gmsh.exe || true

profile="$(mktemp -d)"
trap 'rm -rf "${profile}"' EXIT
if [ "${MODE}" = "--stock" ]; then
    mkdir -p "${profile}/Mod"
    cp -r "${REPO}/src/Mod/SciForge" "${profile}/Mod/SciForge"
fi
mkdir -p "${OUT}"
export FREECAD_USER_HOME="$(cygpath -w "${profile}")"
export SCIFORGE_HEADLESS_OUT="$(cygpath -w "$(cd "${OUT}" && pwd)")"
rm -f "${OUT}/sim-benchmarks.json" "${OUT}/sim-accuracy-qa.json"

failed=0
# run NAME MODULE REPORT PREFIX: one runner; its [SciForge] lines go to the job log, the
# end of its output too when it wrote no report (a start-up error has no [SciForge] in it).
run() {
    local name="$1" module="$2" report="$3" prefix="$4"
    echo "== [SciForge] ${name}"
    "${exe}" -c "from SciForgeTests.headless import ${module}; ${module}.main()" 2>&1 \
        | tr -d '\r' > "${OUT}/${module}.log" || true
    grep -aE "\[SciForge\] ${prefix} (FAIL|summary)" "${OUT}/${module}.log" || true
    if [ ! -f "${OUT}/${report}" ]; then
        echo "[SciForge] no ${report}; the end of FreeCAD's output:"
        tail -n 60 "${OUT}/${module}.log"
    fi
    python - "${OUT}/${report}" <<'EOF' || failed=1
import json
import sys

try:
    report = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception as exc:
    print("[SciForge] no report (FreeCAD or SciForge did not start): %s" % exc)
    sys.exit(1)
sys.exit(0 if report.get("passed") else 1)
EOF
}

run "Static Stress hand calculations" sim_benchmarks sim-benchmarks.json sim
run "Static Stress accuracy (the QA's own hand calculations)" sim_accuracy_qa \
    sim-accuracy-qa.json simqa
exit "${failed}"
