# SPDX-License-Identifier: LGPL-2.1-or-later
"""The SETUP dialogs in the design's own units (builder sim-ui), with real clicks. Fusion's
Simulation follows the document's units (research 6); the engine keeps N, MPa and mm.

A  A bracket in millimetres; Workspace > Simulation, Create Study. Document Settings > Units
   (in the SIMULATION browser): Inch, OK: the browser says "Units: in", SETUP still shows.
B  Structural Constraints on the hole walls, OK. Structural Loads on the arm's top face: the
   Magnitude shows lbf; "50" typed is 50 lbf (the engine keeps 222.4 N); the browser row and
   Load Case Attributes say 50 lbf.
C  Edit Load from the browser, OK without a change: the force stays exactly what it was (the
   field rounds to 4 figures, the value is not rounded).
D  Structural Loads > Pressure shows psi, Esc. Local Mesh Control's Length is in inches, Esc.
   Settings > Mesh offers the absolute size in inches, Esc. Automatic Contacts shows the
   tolerance in inches; OK keeps 0.1 mm exactly.
E  Units back to Millimeter: Edit Load shows 222.4 N; Esc.
"""

from PySide import QtWidgets

from SciForgeTests.gui import dialog_input as di
from SciForgeTests.gui import harness as h
from SciForgeTests.gui import simsetup_steps as s

LBF = 4.4482216152605
state = {}


def setup():
    s.new_bracket("SimUnits")()


def enter():
    s.workspace("Simulation")


def create():
    dialog = s.new_study_dialog()
    if h.check("New Study opened", dialog is not None):
        s.click_widget(dialog.create_button)


def _units_panel(unit):
    from sciforge import browser_ui

    panel = browser_ui.UnitsPanel.last
    if not h.check("Change Active Units opened", panel is not None and not panel._closed):
        return
    combo = panel.form.findChild(QtWidgets.QComboBox, "SciForgeUnitType")
    di.choose(combo, unit)
    h.task_button("OK")


def _field_text(name):
    field = s.panel_field(name, QtWidgets.QLineEdit)
    return field.text() if field is not None else ""


# -- A ------------------------------------------------------------------------------------------
def a_units():
    h.check("the study made", len(s.studies()) == 1)
    s.click_row("Units: mm")


def a_inch():
    _units_panel("Inch")


def a_check():
    h.check("the browser says inches", "Units: in" in s.browser_labels(), s.browser_labels())
    h.check("SETUP still shows", s.tab_visible("sim_setup"))
    h.ribbon("Structural Constraints")


# -- B ------------------------------------------------------------------------------------------
def b_fixed():
    for face in s.hole_faces(s.body()):
        s.click_face(s.body(), face)
    s.ok()


def b_load():
    h.check("Fixed 1 made", [i.Label for i in s.items("constraint")] == ["Fixed 1"])
    h.ribbon("Structural Loads")


def b_pick():
    s.click_face(s.body(), s.arm_top(s.body()))
    text = _field_text("SciForgeSim_magnitude")
    h.check("the Magnitude shows lbf", text.endswith(" lbf"), text)
    s.type_in("SciForgeSim_magnitude", "50")
    s.ok()


def b_check():
    loads = s.items("load")
    if not h.check("Force 1 made", [i.Label for i in loads] == ["Force 1"]):
        return
    magnitude = s.sim().item_data(loads[0])["options"]["magnitude"]
    h.check("50 lbf kept as 222.4 N", abs(magnitude - 50 * LBF) < 1e-9, magnitude)
    state["magnitude"] = magnitude
    tip = (s.row_node("Force 1") or {}).get("tip", "")
    h.check("the browser row says 50 lbf", "Force 50 lbf" in tip, tip)
    s.menu_item("MANAGE", "Load Case Attributes")


def b_attributes():
    dialog = s.popup_named("SciForgeSimAttributes")
    if h.check("Load Case Attributes opened", dialog is not None):
        table = dialog.findChild(QtWidgets.QTableWidget)
        rows = [
            [table.item(r, c).text() for c in range(table.columnCount())]
            for r in range(table.rowCount())
        ]
        force = [r for r in rows if r[0] == "Force 1"]
        h.check("Force 1 is 50 lbf", force and "50 lbf" in force[0][3], rows)
        s.close_popup("SciForgeSimAttributes")


