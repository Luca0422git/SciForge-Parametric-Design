# SPDX-License-Identifier: LGPL-2.1-or-later
"""Every SETUP dialog with real clicks: Esc / Cancel, a refusal, the settings, the study
materials, gravity, contacts, Load Case Attributes, and undo / redo of setup changes (builder
sim-ui).

A  New Study opens on entering; Esc closes it and makes nothing; New Simulation Study again:
   the gear opens Study Settings (General, Mesh, Adaptive Mesh Refinement, Contacts);
   an Average Element Size of 8 % is kept by the study made with Create Study.
B  A refusal: Solve with nothing holding the model: the Solve dialog says why (the
   pre-check's sentence) and no solve starts.
C  Structural Constraints, Esc: nothing made; Structural Loads, Cancel: nothing made, and
   nothing in the undo history.
D  Study Materials: Aluminium for the bracket in this study, Ultimate Tensile Strength as the
   safety factor's basis, the properties shown; OK. Undo: back to (Same as Model); Redo:
   Aluminium again. The body's own material in the design did not change.
E  Settings: Mesh > Element Order Linear; Adaptive Mesh Refinement Low (its numbers shown,
   greyed), then Custom with 3 refinements; OK; Undo brings Parabolic and no refinement back.
F  LOADS > Toggle Gravity On/Off: gravity on, a Gravity row under Loads; right-click Gravity >
   Edit Gravity: Flip Direction, OK: it points up; Undo: down again. Edit Gravity, Direction
   Type Normal, a click on a side face: OK, gravity points into that face; Undo. Normal from a
   straight edge (the plate's front edge): gravity along it; Undo.
G  Automatic Contacts on one body: Generate finds none; Contact Manager says no bodies
   touch.
H  Load Case Attributes lists every item with its place and size.
I  A Fixed on the plate's top face, then Undo (gone) and Redo (back).
"""

import FreeCAD as App
from PySide import QtCore, QtWidgets
from PySide6 import QtTest

from SciForgeTests.gui import harness as h
from SciForgeTests.gui import simsetup_steps as s

state = {}


def study():
    return s.active_study()


def settings():
    return s.sim().settings(study())


# -- A ------------------------------------------------------------------------------------------
def a_enter():
    s.workspace("Simulation")


def a_escape():
    dialog = s.new_study_dialog()
    h.check("New Study opened", dialog is not None)
    if dialog is not None:
        QtTest.QTest.keyClick(dialog, QtCore.Qt.Key_Escape)
        QtWidgets.QApplication.processEvents()


def a_check_nothing():
    h.check("Esc closed New Study", s.new_study_dialog() is None)
    h.check("no study made", not s.studies())
    h.check("still in SIMULATION", s.tab_visible("sim_setup"))


def a_new_study():
    h.ribbon("New Simulation Study")


def a_gear():
    dialog = s.new_study_dialog()
    h.check("New Study opened from the ribbon", dialog is not None)
    if dialog is None:
        return

    def fill():
        try:
            settings_dialog = s.popup_named("SciForgeSimSettingsDialog")
            state["gear_seen"] = settings_dialog is not None
            if settings_dialog is None:
                return
            tabs = settings_dialog.form
            state["tabs"] = [tabs.tabText(i) for i in range(tabs.count())]
            state["adaptive"] = tabs.adaptive.isEnabled()
            tabs.setCurrentIndex(1)
            from SciForgeTests.gui import dialog_input as ui

            box = tabs.size
            box.setFocus()
            box.selectAll()
            QtTest.QTest.keyClicks(box, "8")
            QtTest.QTest.keyClick(box, QtCore.Qt.Key_Tab)
            ok = [
                b
                for b in settings_dialog.findChildren(QtWidgets.QPushButton)
                if b.text().replace("&", "") == "OK"
            ]
            if ok:
                ui.click(ok[0])
        except Exception as exc:
            state["gear_error"] = str(exc)

    QtCore.QTimer.singleShot(400, fill)
    s.click_widget(dialog.gear)


def a_create():
    h.check("the gear opened Study Settings", state.get("gear_seen"), state)
    h.check(
        "its tabs",
        state.get("tabs") == ["General", "Mesh", "Adaptive Mesh Refinement", "Contacts"],
        state.get("tabs"),
    )
    h.check("adaptive refinement offered (the engine runs it)", state.get("adaptive") is True)
    dialog = s.new_study_dialog()
    if dialog is not None:
        h.check(
            "the gear's size kept for the new study",
            abs(dialog.settings["mesh"]["size_pct"] - 8.0) < 1e-9,
            dialog.settings,
        )
        s.click_widget(dialog.create_button)


