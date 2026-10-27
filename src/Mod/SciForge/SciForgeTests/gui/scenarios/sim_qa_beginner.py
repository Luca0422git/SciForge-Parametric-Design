# SPDX-License-Identifier: LGPL-2.1-or-later
"""What a beginner does in SIMULATION that the builders' scenarios did not (sim QA), on a steel
beam 100 x 10 x 10 held at x = 0 (the study made by script, every step after it real input).

A  A study with no load: the Pre-check light is yellow and says nothing pushes; Solve anyway:
   the results show without an error: every movement and stress 0, the safety factor the cap
   (15) everywhere, the legend without "nan", Results Details opens, Deformation Adjusted and
   Animate work on a part that does not move, a Surface Probe reads 0 MPa.
B  Finish Results, Structural Loads: Force 100 N down on the free end (clicks, typed); Solve:
   the end moves F L^3 / 3 E I (Timoshenko-free beam: 100 x 100^3 / (3 x 200000 x 833.3) =
   0.2 mm, within 5 %).
C  Clone Study from the study's right-click menu: a second study with its own copies of the
   constraint and load; its force edited to 200 N from the browser; the Solve dialog with both
   ticked says "Solve 2 Studies"; the clone moves twice as far (linear), the first study is
   unchanged and up to date; no solve among the undo steps.
D  Ctrl+Z: the clone's force is 100 N again (the last setup change undone, never a solve), its
   results out of date (kept), the first study's not; Redo: 200 N, up to date again.
"""

import FreeCAD as App
import FreeCADGui as Gui

from SciForgeTests.gui import harness as h
from SciForgeTests.gui import simres_steps as rs
from SciForgeTests.gui import simsetup_steps as s

state = {}
E_STEEL = 200000.0
I_BEAM = 10.0 * 10.0**3 / 12.0


def setup():
    from sciforge import simulation

    Gui.activateWorkbench("SciForgeWorkbench")
    doc = App.newDocument("SimQABeginner")
    body = rs.beam(doc)
    study = simulation.create_study(doc)
    simulation.add_item(study, "constraint", "fixed", [(body, rs.face_at_x(body, 0.0))])
    doc.recompute()
    h.fit()


def enter():
    s.workspace("Simulation")


# -- A ------------------------------------------------------------------------------------------
def a_precheck():
    rs.close_new_study_dialog()
    h.ribbon("Pre-check")


def a_light():
    h.check("A the light is yellow", s.light() == "yellow", s.light())
    dialog = s.popup_named("SciForgeSimPrecheck")
    if h.check("A the Pre-check list", dialog is not None):
        texts = [dialog.list.item(i).text() for i in range(dialog.list.count())]
        h.check("A it says nothing pushes", any("Nothing pushes" in x for x in texts), texts)
        s.close_popup("SciForgeSimPrecheck")
    h.ribbon("Solve")


def a_go():
    dialog = s.solve_dialog()
    if h.check("A the Solve dialog takes a yellow study", dialog is not None):
        h.check("A Solve enabled", dialog.go.isEnabled())
        s.click_widget(dialog.go)


def a_results():
    from sciforge import simulation_solve_dialog

    results = simulation_solve_dialog.last_results()
    h.check("A solved", any(r[0] == "done" for r in results.values()), results)
    s.close_popup("SciForgeSimJobStatus")  # (the progress window, Esc)
    stats = rs.summary().get("stats", {})
    h.check("A nothing moves", stats.get("displacement", {}).get("max", 1) < 1e-9, stats)
    h.check("A no stress", stats.get("von_mises", {}).get("max", 1) < 1e-9, stats)
    sf = stats.get("safety", {})
    h.check("A the safety factor is the cap everywhere", sf.get("min") == 15.0, sf)
    sess = rs.session()
    if not h.check("A the results show", sess is not None):
        return
    texts = " ".join(
        w.text() for w in sess.legend.findChildren(__import__("PySide").QtWidgets.QLabel)
    )
    h.check("A the legend has no nan", "nan" not in texts.lower(), texts)
    rs.big("Results Details")


