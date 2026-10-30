# SPDX-License-Identifier: LGPL-2.1-or-later
"""VEX: many STEP parts in one go, and the same part again (docs/sciforge/parity/vex-assembly.md).
The parts are SciForge's own VEX-like parts (SciForgeTests/fixtures/vex), never VEX's files.

  P1  INSERT > Insert STEP with ten files picked at once: ten components named after the
      files, laid side by side along X (no two on top of each other), the Move dialog on all
      of them; Esc leaves them there.
  P2  One Ctrl+Z takes all ten away; Ctrl+Y brings them back.
  P3  The screw's file again: another occurrence of the screw ("screw_8_32_x_0_5:2", linked
      to the first: same solid), not a second copy read from the file; its Move dialog.
  P4  Twenty files in one go (another design): all in, timed.
  P5  Data Panel: Upload takes three files at once; two STEP cards selected, right-click >
      Insert into Current Design: both come in (one undo step).
  P6  A STEP card dragged from the Data Panel into the 3D view comes in as a component.
"""

import os
import shutil
import tempfile
import time

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets

from SciForgeTests.gui import harness as h
from SciForgeTests.gui import polish2_steps as p2
from SciForgeTests.gui import vex_steps as vx
from SciForgeTests.gui import widget_input as wi

S = {}
TEN = [
    "c_channel_1x2x1x25",
    "c_channel_1x2x1x5",
    "c_channel_1x2x1x5_round",
    "angle_2x2x25",
    "plate_5x25",
    "standoff_1in",
    "screw_8_32_x_0_5",
    "keps_nut",
    "shaft_3in",
    "bearing_flat",
]


def comps():
    from sciforge import components

    return components.list_components(App.ActiveDocument)


def comp(label):
    for c in comps():
        if c.Label == label:
            return c
    return None


def use_files(paths):
    from sciforge import insert_ui

    insert_ui.FILE_PICKER = lambda kind, p=list(paths): p


def no_files():
    from sciforge import insert_ui

    insert_ui.FILE_PICKER = None


def move_panel():
    from sciforge import component_move_ui, taskui

    p = taskui.current()
    return p if isinstance(p, component_move_ui.ComponentMovePanel) else None


# -- setup -----------------------------------------------------------------------------------------
def setup():
    Gui.activateWorkbench("SciForgeWorkbench")
    S["files"] = vx.step_files(TEN)
    S["project"] = tempfile.mkdtemp(prefix="sciforge-vex-project-")
    p2.set_project(S["project"])
    App.newDocument("VexInsert")
    h.fit()
    h.check("ten STEP files made", len(S["files"]) == 10, list(S["files"]))


setup.wait_ms = 1500


# -- P1 --------------------------------------------------------------------------------------------
def p1_insert():
    use_files([S["files"][n] for n in TEN])
    S["t0"] = time.perf_counter()
    vx.menu("INSERT", "Insert STEP")
    S["insert10"] = time.perf_counter() - S["t0"]


p1_insert.wait_ms = 2500
# ten VEX parts inserted, then what the app does after (browser, timeline, joints): about 10 s
# here, three times that under --stress; a hang is far longer
p1_insert.timeout_s = 120


def p1_check():
    labels = sorted(c.Label for c in comps() if c.Label in TEN)
    h.check("P1 ten components named after the files", labels == sorted(TEN), labels)
    boxes = []
    for name in TEN:
        c = comp(name)
        if c is not None:
            boxes.append(vx.bbox(c))
    boxes.sort(key=lambda b: b.XMin)
    apart = all(boxes[i].XMax < boxes[i + 1].XMin + 1e-6 for i in range(len(boxes) - 1))
    h.check("P1 laid side by side along X (none on top of another)", apart and len(boxes) == 10)
    p = move_panel()
    picked = getattr(p, "picks", None) if p is not None else None
    h.check("P1 the Move dialog places them", p is not None, p)
    if picked is not None:
        h.check("P1 ... all ten", len(picked) == 10, len(picked))
    print("[SciForge] vex: ten STEP files inserted in %.2f s" % S["insert10"], flush=True)
    h.shot("P1-ten")
    h.press(QtCore.Qt.Key_Escape)


p1_check.wait_ms = 1000


def p1_after_esc():
    h.check("P1 Esc: the dialog closed", move_panel() is None)
    h.check("P1 the ten stay", len([c for c in comps() if c.Label in TEN]) == 10)


# -- P2 --------------------------------------------------------------------------------------------
def p2_undo():
    vx.undo()


p2_undo.wait_ms = 1500


def p2_undone():
    h.check("P2 one Ctrl+Z takes all ten away", not comps(), [c.Label for c in comps()])
    vx.redo()


p2_undone.wait_ms = 1500


def p2_redone():
    labels = sorted(c.Label for c in comps())
    h.check("P2 Ctrl+Y brings them back", labels == sorted(TEN), labels)


