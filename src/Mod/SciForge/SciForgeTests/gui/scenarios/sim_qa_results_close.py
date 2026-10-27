# SPDX-License-Identifier: LGPL-2.1-or-later
"""A design closed while a probe tool of its results is open (sim QA): SciForge crashed.

Closing the design destroys its 3D view; Qt then tells the view's widget that the mouse left
it, and the probes' hover drew its tags at once (asking the dying view where each tag is): a
segmentation fault, every open design lost (found at the end of the bracket journey, made
plain here). The hover now clears a moment later, only while its results still show.

A  A solved beam, RESULTS, Surface Probes, the mouse over the result (the value under it
   shows), the design closed with the dialog open: no crash, the dialog ended, no results
   left, no error.
B  A second beam, Point Probes, the mouse over the result, its design closed: the same.
C  A third design opens and solves after it (SciForge still works).
"""

import FreeCAD as App
import FreeCADGui as Gui

from SciForgeTests.gui import harness as h
from SciForgeTests.gui import simres_steps as s

state = {}


def enter():
    s.workspace("Simulation")


def results():
    s.close_new_study_dialog()
    s.click_tab("sim_results")


def tool(label):
    def open_tool():
        h.check("%s: results shown" % label, s.session() is not None)
        if label == "Point Probes":
            s.menu("INSPECT", label)
        else:
            s.big(label)

    open_tool.__name__ = "open_" + label.replace(" ", "_")
    return open_tool


def hover(tag):
    def move():
        sess = s.session()
        node = sess.display.nodes.tolist()[len(sess.display.nodes) // 2]
        h.move(h.screen_point(App.Vector(*sess.display.node_place(node))))

    move.__name__ = "hover_" + tag
    move.wait_ms = 500
    return move


def close(tag):
    def close_doc():
        state[tag] = App.ActiveDocument.Name
        h.check("%s: the dialog is open" % tag, s.task_panel() is not None)
        App.closeDocument(state[tag])  # (the tab's close button, Don't Save)

    close_doc.__name__ = "close_" + tag
    return close_doc


def closed(tag):
    def check():
        h.check("%s: the design closed (no crash)" % tag, state[tag] not in App.listDocuments())
        h.check("%s: its dialog ended" % tag, not Gui.Control.activeDialog())
        h.check("%s: no results left" % tag, s.session() is None)

    check.__name__ = "closed_" + tag
    check.wait_ms = 800
    return check


def c_solved():
    stats = s.stats("displacement")
    h.check("C a new design solves after it", stats.get("max", 0) > 0, stats)


h.run(
    "sim_qa_results_close",
    [
        s.new_solved_beam("SimQAClosedA"),
        enter,
        results,
        tool("Surface Probes"),
        hover("A"),
        close("A"),
        closed("A"),
        s.new_solved_beam("SimQAClosedB"),
        enter,
        results,
        tool("Point Probes"),
        hover("B"),
        close("B"),
        closed("B"),
        s.new_solved_beam("SimQAClosedC"),
        c_solved,
    ],
)
