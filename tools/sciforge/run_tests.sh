#!/usr/bin/env bash
# Runs every SciForge test that does not need a full SciForge build:
#   1. unit tests          (plain Python, no FreeCAD)
#   2. golden models       (real FreeCAD, headless)
#   2b. headless AI tools  (every AI tool once, real FreeCAD without a window, every tool
#                           call of the documentation for AI models, and an AI agent
#                           building and checking a part only through MCP)
#   3. GUI smoke test      (real FreeCAD GUI on a virtual screen via xvfb-run)
#
#   2c. simulation benchmarks (Static Stress against hand calculations, real FreeCAD:
#                           SciForgeTests/headless/sim_benchmarks.py, and the QA agent's
#                           own cases, SciForgeTests/headless/sim_accuracy_qa.py)
#
#   tools/sciforge/run_tests.sh [--freecad DIR] [--out DIR]
#                               [--only unit|golden|headless|sim|recognize|gui|scenarios|base]
#                               [--scenario NAME[,NAME...]]   (files of SciForgeTests/gui/
#                                                   scenarios, each in a fresh profile)
#                               [--shard K/N]       (every N-th scenario, from the K-th)
#                               [--repeat N]        (the scenarios N times each)
#                               [--stress]          (on a slow machine on purpose)
#
# --freecad  folder from tools/sciforge/get_freecad.sh (default .sciforge-cache/freecad),
#            an unpacked SciForge AppImage, or a SciForge install prefix containing
#            bin/SciForgeCmd (bin/FreeCADCmd for a build before the branding pass)
# --out      where reports and the screenshot go (default .sciforge-cache/test-output)
# --only     base = everything but the scenarios (unit, golden, headless, sim, smoke, journey)
# --shard    splits the scenarios over N runs (CI runs them side by side): 1/4 runs the
#            1st, 5th, 9th... scenario in name order, 2/4 the 2nd, 6th... (N runs cover all)
# --repeat   runs each scenario N times in a row (a fresh profile each time) and prints how
#            often each passed: a race shows up as a scenario that passes only sometimes
# --stress   the GUI tests on a slow machine on purpose: FreeCAD and its X server pinned to
#            one CPU core (SCIFORGE_STRESS_CPU, default 0) that SCIFORGE_STRESS_LOAD busy
#            loops (default 2) share with them.
#            A scenario that waits for the app's state passes just as well when slow; one
#            that waits a fixed time shows its race here first.
#
# FreeCAD runs with a throw-away user profile, so your own FreeCAD settings are untouched.
set -uo pipefail
LC_COLLATE=C  # the same scenario order everywhere (--shard relies on it)

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FREECAD_DIR="${REPO}/.sciforge-cache/freecad"
OUT="${REPO}/.sciforge-cache/test-output"
ONLY=""
SHARD_INDEX=1
SHARD_COUNT=1
REPEAT=1
STRESS=0
while [ $# -gt 0 ]; do
    case "$1" in
        --freecad) FREECAD_DIR="$2"; shift 2 ;;
        --out) OUT="$2"; shift 2 ;;
        --only) ONLY="$2"; shift 2 ;;
        --scenario) SCENARIO="$2"; ONLY="scenarios"; shift 2 ;;
        --repeat)
            REPEAT="$2"
            if ! [[ "${REPEAT}" =~ ^[0-9]+$ ]] || [ "${REPEAT}" -lt 1 ]; then
                echo "--repeat must be a number of runs, e.g. 3" >&2; exit 2
            fi
            shift 2 ;;
        --stress) STRESS=1; shift ;;
        --shard)
            SHARD_INDEX="${2%/*}"; SHARD_COUNT="${2#*/}"
            if ! [[ "${SHARD_INDEX}" =~ ^[0-9]+$ && "${SHARD_COUNT}" =~ ^[0-9]+$ ]] \
                || [ "${SHARD_INDEX}" -lt 1 ] || [ "${SHARD_INDEX}" -gt "${SHARD_COUNT}" ]; then
                echo "--shard must be K/N with 1 <= K <= N, e.g. 2/4" >&2; exit 2
            fi
            shift 2 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

