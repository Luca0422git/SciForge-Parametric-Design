# SPDX-License-Identifier: LGPL-2.1-or-later
"""VEX: a drivetrain of about 300 parts (SciForge's own VEX-like parts: rails, cross members,
angles, a plate, shafts, bearings, standoffs, 130 screws and 130 Keps nuts; every part file
inserted once, the repeats occurrences of it: SciForgeTests/fixtures/vex/vex_robot.py), and
how long what a person does with it takes (docs/sciforge/parity/vex-assembly.md, "Speed").

  A  The robot is built (inserted) and saved: under 10 s to save.
  B  Closed and opened again: under 30 s; every part is there, the shaft's joint too.
  C  The browser and the timeline read the design again (a refresh): under 0.3 s.
  D  Orbit: a camera turn redrawn.
  E  J: the mouse onto a rail's web (a steel 1x5x1x35 with 245 square holes): its hole
     centres light up; how long the first time (the part's snap index is made) and the next
     times (under 0.1 s).
  F  Drive Joints on a shaft's revolute: each step of the slider follows live.
  G  A recompute after the screw's part changed (every screw occurrence follows).
  H  Twenty STEP files in one go (another design), with what the time went on.

The times are written to vex-perf.json next to the test output (best and spread of a few
tries: other programs share this machine).
"""

import cProfile
import io
import json
import os
import pstats
import shutil
import statistics
import tempfile
import time

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtWidgets

from SciForgeTests.fixtures.vex import vex_parts as vp
from SciForgeTests.fixtures.vex import vex_robot
from SciForgeTests.gui import harness as h
from SciForgeTests.gui import vex_steps as vx

S = {}
TIMES = {}


def out_dir():
    return os.environ.get("SCIFORGE_SMOKE_OUT") or tempfile.gettempdir()


def pump(seconds=0.0):
    end = time.perf_counter() + seconds
    while True:
        QtWidgets.QApplication.processEvents()
        if time.perf_counter() >= end:
            break


def note(label, values):
    """Record a measurement: one number or a list of tries (best, median, worst kept)."""
    if isinstance(values, (list, tuple)):
        TIMES[label] = {
            "best": min(values),
            "median": statistics.median(values),
            "worst": max(values),
            "tries": len(values),
        }
    else:
        TIMES[label] = values
    print("[SciForge] vex perf: %s = %s" % (label, TIMES[label]), flush=True)
    with open(os.path.join(out_dir(), "vex-perf.json"), "w", encoding="utf-8") as handle:
        json.dump(TIMES, handle, indent=1, sort_keys=True, default=str)


def profile_top(pr, n=22):
    s = io.StringIO()
    pstats.Stats(pr, stream=s).sort_stats("cumulative").print_stats(n)
    return s.getvalue()


def comps():
    from sciforge import components

    return components.list_components(App.ActiveDocument)


# -- A ---------------------------------------------------------------------------------------------
def profiled(label, fn):
    """fn() under the profiler; its top lines go to the log (what the time went on)."""
    pr = cProfile.Profile()
    pr.enable()
    try:
        return fn()
    finally:
        pr.disable()
        s = io.StringIO()
        stats = pstats.Stats(pr, stream=s)
        stats.sort_stats("cumulative").print_stats(28)
        stats.sort_stats("tottime").print_stats(18)
        print("[SciForge] vex profile of %s:\n%s" % (label, s.getvalue()), flush=True)


def a_build():
    Gui.activateWorkbench("SciForgeWorkbench")
    reuse = os.environ.get("SCIFORGE_VEX_ROBOT", "")
    if reuse and os.path.isfile(reuse):  # (local profiling: a robot saved by an earlier run)
        App.openDocument(reuse)
        S["facts"] = {"parts": len(comps()), "objects": len(App.ActiveDocument.Objects)}
        S["facts"]["joints"] = [1]
        h.fit()
        return
    doc = App.newDocument("VexRobot")
    t0 = time.perf_counter()
    facts = vex_robot.build(doc)
    pump(0.5)
    note("build: robot made (insert + occurrences + recompute + 1 joint)", time.perf_counter() - t0)
    note("build: phases", {k: round(v, 2) for k, v in facts["seconds"].items()})
    S["facts"] = facts
    note("robot: parts / document objects", [facts["parts"], facts["objects"]])
    h.fit()
    h.check("about 300 parts", 290 <= facts["parts"] <= 310, facts["parts"])
    h.check("a shaft's revolute joint", len(facts["joints"]) == 1, facts["joints"])


