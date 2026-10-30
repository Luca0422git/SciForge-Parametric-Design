# SPDX-License-Identifier: LGPL-2.1-or-later
"""Two bodies half a millimetre apart, two studies solved together (builder sim-ui), with real
clicks. The blocks and the first study's Fixed and Force are made by script.

A  A base block and a top block 0.5 mm above it. Workspace > Simulation: the pre-check is red
   (the top touches nothing held). Solve > Repair: DOF View comes on, the top's arrows drawn and
   the top named; DOF View off. Automatic Contacts: Generate finds nothing at 0.1 mm; the
   tolerance typed as 1 mm, Generate: one bonded pair with a 0.5 mm gap; OK keeps 1 mm.
B  DOF View: every body is held (the top through its contact with the held base); off again.
C  Clone Study: Study 2, active. Its Study Materials: Aluminium for the top block; OK. Again:
   In Study unticked for the top: Study 2 without it (its row greyed); Undo: back.
D  Solve with both studies ticked ("Solve 2 Studies"): both solved one after the other, each
   with a result for each body; Study 2 solved the top in aluminium, which moves more (it is
   softer); the progress lists both as done.
E  Right-click Top > Exclude from Study (Study 2): its force is on a body the study leaves
   out: red. Solve > Repair on Study 2's row: Study Materials opens, told why; Top ticked In
   Study, OK: the top is back and the pre-check is not red.
"""

import FreeCAD as App
from PySide import QtCore
from PySide6 import QtTest

from SciForgeTests.gui import dialog_input as ui
from SciForgeTests.gui import harness as h
from SciForgeTests.gui import simsetup_steps as s
from SciForgeTests.gui import widget_input as w

state = {}


def setup():
    from sciforge import bodies

    doc = App.newDocument("SimTwo")
    base = s.block(doc, "Base", (40, 20, 10), (0, 0, 0))
    top = s.block(doc, "Top", (20, 20, 10), (10, 0, 10.5))
    sim = s.sim()
    study = sim.create_study(doc)

    def face(body, test):
        for i, f in enumerate(bodies.global_shape(body).Faces, 1):
            if test(f.BoundBox):
                return "Face%d" % i
        return None

    end = face(base, lambda b: abs(b.XMin) < 1e-6 and abs(b.XMax) < 1e-6)
    roof = face(top, lambda b: abs(b.ZMin - 20.5) < 1e-6 and abs(b.ZMax - 20.5) < 1e-6)
    sim.add_item(study, "constraint", "fixed", [(base, end)])
    sim.add_item(study, "load", "force", [(top, roof)], {"magnitude": 200.0})
    doc.recompute()
    state["base"], state["top"] = base.Name, top.Name
    h.fit()


def enter():
    s.workspace("Simulation")


# -- A ------------------------------------------------------------------------------------------
def a_red():
    h.check("pre-check red: the top is held by nothing", s.light() == "red", s.light())
    h.ribbon("Solve")


def a_repair():
    dialog = s.solve_dialog()
    button = dialog.table.cellWidget(0, 3) if dialog is not None else None
    if h.check("Repair next to the study", button is not None and button.text() == "Repair"):
        s.click_widget(button)


def a_dof():
    from sciforge import simulation_ui

    h.check("the Solve dialog closed", s.solve_dialog() is None)
    h.check("Repair switched DOF View on", simulation_ui.dof_on())
    h.check("the top named", "Top" in s.told() and "Base" not in s.told(), s.told())
    h.check("its arrows drawn", s.glyph_counts().get("dof", 0) > 0, s.glyph_counts())
    s.menu_item("DISPLAY", "DOF View")


def a_contacts():
    from sciforge import simulation_ui

    h.check("DOF View off again", not simulation_ui.dof_on())
    h.ribbon("Automatic Contacts")