def a_check():
    h.check("the study made", len(s.studies()) == 1)
    h.check("with 8 %", abs(settings()["mesh"]["size_pct"] - 8.0) < 1e-9, settings()["mesh"])
    h.check("gravity off in a new study", settings()["gravity"]["on"] is False)


# -- B ------------------------------------------------------------------------------------------
def b_solve():
    h.ribbon("Solve")


def b_refuse():
    dialog = s.solve_dialog()
    h.check("Solve dialog", dialog is not None)
    if dialog is None:
        return
    s.click_widget(dialog.go)
    text = dialog.message.text()
    h.check("refused with the pre-check's sentence", "Nothing holds the model" in text, text)
    h.check("no solve started", not s.solving())
    h.check("the dialog stays open to read it", dialog.isVisible())
    cancel = dialog.findChild(QtWidgets.QPushButton, "SciForgeSimSolveCancel")
    s.click_widget(cancel)


# -- C ------------------------------------------------------------------------------------------
def c_constraints():
    state["undo"] = list(App.ActiveDocument.UndoNames)
    h.ribbon("Structural Constraints")


def c_escape():
    h.check("Structural Constraints opened", s.item_panel() is not None)
    s.click_face(s.body(), s.plate_top(s.body()))
    s.esc()


def c_loads():
    h.check("Esc closed it", s.item_panel() is None)
    h.check("no constraint made", not s.items())
    h.ribbon("Structural Loads")


def c_cancel():
    h.check("Structural Loads opened", s.item_panel() is not None)
    s.cancel()


def c_check():
    h.check("Cancel closed it", s.item_panel() is None)
    h.check("no load made", not s.items())
    h.check(
        "nothing new in the undo history",
        list(App.ActiveDocument.UndoNames) == state["undo"],
        App.ActiveDocument.UndoNames,
    )


# -- D ------------------------------------------------------------------------------------------
def d_materials():
    state["model_material"] = s.sim().model_material(s.body())[0]
    h.ribbon("Study Materials")


def d_change():
    from sciforge import simulation_dialogs

    p = simulation_dialogs.MaterialsPanel.last
    h.check("Study Materials opened", p is not None and not p._closed)
    if p is None:
        return
    h.check("one row per body", p.table.rowCount() == 1, p.table.rowCount())
    combo = p.combos[0]
    h.check(
        "(Same as Model) by default", combo.currentText() == "(Same as Model)", combo.currentText()
    )
    h.check("the properties are shown", "Young's Modulus" in p.props.text(), p.props.text())
    from SciForgeTests.gui import dialog_input as ui

    ui.choose(combo, "Aluminium")
    ui.choose(p.basis, "Ultimate Tensile Strength")
    state["props"] = p.props.text()


def d_ok():
    h.check(
        "Aluminium's properties shown", "Aluminum" in state.get("props", ""), state.get("props")
    )
    s.ok()


def d_check():
    name, _props, source = s.sim().study_material(study(), s.body())
    h.check("Aluminium for this study", source == "study" and "Aluminum" in name, (name, source))
    h.check("ultimate basis", settings()["safety_basis"] == "ultimate", settings())
    h.check(
        "the design's own material unchanged",
        s.sim().model_material(s.body())[0] == state["model_material"],
    )
    s.undo()


def d_undone():
    _name, _props, source = s.sim().study_material(study(), s.body())
    h.check("Undo: (Same as Model) again", source == "model", source)
    h.check("Undo: yield basis again", settings()["safety_basis"] == "yield")
    s.redo()


def d_redone():
    name, _props, source = s.sim().study_material(study(), s.body())
    h.check("Redo: Aluminium again", source == "study" and "Aluminum" in name, name)


# -- E ------------------------------------------------------------------------------------------
def e_settings():
    s.menu_item("MANAGE", "Settings")


def e_linear():
    from sciforge import simulation_dialogs

    p = simulation_dialogs.SettingsPanel.last
    h.check("Study Settings opened", p is not None and not p._closed)
    if p is None:
        return
    from SciForgeTests.gui import dialog_input as ui

    p.tabs.setCurrentIndex(1)
    ui.choose(p.tabs.order, "Linear")
    p.tabs.setCurrentIndex(2)
    ui.choose(p.tabs.adaptive, "Low")
    h.check(
        "a named level brings its own numbers (greyed)",
        not p.tabs.passes.isEnabled() and abs(p.tabs.passes.value() - 2) < 1e-9,
        (p.tabs.passes.isEnabled(), p.tabs.passes.value()),
    )
    ui.choose(p.tabs.adaptive, "Custom")
    h.check("Custom: the numbers can be typed", p.tabs.passes.isEnabled())
    ui.type_into(p.tabs.passes, "3")
    s.ok()


