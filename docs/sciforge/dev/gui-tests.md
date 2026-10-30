# GUI scenario tests: wait for the app, never for the clock

The GUI scenarios (`src/Mod/SciForge/SciForgeTests/gui/scenarios/*.py`) use SciForge like a
person: real clicks, drags and keys in a real FreeCAD window on a virtual screen. They must pass
when SciForge works and fail only when something in SciForge is broken, the same way on Luca's
machine, in a Claude sandbox and on GitHub Actions.

Until October 2026 they were paced by a clock: each step waited a fixed `wait_ms` (700 ms by
default, about 2,150 explicit waits). On a slower runner a step that needed 1.6 s got 1.5 s and
the next click landed on the wrong state; every red CI run turned up a new flake in a different
scenario (CI #277 to #287). This page is how they work now. The brief that started it:
"SciForge GUI tests: rework brief for Claude Code" (Luca, 2026-10-27).

## The rules

1. **Wait for state, never for time.** Before each input, wait until the app shows the state
   that input needs (the dialog is open, the menu has lit the entry, nothing is recomputing).
   No new `wait_ms`, `qWait(n)`, `singleShot(n, ...)` or `time.sleep` used as a delay.
   (`singleShot(0, fn)` is not a delay: fn runs once the current handler returns, to click
   inside a menu's own loop. A pause that is the thing tested, or the pace of a hand, says so
   on its line: `# input pace: ...` or `# on purpose: ...`; `check_waits.py` does not count
   those.)
2. **Timeouts only catch hangs.** Every wait has a generous bound (30 s, longer for a solve).
   Reaching it means something is broken. Never lower one to go faster, never raise one to pass.
3. **Check after the input, by state.** Wait for the input's effect, then look.
4. **Input reaches the app before the next input.** A pointer move is complete when Qt has been
   told of it (`h.pointer_to` waits for that).
5. **A failure says what it waited for**, with what was on screen instead and a screenshot; open
   menus and modal dialogs are closed and the scenario stops in seconds.
6. **Every scenario starts from a clean profile** (`run_tests.sh` copies one for each run).
7. **Same environment everywhere** (`tools/sciforge/gui_env.sh`).
8. **Retries diagnose, they never pass a test.** A failed scenario runs once more in a fresh
   profile only to label it FLAKY (failed, then passed: a race to fix) or FAILED (twice). The
   job stays red either way.
9. **Never skip, disable or loosen a check to get green.** If a check is wrong, fix what it
   checks and say why in the commit.

## How a scenario waits

```python
from SciForgeTests.gui import harness as h

def open_offset():
    st.menu("CREATE", "Offset")
open_offset.done = lambda: st.panel() is not None      # what proves the step worked
open_offset.done_what = "the Offset dialog is open"    # how the failure names it

def solve():
    ui.click(solve_button)
solve.done = lambda: job.finished()
solve.timeout_s = 600                                  # a solve: a longer bound, said once

h.run("my_scenario", [new_design, open_offset, solve, ...], paced_by="state")
```

- `paced_by="state"`: a converted scenario. Each step starts once the app has **settled** after
  the step before and its own `step.ready` holds; the next step starts once `step.done` holds and
  the app has settled again. A scenario without it (`paced_by="timer"`, the default for the ones
  not converted yet) waits each step's fixed `wait_ms` as before.
- Inside a step: `h.wait_for(condition, "what it is")`, `h.settle()`, `h.view_still()` (two
  frames in a row show the same view: after a fit, before a pixel is computed; `h.fit()` waits
  for it), and for something that
  opens and runs its own loop (a menu, a modal dialog) `h.when(condition, action, "what")` set up
  before the call that opens it. A step that only waits for a long operation (inserting
  twenty parts, a solve) says so once with `step.timeout_s`. Menus: `h.choose_from(open_it, path, "the X menu")`,
  `h.choose_path(menu, path)`, `h.light_entry(menu, action)`. The 3D view:
  `h.view_drawn()` (FreeCAD's sketch finds what is under the pointer when it redraws).
- **Settled** (`h.busy()` lists why not): no design recomputing, no input still being played
  (`h.BUSY`), no dialog searching for a value limit, no work SciForge posted for a moment later
  (every `QTimer.singleShot` and single-shot `QTimer` started from Python with a delay under
  1 s is tracked), no pointer move Qt has not seen, no start-up window work due
  (`shell.settling()`). Two quiet looks in a row.
- **What settling cannot see, so a `done` must name it:** an external program (CalculiX, gmsh,
  a QProcess), a Python thread, a repeating timer (a poll, an animation), FreeCAD's own C++
  timers, and timers of 1 s or more. Those last ones are left out on purpose: they are display
  times or decisions (the timeline shows a refusal for 2.5 s; a long press opens Select Other),
  and waiting for them would undo the state a step checks.
- An animation (a joint's motion, Animate in RESULTS) keeps changing the design, so the app
  never settles while it plays: a step that acts while it runs says `step.while_busy = True`
  (no waiting for a quiet app around it, only its `ready` / `done`).
- The browser and the timeline read the design on a poll (0.5 / 0.4 s) once it changed:
  settling includes them having read the last change (an active component's see-through look
  comes with the browser's read). The RESULTS view follows the bodies' eyes on its own tick:
  settling includes it having followed them. So do the SKETCH PALETTE (it reads the
  construction mode X toggles every 0.3 s) and the sketch's floating finish check (it follows
  the line chain's end every 0.1 s, also after a zoom).
- TechDraw draws a drawing view's lines and faces in a thread (Qt's thread pool): settling
  includes it being done. A straight section then switches off its lines beyond its depth on
  SciForge's next look (1.5, 3, 6 and 12 s after a change): settling includes every section's
  switched-off lines being worked out from the lines TechDraw now draws. (`d.wait_geometry`
  is a plain settle when paced by state.)
- The AI chat's worker thread hands its answers to the panel, which takes them every 50 ms:
  settling includes nothing waiting there (the worker can end while Send is still grey).
- A menu entry the browser runs a moment after its menu closed (Rename opens its field then):
  the menu helpers (`widget_input.right_click`, `click_menu`) process the events the click
  posted before they return; a check that needs more waits for it by state.
- Steps that re-insert themselves into the queue to poll (`h.state["queue"].insert(0, step)`)
  become a `done`.

The waits that came up most, and the state each stood for:

| A fixed wait before... | waits now for |
|---|---|
| a click or press after hovering in a sketch | `h.view_drawn()`: the view drew what is under the pointer |
| reading screen colours, a screenshot | `h.view_drawn()` |
| a check after typing into a dialog | `h.caught_up(panel)`: its preview timer done, no recompute |
| a check after a click, a drag, an Undo | `h.settle()` (the app settled: posted work, panels' reads, handles) |
| clicking a menu entry | `h.choose_from` / `h.light_entry`: the entry lit under the pointer |
| answering a modal question | `h.when(question shown, answer)` set up before the click |
| a marking-menu slot after a right click | `sketch_input.marking_choose(label)` |
| a program or thread of its own (a fake slicer, the update check, the AI connector) | `h.wait_for` on what it writes or answers |
| "nothing happened" (no second start, GitHub not asked) | the app's own record of it (programs started, a check running) |

## Converting a scenario

1. `h.run(..., paced_by="state")`.
2. Remove each `wait_ms`. For each, name the state it stood in for: the dialog the step opened,
   the value it typed reaching the preview, the solve it started finishing. If settling covers it
   (a dialog opened synchronously, a debounced preview), nothing more is needed; if not, give the
   step a `done`. If you cannot name the state, the step is underspecified: read the command's
   code until you can.
3. Replace `qWait(n)`, `time.sleep` and `singleShot(n, ...)` inside steps and helpers with
   `wait_for` / `settle` / `when`.
4. Prove it (below), lower the allowance (`tools/sciforge/check_waits.py --update`) and commit
   with the reason.

`SCIFORGE_PACED_BY=state tools/sciforge/run_tests.sh --scenario NAME` runs an unconverted
scenario without its fixed waits: the steps that then fail are the ones that need a `done`.

## Proving it holds

A green run proves little: the flaky scenarios also passed on most runs.

- **Slow on purpose:** `tools/sciforge/run_tests.sh --scenario a,b --stress --repeat 3` (FreeCAD
  and its X server pinned to one CPU core, `SCIFORGE_STRESS_CPU`, default 0, with two busy loops;
  `SCIFORGE_STRESS_LOAD=4` for more). A scenario that waits on state passes just as well when
  slow. Every converted batch passes three times in a row under stress before it is pushed. A
  speed limit in a check (the window never froze longer than 4 s) is written `4.0 * h.SLOWDOWN`:
  1 normally, the deliberate slowdown (loops + 1) under `--stress`; it never changes a wait.
  A real-time check no limit can scale (no exact rebuild between the moves of a drag at a
  hand's pace) is `h.speed_check`: counted on every normal run, only printed under `--stress`.
- **Repeat in CI:** Actions > SciForge tests > Run workflow with `repeat` (and optionally
  `scenarios`, `stress`): each scenario part runs its scenarios that many times and the job
  summary lists each one's pass count. Such a run is titled "Repeat GUI scenarios xN" and does not
  count as "tests green" for a patch release (it skips the base tests). On a build's AppImage:
  Actions > SciForge scenario debug, input `repeat`.
- **A real bug still fails:** break the feature on purpose in a throwaway change (the menu command
  does nothing) and check that the scenario fails fast, naming the step and the state. Do not push
  that change. Done for the rewritten helpers (2026-10-29/30), each failing in seconds:

  | Broken on purpose | Scenario | Failed with |
  |---|---|---|
  | Duplicate With Joints does nothing (ribbon menu) | vex_duplicate | step a_open: "Waited for Duplicate With Joints is open", stopped, 27 steps not run |
  | a command hangs in a question box | (a test scenario) | the watchdog: "Step a_open ended within 20 s ... modal: QMessageBox" |
  | the browser's Rename does nothing (right-click menu) | components_basic | step e_rename: "Waited for the rename field of 'Pin' to open", stopped |
  | Combine's operation greyed out (drop-down) | bodies_combine | step b_choose_cut: "the drop-down takes a choice (Cut): greyed out", at once |
  | the ViewCube menu's Go Home renamed | viewcube_menu | step menu: the entries listed, Go Home missing, at once |
  | the Move dialog ignores picks (3D click) | bodies_qa | step d_drag_negative: "body picked" with the dialog's empty pick list |
  | Extrude ignores a picked Operation (drop-down; `choose` checks the list's `activated`) | extrude_presspull_objects | step intersected: "Intersect keeps the 10 x 10 x 10 inside the extrusion", the volume shown |

The journey (`journey_gui.py`, part of the base tests) runs on the harness too, paced by state.

## Tools

| What | Where |
|---|---|
| The harness (waits, input, pacing, watchdog) | `SciForgeTests/gui/harness.py` |
| Input helpers on it | `widget_input.py`, `sketch_input.py` (ribbon menus), `selection_input.py`, `dialog_input.py`, `nav_input.py`, `viewcube_input.py`, `drawing_input.py`, `arrow_input.py` |
| One scenario run per fresh profile, `--stress`, `--repeat`, FLAKY/FAILED label | `tools/sciforge/run_tests.sh` (`--only gui-base`: the smoke test, the journey and the restart only) |
| Failures on the run page (`::error::` lines and the job summary) | `tools/sciforge/scenario_result.py` |
| The GUI environment (Xvfb 1920x1200 at 96 DPI, Qt scale 1, software GL, DejaVu fonts only) | `tools/sciforge/gui_env.sh` (`--install` on CI) |
| Fixed waits left, and the allowance that only goes down | `tools/sciforge/check_waits.py`, `check_waits.json` (a step of the tests workflow) |

The harness also ends a step that has not returned after 300 s (a dialog waiting for an answer
nobody gives) with what was on screen, and a thread ends FreeCAD when the event loop itself is
stuck, both long before the runner's 15-minute kill.

## The long build

The 4-hour build is never the first place a test problem shows up. A release tag is pushed only
after **SciForge tests** is fully green on that exact commit (`beta-release.md`, section 1). The
build's scenario parts test the compiled program only (C++ changes on the AppImage); they run on
the same image (`ubuntu-24.04`) with the same `gui_env.sh` and `run_tests.sh` options as the tests
workflow, so a pass there predicts a pass here. If one part fails, **Re-run failed jobs** runs just
that part: it downloads the AppImage of the same run (`gh run download $GITHUB_RUN_ID`), nothing is
compiled again (an artifact of attempt 1 is there for attempt 2: the scenario debug workflow's
`rerun-test` job, MEMORY 2026-10-21).

## Facts found on the way

- **QTest.mouseMove does not always move the pointer.** It moves the real (X) pointer only while
  QTest thinks no mouse button is down; inside a menu that opened on a press (a tool button's
  drop-down), before that press's release, it sends the widget a made-up move instead and the
  pointer stays where it was. `h.pointer_to` uses `QCursor.setPos` and waits until Qt has been told.
- The X server tells Qt about a pointer move a moment after `QCursor.setPos`; two moves told
  together are folded into the last, and a move to where Qt last saw the pointer is no move at all.
  A click sent before Qt saw the move lands where Qt still thinks the pointer is (CI #285 - #287).
- A `QMenu` takes a click only on the entry it has lit, lights one only on a move it was told
  about, and ignores the first six moves within 10 px of where it opened (`hasMouseMoved`).
- A drop-down list that opens under the pointer follows the pointer: `dialog_input.choose` leaves
  the pointer where it is and steps with the keys, counted from the list's own row. (Moving the
  pointer onto the drop-down first kept its list from opening at all: bodies_combine, 2 of 2.)
  It checks that the list took the choice (its `activated` signal), not what the box shows a
  moment later: the app may answer with another (Extrude shows New Body again, and says why,
  when Join is refused; extrude_presspull_qa2 P8, CI trial #312).
- Any wait lets the app's timers run: a row aimed at, then the wait for the pointer, then the
  click landed on another row after the browser rebuilt. `widget_input.click_item` presses only
  once the row under the pointer is the row wanted.
- A target outside every SciForge window (a model point off the view) gets no pointer wait: Qt
  is never told of a pointer there; the input goes to the widget as it always did.
- **The app times some clicks itself.** For 0.6 - 0.8 s after a click an overlay took (the
  Move triad's axes, pattern axes, Split's and Align's planes), after a pick (profile, axis,
  plane, cell, point) and after a drag of the Move triad, SciForge ignores the selection a
  click makes (to drop the one FreeCAD makes behind the overlay with the same click); FreeCAD's
  sketcher counts two presses within the double-click interval as a double-click. So every
  press in the 3D view comes at least `h.click_gap()` after the one before (`h.press_pace`,
  applied to every `QTest` press on the 3D view, the scenarios' own included): the pace of a
  hand, not a wait for the app. Without the fixed waits two clicks came 0.4 s apart and the
  second was lost (inspect_qa4: the face after the Center of Mass dot; bodies_qa: a Move arrow
  dragged right after the body was picked moved nothing).
