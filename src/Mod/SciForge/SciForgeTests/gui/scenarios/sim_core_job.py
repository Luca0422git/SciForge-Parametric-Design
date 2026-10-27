# SPDX-License-Identifier: LGPL-2.1-or-later
"""The Static Stress engine with the SciForge window up (beta 3, sim-core): a solve runs as a
simulation.Job polled by a QTimer, as the Solve dialog does, so the window keeps working while
Gmsh and CalculiX run in the background.

A  A steel cantilever 100 x 10 x 10 mm in a study: Fixed at one end (an undo step), 100 N down
   at the other (an undo step), a fine mesh so the solve takes a few seconds.
B  Solve: a QTimer polls the Job every 100 ms; while it runs, Cancel in the middle of the
   solver stage: the job says cancelled, no run is left in the design, no temporary folder,
   no results (the study was never solved).
C  Solve again to the end: done, the tip bends 0.2 mm (beam theory 0.2000, within 3 %), the
   reaction at Fixed 1 is 100 N; the timer kept ticking while Gmsh and CalculiX ran (the
   window was never stuck for long); the undo list is what the setup made (a solve is no
   undo step).
D  Generate Mesh (a mesh-only job): the mesh statistics, the results kept.
E  A third solve cancelled while meshing: the last results stay (same summary, the result
   object still there), nothing left behind.
F  solve_study from SciForge's AI chat: solved, and the window's timers kept running while it
   solved (the window repaints; no mouse or keys meanwhile).
G  Nothing printed as an error at any step (the harness checks after every step).
"""

import os
import time

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore

from SciForgeTests.gui import harness as h

S = {"ticks": [], "stages": [], "job": None, "timer": None}


def _sim():
    from sciforge import simulation

    return simulation


def _run_objects(doc):
    sim = _sim()
    return [o.Name for o in doc.Objects if sim._type(o) in (sim.RUN, sim.MODEL)]


def setup():
    import Part

    from sciforge import bodies

    Gui.activateWorkbench("SciForgeWorkbench")
    doc = App.newDocument("SimCoreJob")
    base = doc.addObject("Part::Feature", "BeamShape")
    base.Shape = bodies.baked(Part.makeBox(100, 10, 10))
    body = doc.addObject("PartDesign::Body", "Beam")
    body.BaseFeature = base
    doc.recompute()
    base.Visibility = False
    sim = _sim()
    S["doc"], S["body"] = doc, body
    S["study"] = sim.create_study(doc)
    sim.set_settings(S["study"], {"mesh": {"size_pct": 2.0}})
    faces = body.Shape.Faces
    root = [i for i, f in enumerate(faces, 1) if abs(f.CenterOfMass.x) < 1e-6][0]
    tip = [i for i, f in enumerate(faces, 1) if abs(f.CenterOfMass.x - 100) < 1e-6][0]
    doc.openTransaction("Add Fixed")
    sim.add_item(S["study"], "constraint", "fixed", [(body, "Face%d" % root)])
    doc.commitTransaction()
    doc.openTransaction("Add Force")
    sim.add_item(
        S["study"],
        "load",
        "force",
        [(body, "Face%d" % tip)],
        {"direction": "vector", "vector": [0, 0, -1], "magnitude": 100.0},
    )
    doc.commitTransaction()
    S["undo"] = list(doc.UndoNames)
    Gui.SendMsgToActiveView("ViewFit")
    h.check("setup: two undo steps", S["undo"][:2] == ["Add Force", "Add Fixed"], S["undo"])


def _tick():
    job = S["job"]
    if job is None:
        return
    now = time.time()
    S["ticks"].append(now)
    try:
        state = job.poll()  # (the Solve dialog's timer does exactly this)
    except Exception as exc:  # poll never raises; a failure here is a bug
        h.check("Job.poll raised", False, str(exc))
        state = "failed"
    if not S["stages"] or S["stages"][-1] != job.stage:
        S["stages"].append(job.stage)
    if state != "running":
        S["timer"].stop()


def _start(mesh_only=False):
    S["ticks"], S["stages"] = [], []
    S["job"] = _sim().Job(S["study"], mesh_only=mesh_only)
    timer = S["timer"] = QtCore.QTimer()
    timer.setInterval(100)
    timer.timeout.connect(_tick)
    timer.start()


def _wait_for(cond, name, tries=600):
    """A step that comes back every 200 ms until cond() (at most `tries` times)."""
    count = {"n": 0}

    def step():
        if not cond() and count["n"] < tries:
            count["n"] += 1
            h.state["queue"].insert(0, step)

    step.__name__ = name
    step.wait_ms = 200
    return step


def start_first():
    _start()


def cancel_in_solver():
    job = S["job"]
    h.check("B: the job reached the solver", job.stage == "solve", (job.state, job.stage))
    job.cancel()


