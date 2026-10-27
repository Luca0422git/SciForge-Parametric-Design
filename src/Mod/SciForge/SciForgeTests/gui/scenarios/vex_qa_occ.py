# SPDX-License-Identifier: LGPL-2.1-or-later
"""VEX QA (beta 3): occurrences of inserted parts, the way a team uses them, through the real
commands (INSERT > Insert STEP with its file picker, the browser's right-click). SciForge's
own VEX-like parts (SciForgeTests/fixtures/vex), never VEX's files.

  O1  Insert STEP of ten part files at once: ten parts. Esc (the Move dialog).
  O2  Insert STEP of twenty files at once: the same ten again (ten occurrences, "...:2",
      linked to the first) and ten copies of them from another folder (ten parts of their
      own); side by side. One Ctrl+Z takes the twenty away; Ctrl+Y brings them back with
      their solids, where they were, the occurrences still linked.
  O3  A file that changed on disk: the screw's file inserted, then rewritten with a longer
      screw and inserted again: a part of its own with the new length; the first unchanged.
  O4  The first occurrence deleted (the browser's right-click > Delete): its occurrence
      takes over as the part (Fusion keeps a component while an occurrence remains): named
      like the original, no occurrence any more, with its solid, where it was; the browser
      lists it; the parts list still counts it as that part. Ctrl+Z: the original back, the
      occurrence linked again; Ctrl+Y: deleted again, taken over again.
  O5  Save, close, reopen: the part that took over is still there, with its solid; the parts
      list the same.
  O6  Insert STEP of the same file again: an occurrence of the part that took over ("...:2",
      linked to it).
"""

import os
import shutil
import tempfile

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore

from SciForgeTests.fixtures.vex import vex_parts as vp
from SciForgeTests.gui import harness as h
from SciForgeTests.gui import timeline_input as t
from SciForgeTests.gui import vex_steps as vx

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
SCREW = "screw_8_32_x_0_5"


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


def solid(c):
    try:
        body = vx.body_of(c)
        return body is not None and body.Shape.Volume > 1.0
    except Exception:
        return False


def parts_list():
    from sciforge import drawing, drawing_core

    found = [b for b in App.ActiveDocument.Objects if b.TypeId == "PartDesign::Body"]
    return {
        r["PartNumber"]: r["Qty"] for r in drawing_core.parts_rows(drawing.components_of(found))
    }


def esc_move():
    h.press(QtCore.Qt.Key_Escape)


# -- setup -----------------------------------------------------------------------------------------
def setup():
    Gui.activateWorkbench("SciForgeWorkbench")
    S["files"] = vx.step_files(TEN)
    S["work"] = tempfile.mkdtemp(prefix="sciforge-vexqa-occ-")
    S["copies"] = []
    for name in TEN:
        target = os.path.join(S["work"], "x_%s.step" % name)
        shutil.copy(S["files"][name], target)
        S["copies"].append(target)
    S["screw"] = os.path.join(S["work"], "screw.step")
    shutil.copy(S["files"][SCREW], S["screw"])
    S["longer"] = os.path.join(S["work"], "longer.step")  # the screw's file, changed later
    vp.write_step(vp.screw(0.75), "screw", S["longer"])
    App.newDocument("VexQaOcc")
    h.fit()


setup.wait_ms = 1500


# -- O1 --------------------------------------------------------------------------------------------
def o1_insert():
    use_files([S["files"][n] for n in TEN])
    vx.menu("INSERT", "Insert STEP")


o1_insert.wait_ms = 2500


def o1_check():
    labels = sorted(c.Label for c in comps())
    h.check("O1 ten parts", labels == sorted(TEN), labels)
    esc_move()


o1_check.wait_ms = 800


# -- O2 --------------------------------------------------------------------------------------------
def o2_insert():
    use_files([S["files"][n] for n in TEN] + S["copies"])
    vx.menu("INSERT", "Insert STEP")


o2_insert.wait_ms = 3000


def twenty():
    from sciforge import instances

    occ = [comp(n + ":2") for n in TEN]
    own = [comp("x_" + n) for n in TEN]
    linked = all(
        c is not None and instances.is_instance(c) and instances.source_of(c) is comp(n)
        for c, n in zip(occ, TEN)
    )
    return occ, own, linked


