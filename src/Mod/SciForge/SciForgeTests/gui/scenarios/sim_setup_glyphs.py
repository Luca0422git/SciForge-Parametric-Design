# SPDX-License-Identifier: LGPL-2.1-or-later
"""The glyphs of the SIMULATION workspace are really drawn (builder sim-ui): the 3D view is
rendered off screen (xvfb shows no 3D on the screen, but FreeCAD's saveImage renders) with the
glyphs shown and hidden, and the pictures are compared.

A  A bracket with a study made by script: Fixed at the holes, a Force on the arm, a Pressure on
   the plate, a Moment, gravity on. Workspace > Simulation: the glyphs are counted per item.
B  The picture with the glyphs has the loads' orange and the constraints' teal; hidden
   (simulation_glyphs.set_visible(False), as sim-results does on its results), those colours
   are gone and the model is the same.
C  Zoomed out: the glyphs keep their size on the screen (their size in mm grows).
D  Workspace > Design: no glyph left in the view (the picture has none of their colours).
E  Back in Simulation with the Fixed suppressed (nothing holds the bracket): DISPLAY > DOF
   View draws its arrows (three slides, three turns) over the model in their own colour;
   DOF View off: that colour is gone.
"""

import os

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtGui

from SciForgeTests.gui import harness as h
from SciForgeTests.gui import simsetup_steps as s

OUT = os.environ.get("SCIFORGE_SMOKE_OUT") or App.getUserAppDataDir()
state = {}
ORANGE = (245, 133, 26)  # simulation_glyphs.PUSH, lit
TEAL = (26, 158, 168)  # simulation_glyphs.HOLD
MAGENTA = (219, 66, 168)  # simulation_glyphs.DOF


def setup():
    s.new_bracket("SimGlyphs")()
    sim = s.sim()
    doc = App.ActiveDocument
    body = s.body()
    study = sim.create_study(doc)
    sim.add_item(study, "constraint", "fixed", [(body, s.hole_faces(body))])
    sim.add_item(study, "load", "force", [(body, s.arm_top(body))], {"magnitude": 250.0})
    sim.add_item(study, "load", "pressure", [(body, s.plate_top(body))], {"magnitude": 0.2})
    sim.add_item(study, "load", "moment", [(body, s.arm_top(body))], {"magnitude": 1000.0})
    sim.set_settings(study, {"gravity": {"on": True}})
    doc.recompute()


def enter():
    s.workspace("Simulation")


def picture(name):
    path = os.path.join(OUT, "sim_setup_glyphs-%s.png" % name)
    Gui.ActiveDocument.ActiveView.saveImage(path, 800, 560, "White")
    return QtGui.QImage(path)


def near(color, want, tol=60):
    return all(abs(a - b) <= tol for a, b in zip(color, want))


def count(image, want):
    """Pixels close to the colour `want` (every second pixel)."""
    n = 0
    for y in range(0, image.height(), 2):
        for x in range(0, image.width(), 2):
            c = image.pixelColor(x, y)
            if near((c.red(), c.green(), c.blue()), want):
                n += 1
    return n


def differ(a, b):
    n = 0
    for y in range(0, a.height(), 2):
        for x in range(0, a.width(), 2):
            if a.pixel(x, y) != b.pixel(x, y):
                n += 1
    return n


# -- A, B ---------------------------------------------------------------------------------------
def a_counts():
    counts = s.glyph_counts()
    h.check("glyphs for the four items and gravity", len(counts) == 5, counts)
    h.check("several per face", all(n >= 1 for n in counts.values()), counts)
    h.fit()


def b_shown_hidden():
    from sciforge import simulation_glyphs as g

    shown = picture("shown")
    g.set_visible(False)
    hidden = picture("hidden")
    g.set_visible(True)
    state["orange_shown"] = count(shown, ORANGE)
    state["orange_hidden"] = count(hidden, ORANGE)
    state["teal_shown"] = count(shown, TEAL)
    state["teal_hidden"] = count(hidden, TEAL)
    state["diff"] = differ(shown, hidden)
    h.check("the glyphs are drawn (the pictures differ)", state["diff"] > 200, state)
    h.check("the loads' orange shows", state["orange_shown"] > 20, state)
    h.check("the constraints' teal shows", state["teal_shown"] > 3, state)
    h.check("hidden: no orange", state["orange_hidden"] == 0, state)
    h.check("hidden: no teal", state["teal_hidden"] == 0, state)


# -- C ------------------------------------------------------------------------------------------
def c_zoom():
    from sciforge import simulation_glyphs as g

    state["size"] = g.size()
    view = Gui.ActiveDocument.ActiveView
    view.zoomOut()
    view.zoomOut()


def c_check():
    from sciforge import simulation_glyphs as g

    g.follow_zoom()
    h.check(
        "zoomed out: the glyphs grow in mm (same on the screen)",
        g.size() > state["size"] * 1.3,
        (state["size"], g.size()),
    )


# -- D ------------------------------------------------------------------------------------------
def d_leave():
    s.workspace("Design")


def d_check():
    h.fit()
    image = picture("design")
    orange = count(image, ORANGE)
    h.check("no glyph left in DESIGN", orange == 0 and count(image, TEAL) == 0, orange)
    fixed = [i for i in s.items("constraint")]
    if fixed:
        fixed[0].Suppressed = True  # (nothing holds the bracket now)
        App.ActiveDocument.recompute()
    s.workspace("Simulation")


# -- E ------------------------------------------------------------------------------------------
def e_dof():
    h.fit()
    state["magenta_before"] = count(picture("before-dof"), MAGENTA)
    s.menu_item("DISPLAY", "DOF View")


def e_check():
    from sciforge import simulation_ui

    h.check("DOF View on", simulation_ui.dof_on())
    h.check("six free movements", s.glyph_counts().get("dof") == 6, s.glyph_counts())
    magenta = count(picture("dof"), MAGENTA)
    h.check(
        "its arrows are drawn",
        magenta > 20 and state["magenta_before"] == 0,
        (state["magenta_before"], magenta),
    )
    s.menu_item("DISPLAY", "DOF View")


def e_off():
    from sciforge import simulation_ui

    h.check("DOF View off", not simulation_ui.dof_on())
    magenta = count(picture("dof-off"), MAGENTA)
    h.check("its arrows are gone", magenta == 0, magenta)


h.run(
    "sim_setup_glyphs",
    [
        setup,
        enter,
        a_counts,
        b_shown_hidden,
        c_zoom,
        c_check,
        d_leave,
        d_check,
        e_dof,
        e_check,
        e_off,
    ],
)