def a_generate():
    from sciforge import simulation_dialogs

    p = simulation_dialogs.ContactsPanel.last
    if not h.check("Automatic Contacts opened", p is not None and not p._closed):
        return
    s.click_widget(p.generate)
    h.check("nothing at 0.1 mm", p.table.rowCount() == 0, p.table.rowCount())
    p.tolerance.setFocus()
    p.tolerance.selectAll()
    QtTest.QTest.keyClicks(p.tolerance, "1")
    QtTest.QTest.keyClick(p.tolerance, QtCore.Qt.Key_Tab)
    s.click_widget(p.generate)
    rows = [
        [p.table.item(r, c).text() for c in range(p.table.columnCount())]
        for r in range(p.table.rowCount())
    ]
    h.check("one bonded pair at 1 mm", len(rows) == 1, rows)
    h.check("a 0.5 mm gap", rows and rows[0][2] == "0.5 mm", rows)
    s.ok()


def a_check():
    tolerance = s.sim().settings(s.active_study())["contact_tolerance"]
    h.check("1 mm kept", abs(tolerance - 1.0) < 1e-9, tolerance)


# -- B ------------------------------------------------------------------------------------------
def b_dof():
    s.menu_item("DISPLAY", "DOF View")


def b_check():
    text = s.tooltip_text()
    h.check("every body is held (through the contact)", "every body" in text, text)
    h.check("no arrows", not s.glyph_counts().get("dof"), s.glyph_counts())
    s.menu_item("DISPLAY", "DOF View")


# -- C ------------------------------------------------------------------------------------------
def c_clone():
    from sciforge import simulation_ui

    h.check("DOF View off", not simulation_ui.dof_on())
    s.right_click_row("Study 1 - Static Stress", "Clone Study")


def c_materials():
    h.check(
        "Study 2 active",
        s.active_study() is not None and s.active_study().Label == "Study 2 - Static Stress",
    )
    h.ribbon("Study Materials")


def c_change():
    from sciforge import simulation_dialogs

    p = simulation_dialogs.MaterialsPanel.last
    if not h.check("Study Materials opened", p is not None and not p._closed):
        return
    rows = [p.table.item(r, 0).text() for r in range(p.table.rowCount())]
    h.check("a row per body", sorted(rows) == ["Base", "Top"], rows)
    if "Top" in rows:
        ui.choose(p.combos[rows.index("Top")], "Aluminium")
    s.ok()


def c_check():
    doc = App.ActiveDocument
    name, _props, source = s.sim().study_material(s.active_study(), doc.getObject(state["top"]))
    h.check("Aluminium for the top in Study 2", source == "study" and "Alumin" in name, name)
    h.ribbon("Study Materials")


