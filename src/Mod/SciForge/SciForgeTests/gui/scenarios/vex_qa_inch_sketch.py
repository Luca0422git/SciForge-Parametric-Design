# SPDX-License-Identifier: LGPL-2.1-or-later
"""VEX QA (beta 3): sketching in a design in INCHES, as the team page tells a VEX team to set
it up (docs/sciforge/vex.md: Change Active Units > Inch). Fusion: a sketch's value boxes show
lengths in the design's units and read a plain number in them. Only real input.

  A  Browser > Units: mm > Change Active Units: Inch, OK; Create Sketch on the XY plane.
  B  2-Point Circle (CREATE menu): click the origin, move right: the box shows the diameter
     in inches; type 1, Enter: a circle 1 in wide (25.4 mm) with its Diameter dimension.
     Then one typed with its unit, "20 mm": 20 mm wide.
  C  A third circle by two clicks; Esc. Sketch Dimension (D) on it: the dimension's box shows
     the diameter in inches; type 1.5, Enter: the circle is 1.5 in wide (38.1 mm).
  D  L (FreeCAD's own line tool and its field): click, type 2, Enter: a line 2 in long.
"""

import math

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtWidgets

from SciForgeTests.gui import dialog_input as di
from SciForgeTests.gui import harness as h
from SciForgeTests.gui import sketch_input as si
from SciForgeTests.gui import sketch_tools_steps as st
from SciForgeTests.gui import timeline_input as ti

V = App.Vector
IN = 25.4
s = st.s


def setup():
    Gui.activateWorkbench("SciForgeWorkbench")
    App.newDocument("VexInchSketch")
    h.fit()


# -- A: inches, a sketch ---------------------------------------------------------------------------
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
    st.create_sketch()


def a_open():
    s["count"] = 0
    si.menu_item("CREATE", "2-Point Circle")


# -- B: a 2-Point Circle typed -----------------------------------------------------------------
def b_first():
    h.check("2-Point Circle runs", st.tool_title() == "2-Point Circle", st.tool_title())
    s["count"] = len(st.sketch().Geometry)
    st.click(V(0, 0, 0))


def b_hover():
    st.hover(V(30, 0, 0))
    texts = st.box_texts()
    h.check("the box shows the diameter in inches", any(t.endswith(" in") for t in texts), texts)


def b_type():
    st.keys("1\n")


def _new_circle():
    new = st.new_geometry(s["count"])
    circles = st.of_type(new, "Part::GeomCircle")
    s["count"] = len(st.sketch().Geometry)
    return circles[0] if len(circles) == 1 else (None, None)


def b_typed():
    i, c = _new_circle()
    if h.check("typed 1: a circle", c is not None):
        h.check("... 1 in wide (25.4 mm), not 1 mm", st.near(c.Radius, IN / 2, 1e-6), c.Radius)
        dims = [t for t in st.constraints_of(i) if t[0] == "Diameter"]
        h.check("... with its Diameter dimension", len(dims) == 1, st.constraints_of(i))
    st.click(V(-80, 0, 0))


def b_unit_hover():
    st.hover(V(-50, 0, 0))


def b_unit_type():
    st.keys("20 mm\n")


def b_unit_typed():
    _i, c = _new_circle()
    if h.check("typed 20 mm: a circle", c is not None):
        h.check("... 20 mm wide", st.near(c.Radius, 10.0, 1e-6), c.Radius)


# -- C: Sketch Dimension on a circle -----------------------------------------------------------
def c_first():
    st.click(V(40, 30, 0))


def c_second():
    st.click(V(60, 30, 0), towards=V(0, 0, 0))


def c_drawn():
    _i, c = _new_circle()
    h.check("a third circle by two clicks", c is not None)
    s["circle"] = c
    st.esc()


def c_dim_key():
    st.esc()
    h.press("d")


def c_dim_pick():
    c = s["circle"]
    si.click(c.Center + V(c.Radius * math.cos(1.0), c.Radius * math.sin(1.0), 0))


def c_dim_place():
    c = s["circle"]
    si.click(c.Center + V(c.Radius + 5, -4, 0))


def c_dim_box():
    from sciforge import sketch_mode

    session = sketch_mode.current()
    editor = session.editor if session is not None else None
    text = editor.edit.text() if editor is not None else None
    h.check("the dimension's box opens", editor is not None)
    h.check("... showing the diameter in inches", bool(text) and text.endswith(" in"), text)
    si.type_text("1.5")


def c_dim_typed():
    st.esc()
    circles = [g for _i, g in si.circles(st.sketch(), construction=False)]
    widths = sorted(round(2 * g.Radius, 6) for g in circles)
    h.check(
        "typed 1.5 in the dimension's box: the circle is 1.5 in wide (38.1 mm)",
        any(abs(w - 1.5 * IN) < 1e-6 for w in widths),
        widths,
    )
    h.check("no pop-up", not h.popups(), h.popups())


# -- D: FreeCAD's own line tool ------------------------------------------------------------------
def d_line():
    st.esc()
    s["lines"] = len(si.lines(st.sketch()))
    si.key("l")


def d_first():
    si.click(V(0, -40, 0))


def d_type():
    si.move_towards(V(8, -39.7, 0), V(1, 0, 0))
    si.type_text("2")


def d_typed():
    new = si.lines(st.sketch())[s["lines"] :]
    if h.check("typed 2 in the line's field: a line", len(new) >= 1, new):
        g = new[0][1]
        length = (g.EndPoint - g.StartPoint).Length
        h.check("... 2 in long (50.8 mm)", st.near(length, 2 * IN, 1e-6), length)
    st.esc()
    h.check("no pop-up at the end", not h.popups(), h.popups())


h.run(
    "vex_qa_inch_sketch",
    [
        setup,
        a_units,
        a_inch,
        a_inches,
        st.pick_xy,
        st.sketch_open,
        a_open,
        b_first,
        b_hover,
        b_type,
        b_typed,
        b_unit_hover,
        b_unit_type,
        b_unit_typed,
        c_first,
        c_second,
        c_drawn,
        c_dim_key,
        c_dim_pick,
        c_dim_place,
        c_dim_box,
        c_dim_typed,
        d_line,
        d_first,
        d_type,
        d_typed,
    ],
    paced_by="state",
)