def e_check():
    h.check("linear elements kept", settings()["mesh"]["order"] == "linear", settings()["mesh"])
    adaptive = settings()["adaptive"]
    h.check(
        "custom refinement, 3 passes",
        adaptive["level"] == "custom" and adaptive["passes"] == 3,
        adaptive,
    )
    s.undo()


def e_undone():
    h.check("Undo: parabolic again", settings()["mesh"]["order"] == "parabolic")
    h.check("Undo: no refinement again", settings()["adaptive"]["level"] == "none")


# -- F ------------------------------------------------------------------------------------------
def f_gravity():
    s.menu_item("LOADS", "Toggle Gravity On/Off")


def f_check_on():
    h.check("gravity on", settings()["gravity"]["on"] is True, settings()["gravity"])
    h.check("a Gravity row under Loads", "Gravity" in s.browser_labels(), s.browser_labels())
    h.check("its glyph is drawn", s.glyph_counts().get("gravity") == 1, s.glyph_counts())
    s.right_click_row("Gravity", "Edit Gravity")


def f_flip():
    from sciforge import simulation_panels

    p = simulation_panels.GravityPanel.last
    h.check("Edit Gravity opened", p is not None and not p._closed)
    if p is None:
        return
    s.click_widget(p.flip)
    s.ok()


def f_check_up():
    d = settings()["gravity"]["direction"]
    h.check("gravity points up now", abs(d[2] - 1.0) < 1e-9, d)
    s.undo()


def f_undone():
    d = settings()["gravity"]["direction"]
    h.check("Undo: down again", abs(d[2] + 1.0) < 1e-9, d)
    s.right_click_row("Gravity", "Edit Gravity")


def f_normal():
    from sciforge import simulation_panels

    p = simulation_panels.GravityPanel.last
    if not h.check("Edit Gravity opened again", p is not None and not p._closed):
        return
    s.choose("SciForgeSim_gravity_direction", "Normal")
    body = s.body()
    sides = []
    for i, face in enumerate(body.Shape.Faces, 1):
        if "Plane" in face.Surface.TypeId:
            n = face.normalAt(0, 0)
            if abs(n.z) < 1e-6:
                sides.append(("Face%d" % i, (n.x, n.y, n.z)))
    name = s.visible_face(body, [n for n, _v in sides])
    if h.check("a side face can be clicked", name is not None):
        state["side_normal"] = dict(sides)[name]
        s.click_face(body, name)


def f_normal_ok():
    from sciforge import simulation_panels

    p = simulation_panels.GravityPanel.last
    if p is not None and not p._closed:
        QtTest.QTest.qWait(120)  # (a pick is handled a moment after the click)
        h.check("the face gives the direction", p.pick is not None, s.message())
    s.ok()


def f_normal_check():
    d = settings()["gravity"]["direction"]
    n = state.get("side_normal") or (0.0, 0.0, 0.0)
    h.check(
        "gravity points into the face (Normal)",
        all(abs(d[i] + n[i]) < 1e-6 for i in range(3)),
        (d, n),
    )
    s.undo()


def f_normal_undone():
    d = settings()["gravity"]["direction"]
    h.check("Undo: down again", abs(d[2] + 1.0) < 1e-9, d)
    s.right_click_row("Gravity", "Edit Gravity")


def f_edge():
    from sciforge import simulation_panels

    p = simulation_panels.GravityPanel.last
    if not h.check("Edit Gravity opened (edge)", p is not None and not p._closed):
        return
    s.choose("SciForgeSim_gravity_direction", "Normal")
    # the plate's top front edge, along X
    h.check("an edge clicked", h.click_edge(App.Vector(37.0, 0.0, 6.0)), h.state.get("last_click"))


def f_edge_ok():
    from sciforge import simulation_panels

    p = simulation_panels.GravityPanel.last
    if p is not None and not p._closed:
        QtTest.QTest.qWait(120)  # (a pick is handled a moment after the click)
        pick = p.pick
        h.check(
            "the edge gives the direction",
            pick is not None and str(pick[1]).startswith("Edge"),
            pick,
        )
    s.ok()


def f_edge_check():
    d = settings()["gravity"]["direction"]
    h.check("gravity along the edge (X)", abs(abs(d[0]) - 1.0) < 1e-6, d)
    s.undo()