# -- P3 --------------------------------------------------------------------------------------------
def p3_again():
    use_files([S["files"]["screw_8_32_x_0_5"]])
    vx.menu("INSERT", "Insert STEP")


p3_again.wait_ms = 2000


def p3_occurrence():
    from sciforge import instances

    first = comp("screw_8_32_x_0_5")
    second = comp("screw_8_32_x_0_5:2")
    h.check(
        "P3 the screw again: screw_8_32_x_0_5:2", second is not None, [c.Label for c in comps()]
    )
    if second is None or first is None:
        return
    h.check(
        "P3 an occurrence of the first screw (linked)",
        instances.is_instance(second) and instances.source_of(second) is first,
    )
    v1 = vx.body_of(first).Shape.Volume
    v2 = vx.body_of(second).Shape.Volume
    h.check("P3 the same solid", abs(v1 - v2) < 1e-6 * v1, (v1, v2))
    h.check("P3 no second component read from the file", len(comps()) == 11, len(comps()))
    p = move_panel()
    h.check("P3 the Move dialog places it", p is not None)
    h.press(QtCore.Qt.Key_Escape)


p3_occurrence.wait_ms = 800


def p3_undo():
    vx.undo()


p3_undo.wait_ms = 1200


def p3_undone():
    h.check("P3 Ctrl+Z: the occurrence goes", comp("screw_8_32_x_0_5:2") is None)
    no_files()


# -- P4 --------------------------------------------------------------------------------------------
def p4_twenty():
    folder = tempfile.mkdtemp(prefix="sciforge-vex-twenty-")
    paths = []
    for k in range(2):
        for name in TEN:
            target = os.path.join(folder, "%s_%d.step" % (name, k + 1))
            shutil.copy(S["files"][name], target)
            paths.append(target)
    S["twenty"] = paths
    App.newDocument("VexTwenty")
    h.fit()
    use_files(paths)
    t0 = time.perf_counter()
    vx.menu("INSERT", "Insert STEP")
    S["insert20"] = time.perf_counter() - t0


p4_twenty.wait_ms = 2500
p4_twenty.timeout_s = 120  # (twenty parts: about 17 s with what follows, as p1_insert)


def p4_check():
    n = len([c for c in comps() if c.Label.endswith(("_1", "_2"))])
    h.check("P4 twenty components", n == 20, [c.Label for c in comps()])
    print("[SciForge] vex: twenty STEP files inserted in %.2f s" % S["insert20"], flush=True)
    h.check("P4 twenty files in under a minute here", S["insert20"] < 60.0 * h.SLOWDOWN, S["insert20"])
    h.press(QtCore.Qt.Key_Escape)
    no_files()


def p4_close():
    Gui.getDocument("VexTwenty").Modified = False
    App.closeDocument("VexTwenty")


# -- P5 --------------------------------------------------------------------------------------------
def ui():
    from sciforge import versions_ui

    return versions_ui


def panel():
    return ui().panel()


def card(text_start):
    lst = panel().list
    for i in range(lst.count()):
        if lst.item(i).text().startswith(text_start):
            return lst.item(i)
    return None


def p5_panel():
    h.check("back on the first design", App.ActiveDocument.Name == "VexInsert")
    h.fit()
    ui().show_panel()


p5_panel.wait_ms = 1000


def p5_upload():
    files = [S["files"][n] for n in ("shaft_3in", "keps_nut", "bearing_flat")]
    ui().UPLOAD_PICKER = lambda f=files: f
    try:
        p = panel()
        if h.check("P5 the Data Panel", p is not None):
            p.set_folder(S["project"])
            wi.click(p.upload)
    finally:
        ui().UPLOAD_PICKER = None


p5_upload.wait_ms = 1500


def p5_cards_names():
    doc = App.ActiveDocument
    print("[SciForge] vex: before P5 %s comps %d" % (doc.UndoNames[:3], len(comps())), flush=True)


def p5_cards():
    p5_cards_names()
    names = sorted(os.listdir(S["project"]))
    wanted = ["bearing_flat.step", "keps_nut.step", "shaft_3in.step"]
    h.check("P5 Upload took three files at once", all(n in names for n in wanted), names)
    lst = panel().list
    a, b = card("shaft_3in"), card("keps_nut")
    if not h.check("P5 their cards", a is not None and b is not None):
        return
    wi.click(lst.viewport(), lst.visualItemRect(a).center())
    wi.click(lst.viewport(), lst.visualItemRect(b).center(), modifiers=QtCore.Qt.ControlModifier)
    S["before"] = len(comps())


def p5_insert():
    lst = panel().list
    b = card("keps_nut")
    ok = wi.right_click(
        lst.viewport(), lst.visualItemRect(b).center(), "Insert into Current Design"
    )
    h.check("P5 right-click > Insert into Current Design", ok)