# -- C ------------------------------------------------------------------------------------------
def c_edit():
    s.right_click_row("Force 1", "Edit Load")


def c_ok():
    text = _field_text("SciForgeSim_magnitude")
    h.check("Edit Load shows 50 lbf", text == "50 lbf", text)
    s.ok()


def c_check():
    magnitude = s.sim().item_data(s.items("load")[0])["options"]["magnitude"]
    h.check("OK without a change kept it exactly", magnitude == state["magnitude"], magnitude)


# -- D ------------------------------------------------------------------------------------------
def d_pressure():
    h.ribbon("Structural Loads")


def d_choose():
    s.choose("SciForgeSimItemType", "Pressure")


def d_check():
    text = _field_text("SciForgeSim_magnitude")
    h.check("Pressure shows psi", text.endswith(" psi"), text)
    s.esc()


def d_mesh():
    h.check("Esc closed it", s.task_panel() is None)
    s.menu_item("MANAGE", "Local Mesh Control")


def d_mesh_check():
    text = _field_text("SciForgeSim_size")
    h.check("the Length is in inches", text.endswith(" in"), text)
    s.esc()


def d_settings():
    h.check("Esc closed it", s.task_panel() is None)
    s.menu_item("MANAGE", "Settings")


def d_settings_check():
    from sciforge import simulation_dialogs

    p = simulation_dialogs.SettingsPanel.last
    if not h.check("Study Settings opened", p is not None and not p._closed):
        return
    kinds = [p.tabs.size_kind.itemText(i) for i in range(p.tabs.size_kind.count())]
    h.check("the absolute size in inches", "Absolute value (in)" in kinds, kinds)
    h.check("its field too", p.tabs.size_mm.suffix() == " in", p.tabs.size_mm.suffix())
    s.esc()


def d_contacts():
    h.check("Esc closed it", s.task_panel() is None)
    s.menu_item("CONTACTS", "Automatic Contacts")


def d_contacts_check():
    from sciforge import simulation_dialogs

    p = simulation_dialogs.ContactsPanel.last
    if not h.check("Automatic Contacts opened", p is not None and not p._closed):
        return
    h.check("the tolerance in inches", p.tolerance.suffix() == " in", p.tolerance.suffix())
    h.check(
        "0.1 mm shown in inches",
        abs(p.tolerance.value() - 0.1 / 25.4) < 1e-4,
        p.tolerance.value(),
    )
    s.ok()


def d_contacts_kept():
    tolerance = s.sim().settings(s.active_study())["contact_tolerance"]
    h.check("OK kept 0.1 mm exactly", tolerance == 0.1, tolerance)


# -- E ------------------------------------------------------------------------------------------
def e_units():
    s.click_row("Units: in")


def e_mm():
    _units_panel("Millimeter")


def e_edit():
    h.check("the browser says mm", "Units: mm" in s.browser_labels(), s.browser_labels())
    s.right_click_row("Force 1", "Edit Load")


def e_check():
    text = _field_text("SciForgeSim_magnitude")
    h.check("Edit Load shows 222.4 N", text.startswith("222.411") and text.endswith(" N"), text)
    s.esc()


def e_closed():
    h.check("Esc closed it", s.task_panel() is None)
    magnitude = s.sim().item_data(s.items("load")[0])["options"]["magnitude"]
    h.check("the force unchanged", magnitude == state["magnitude"], magnitude)


h.run(
    "sim_setup_units",
    [
        setup,
        enter,
        create,
        a_units,
        a_inch,
        a_check,
        b_fixed,
        b_load,
        b_pick,
        b_check,
        b_attributes,
        c_edit,
        c_ok,
        c_check,
        d_pressure,
        d_choose,
        d_check,
        d_mesh,
        d_mesh_check,
        d_settings,
        d_settings_check,
        d_contacts,
        d_contacts_check,
        d_contacts_kept,
        e_units,
        e_mm,
        e_edit,
        e_check,
        e_closed,
    ],
)
