# SPDX-License-Identifier: LGPL-2.1-or-later
"""The SIMULATION workspace's right-click ring on each tab (sim QA), on a solved cantilever.

A  RESULTS: a right click on the 3D view offers the result tools (Surface Probes, Show
   Min/Max, Animate, Results Details, Finish Results, Report; Slice Plane and Reaction Force
   in the list), none of SETUP's (it showed SETUP's ring: Structural Loads, Pre-check...).
   Results Details from the ring opens the details window.
B  Surface Probes from the ring; Close; the ring then offers Repeat Surface Probes.
C  The SETUP tab: the ring is SETUP's again (Structural Loads...), without the result tools,
   and its Repeat is not a RESULTS tool.
D  Finish Results from the RESULTS ring: back to SETUP.
"""

from PySide import QtCore, QtWidgets

from SciForgeTests.gui import harness as h
from SciForgeTests.gui import simres_steps as s
from SciForgeTests.gui import sketch_input as si
from SciForgeTests.gui import widget_input as w

RESULT_TOOLS = (
    "Surface Probes",
    "Show Min/Max",
    "Animate",
    "Results Details",
    "Finish Results",
    "Report",
    "Slice Plane",
    "Reaction Force",
)
SETUP_ONLY = ("Structural Loads", "Structural Constraints", "Pre-check", "Study Materials")


def _open_menu():
    from sciforge import marking_menu

    marking_menu._last_menu["widget"] = None
    gl = h.gl_widget()
    w.click(gl, QtCore.QPoint(gl.width() - 140, 140), button=QtCore.Qt.RightButton)
    menu = marking_menu._last_menu["widget"]
    h.check("a right click opens the marking menu", menu is not None and menu.isVisible())
    return menu


def _labels(menu):
    if menu is None:
        return []
    ring = [b.text() for b in menu.findChildren(QtWidgets.QToolButton)]
    listing = menu.findChild(QtWidgets.QListWidget, "SciForgeMarkingList")
    rows = [listing.item(i).text() for i in range(listing.count())] if listing else []
    return ring + rows


def enter():
    s.workspace("Simulation")


def results():
    s.close_new_study_dialog()
    s.click_tab("sim_results")


# -- A ------------------------------------------------------------------------------------------
def a_menu():
    h.check("results shown", s.session() is not None)
    h.fit()
    labels = _labels(_open_menu())
    for name in RESULT_TOOLS:
        h.check("A the RESULTS ring offers %s" % name, name in labels, labels)
    for name in SETUP_ONLY:
        h.check("A no SETUP command %s" % name, name not in labels, labels)
    si.marking_slot("Results Details")


def a_details():
    h.check("A Results Details opened from the ring", s.dialog("SciForgeSimDetails") is not None)
    d = s.dialog("SciForgeSimDetails")
    if d is not None:
        d.close()


# -- B ------------------------------------------------------------------------------------------
def b_probes():
    _open_menu()
    si.marking_slot("Surface Probes")


def b_open():
    panel = s.task_panel()
    h.check(
        "B Surface Probes opened from the ring",
        panel is not None and panel.title == "Surface Probes",
    )
    h.task_button("Close")


def b_repeat():
    labels = _labels(_open_menu())
    h.check("B Repeat Surface Probes", "Repeat Surface Probes" in labels, labels)
    from sciforge import marking_menu

    menu = marking_menu._last_menu["widget"]
    if menu is not None:
        menu.close()


# -- C ------------------------------------------------------------------------------------------
def c_setup():
    s.click_tab("sim_setup")


def c_menu():
    h.check("C the SETUP tab", s.current_tab() == "sim_setup", s.current_tab())
    labels = _labels(_open_menu())
    for name in SETUP_ONLY:
        h.check("C the SETUP ring offers %s" % name, name in labels, labels)
    for name in ("Surface Probes", "Finish Results", "Results Details"):
        h.check("C no result tool %s" % name, name not in labels, labels)
    h.check(
        "C its Repeat is not a RESULTS tool",
        not any(x.startswith("Repeat Surface") for x in labels),
        labels,
    )
    from sciforge import marking_menu

    menu = marking_menu._last_menu["widget"]
    if menu is not None:
        menu.close()


# -- D ------------------------------------------------------------------------------------------
def d_results():
    s.click_tab("sim_results")


def d_finish():
    _open_menu()
    si.marking_slot("Finish Results")


def d_check():
    h.check(
        "D Finish Results from the ring: SETUP", s.current_tab() == "sim_setup", s.current_tab()
    )
    h.check("D no results on the screen", s.session() is None)


h.run(
    "sim_qa_menus",
    [
        s.new_solved_beam("SimQAMenus"),
        enter,
        results,
        a_menu,
        a_details,
        b_probes,
        b_open,
        b_repeat,
        c_setup,
        c_menu,
        d_results,
        d_finish,
        d_check,
    ],
    paced_by="state",
)
