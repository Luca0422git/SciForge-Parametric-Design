# SPDX-License-Identifier: LGPL-2.1-or-later
"""VEX QA (beta 3): a design in INCHES, as the team page tells a VEX team to set it up
(docs/sciforge/vex.md: Change Active Units > Inch; VEX sizes are in inches), and a value typed
without a unit in a dialog. Fusion: a plain number is in the design's units. Only real input.
SciForge's own VEX-like parts: a 1x2x1x5 C-channel and a 1/8 in square shaft.

  A  Browser > Units: mm > Change Active Units: Inch, OK: the design is in inches.
  B  J: the shaft's top end, then the dot next to a square hole: the shaft stands on the web.
     Offset Z typed as a plain -1.5 (the design is in inches): the shaft goes 1.5 in down
     through the hole, not 1.5 mm. The box shows inches.
  C  OK; then the units back to millimetres and Offset Z of the joint (edit) typed as a plain
     -20: 20 mm.
"""

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtWidgets

from SciForgeTests.gui import bodies_steps as s
from SciForgeTests.gui import dialog_input as di
from SciForgeTests.gui import harness as h
from SciForgeTests.gui import timeline_input as ti
from SciForgeTests.gui import vex_steps as vx

V = App.Vector
S = {}
SHAFT_AT = V(-20, 19.05, 0)
HOLE = (2, 1)
LENGTH = 3.0 * vx.IN


def hover():
    p = vx.panel()
    return getattr(p, "hover", None) if p is not None else None


def setup():
    Gui.activateWorkbench("SciForgeWorkbench")
    App.newDocument("VexInch")
    S["channel"] = vx.insert("c_channel_1x2x1x5")
    S["shaft"] = vx.insert("shaft_3in", App.Placement(SHAFT_AT, App.Rotation()))
    vx.fit()


# -- A: inches -------------------------------------------------------------------------------------
def a_units():
    ti.click_row("Units: mm")


def a_inch():
    from sciforge import browser_ui

    panel = browser_ui.UnitsPanel.last
    h.check("Change Active Units opens", panel is not None and not panel._closed)
    if panel is None:
        return
    combo = panel.form.findChild(QtWidgets.QComboBox, "SciForgeUnitType")
    di.choose(combo, "Inch")
    h.task_button("OK")


def a_inches():
    h.check(
        "the design is in inches",
        App.ActiveDocument.UnitSystem.startswith("Imperial decimal"),
        App.ActiveDocument.UnitSystem,
    )


# -- B: a plain number in an inch design -----------------------------------------------------------
def b_press_j():
    h.click_empty()
    vx.fit()
    h.press("j")


def b_hover_top():
    box = vx.bbox(S["shaft"])
    S["top"] = V((box.XMin + box.XMax) / 2.0, (box.YMin + box.YMax) / 2.0, box.ZMax)
    vx.look_at(S["top"], 15.0)
    S["pt"] = vx.toward_viewer(S["top"], 0.6)
    vx.hover(S["pt"])


def b_click_top():
    vx.lit(hover(), "the shaft's top end", "centre", S["top"])
    h.click(S["pt"])


def b_hover_hole():
    c = vx.hole_centre(*HOLE)
    vx.look_at(c, 40.0)
    S["pt"] = V(c.x + 3.6, c.y, vx.T)
    vx.hover(S["pt"])


def b_click_hole():
    vx.lit(hover(), "next to the hole", "loop", vx.hole_centre(*HOLE))
    h.click(S["pt"])


def b_type():
    box = vx.bbox(S["shaft"])
    h.check("the shaft stands on the web", abs(box.ZMin - vx.T) < 1e-3, box)
    p = vx.joint_panel()
    if h.check("the Joint dialog stays open", p is not None, p):
        S["field"] = p.offset_fields["z"]
        s.type_value(S["field"].widget, "-1.5")


def b_inches():
    box = vx.bbox(S["shaft"])
    want = vx.T - 1.5 * vx.IN
    h.check(
        "a plain -1.5 in an inch design: the shaft 1.5 in down (not 1.5 mm)",
        abs(box.ZMin - want) < 1e-3,
        (box.ZMin, want),
    )
    text = S["field"].widget.text() if S.get("field") is not None else ""
    h.check("the box shows inches", "in" in text and "-1.5" in text, text)
    vx.ok()


def b_made():
    h.check("one joint", len(vx.joints_list()) == 1, [o.Label for o in vx.joints_list()])
    box = vx.bbox(S["shaft"])
    h.check("kept after OK", abs(box.ZMin - (vx.T - 1.5 * vx.IN)) < 1e-3, box)


# -- C: millimetres again ------------------------------------------------------------------------
def c_units():
    h.click_empty()
    ti.click_row("Units: in")


def c_mm():
    from sciforge import browser_ui

    combo = browser_ui.UnitsPanel.last.form.findChild(QtWidgets.QComboBox, "SciForgeUnitType")
    di.choose(combo, "Millimeter")
    h.task_button("OK")


def c_edit():
    h.check(
        "back in millimetres",
        App.ActiveDocument.UnitSystem.startswith("Standard"),
        App.ActiveDocument.UnitSystem,
    )
    joint = vx.joints_list()[0] if vx.joints_list() else None
    if h.check("the joint", joint is not None):
        from SciForgeTests.gui import joints_steps as j

        j.browser_menu(joint.Label, "Edit Joint")


def c_type():
    p = vx.joint_panel()
    if h.check("the joint's dialog open", p is not None, p):
        s.type_value(p.offset_fields["z"].widget, "-20")


def c_mm_value():
    box = vx.bbox(S["shaft"])
    h.check("a plain -20 in a millimetre design: 20 mm", abs(box.ZMin - (vx.T - 20.0)) < 1e-3, box)
    vx.ok()


def c_done():
    box = vx.bbox(S["shaft"])
    h.check("kept after OK", abs(box.ZMin - (vx.T - 20.0)) < 1e-3, box)
    vx.no_popups("the inch design")


h.run(
    "vex_qa_inch",
    [
        setup,
        a_units,
        a_inch,
        a_inches,
        b_press_j,
        b_hover_top,
        b_click_top,
        b_hover_hole,
        b_click_hole,
        b_type,
        b_inches,
        b_made,
        c_units,
        c_mm,
        c_edit,
        c_type,
        c_mm_value,
        c_done,
    ],
    paced_by="state",
)