MODULE="${REPO}/src/Mod/SciForge"
# An absolute FreeCAD folder: the unit tests run from the module folder and start FreeCAD
# themselves (SCIFORGE_FC_CMD), so a relative --freecad (CI passes .sciforge-cache/freecad)
# pointed nowhere there
if [ -d "${FREECAD_DIR}" ]; then FREECAD_DIR="$(cd "${FREECAD_DIR}" && pwd)"; fi
mkdir -p "${OUT}"
OUT="$(cd "${OUT}" && pwd)"
FAILED=()

# Locate FreeCAD: an unpacked AppImage (stock FreeCAD + SciForge as a user add-on)
# or a SciForge install where the module is already built in.
if [ -x "${FREECAD_DIR}/squashfs-root/AppRun" ]; then
    # A SciForge AppImage has sciforgecmd / sciforge (the branding pass), FreeCAD's has
    # freecadcmd / freecad.
    if [ -x "${FREECAD_DIR}/squashfs-root/usr/bin/sciforgecmd" ]; then
        FC_CMD=("${FREECAD_DIR}/squashfs-root/AppRun" sciforgecmd)
        FC_GUI=("${FREECAD_DIR}/squashfs-root/AppRun" sciforge)
    else
        FC_CMD=("${FREECAD_DIR}/squashfs-root/AppRun" freecadcmd)
        FC_GUI=("${FREECAD_DIR}/squashfs-root/AppRun" freecad)
    fi
    # A SciForge AppImage already has the module built in; stock FreeCAD needs the add-on link.
    if [ -d "${FREECAD_DIR}/squashfs-root/usr/Mod/SciForge" ]; then ADDON=0; else ADDON=1; fi
elif ls "${FREECAD_DIR}"/bin/{SciForgeCmd,sciforgecmd,FreeCADCmd,freecadcmd} >/dev/null 2>&1; then
    FC_CMD=("$(ls "${FREECAD_DIR}"/bin/{SciForgeCmd,sciforgecmd,FreeCADCmd,freecadcmd} 2>/dev/null | head -1)")
    FC_GUI=("$(ls "${FREECAD_DIR}"/bin/{SciForge,sciforge,FreeCAD,freecad} 2>/dev/null | head -1)")
    ADDON=0
else
    FC_CMD=()
fi