def o2_check():
    occ, own, linked = twenty()
    h.check("O2 ten occurrences of the parts already there", linked, [c.Label for c in comps()])
    h.check("O2 ten parts of their own (another folder)", all(c is not None for c in own))
    new = [c for c in occ + own if c is not None]
    boxes = sorted((vx.bbox(c) for c in new), key=lambda b: b.XMin)
    apart = all(boxes[i].XMax < boxes[i + 1].XMin + 1e-6 for i in range(len(boxes) - 1))
    h.check("O2 the twenty side by side", apart and len(boxes) == 20, len(boxes))
    h.check("O2 every one has its solid", all(solid(c) for c in new))
    S["boxes"] = {c.Label: (round(vx.bbox(c).XMin, 4), round(vx.bbox(c).YMin, 4)) for c in new}
    esc_move()


o2_check.wait_ms = 800


def o2_undo():
    vx.undo()


o2_undo.wait_ms = 2000


def o2_undone():
    labels = sorted(c.Label for c in comps())
    h.check("O2 one Ctrl+Z takes the twenty away", labels == sorted(TEN), labels)
    vx.redo()


o2_undone.wait_ms = 2500


def o2_redone():
    occ, own, linked = twenty()
    h.check("O2 Ctrl+Y: the occurrences back, linked", linked, [c.Label for c in comps()])
    new = [c for c in occ + own if c is not None]
    h.check("O2 Ctrl+Y: the twenty back", len(new) == 20, len(new))
    h.check(
        "O2 Ctrl+Y: every one with its solid",
        all(solid(c) for c in new),
        [c.Label for c in new if not solid(c)],
    )
    where = {c.Label: (round(vx.bbox(c).XMin, 4), round(vx.bbox(c).YMin, 4)) for c in new}
    h.check("O2 Ctrl+Y: where they were", where == S["boxes"], (where, S["boxes"]))


# -- O3 --------------------------------------------------------------------------------------------
def o3_insert():
    use_files([S["screw"]])
    vx.menu("INSERT", "Insert STEP")


o3_insert.wait_ms = 2000


def o3_change():
    first = comp("screw")
    h.check(
        "O3 the screw's file: a part named screw", first is not None, [c.Label for c in comps()]
    )
    S["first_len"] = vx.bbox(first).ZLength if first is not None else None
    esc_move()
    shutil.copyfile(S["longer"], S["screw"])  # the file changes on disk


o3_change.wait_ms = 800


def o3_again():
    use_files([S["screw"]])
    vx.menu("INSERT", "Insert STEP")


o3_again.wait_ms = 2000


def o3_check():
    from sciforge import instances

    first = comp("screw")
    labels = [c.Label for c in comps() if c.Label.startswith("screw") and c is not first]
    new = [c for c in comps() if c.Label.startswith("screw ") or c.Label == "screw (2)"]
    if h.check("O3 the changed file: a part of its own", len(new) == 1, labels):
        c = new[0]
        h.check("O3 ... no occurrence of the old screw", not instances.is_instance(c), c.Label)
        length = vx.bbox(c).ZLength
        h.check("O3 ... with the new length (0.83 in)", abs(length - 0.83 * vx.IN) < 1e-3, length)
    if first is not None:
        h.check(
            "O3 the first screw unchanged",
            abs(vx.bbox(first).ZLength - S["first_len"]) < 1e-6,
            vx.bbox(first).ZLength,
        )
    esc_move()
    no_files()


o3_check.wait_ms = 800


# -- O4 --------------------------------------------------------------------------------------------
def o4_delete():
    S["occ"] = comp(SCREW + ":2").Name
    S["first"] = comp(SCREW).Name
    S["occ_box"] = vx.bbox(comp(SCREW + ":2"))
    S["before"] = parts_list()
    h.click_empty()
    t.row_menu(SCREW, "Delete")


o4_delete.wait_ms = 2000