a_build.wait_ms = 2000


def a_save():
    path = os.path.join(out_dir(), "VexRobot.FCStd")
    if os.path.exists(path):
        os.remove(path)
    S["path"] = path
    t0 = time.perf_counter()
    App.ActiveDocument.saveAs(path)
    seconds = time.perf_counter() - t0
    note("save the robot", seconds)
    h.check("saved in under 10 s", seconds < 10.0, seconds)
    note("robot file size (MB)", round(os.path.getsize(path) / 1e6, 1))


# -- B ---------------------------------------------------------------------------------------------
def b_close():
    App.closeDocument(App.ActiveDocument.Name)
    pump(0.5)


def b_open():
    t0 = time.perf_counter()

    def run():
        App.openDocument(S["path"])
        pump(0.2)

    if os.environ.get("SCIFORGE_VEX_PROFILE"):
        profiled("open", run)
    else:
        run()
    seconds = time.perf_counter() - t0
    S["open"] = seconds
    note("open the robot", seconds)


b_open.wait_ms = 2500


def b_opened():
    from sciforge import joints

    n = len(comps())
    h.check("every part is back", n == S["facts"]["parts"], (n, S["facts"]["parts"]))
    h.check("the joint is back", len(joints.joints(App.ActiveDocument)) == 1)
    h.check("opened in under 30 s", S["open"] < 30.0, S["open"])
    h.fit()


# -- C ---------------------------------------------------------------------------------------------
def c_refresh():
    from sciforge import browser_ui, timeline_ui

    browser = browser_ui.widget()
    if os.environ.get("SCIFORGE_VEX_PROFILE"):
        profiled("browser refresh", lambda: browser.refresh(force=True))
    tries = []
    for _ in range(4):
        t0 = time.perf_counter()
        browser.refresh(force=True)
        QtWidgets.QApplication.processEvents()
        tries.append(time.perf_counter() - t0)
    note("browser refresh (forced)", tries)
    h.check("the browser refreshes in under 0.3 s", min(tries) < 0.3, tries)
    timeline = timeline_ui.widget()
    if timeline is not None:
        tries = []
        for _ in range(4):
            t0 = time.perf_counter()
            timeline.refresh(force=True)
            QtWidgets.QApplication.processEvents()
            tries.append(time.perf_counter() - t0)
        note("timeline refresh (forced)", tries)


# -- D ---------------------------------------------------------------------------------------------
def d_orbit():
    from pivy import coin

    h.fit()
    pump(0.2)
    cam = h.view().getCameraNode()
    start = cam.orientation.getValue()
    tries = []
    for _ in range(20):
        t0 = time.perf_counter()
        cam.orientation.setValue(
            cam.orientation.getValue() * coin.SbRotation(coin.SbVec3f(0, 0, 1), 0.05)
        )
        h.view().redraw()
        QtWidgets.QApplication.processEvents()
        tries.append(time.perf_counter() - t0)
    cam.orientation.setValue(start)
    note("orbit: one frame", tries)


# -- E ---------------------------------------------------------------------------------------------
def rail_web_point(i, j):
    """A point on the first rail's web top, next to its hole (i, j) (on the metal)."""
    rail = S["rail"]
    plc = rail.getGlobalPlacement()
    return plc.multVec(
        App.Vector(vp.PITCH / 2.0 + i * vp.PITCH + 3.6, vp.PITCH / 2.0 + j * vp.PITCH, vp.STEEL)
    )


