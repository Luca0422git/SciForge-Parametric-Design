# SPDX-License-Identifier: LGPL-2.1-or-later
"""The Static Stress engine with the window up, checked by the engine's QA (beta 3,
sim-engine-qa): what sim-results found while building the RESULTS tab.

A  A steel cantilever 100 x 10 x 10 mm and a study of the whole design (no bodies chosen):
   Fixed at one end, 100 N down at the other.
B  Solve as the Solve dialog does (a QTimer polls the Job): done; afterwards no object of the
   design is left "touched" (FreeCAD's recompute mark), not even after the window has drawn,
   or after a setting of the study changed (it has nothing to compute).
C  The body's eye off (the RESULTS tab says to do it to look inside), and back on: the results
   are not out of date, and the study's bodies are the same (they went by the eyes).
D  A new body, hidden, in the design: a study of the whole design takes it in (hidden is not
   left out: Fusion's simulation model is the design's bodies), so the results are out of
   date, and the pre-check names it as held by nothing; leaving it out of the study (Study
   Materials) makes it solvable again.
E  A Gui document observer that reads the view providers it is told about (another tool's,
   as sim-results' was): a solve still works.
F  Nothing printed as an error at any step (the harness checks after every step).
"""

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore

from SciForgeTests.gui import harness as h

S = {"job": None, "timer": None, "observer": None}


def _sim():
    from sciforge import simulation

    return simulation


def _touched(doc):
    return [o.Name for o in doc.Objects if "Touched" in (o.State or [])]


def _body(doc, name, x, shown=True):
    import Part

    from sciforge import bodies

    base = doc.addObject("Part::Feature", name + "Shape")
    base.Shape = bodies.baked(Part.makeBox(100, 10, 10, App.Vector(x, 0, 0)))
    body = doc.addObject("PartDesign::Body", name)
    body.BaseFeature = base
    doc.recompute()
    base.Visibility = False
    if not shown:
        body.ViewObject.Visibility = False
    return body


def setup():
    Gui.activateWorkbench("SciForgeWorkbench")
    doc = App.newDocument("SimQAEngine")
    body = _body(doc, "Beam", 0.0)
    sim = _sim()
    S["doc"], S["body"] = doc, body
    S["study"] = sim.create_study(doc)
    faces = body.Shape.Faces
    root = [i for i, f in enumerate(faces, 1) if abs(f.CenterOfMass.x) < 1e-6][0]
    tip = [i for i, f in enumerate(faces, 1) if abs(f.CenterOfMass.x - 100) < 1e-6][0]
    sim.add_item(S["study"], "constraint", "fixed", [(body, "Face%d" % root)])
    sim.add_item(
        S["study"],
        "load",
        "force",
        [(body, "Face%d" % tip)],
        {"direction": "vector", "vector": [0, 0, -1], "magnitude": 100.0},
    )
    doc.recompute()
    Gui.SendMsgToActiveView("ViewFit")


def _tick():
    job = S["job"]
    if job is None:
        return
    try:
        state = job.poll()  # (the Solve dialog's timer does exactly this)
    except Exception as exc:  # poll never raises; a failure here is a bug
        h.check("Job.poll raised", False, str(exc))
        state = "failed"
    if state != "running":
        S["timer"].stop()


def _start():
    S["job"] = _sim().Job(S["study"])
    timer = S["timer"] = QtCore.QTimer()
    timer.setInterval(100)
    timer.timeout.connect(_tick)
    timer.start()


def _wait_for(cond, name, seconds=120):
    """A step that waits until cond() (a mesh and a solve: up to `seconds`)."""

    def step():
        pass

    step.__name__ = name
    step.done = cond
    step.done_what = "the job: " + name.replace("_", " ")
    step.timeout_s = seconds
    return step


def start_solve():
    _start()


def after_solve():
    job = S["job"]
    h.check("B: done", job.state == "done", (job.state, job.message))
    touched = _touched(S["doc"])
    h.check("B: nothing left touched right after the solve", not touched, touched)


def after_drawing():
    touched = _touched(S["doc"])
    h.check("B: nothing touched after the window drew the results", not touched, touched)
    # a setting changed after the solve (Keep results in the file) and a study material set
    # back to the body's own: the study has nothing to compute, so nothing asks to recompute
    sim = _sim()
    sim.set_settings(S["study"], {"keep_results": True})
    sim.set_study_material(S["study"], S["body"], None)
    touched = _touched(S["doc"])
    h.check("B: a setting changed after the solve leaves nothing touched", not touched, touched)
    h.check("B: and the results are not out of date", not sim.out_of_date(S["study"]))


def hide_body():
    sim = _sim()
    S["bodies"] = [b.Name for b in sim.study_bodies(S["study"])]
    S["body"].ViewObject.Visibility = False


def hidden():
    sim = _sim()
    h.check("C: the body's eye off: not out of date", not sim.out_of_date(S["study"]))
    names = [b.Name for b in sim.study_bodies(S["study"])]
    h.check("C: the body's eye off: the same bodies", names == S["bodies"], names)
    S["body"].ViewObject.Visibility = True


def shown_again():
    h.check("C: shown again: not out of date", not _sim().out_of_date(S["study"]))


def hidden_new_body():
    sim = _sim()
    S["spare"] = _body(S["doc"], "Spare", 300.0, shown=False)
    names = [b.Name for b in sim.study_bodies(S["study"])]
    h.check("D: a study of the design takes the hidden new body", names == ["Beam", "Spare"], names)
    h.check("D: a new body: out of date", sim.out_of_date(S["study"]))
    errors = [t for level, t in sim.precheck(S["study"]) if level == "error"]
    h.check("D: the pre-check names it", any("Spare" in t for t in errors), errors)
    S["study"].SimBodies = [S["body"]]  # (Study Materials: Spare left out)
    S["doc"].recompute()
    h.check("D: left out: solvable", not any(lv == "error" for lv, _t in sim.precheck(S["study"])))


class _Observer:
    """A Gui document observer like another tool's (sim-results had one): it is told about
    created and changed objects (their view providers) and reads them."""

    def __init__(self):
        self.created = 0
        self.changed = 0

    def slotCreatedObject(self, vp):
        self.created += 1
        for name in ("Visibility", "DisplayMode"):
            getattr(vp, name, None)
        obj = getattr(vp, "Object", None)
        if obj is not None:
            _ = (obj.Name, obj.TypeId)

    def slotChangedObject(self, vp, prop):
        self.changed += 1
        try:
            getattr(vp, prop)
        except Exception:
            pass


def observe_and_solve():
    S["observer"] = _Observer()
    Gui.addDocumentObserver(S["observer"])
    _start()


def after_observed_solve():
    job = S["job"]
    try:
        Gui.removeDocumentObserver(S["observer"])
    except Exception:
        pass
    h.check("E: with a Gui document observer the solve works", job.state == "done", job.message)
    h.check("E: the observer saw the solve's objects", S["observer"].created > 0)


def close():
    App.closeDocument(S["doc"].Name)


h.run(
    "sim_qa_engine",
    [
        setup,
        start_solve,
        _wait_for(lambda: S["job"].state != "running", "wait_done"),
        after_solve,
        after_drawing,
        hide_body,
        hidden,
        shown_again,
        hidden_new_body,
        observe_and_solve,
        _wait_for(lambda: S["job"].state != "running", "wait_observed"),
        after_observed_solve,
        close,
    ],
    paced_by="state",
)