# Throw-away FreeCAD profiles; with stock FreeCAD, SciForge is linked in as an add-on.
# TEMPLATE is a clean one: every GUI scenario starts from its own fresh copy of it, so
# nothing one scenario leaves behind (window layout, a recovery copy after a kill, a
# selection mode, a preference) can change another (CI #135, #283). PROFILE is the one the
# other tests share (the restart test needs two starts with one profile).
TEMPLATE="$(mktemp -d)"
PROFILE="$(mktemp -d)"
STRESS_PIDS=()
PIN=()
cleanup() {
    rm -rf "${PROFILE}" "${TEMPLATE}"
    [ ${#STRESS_PIDS[@]} -gt 0 ] && kill "${STRESS_PIDS[@]}" 2>/dev/null
    return 0
}
trap cleanup EXIT
for dir in "${TEMPLATE}" "${PROFILE}"; do
    mkdir -p "${dir}/Mod"
    if [ "${ADDON:-0}" = 1 ]; then
        ln -s "${MODULE}" "${dir}/Mod/SciForge"
    fi
done
export FREECAD_USER_HOME="${PROFILE}"
# The same virtual screen, fonts and Qt settings as on CI (tools/sciforge/gui_env.sh)
# shellcheck source=gui_env.sh
source "${REPO}/tools/sciforge/gui_env.sh"
# No test goes online: the update check (sciforge/update_core.py) refuses every address but
# this computer's own (the tests' fake GitHub), and does not even start by itself.
export SCIFORGE_NO_INTERNET=1
# The unit tests that check geometry against FreeCAD's exact solids run FreeCAD headless
# themselves (SciForgeTests/unit/test_live_shapes_freecad.py); skipped without it.
if [ ${#FC_CMD[@]} -gt 0 ]; then
    export SCIFORGE_FC_CMD="$(printf '%q ' "${FC_CMD[@]}")"
fi

run_unit() {
    echo "== [SciForge] unit tests"
    (cd "${MODULE}" && python3 -m unittest discover -s SciForgeTests/unit -v) > "${OUT}/unit.log" 2>&1
    local rc=$?
    tail -3 "${OUT}/unit.log"
    if [ $rc -ne 0 ]; then
        # The failures themselves, so a CI log says which test failed and why
        sed -n '/^======/,/^Ran [0-9]* tests/p' "${OUT}/unit.log" | head -200
        FAILED+=("unit")
    fi
}

need_freecad() {
    if [ ${#FC_CMD[@]} -eq 0 ]; then
        echo "FreeCAD not found in ${FREECAD_DIR}. Run tools/sciforge/get_freecad.sh first." >&2
        FAILED+=("$1 (no FreeCAD)")
        return 1
    fi
}

run_golden() {
    echo "== [SciForge] golden models"
    need_freecad golden || return
    SCIFORGE_GOLDEN_OUT="${OUT}" "${FC_CMD[@]}" -c \
        "from SciForgeTests.golden import runner; runner.main()" > "${OUT}/golden.log" 2>&1
    grep -aoE "\[SciForge\] golden (FAIL|ERROR|XFAIL|XPASS|summary).*" "${OUT}/golden.log"
    python3 - "${OUT}/golden-report.json" <<'EOF' || FAILED+=("golden")
import json, sys
try:
    report = json.load(open(sys.argv[1]))
except Exception as exc:
    print("no golden report: %s" % exc); sys.exit(1)
sys.exit(0 if report.get("passed") else 1)
EOF
}

# Every AI tool called once in real FreeCAD without a window (SciForgeTests/headless).
run_headless() {
    echo "== [SciForge] headless AI tools"
    need_freecad headless || return
    SCIFORGE_HEADLESS_OUT="${OUT}" timeout 1200 "${FC_CMD[@]}" -c \
        "from SciForgeTests.headless import runner; runner.main()" > "${OUT}/headless.log" 2>&1
    grep -aoE "\[SciForge\] headless (FAIL|MISSING|summary).*" "${OUT}/headless.log"
    python3 - "${OUT}/headless-report.json" <<'EOF2' || FAILED+=("headless")
import json, sys
try:
    report = json.load(open(sys.argv[1]))
except Exception as exc:
    print("no headless report: %s" % exc); sys.exit(1)
sys.exit(0 if report.get("passed") else 1)
EOF2
    # Every tool call shown in the documentation for AI models, and every tool's reference
    # example, run in real FreeCAD (SciForgeTests/headless/docs_runner.py).
    echo "== [SciForge] documentation examples (headless)"
    SCIFORGE_HEADLESS_OUT="${OUT}" timeout 1200 "${FC_CMD[@]}" -c \
        "from SciForgeTests.headless import docs_runner; docs_runner.main()" > "${OUT}/docs.log" 2>&1
    grep -aoE "\[SciForge\] docs (FAIL|summary).*" "${OUT}/docs.log"
    python3 - "${OUT}/docs-report.json" <<'EOF3' || FAILED+=("docs examples")
import json, sys
try:
    report = json.load(open(sys.argv[1]))
except Exception as exc:
    print("no docs report: %s" % exc); sys.exit(1)
sys.exit(0 if report.get("passed") else 1)
EOF3
    # An AI agent builds a part and checks it only through MCP, as an AI app does
    # (tools/sciforge/sciforge-cli mcp --headless; SciForgeTests/headless/agent_e2e.py).
    echo "== [SciForge] AI agent end to end (MCP, headless)"
    SCIFORGE_FREECAD="${FREECAD_DIR}" SCIFORGE_CLI_PROFILE="${PROFILE}" timeout 900 python3 \
        "${MODULE}/SciForgeTests/headless/agent_e2e.py" --out "${OUT}" \
        > "${OUT}/agent-e2e.log" 2>&1 || FAILED+=("agent e2e")
    grep -aoE "\[SciForge\] agent (FAIL|summary).*" "${OUT}/agent-e2e.log"
    # --- at-tools (beta 3): Auto Timeline, parts without a timeline rebuilt only through the
    # AI tools, in-process and through the real MCP server (SciForgeTests/headless/rebuild_e2e.py)
    echo "== [SciForge] Auto Timeline end to end (headless)"
    SCIFORGE_HEADLESS_OUT="${OUT}" timeout 900 "${FC_CMD[@]}" -c \
        "from SciForgeTests.headless import rebuild_e2e; rebuild_e2e.main()" \
        > "${OUT}/rebuild-e2e.log" 2>&1
    grep -aoE "\[SciForge\] rebuild (FAIL|summary).*" "${OUT}/rebuild-e2e.log"
    python3 - "${OUT}/rebuild-e2e-report.json" <<'EOF_REBUILD' || FAILED+=("rebuild e2e")
import json, sys
try:
    report = json.load(open(sys.argv[1]))
except Exception as exc:
    print("no rebuild report: %s" % exc); sys.exit(1)
sys.exit(0 if report.get("passed") else 1)
EOF_REBUILD
    SCIFORGE_FREECAD="${FREECAD_DIR}" SCIFORGE_CLI_PROFILE="${PROFILE}" timeout 900 python3 \
        "${MODULE}/SciForgeTests/headless/rebuild_e2e.py" --mcp --out "${OUT}" \
        > "${OUT}/rebuild-mcp.log" 2>&1 || FAILED+=("rebuild e2e (MCP)")
    grep -aoE "\[SciForge\] rebuild-mcp (FAIL|summary).*" "${OUT}/rebuild-mcp.log"
    run_recognize  # (at-recognize, beta 3: part of --only headless and base)
}

# Auto Timeline (beta 3, at-recognize): parts built, sent through STEP / STL and back,
# described by sciforge/recognize.py, rebuilt from the plan by the headless AI executor and
# compared (SciForgeTests/headless/recognize_bench.py). Also --only recognize on its own.
run_recognize() {
    echo "== [SciForge] Auto Timeline recognition (headless)"
    need_freecad recognize || return
    SCIFORGE_RECOGNIZE_OUT="${OUT}" timeout 1200 "${FC_CMD[@]}" -c \
        "from SciForgeTests.headless import recognize_bench; recognize_bench.main()" \
        > "${OUT}/recognize.log" 2>&1
    grep -aoE "\[SciForge\] recognize (FAIL|summary).*" "${OUT}/recognize.log"
    python3 - "${OUT}/recognize-report.json" <<'EOF4' || FAILED+=("recognize")
import json, sys
try:
    report = json.load(open(sys.argv[1]))
except Exception as exc:
    print("no recognize report: %s" % exc); sys.exit(1)
sys.exit(0 if report.get("passed") else 1)
EOF4
}

# The Static Stress engine against hand calculations (beta 3, sim-core): every case at the
# default mesh and a finer one (SciForgeTests/headless/sim_benchmarks.py).
run_sim() {
    echo "== [SciForge] simulation benchmarks"
    need_freecad sim || return
    SCIFORGE_HEADLESS_OUT="${OUT}" OMP_NUM_THREADS=1 timeout 1500 "${FC_CMD[@]}" -c \
        "from SciForgeTests.headless import sim_benchmarks; sim_benchmarks.main()" > "${OUT}/sim.log" 2>&1
    grep -aoE "\[SciForge\] sim (FAIL|summary).*" "${OUT}/sim.log"
    python3 - "${OUT}/sim-benchmarks.json" <<'EOF4' || FAILED+=("sim")
import json, sys
try:
    report = json.load(open(sys.argv[1]))
except Exception as exc:
    print("no simulation report: %s" % exc); sys.exit(1)
sys.exit(0 if report.get("passed") else 1)
EOF4
    # The QA agent's own hand calculations and wrong-without-a-word checks (beta 3 QA,
    # SciForgeTests/headless/sim_accuracy_qa.py), through the engine and the AI tools.
    echo "== [SciForge] simulation accuracy (QA's own hand calculations)"
    SCIFORGE_HEADLESS_OUT="${OUT}" OMP_NUM_THREADS=1 timeout 1500 "${FC_CMD[@]}" -c \
        "from SciForgeTests.headless import sim_accuracy_qa; sim_accuracy_qa.main()" > "${OUT}/sim-qa.log" 2>&1
    grep -aoE "\[SciForge\] simqa (FAIL|summary).*" "${OUT}/sim-qa.log"
    python3 - "${OUT}/sim-accuracy-qa.json" <<'EOF5' || FAILED+=("sim accuracy")
import json, sys
try:
    report = json.load(open(sys.argv[1]))
except Exception as exc:
    print("no simulation accuracy report: %s" % exc); sys.exit(1)
sys.exit(0 if report.get("passed") else 1)
EOF5
}

# run_gui_script NAME SCRIPT LOG RESULT: one GUI test in a real FreeCAD window.
run_gui_script() {
    local name="$1" script="$2" log="$3" result="$4"
    rm -f "${OUT}/${result}"
    SCIFORGE_SMOKE_OUT="${OUT}" timeout 300 xvfb-run -a -s "${SCIFORGE_XVFB_ARGS}" \
        "${FC_GUI[@]}" "${MODULE}/SciForgeTests/gui/${script}" > "${OUT}/${log}" 2>&1
    grep -aoE "\[SciForge\] ${name} .*" "${OUT}/${log}"
    # A Python error that FreeCAD only printed (e.g. inside a Qt callback) is still a failure.
    if grep -aq "Traceback (most recent call last)" "${OUT}/${log}"; then
        echo "Python errors in ${log}:"
        grep -a -A 6 "Traceback (most recent call last)" "${OUT}/${log}" | head -40
        FAILED+=("gui ${name} (Python errors in log)")
    fi
    python3 - "${OUT}/${result}" "${log}" <<'EOF' || FAILED+=("gui ${name}")
import json, sys
try:
    result = json.load(open(sys.argv[1]))
except Exception as exc:
    print("no GUI result (FreeCAD may have crashed; see %s): %s" % (sys.argv[2], exc)); sys.exit(1)
sys.exit(0 if result.get("passed") else 1)
EOF
}

run_gui() {
    run_gui_base && run_scenarios
}

# The GUI smoke test and the journey (not the scenarios).
run_gui_base() {
    echo "== [SciForge] GUI tests"
    need_freecad gui || return
    if ! command -v xvfb-run >/dev/null; then
        echo "xvfb-run not installed; skipping GUI tests" >&2
        FAILED+=("gui (no xvfb-run)")
        return 1
    fi
    run_gui_script smoke smoke_gui.py gui.log result.json
    # The journey uses SciForge like a person: real clicks and drags on the 3D view.
    run_gui_script journey journey_gui.py journey.log journey-result.json
    # FreeCAD opened twice with one profile: the second start restores the window layout the
    # first one saved, after SciForge is on (Luca, 2026-10-17: only the browser was left)
    local phase
    for phase in 1 2; do
        SCIFORGE_RESTART_PHASE="${phase}" run_gui_script restart restart_gui.py \
            "restart-${phase}.log" "restart-${phase}.json"
    done
    return 0
}

# Scenario tests (SciForgeTests/gui/scenarios/*.py, see harness.py): each one a
# person's workflow with real input; any error FreeCAD prints fails it.
#
# run_one_scenario FILE NAME OUTDIR LABEL: one run in a fresh profile; 0 when it passed.
run_one_scenario() {
    local file="$1" name="$2" out="$3" label="$4" profile rc=0 marker left
    mkdir -p "${out}"
    profile="$(mktemp -d)"
    cp -a "${TEMPLATE}/." "${profile}/"
    # Through the launcher: a scenario that does not even load fails at once instead of
    # leaving FreeCAD open until the timeout. The harness ends a stuck step itself (with
    # what was on screen) long before this 15-minute kill.
    FREECAD_USER_HOME="${profile}" SCIFORGE_SCENARIO="${name}" SCIFORGE_SCENARIO_FILE="${file}" \
        SCIFORGE_SMOKE_OUT="${out}" \
        timeout 900 "${PIN[@]}" xvfb-run -a -s "${SCIFORGE_XVFB_ARGS}" \
        "${FC_GUI[@]}" "${MODULE}/SciForgeTests/gui/scenario_launcher.py" \
        > "${out}/scenario-${name}.log" 2>&1
    # what failed, step by step, in the job log; on CI also as ::error:: lines and in the
    # job summary, so the run page names the broken scenario without an artifact download
    python3 "${REPO}/tools/sciforge/scenario_result.py" "${out}" "${name}" \
        ${label:+--attempt "${label}"} || rc=1
    # A FreeCAD that did not end cleanly (a crash at exit after the checks passed, or a
    # kill) leaves SciForge's crash marker in its profile: name the scenario and keep the
    # marker, its crash log and SciForge's recovery copies with the reports.
    for marker in "${profile}"/SciForge/crash/running-*.json; do
        [ -e "${marker}" ] || continue
        left="${out}/crash-left-by-${name}"
        mkdir -p "${left}"
        mv "${marker}" "${left}/"
        marker="$(basename "${marker}" .json)"
        mv "${profile}/SciForge/crash/session-${marker#running-}.log" "${left}/" 2>/dev/null || true
        # what Python's faulthandler wrote (the stack at a crash), in the job's own log
        if [ -s "${left}/session-${marker#running-}.log" ]; then
            head -n 80 "${left}/session-${marker#running-}.log" | cut -c1-300 | sed 's/^/    ! /'
        fi
        if compgen -G "${profile}/SciForge/recovery/*" > /dev/null; then
            mkdir -p "${left}/recovery"
            mv "${profile}"/SciForge/recovery/* "${left}/recovery/" 2>/dev/null || true
        fi
        echo "  FAIL ${name}: FreeCAD did not end cleanly (SciForge's crash marker was left; see ${left})"
        if [ -n "${GITHUB_ACTIONS:-}" ]; then
            echo "::error title=Scenario ${name}::FreeCAD did not end cleanly (crash marker left; see ${left#"${OUT}"/} in the test-output artifact)"
        fi
        rc=2
    done
    rm -rf "${profile}"
    return "${rc}"
}

# --stress: FreeCAD and its X server share CPU core 0 with busy loops
start_stress() {
    PIN=()
    [ "${STRESS}" = 1 ] || return 0
    if ! command -v taskset >/dev/null; then
        echo "--stress needs taskset (util-linux)" >&2
        exit 2
    fi
    local i cpu="${SCIFORGE_STRESS_CPU:-0}"
    for i in $(seq 1 "${SCIFORGE_STRESS_LOAD:-2}"); do
        taskset -c "${cpu}" python3 -c 'while True: pass' &
        STRESS_PIDS+=($!)
    done
    PIN=(taskset -c "${cpu}")
    # FreeCAD gets about 1 / (loops + 1) of the core: speed limits in checks scale by it
    export SCIFORGE_SLOWDOWN=$(( ${#STRESS_PIDS[@]} + 1 ))
    echo "== [SciForge] stress: FreeCAD pinned to CPU ${cpu} with ${#STRESS_PIDS[@]} busy loops"
}

stop_stress() {
    if [ ${#STRESS_PIDS[@]} -gt 0 ]; then
        kill "${STRESS_PIDS[@]}" 2>/dev/null
        wait "${STRESS_PIDS[@]}" 2>/dev/null
        STRESS_PIDS=()
    fi
    return 0
}

run_scenarios() {
    echo "== [SciForge] GUI scenarios"
    need_freecad scenarios || return
    local dir="${MODULE}/SciForgeTests/gui/scenarios" file name index=0 round rc
    local -a chosen=()
    for file in "${dir}"/*.py; do
        name="$(basename "${file}" .py)"
        [ "${name}" = "__init__" ] && continue
        index=$((index + 1))
        [ $(((index - 1) % SHARD_COUNT + 1)) -ne "${SHARD_INDEX}" ] && continue
        # --scenario a,b,c: those, in name order
        [ -n "${SCENARIO:-}" ] && [[ ",${SCENARIO}," != *",${name},"* ]] && continue
        chosen+=("${file}")
    done
    start_stress
    if [ "${REPEAT}" -gt 1 ]; then
        # every scenario REPEAT times, round after round (as REPEAT CI runs would), each run
        # in its own folder; then each scenario's pass count
        declare -A passes=()
        for round in $(seq 1 "${REPEAT}"); do
            echo "== [SciForge] round ${round} of ${REPEAT}"
            for file in "${chosen[@]}"; do
                name="$(basename "${file}" .py)"
                if run_one_scenario "${file}" "${name}" "${OUT}/run-${round}" "run ${round} of ${REPEAT}"; then
                    passes[${name}]=$(( ${passes[${name}]:-0} + 1 ))
                else
                    passes[${name}]=${passes[${name}]:-0}
                fi
            done
        done
        echo "== [SciForge] passes in ${REPEAT} runs"
        local table=("| Scenario | Passed |" "|---|---|")
        for file in "${chosen[@]}"; do
            name="$(basename "${file}" .py)"
            echo "  ${name}: ${passes[${name}]} of ${REPEAT}"
            table+=("| ${name} | ${passes[${name}]} of ${REPEAT} |")
            [ "${passes[${name}]}" -lt "${REPEAT}" ] && FAILED+=("scenario ${name} (${passes[${name}]} of ${REPEAT})")
        done
        if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
            {
                echo "#### Scenario passes in ${REPEAT} runs$([ "${STRESS}" = 1 ] && echo ' (under --stress)')"
                echo
                printf '%s\n' "${table[@]}"
                echo
            } >> "${GITHUB_STEP_SUMMARY}"
        fi
    else
        for file in "${chosen[@]}"; do
            name="$(basename "${file}" .py)"
            run_one_scenario "${file}" "${name}" "${OUT}" ""
            rc=$?
            [ "${rc}" -eq 0 ] && continue
            # Once more in a fresh profile, only to say FLAKY (passes the second time: a race
            # in the test or the app to fix) or FAILED (fails twice). The job stays red
            # either way: a retry never turns a scenario green.
            echo "  ${name}: once more in a fresh profile, to tell a flaky test from a failing one"
            if run_one_scenario "${file}" "${name}" "${OUT}/second-run" "second run"; then
                echo "  ${name}: FLAKY (failed, then passed)"
                FAILED+=("scenario ${name} (FLAKY: failed, then passed)")
                [ -n "${GITHUB_STEP_SUMMARY:-}" ] && echo "**FLAKY** \`${name}\`: failed, then passed in a fresh profile. A race to fix; the job stays red." >> "${GITHUB_STEP_SUMMARY}"
            else
                echo "  ${name}: FAILED (twice)"
                FAILED+=("scenario ${name} (FAILED twice)")
                [ -n "${GITHUB_STEP_SUMMARY:-}" ] && echo "**FAILED** \`${name}\`: failed twice." >> "${GITHUB_STEP_SUMMARY}"
            fi
        done
    fi
    stop_stress
}

case "${ONLY}" in
    unit) run_unit ;;
    golden) run_golden ;;
    headless) run_headless ;;
    sim) run_sim ;;
    recognize) run_recognize ;;
    gui) run_gui ;;
    scenarios) run_scenarios ;;
    base) run_unit; run_golden; run_headless; run_sim; run_gui_base ;;
    "") run_unit; run_golden; run_headless; run_sim; run_gui ;;
    *) echo "--only must be unit, golden, headless, sim, recognize, gui, scenarios or base" >&2; exit 2 ;;
esac

echo "== [SciForge] reports in ${OUT}"
if [ ${#FAILED[@]} -gt 0 ]; then
    echo "== [SciForge] FAILED: ${FAILED[*]}"
    if [ -n "${GITHUB_ACTIONS:-}" ]; then
        # The parts that are not scenarios (their own ::error:: lines came with them) named
        # on the run page too; the job summary gets the whole list.
        for part in "${FAILED[@]}"; do
            case "${part}" in scenario*) ;; *) echo "::error title=SciForge tests::${part} failed (its log is in the job output above)" ;; esac
        done
        if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
            {
                echo "#### Failed in this part"
                echo
                for part in "${FAILED[@]}"; do echo "- ${part}"; done
                echo
            } >> "${GITHUB_STEP_SUMMARY}"
        fi
    fi
    exit 1
fi
echo "== [SciForge] all passed"