def e_hover():
    from sciforge import hole_snaps

    names = {c.Label: c for c in comps()}
    S["rail"] = names.get("c_channel_1x5x1x35")
    h.click_empty()
    h.fit()
    h.press("j")
    pump(0.3)
    hole_snaps.forget()  # the first hover over the rail makes its index (as after opening)
    hov = vx.panel().hover
    times = []
    for k, (i, j) in enumerate([(30, 2), (30, 2), (31, 2), (29, 3), (28, 3)]):
        point = rail_web_point(i, j)
        vx.look_at(point, 60.0)
        hov.clear()
        h.uncover(point)
        h.move(h.screen_point(point))
        t0 = time.perf_counter()
        hov._update()
        times.append(time.perf_counter() - t0)
        if k == 0:
            S["first"] = times[0]
    S["hover"] = times[1:]
    S["hot"] = hov.hot


def e_check():
    hot = S.get("hot")
    h.check(
        "the rail's hole centre is lit",
        hot is not None and hot["kind"] == "loop",
        hot and hot["kind"],
    )
    note("hover a rail's web: first time (snap index made)", S["first"])
    note("hover a rail's web: next times", S["hover"])
    h.check("hover dots in under 0.1 s", min(S["hover"]) < 0.1, S["hover"])
    h.press(QtCore.Qt.Key_Escape)


# -- F ---------------------------------------------------------------------------------------------
def f_drive():
    from sciforge import joints

    joint = joints.joints(App.ActiveDocument)[0]
    if os.environ.get("SCIFORGE_VEX_PROFILE"):
        profiled("drive", lambda: joints.drive(joint, angle=5.0))
    tries = []
    for k in range(12):
        t0 = time.perf_counter()
        joints.drive(joint, angle=15.0 * (k + 1))
        QtWidgets.QApplication.processEvents()
        tries.append(time.perf_counter() - t0)
    joints.drive(joint, angle=0.0)
    note("drive the shaft's joint: one step", tries)
    h.check(
        "driving stays live (a step well under a second)", statistics.median(tries) < 1.0, tries
    )


# -- G ---------------------------------------------------------------------------------------------
def g_recompute():
    from sciforge import components

    doc = App.ActiveDocument
    screw = {c.Label: c for c in comps()}.get("screw_8_32_x_0_5")
    body = components.bodies_in(doc, screw, recursive=True)[0]
    base = body.BaseFeature
    tries = []
    for _ in range(2):
        base.touch()
        t0 = time.perf_counter()
        doc.recompute()
        QtWidgets.QApplication.processEvents()
        tries.append(time.perf_counter() - t0)
    note("recompute after the screw's part changed (130 occurrences follow)", tries)


# -- H ---------------------------------------------------------------------------------------------
def h_twenty():
    from sciforge import exchange_ui

    files = vp.write_all(vp.default_folder())
    folder = tempfile.mkdtemp(prefix="sciforge-vex-twenty-")
    names = [n for n in sorted(files) if n != "c_channel_1x5x1x35"][:10]
    paths = []
    for k in range(2):
        for name in names:
            target = os.path.join(folder, "%s_%d.step" % (name, k + 1))
            shutil.copy(files[name], target)
            paths.append(target)
    App.newDocument("VexTwenty")
    h.fit()
    pr = cProfile.Profile()
    t0 = time.perf_counter()
    pr.enable()
    made = exchange_ui.insert_cad_files(paths, place=False)
    pr.disable()
    seconds = time.perf_counter() - t0
    pump(0.3)
    note("insert twenty STEP files in one go", seconds)
    print(profile_top(pr), flush=True)
    h.check("twenty in", len(made) == 20, len(made))


h.run(
    "vex_robot",
    [
        a_build,
        a_save,
        b_close,
        b_open,
        b_opened,
        c_refresh,
        d_orbit,
        e_hover,
        e_check,
        f_drive,
        g_recompute,
        h_twenty,
    ],
)