def f_edge_undone():
    d = settings()["gravity"]["direction"]
    h.check("Undo: down again (edge)", abs(d[2] + 1.0) < 1e-9, d)


# -- G ------------------------------------------------------------------------------------------
def g_contacts():
    s.menu_item("CONTACTS", "Automatic Contacts")


def g_generate():
    from sciforge import simulation_dialogs

    p = simulation_dialogs.ContactsPanel.last
    h.check("Automatic Contacts opened", p is not None and not p._closed)
    if p is None:
        return
    h.check("0.1 mm by default", abs(p.tolerance.value() - 0.1) < 1e-9, p.tolerance.value())
    s.click_widget(p.generate)
    h.check("no contacts on one body", p.table.rowCount() == 0, p.table.rowCount())
    h.check("it says so", "No bodies touch" in p.message.text(), p.message.text())
    s.esc()


def g_manager():
    h.check("Esc closed it", s.task_panel() is None)
    s.menu_item("CONTACTS", "Contact Manager")


def g_check():
    dialog = s.popup_named("SciForgeSimContactManager")
    h.check("Contact Manager opened", dialog is not None)
    if dialog is not None:
        labels = [w.text() for w in dialog.findChildren(QtWidgets.QLabel)]
        h.check(
            "it says no bodies touch",
            any("No bodies of this study touch" in t for t in labels),
            labels,
        )
        s.close_popup("SciForgeSimContactManager")


# -- H, I ---------------------------------------------------------------------------------------
def i_fixed():
    h.ribbon("Structural Constraints")


def i_pick():
    import FreeCADGui as Gui
    from sciforge import simulation_ui

    opened = s.item_panel() is not None
    h.check(
        "Structural Constraints opened",
        opened,
        {
            "active": Gui.Command.get("SciForge_SimConstraints").isActive(),
            "document": App.ActiveDocument.Name if App.ActiveDocument else None,
            "in workspace": simulation_ui.in_workspace(),
            "task dialog": bool(Gui.Control.activeDialog()),
        },
    )
    s.click_face(s.body(), s.plate_top(s.body()))
    if opened:
        QtTest.QTest.qWait(120)  # (a pick is handled a moment after the click)
        h.check("the plate's top face picked", len(s.item_panel().picks) == 1, s.message())
    s.ok()


def i_check():
    h.check(
        "Fixed 1 made", [i.Label for i in s.items()] == ["Fixed 1"], [i.Label for i in s.items()]
    )
    s.menu_item("MANAGE", "Load Case Attributes")


def h_attributes():
    dialog = s.popup_named("SciForgeSimAttributes")
    h.check("Load Case Attributes opened", dialog is not None)
    if dialog is not None:
        table = dialog.findChild(QtWidgets.QTableWidget)
        rows = [
            [table.item(r, c).text() for c in range(table.columnCount())]
            for r in range(table.rowCount())
        ]
        h.check(
            "Fixed 1 and Gravity (still on)",
            [r[0] for r in rows] == ["Fixed 1", "Gravity"],
            rows,
        )
        h.check("its place", rows and "1 face" in rows[0][2], rows)
        s.close_popup("SciForgeSimAttributes")
    s.undo()


def i_undone():
    h.check("Undo: the Fixed is gone", not s.items(), [i.Label for i in s.items()])
    h.check("its glyphs went too", list(s.glyph_counts()) == ["gravity"], s.glyph_counts())
    s.redo()


def i_redone():
    h.check("Redo: the Fixed is back", [i.Label for i in s.items()] == ["Fixed 1"])
    h.check("Fixed 1 back in the browser", "Fixed 1" in s.browser_labels())


h.run(
    "sim_setup_dialogs",
    [
        s.new_bracket("SimDialogs"),
        a_enter,
        a_escape,
        a_check_nothing,
        a_new_study,
        a_gear,
        a_create,
        a_check,
        b_solve,
        b_refuse,
        c_constraints,
        c_escape,
        c_loads,
        c_cancel,
        c_check,
        d_materials,
        d_change,
        d_ok,
        d_check,
        d_undone,
        d_redone,
        e_settings,
        e_linear,
        e_check,
        e_undone,
        f_gravity,
        f_check_on,
        f_flip,
        f_check_up,
        f_undone,
        f_normal,
        f_normal_ok,
        f_normal_check,
        f_normal_undone,
        f_edge,
        f_edge_ok,
        f_edge_check,
        f_edge_undone,
        g_contacts,
        g_generate,
        g_manager,
        g_check,
        i_fixed,
        i_pick,
        i_check,
        h_attributes,
        i_undone,
        i_redone,
    ],
)