def took_over():
    """The part named SCREW is the former SCREW:2, no occurrence any more."""
    from sciforge import instances

    heir = comp(SCREW)
    return (
        heir is not None
        and heir.Name == S["occ"]
        and not instances.is_instance(heir)
        and comp(SCREW + ":2") is None
        and App.ActiveDocument.getObject(S["first"]) is None
    )


def o4_deleted():
    from sciforge import instances

    h.check(
        "O4 the first occurrence deleted: its occurrence takes over as the part",
        took_over(),
        [c.Label for c in comps()],
    )
    heir = comp(SCREW)
    if heir is not None:
        h.check("O4 ... with its solid", solid(heir))
        box = vx.bbox(heir)
        h.check(
            "O4 ... where it was",
            abs(box.XMin - S["occ_box"].XMin) < 1e-6 and abs(box.ZMin - S["occ_box"].ZMin) < 1e-6,
            (box, S["occ_box"]),
        )
        h.check("O4 ... it can be copied again", instances.definition(heir) is heir)
        h.check("O4 ... the browser lists it", SCREW in t.labels(), t.labels())
    rows = parts_list()
    h.check(
        "O4 the parts list still counts it as the screw",
        rows.get(SCREW) == S["before"].get(SCREW, 0) - 1 and SCREW + ":2" not in rows,
        (rows, S["before"]),
    )
    vx.undo()


o4_deleted.wait_ms = 2000


def o4_undone():
    from sciforge import instances

    first, occ = comp(SCREW), comp(SCREW + ":2")
    h.check(
        "O4 Ctrl+Z: the original back",
        first is not None and first.Name == S["first"] and solid(first),
        first and first.Name,
    )
    h.check(
        "O4 Ctrl+Z: the occurrence linked to it again",
        occ is not None and occ.Name == S["occ"] and instances.source_of(occ) is first,
        occ and occ.Label,
    )
    h.check("O4 Ctrl+Z: the parts list as before", parts_list() == S["before"], parts_list())
    vx.redo()


o4_undone.wait_ms = 2000


def o4_redone():
    h.check("O4 Ctrl+Y: deleted again, taken over again", took_over(), [c.Label for c in comps()])
    h.check("O4 Ctrl+Y: with its solid", solid(comp(SCREW)))


# -- O5 --------------------------------------------------------------------------------------------
def o5_save():
    S["rows"] = parts_list()
    S["path"] = vx.save_as("vex_qa_occ")
    App.closeDocument(App.ActiveDocument.Name)


o5_save.wait_ms = 1000


def o5_open():
    App.openDocument(S["path"])
    Gui.activateWorkbench("SciForgeWorkbench")


o5_open.wait_ms = 3000


def o5_reopened():
    h.check(
        "O5 the part that took over is back",
        took_over() and solid(comp(SCREW)),
        [c.Label for c in comps()],
    )
    h.check("O5 the parts list the same", parts_list() == S["rows"], (parts_list(), S["rows"]))
    vx.no_popups("reopening")


# -- O6 --------------------------------------------------------------------------------------------
def o6_insert():
    use_files([S["files"][SCREW]])
    vx.menu("INSERT", "Insert STEP")


o6_insert.wait_ms = 2000


def o6_check():
    from sciforge import instances

    new = comp(SCREW + ":2")
    h.check(
        "O6 the same file again: an occurrence of the part that took over",
        new is not None and instances.source_of(new) is comp(SCREW),
        [c.Label for c in comps()],
    )
    h.check("O6 ... with its solid", new is not None and solid(new))
    esc_move()
    no_files()
    try:
        os.remove(S["path"])
        shutil.rmtree(S["work"], ignore_errors=True)
    except OSError:
        pass


o6_check.wait_ms = 800


h.run(
    "vex_qa_occ",
    [
        setup,
        o1_insert,
        o1_check,
        o2_insert,
        o2_check,
        o2_undo,
        o2_undone,
        o2_redone,
        o3_insert,
        o3_change,
        o3_again,
        o3_check,
        o4_delete,
        o4_deleted,
        o4_undone,
        o4_redone,
        o5_save,
        o5_open,
        o5_reopened,
        o6_insert,
        o6_check,
    ],
)