def after_cancel():
    job = S["job"]
    h.check("B: cancelled", job.state == "cancelled", (job.state, job.message))
    h.check("B: no run left in the design", not _run_objects(S["doc"]), _run_objects(S["doc"]))
    h.check("B: never solved: no results", _sim().results(S["study"]) is None)
    h.check("B: its temporary folder is gone", not os.path.isdir(job.work), job.work)


def start_second():
    _start()


def after_solve():
    sim = _sim()
    job = S["job"]
    h.check("C: done", job.state == "done", (job.state, job.message))
    summary = sim.summary(S["study"])
    tip = summary.get("stats", {}).get("displacement", {}).get("max")
    h.check("C: the tip bends 0.2 mm (3 %)", tip is not None and abs(tip - 0.2) <= 0.006, tip)
    reaction = summary.get("reactions", {}).get("Fixed 1", {}).get("total")
    h.check("C: Fixed 1 holds 100 N", reaction is not None and abs(reaction - 100) < 0.5, reaction)
    h.check("C: results to show", sim.results(S["study"]) is not None)
    h.check("C: it meshed, then solved", {"mesh", "solve"} <= set(S["stages"]), S["stages"])
    gaps = [b - a for a, b in zip(S["ticks"], S["ticks"][1:])]
    # (the freezes this guards against were 84 s and ~10 min; a CI runner with software GL
    # paused 3.2 s once, in run #277, on the main thread's turn of reading the results)
    h.check(
        "C: the window kept working (the longest pause between timer ticks under 4 s)",
        bool(gaps) and max(gaps) < 4.0,
        "%d ticks, longest pause %.2f s" % (len(gaps), max(gaps) if gaps else -1),
    )
    h.check(
        "C: a solve is no undo step",
        list(S["doc"].UndoNames) == S["undo"],
        (list(S["doc"].UndoNames)[:4], S["undo"]),
    )
    h.check("C: not out of date", not sim.out_of_date(S["study"]))
    S["summary"] = summary
    S["result"] = sim.result_object(S["study"])
    h.check("C: its temporary folder is gone", not os.path.isdir(job.work), job.work)


def start_mesh():
    _start(mesh_only=True)


def after_mesh():
    sim = _sim()
    job = S["job"]
    h.check("D: Generate Mesh done", job.state == "done", (job.state, job.message))
    info = sim.mesh_summary(S["study"])
    h.check(
        "D: mesh statistics",
        info.get("nodes", 0) > 1000 and info.get("elements", 0) > 100 and info.get("smallest"),
        info,
    )
    h.check("D: the mesh object is there", sim.mesh_object(S["study"]) is not None)
    h.check("D: the results stay", sim.result_object(S["study"]) is S["result"])
    h.check("D: its temporary folder is gone", not os.path.isdir(job.work), job.work)


def start_third_and_cancel_in_mesh():
    _start()
    job = S["job"]
    job.poll()  # the first turn checks the study (the pre-check)
    job.poll()  # the second builds the model and starts Gmsh in the background
    h.check("E: the job is meshing", job.stage == "mesh", (job.state, job.stage))
    job.cancel()


def after_second_cancel():
    sim = _sim()
    job = S["job"]
    h.check("E: cancelled", job.state == "cancelled", (job.state, job.message))
    h.check("E: the last results stay", sim.result_object(S["study"]) is S["result"])
    h.check("E: the same summary", sim.summary(S["study"]) == S["summary"])
    runs = _run_objects(S["doc"])
    h.check("E: only the kept runs are in the design", len(runs) == 4, runs)  # results + mesh
    h.check("E: its temporary folder is gone", not os.path.isdir(job.work), job.work)


def ai_solve():
    from sciforge.ai import bridge

    ticks = []
    timer = QtCore.QTimer()
    timer.setInterval(100)
    timer.timeout.connect(lambda: ticks.append(time.time()))
    timer.start()
    started = time.time()
    answer = bridge.call("solve_study", {"study": S["study"].Name}, from_chat=True)
    took = time.time() - started
    timer.stop()
    text = str(answer)
    h.check("F: the AI's solve is done", "solved" in text, text[:300])
    during = [t for t in ticks if started <= t <= started + took]
    h.check(
        "F: the window's timers ran while the AI solved",
        len(during) >= max(1, int(took / 0.5)),
        "%d ticks in %.1f s" % (len(during), took),
    )


def close():
    App.closeDocument(S["doc"].Name)


h.run(
    "sim_core_job",
    [
        setup,
        start_first,
        _wait_for(lambda: S["job"].stage == "solve" or S["job"].state != "running", "wait_solver"),
        cancel_in_solver,
        _wait_for(lambda: S["job"].state != "running", "wait_cancelled"),
        after_cancel,
        start_second,
        _wait_for(lambda: S["job"].state != "running", "wait_done"),
        after_solve,
        start_mesh,
        _wait_for(lambda: S["job"].state != "running", "wait_mesh"),
        after_mesh,
        start_third_and_cancel_in_mesh,
        _wait_for(lambda: S["job"].state != "running", "wait_cancelled2"),
        after_second_cancel,
        ai_solve,
        close,
    ],
)