def a_details():
    d = rs.dialog("SciForgeSimDetails")
    h.check("A Results Details opens", d is not None)
    if d is not None:
        d.close()
    rs.choose_result("Displacement")
    rs.menu("DEFORMATION", "Adjusted")


def a_adjusted():
    sess = rs.session()
    h.check("A Adjusted on a part that does not move: drawn as it is", sess.factor() == 0.0)
    rs.big("Animate")


a_adjusted.wait_ms = 400


def a_animate():
    from sciforge import simulation_results_ui as ui

    h.check("A Animate runs", ui.animation_on())
    rs.big("Animate")


a_animate.wait_ms = 1200


def a_stop():
    from sciforge import simulation_results_ui as ui

    h.check("A Animate stops", not ui.animation_on())
    rs.choose_result("Stress")
    rs.big("Surface Probes")


def a_probe():
    sess = rs.session()
    node = sess.display.nodes.tolist()[len(sess.display.nodes) // 2]
    h.click(App.Vector(*sess.display.node_place(node)))


def a_probe_read():
    probes = rs.tags("probe")
    h.check("A a probe reads 0 MPa", len(probes) == 1 and abs(probes[0]["value"]) < 1e-6, probes)
    h.task_button("Close")


def a_probes_closed():
    h.check("A Surface Probes closed", not Gui.Control.activeDialog())


# -- B ------------------------------------------------------------------------------------------
def b_finish():
    rs.big("Finish Results")


def b_loads():
    h.check("B back in SETUP", s.current_tab() == "sim_setup", s.current_tab())
    h.ribbon("Structural Loads")


def b_pick():
    p = s.item_panel()
    if not h.check("B Structural Loads", p is not None):
        return
    body = s.body("Beam")
    s.click_face(body, rs.face_at_x(body, 100.0))
    s.choose("SciForgeSim_direction", "Vector")


def b_values():
    s.type_in("SciForgeSim_fx", "0")
    s.type_in("SciForgeSim_fy", "0")
    s.type_in("SciForgeSim_fz", "-100 N")


def b_ok():
    s.ok()


def b_solve():
    h.check("B Force 1", [i.Label for i in s.items("load")] == ["Force 1"], s.items("load"))
    h.ribbon("Solve")


def b_go():
    dialog = s.solve_dialog()
    if h.check("B the Solve dialog", dialog is not None):
        s.click_widget(dialog.go)


def b_check():
    stats = rs.summary().get("stats", {})
    d = stats.get("displacement", {}).get("max", 0.0)
    state["d1"] = d
    hand = 100.0 * 100.0**3 / (3 * E_STEEL * I_BEAM)
    h.check("B the end moves %.4f mm, F L^3 / 3EI = %.4f" % (d, hand), abs(d / hand - 1) < 0.05)
    state["study1"] = s.active_study().Name
    s.close_popup("SciForgeSimJobStatus")


# -- C ------------------------------------------------------------------------------------------
def c_finish():
    rs.big("Finish Results")


def c_clone():
    s.right_click_row(s.active_study().Label, "Clone Study")


def c_cloned():
    found = s.studies()
    h.check("C a second study", len(found) == 2, [x.Label for x in found])
    if len(found) != 2:
        return
    clone = [x for x in found if x.Name != state["study1"]][0]
    state["clone"] = clone.Name
    loads = s.sim().items(clone, "load")
    held = s.sim().items(clone, "constraint")
    h.check("C with its own load and constraint", len(loads) == 1 and len(held) == 1)
    first = App.ActiveDocument.getObject(state["study1"])
    mine = {i.Name for i in s.sim().items(first)}
    h.check("C copies, not the first study's", not ({i.Name for i in loads + held} & mine))
    if loads:
        state["clone_force"] = loads[0].Label
        if s.active_study().Name != clone.Name:
            s.right_click_row(clone.Label, "Activate")


def c_edit():
    h.check("C the clone is active", s.active_study().Name == state.get("clone"))
    s.double_click_row(state.get("clone_force", "?"))


def c_type():
    p = s.item_panel()
    if h.check("C its force opens for editing", p is not None and p.editing):
        s.type_in("SciForgeSim_fz", "-200 N")


def c_ok():
    s.ok()


def c_solve():
    clone = App.ActiveDocument.getObject(state["clone"])
    load = s.sim().items(clone, "load")[0]
    h.check("C 200 N", abs(s.sim().item_data(load)["options"]["magnitude"] - 200.0) < 1e-9)
    first = App.ActiveDocument.getObject(state["study1"])
    first_load = s.sim().items(first, "load")[0]
    h.check(
        "C the first study keeps 100 N",
        abs(s.sim().item_data(first_load)["options"]["magnitude"] - 100.0) < 1e-9,
    )
    h.ribbon("Solve")


def c_tick():
    dialog = s.solve_dialog()
    if not h.check("C the Solve dialog", dialog is not None):
        return
    table = dialog.table
    for row in range(table.rowCount()):
        item = table.item(row, 0)
        if item is not None and item.checkState() != __import__("PySide").QtCore.Qt.Checked:
            s.tick_row(table, row)
    h.check("C Solve 2 Studies", dialog.go.text() == "Solve 2 Studies", dialog.go.text())
    s.click_widget(dialog.go)


def c_check():
    doc = App.ActiveDocument
    first = doc.getObject(state["study1"])
    clone = doc.getObject(state["clone"])
    d1 = s.sim().summary(first).get("stats", {}).get("displacement", {}).get("max", 0.0)
    d2 = s.sim().summary(clone).get("stats", {}).get("displacement", {}).get("max", 0.0)
    h.check("C the first study unchanged", abs(d1 - state["d1"]) < 1e-9 * max(d1, 1), (d1, state))
    h.check("C the clone moves twice as far", abs(d2 / d1 - 2.0) < 1e-6 if d1 else False, (d1, d2))
    h.check("C both up to date", not s.sim().out_of_date(first) and not s.sim().out_of_date(clone))
    state["undo"] = list(doc.UndoNames)
    h.check("C no solve among the undo steps", not any("olve" in n for n in doc.UndoNames))


# -- D ------------------------------------------------------------------------------------------
def d_undo():
    s.undo_key()


def d_undone():
    doc = App.ActiveDocument
    first = doc.getObject(state["study1"])
    clone = doc.getObject(state["clone"])
    load = s.sim().items(clone, "load")[0]
    h.check(
        "D Ctrl+Z takes the clone's 200 N back to 100 N (a setup change, not a solve)",
        abs(s.sim().item_data(load)["options"]["magnitude"] - 100.0) < 1e-9,
        (state["undo"], doc.UndoNames),
    )
    h.check("D the clone's results are out of date", s.sim().out_of_date(clone))
    h.check("D the first study's are not", not s.sim().out_of_date(first))
    h.check("D its results are still there", bool(s.sim().summary(clone)))
    s.redo()


def d_redone():
    doc = App.ActiveDocument
    clone = doc.getObject(state["clone"])
    load = s.sim().items(clone, "load")[0]
    h.check(
        "D Redo: 200 N again", abs(s.sim().item_data(load)["options"]["magnitude"] - 200.0) < 1e-9
    )
    h.check("D the clone's results are up to date again", not s.sim().out_of_date(clone))


h.run(
    "sim_qa_beginner",
    [
        setup,
        enter,
        a_precheck,
        a_light,
        a_go,
        s.wait_solved(),
        a_results,
        a_details,
        a_adjusted,
        a_animate,
        a_stop,
        a_probe,
        a_probe_read,
        a_probes_closed,
        b_finish,
        b_loads,
        b_pick,
        b_values,
        b_ok,
        b_solve,
        b_go,
        s.wait_solved("wait_solved_b"),
        b_check,
        c_finish,
        c_clone,
        c_cloned,
        c_edit,
        c_type,
        c_ok,
        c_solve,
        c_tick,
        s.wait_solved("wait_solved_c", 300),
        c_check,
        h.idle_step(),
        d_undo,
        h.idle_step("wait_undo"),
        d_undone,
        h.idle_step("wait_redo"),
        d_redone,
    ],
)