def c_leave_out():
    from sciforge import simulation_dialogs

    p = simulation_dialogs.MaterialsPanel.last
    if not h.check("Study Materials opened again", p is not None and not p._closed):
        return
    rows = [p.table.item(r, 0).text() for r in range(p.table.rowCount())]
    if "Top" in rows:
        tick = p.ticks[rows.index("Top")]
        w.click(tick, QtCore.QPoint(8, tick.height() // 2))
        h.check("Top unticked (In Study)", not tick.isChecked())
    s.ok()


def c_left_out():
    found = [b.Label for b in s.sim().study_bodies(s.active_study())]
    h.check("Study 2 without the top", found == ["Base"], found)
    h.check("its row greyed in the browser", (s.row_node("Top") or {}).get("status") is not None)
    s.undo()


def c_back():
    found = sorted(b.Label for b in s.sim().study_bodies(s.active_study()))
    h.check("Undo: the top back in Study 2", found == ["Base", "Top"], found)
    h.ribbon("Solve")


# -- D ------------------------------------------------------------------------------------------
def d_both():
    dialog = s.solve_dialog()
    if not h.check("Solve dialog", dialog is not None):
        return
    h.check("both studies listed", dialog.table.rowCount() == 2, dialog.table.rowCount())
    for row in range(dialog.table.rowCount()):
        item = dialog.table.item(row, 0)
        if item.checkState() != QtCore.Qt.Checked:
            s.tick_row(dialog.table, row)
    h.check("Solve 2 Studies", dialog.go.text() == "Solve 2 Studies", dialog.go.text())
    s.click_widget(dialog.go)


def d_check():
    studies = s.studies()
    sums = [s.sim().summary(x) or {} for x in studies]
    h.check("both solved", all(sums) and len(sums) == 2, [bool(x) for x in sums])
    if all(sums):
        for x, data in zip(studies, sums):
            h.check(
                "%s: a result for each body" % x.Label,
                sorted(data.get("bodies", {})) == ["Base", "Top"],
                data.get("bodies"),
            )
        top1 = sums[0]["bodies"]["Top"]
        top2 = sums[1]["bodies"]["Top"]
        h.check(
            "Study 2 solved the top in aluminium (Study 1 in its own material)",
            "Alumin" in str(top2.get("material")) and "Alumin" not in str(top1.get("material")),
            (top1.get("material"), top2.get("material")),
        )
        h.check(
            "the softer top moves more",
            top2["displacement_max"] > top1["displacement_max"],
            (top1["displacement_max"], top2["displacement_max"]),
        )
    status = s.status_dialog()
    rows = [status.studies.item(i).text() for i in range(status.studies.count())] if status else []
    h.check(
        "the progress lists both done",
        sum(1 for r in rows if r.endswith(": Done") and not r.startswith("Earlier")) == 2,
        rows,
    )
    s.close_popup("SciForgeSimJobStatus")
    s.click_tab("sim_setup")  # (the results took the RESULTS tab)


# -- E ------------------------------------------------------------------------------------------
def e_exclude():
    h.check(
        "Study 2 active",
        s.active_study() is not None and s.active_study().Label.startswith("Study 2"),
    )
    s.right_click_row("Top", "Exclude from Study")


def e_red():
    found = [b.Label for b in s.sim().study_bodies(s.active_study())]
    h.check("Top left out of Study 2", found == ["Base"], found)
    h.check("pre-check red: its force is on a body left out", s.light() == "red", s.light())
    h.ribbon("Solve")


def e_repair():
    dialog = s.solve_dialog()
    if not h.check("Solve dialog (E)", dialog is not None):
        return
    button = None
    for row in range(dialog.table.rowCount()):
        if dialog.table.item(row, 0).text().startswith("Study 2"):
            button = dialog.table.cellWidget(row, 3)
    if h.check("Repair next to Study 2", button is not None):
        s.click_widget(button)


def e_materials():
    from sciforge import simulation_dialogs

    p = simulation_dialogs.MaterialsPanel.last
    if not h.check("Repair opened Study Materials", p is not None and not p._closed):
        return
    text = s.told()
    h.check("told why", "Top" in text and "leaves out" in text, text)
    rows = [p.table.item(r, 0).text() for r in range(p.table.rowCount())]
    if h.check("Top listed", "Top" in rows, rows):
        tick = p.ticks[rows.index("Top")]
        w.click(tick, QtCore.QPoint(8, tick.height() // 2))
        h.check("Top ticked In Study", tick.isChecked())
    s.ok()


def e_back():
    found = sorted(b.Label for b in s.sim().study_bodies(s.active_study()))
    h.check("Top back in Study 2", found == ["Base", "Top"], found)
    h.check("pre-check not red", s.light() in ("green", "yellow"), s.light())


h.run(
    "sim_setup_two",
    [
        setup,
        enter,
        a_red,
        a_repair,
        a_dof,
        a_contacts,
        a_generate,
        a_check,
        b_dof,
        b_check,
        c_clone,
        c_materials,
        c_change,
        c_check,
        c_leave_out,
        c_left_out,
        c_back,
        d_both,
        s.wait_solved(),
        d_check,
        e_exclude,
        e_red,
        e_repair,
        e_materials,
        e_back,
    ],
    paced_by="state",
)