p5_insert.wait_ms = 2500


def p5_inserted():
    labels = sorted(c.Label for c in comps())
    # (copies uploaded into the project: other files than the ones inserted in P1, so they
    # come in as parts of their own, "shaft_3in (2)", not as occurrences)
    h.check(
        "P5 both selected STEP files came in",
        len(comps()) == S["before"] + 2 and "shaft_3in (2)" in labels and "keps_nut (2)" in labels,
        labels,
    )
    h.press(QtCore.Qt.Key_Escape)


p5_inserted.wait_ms = 800


def p5_undo():
    h.check("P5 the Move dialog closed", move_panel() is None)
    doc = App.ActiveDocument
    print("[SciForge] vex: undo list %s on %s" % (doc.UndoNames[:4], doc.Name), flush=True)
    h.click_empty()  # back in the 3D view (the Data Panel had the window's focus)
    gdoc = Gui.ActiveDocument
    mdi = Gui.getMainWindow().findChild(QtWidgets.QMdiArea)
    sub = mdi.activeSubWindow() if mdi is not None else None
    print(
        "[SciForge] vex: gui doc %s, window %s"
        % (gdoc and gdoc.Document.Name, sub and sub.windowTitle()),
        flush=True,
    )
    vx.undo()
    print("[SciForge] vex: undo list after %s" % (doc.UndoNames[:4],), flush=True)


p5_undo.wait_ms = 1200


def p5_undone():
    doc = App.ActiveDocument
    print(
        "[SciForge] vex: after undo %s redo %s comps %s"
        % (doc.UndoNames[:3], doc.RedoNames[:3], sorted(c.Label for c in comps())),
        flush=True,
    )
    h.check("P5 one Ctrl+Z takes both away", len(comps()) == S["before"], len(comps()))


# -- P6 --------------------------------------------------------------------------------------------
def dpu():
    from sciforge import data_panel_ui

    return data_panel_ui


def _send(widget, kind, pos, mime):
    actions = QtCore.Qt.CopyAction | QtCore.Qt.MoveAction
    if kind == "enter":
        event = QtGui.QDragEnterEvent(pos, actions, mime, QtCore.Qt.LeftButton, wi.NONE)
    elif kind == "move":
        event = QtGui.QDragMoveEvent(pos, actions, mime, QtCore.Qt.LeftButton, wi.NONE)
    else:
        event = QtGui.QDropEvent(QtCore.QPointF(pos), actions, mime, QtCore.Qt.LeftButton, wi.NONE)
    event.ignore()
    QtWidgets.QApplication.sendEvent(widget, event)
    return event.isAccepted()


def p6_drag_card():
    item = card("bearing_flat")
    if not h.check("P6 the bearing flat's card", item is not None):
        return
    carried = []
    dpu().DRAG_HOOK = carried.append
    try:
        lst = panel().list
        wi.click(lst.viewport(), lst.visualItemRect(item).center())
        start = lst.visualItemRect(item).center()
        wi.drag(lst.viewport(), start, h.gl_widget().mapToGlobal(h.gl_widget().rect().center()))
    finally:
        dpu().DRAG_HOOK = None
    path = os.path.join(S["project"], "bearing_flat.step")
    h.check(
        "P6 a STEP card can be dragged (it carries its file)",
        [[os.path.normcase(p) for p in c] for c in carried] == [[os.path.normcase(path)]],
        carried,
    )
    S["before"] = len(comps())
    gl = h.gl_widget()
    mime = dpu().make_mime([path])
    watch = dpu().DropSession()
    try:
        accepted = [_send(gl, k, gl.rect().center(), mime) for k in ("enter", "move", "drop")]
    finally:
        pending = watch.finish()
    h.check("P6 the 3D view takes the STEP card", accepted == [True] * 3, accepted)
    h.check("P6 an insert is asked for", pending is not None and pending[0] == "view", pending)


p6_drag_card.wait_ms = 3000


def p6_inserted():
    labels = sorted(c.Label for c in comps())
    h.check(
        "P6 the bearing flat came in",
        len(comps()) == S["before"] + 1 and any(x.startswith("bearing_flat") for x in labels),
        labels,
    )
    h.press(QtCore.Qt.Key_Escape)
    h.shot("P6-dropped")


p6_inserted.wait_ms = 800


h.run(
    "vex_insert_many",
    [
        setup,
        p1_insert,
        p1_check,
        p1_after_esc,
        p2_undo,
        p2_undone,
        p2_redone,
        p3_again,
        p3_occurrence,
        p3_undo,
        p3_undone,
        p4_twenty,
        p4_check,
        p4_close,
        p5_panel,
        p5_upload,
        p5_cards,
        p5_insert,
        p5_inserted,
        p5_undo,
        p5_undone,
        p6_drag_card,
        p6_inserted,
    ],
)
