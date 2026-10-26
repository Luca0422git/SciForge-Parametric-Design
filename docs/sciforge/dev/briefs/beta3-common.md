## Beta 3 (2026-10-26): Static Stress simulation, Auto Timeline, VEX assemblies. Rules for every builder

Luca (2026-10-26): "Auto Timeline and Sim is what you will work on. timeline and sim will be beta
3", then "put the vex stuff in beta 3. youre on max effort so make this count. one shot for beta
3." The plan is `docs/sciforge/plan-beta3.md`; the spec changed for simulation (outline 7.18:
**Static Stress only**; flow, thermal, modal, buckling, nonlinear, event and optimization stay
out). A separate Claude session builds patch 0.1.0-beta.2.2 (joint delete bug, drag-to-set joint
limits, hover ghost of hidden bodies, diagonal fillet arrows) on `develop` at the same time: stay
out of those four (`docs/sciforge/dev/briefs/patch-beta2.2.md` says what they touch).

Read first, in this order: `docs/sciforge/dev/briefs/common.md` (every rule there applies,
except where this file says otherwise), this file, your own brief, the plan, the research files
your brief names (Fusion's behaviour with sources: the source of truth for what to build), and
`docs/sciforge/dev/research/integration-map.md` (how a tab, a step, an icon and a test plug into
SciForge, with file:line; written for wave 6 but still right).

### Six builders at the same time

| Builder | Branch | Owns (only it edits these) |
|---|---|---|
| sim-core | `sf/sim-core` | `simulation_core.py`, `simulation.py` (the engine: already working for Fixed, Force, Pressure, gravity, several bodies, Gmsh + CalculiX; extend it), `ai/catalog/simulate_tools.py`, `ai/actions/simulate_actions.py`, `SciForgeTests/headless/sim_benchmarks.py`, `test_simulation_core.py`, `parity/simulation.md` sections "Engine" and "Benchmarks" |
| sim-ui | `sf/sim-ui` | `simulation_ui.py` (commands, dialogs, the workspace switch), `simulation_glyphs.py`, `simulation_browser.py`, the SETUP tab's lines in `ribbon_config.py`, `set_simulation_mode` in `ribbon_ui.py`, `icons_simulation.py`, `parity/simulation.md` section "Setup" |
| sim-results | `sf/sim-results` | `simulation_results*.py`, the RESULTS tab's lines in `ribbon_config.py`, `icons_simresults.py`, `parity/simulation.md` section "Results" |
| at-recognize | `sf/at-recognize` | `recognize_core.py`, `recognize.py`, `recognize_mesh.py`, `test_recognize_core.py`, `SciForgeTests/headless/recognize_bench.py`, `parity/auto-timeline.md` section "Recognition" |
| at-tools | `sf/at-tools` | `rebuild.py`, `rebuild_ui.py`, `ai/catalog/rebuild_tools.py`, `ai/actions/rebuild_actions.py`, `docs/ai/recipes/reverse-engineer.md` + the handbook / troubleshooting sections it adds, `SciForgeTests/headless/rebuild_e2e.py`, `icons_rebuild.py`, `parity/auto-timeline.md` (all but "Recognition") |
| vex | `sf/vex` | the loop-centre snaps in `joints.py` (`_shape_snaps` and helpers) and `align.py` (`snap_points`), bulk insert in `insert_ui.py` / `step_import.py` / `exchange_ui.py` / `data_panel*.py`, speed changes where a big assembly is slow (any file, smallest change that works, each with a measured before / after), `SciForgeTests/fixtures/vex/` (the generator), `icons_vex.py`, `parity/vex-assembly.md` |

- **Shared files** (several builders touch them; change only your own lines, never reformat
  others'): `ribbon_config.py`, `ribbon_ui.py`, `browser_core.py`, `browser_ui.py`,
  `ai/catalog/__init__.py` and `ai/actions/__init__.py` (the scaffold already imports every new
  module), `SciForgeTests/headless/runner.py` (append your own block at the END of the sessions
  list, headed `# --- <builder> ---`), `docs/sciforge/known-issues.md`, `CHANGELOG.md` (do not
  edit these two: the orchestrator writes them from your reports).
- **Reusing a sibling's work in progress:** worktrees share one repository, so a sibling's branch
  is visible. You may `git merge sf/<sibling>` into your branch when you need code it has
  committed (sim-ui and sim-results need sim-core's newer engine; at-tools needs at-recognize's
  `recognize.describe`). Never commit to a sibling's branch, never rebase, never force.
- **Contracts (on the base commit, written by the orchestrator):** `simulation.py` /
  `simulation_core.py` (the engine and its API: study, items, materials, `Job`, `solve`,
  `results`, `summary`, `out_of_date`), `recognize.py` (`describe(shape, options)` returns the
  dict documented there; at-recognize fills it in), `rebuild.py` (the reference and compare API;
  at-tools fills it in). sim-ui / sim-results only *call* the engine; if they need something in it,
  they ask in their report and add a thin helper in their own files meanwhile (sim-core may then
  move it). Never rename or remove what a contract defines.
- **Ribbon:** the scaffold added the SIMULATION workspace's SETUP and RESULTS tabs with every
  command present but greyed (`None`) and an `# owner:` comment. Wire your own lines (command
  name, icon, note); keep Fusion's order.
- **Icons:** in your own `tools/sciforge/icons_<area>.py` (see wave6-common's rules: never edit
  make_icons.py; run `python3 tools/sciforge/make_icons.py`; commit only your new `.svg`).
- **Scenarios:** `SciForgeTests/gui/scenarios/<area>_*.py` with real clicks; helpers in your own
  `SciForgeTests/gui/<area>_steps.py`.
- **FreeCAD 1.1.4** is unpacked at `/home/user/fc/freecad` (with CalculiX, Gmsh, Netgen, VTK):
  pass `--freecad /home/user/fc/freecad`; do not download another copy. Use your own `--out`
  folder under your worktree's `.sciforge-cache/`.
- **Machine:** 4 CPUs shared by six builders. Run one FreeCAD at a time in your worktree; a
  scenario that times out is re-run alone before you conclude anything. CalculiX uses several
  threads: in tests set `OMP_NUM_THREADS=1` unless you measure speed.
- **Web:** WebFetch cannot reach any host from the sandbox; WebSearch works (excerpts only) and
  the budget is shared: at most 25 searches per builder; the research files already hold most of
  what you need.
- **Time:** check `date -u`. Commit working increments at least every hour (a builder that runs
  out of time must leave a branch that passes its tests). **Stop building at 02:30 UTC
  (2026-10-27)**: from then on only finish tests, docs and the report; be done by 03:15 UTC.
- **Scope honesty:** build everything your brief lists. Where FreeCAD, OpenCASCADE, Gmsh or
  CalculiX cannot do what Fusion does, build the closest honest behaviour, refuse the rest in the
  dialog with the reason, and list it in your parity doc's Known gaps with the evidence. Never
  ship a silent wrong result: a stress number that is wrong is worse than no number.
- **Never let FreeCAD print an error** in a normal flow: the GUI test harness fails a scenario on
  any Report-view error (FreeCAD's FEM tools print errors for situations they then handle; the
  engine already avoids two of them, see the comments in `simulation.py`).
- Your session log goes to `docs/sciforge/sessions/beta3-<builder>.md` (never MEMORY.md).
- Report (your final message): branch, commits, every command / tool you built with its options,
  each scenario and test with its check count and PASS/FAIL, gaps with reasons, and a
  plain-language "how to use it" for Luca (a beginner).
