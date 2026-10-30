# SPDX-License-Identifier: LGPL-2.1-or-later
"""Auto Timeline: meshes, a refusal, save / reopen, Esc (beta 3, builder at-tools), with real
clicks. Spec: docs/sciforge/parity/auto-timeline.md.

A  A broken mesh (a box with one triangle missing: not watertight) inserted as a mesh body:
   its right-click > Rebuild with Timeline (AI)... is refused in a window that says why and
   what to do (repair it); nothing changes (no reference, no new body, the mesh still shown).
B  The plate of rebuild_steps.py as an STL mesh body: Rebuild with Timeline (AI)... makes
   it the reference (made from the mesh: kind mesh, its own tolerance), hides the mesh,
   makes "<name> (rebuilt)" active.
C  The AI's base plate, then Compare with Reference; Esc closes the window and clears the
   differences.
D  Save, close, reopen: the reference is back with its solid, drawn faint again, still
   neither in the browser nor in the timeline, and Compare with Reference works on it.
"""

import os

import FreeCAD as App

from SciForgeTests.gui import harness as h
from SciForgeTests.gui import rebuild_steps as r
from SciForgeTests.gui import versions_input as vi
from PySide import QtCore

V = App.Vector
s = {}
ENTRY = "Rebuild with Timeline (AI)..."


def setup():
    import Mesh

    from sciforge import insert

    r.drop_fake_key()
    s["doc"] = r.new_design("RebuildMesh")
    box = Mesh.createBox(20, 20, 20)
    facets = [list(f.Points) for f in box.Facets][1:]  # one triangle missing: a hole
    broken = Mesh.Mesh(facets)
    s["broken"] = insert.make_mesh_body(s["doc"], broken, "", label="Broken")
    s["broken"].Placement.Base = V(-40, 0, 0)
    s["doc"].recompute()
    h.fit()


# -- A ------------------------------------------------------------------------------------------
def a_refused():
    s["count"] = len(App.ActiveDocument.Objects)
    entries = r.browser_entries("Broken")
    h.check("a mesh body's right-click has %s" % ENTRY, ENTRY in entries, entries)
    r.browser_menu("Broken", ENTRY)


def a_said():
    box = r.dialog("SciForgeRebuildRefused")
    h.check("the refusal is said in a window", box is not None, h.popups())
    text = box.text() if box is not None else ""
    h.check("... why (not watertight)", "watertight" in text, text)
    h.check("... and what to do (repair it)", "Repair" in text, text)
    h.check("nothing changed: no reference", not r.references(), r.references())
    h.check("... no new body", len(App.ActiveDocument.Objects) == s["count"])
    h.check("... the mesh still shown", r.shown(s["broken"]))
    if box is not None:
        box.accept()


# -- B ------------------------------------------------------------------------------------------
def b_mesh():
    import Mesh

    from sciforge import insert

    shape = r.plate_shape()
    mesh = Mesh.Mesh(shape.tessellate(0.005))
    path = os.path.join(r.folder(), "plate.stl")
    mesh.write(path)
    s["mesh"] = insert.make_mesh_body(App.ActiveDocument, insert.read_mesh(path), path)
    App.ActiveDocument.recompute()
    s["mesh_label"] = s["mesh"].Label
    r.browser_menu(s["mesh_label"], ENTRY)


def b_started():
    from sciforge import bodies, rebuild

    r.close_dialogs()
    refs = r.references()
    h.check("the mesh is the reference now", len(refs) == 1, refs)
    if not refs:
        return
    ref = s["ref"] = refs[0]
    h.check("... made from the mesh", ref.SourceKind == "mesh", ref.SourceKind)
    h.check(
        "... a solid of the plate's size",
        ref.FrozenShape.Solids and abs(ref.FrozenShape.BoundBox.XLength - 60) < 1e-3,
        ref.FrozenShape.BoundBox,
    )
    h.check("... with a mesh's tolerance", ref.Tolerance > 0.01, ref.Tolerance)
    h.check("the mesh is hidden", not r.shown(s["mesh"]))
    h.check("the reference is drawn faint", r.ghost_drawn(ref))
    target = rebuild.target_of(ref)
    s["target_name"] = target.Name if target else None
    h.check(
        "'<name> (rebuilt)' is active",
        target is not None
        and target.Label == "%s (rebuilt)" % s["mesh_label"]
        and bodies.active_body(App.ActiveDocument) is target,
    )


# -- C ------------------------------------------------------------------------------------------
def c_base():
    r.tool("create_sketch", plane="XY", geometry=[{"rect": [0, 0, 60, 40]}])
    answer = r.tool("extrude", profile="Sketch1", distance=10)
    h.check("the AI's base plate", not answer["is_error"], answer["text"])
    r.utilities_menu("Compare with Reference")


def c_esc():
    box = r.dialog("SciForgeRebuildCompare")
    h.check("Compare with Reference opened", box is not None, h.popups())
    head = box.headline.text() if box is not None else ""
    h.check("... the match of the base against the mesh (about 95 %)", "Match 9" in head, head)
    h.check("... the differences drawn", (r.overlay_count(s.get("ref")) or 0) > 0)
    r.esc(box)


def c_closed():
    h.check("Esc closes Compare", r.dialog("SciForgeRebuildCompare") is None, h.popups())
    h.check("... and clears the differences", r.overlay_count(s.get("ref")) == 0)


# -- D ------------------------------------------------------------------------------------------
def d_save():
    import tempfile

    path = os.path.join(tempfile.mkdtemp(prefix="sciforge-rebuild-"), "rebuild_mesh.FCStd")
    s["path"] = path
    App.ActiveDocument.saveAs(path)
    h.check("saved", os.path.isfile(path), path)
    h.press(QtCore.Qt.Key_S, QtCore.Qt.ControlModifier)


def d_describe():
    vi.accept_save()


def d_close():
    App.closeDocument(App.ActiveDocument.Name)


def d_reopen():
    App.openDocument(s["path"])
    h.fit()


def d_reopened():
    from sciforge import rebuild

    refs = r.references()
    h.check("after reopening the reference is back", len(refs) == 1, refs)
    if not refs:
        return
    ref = refs[0]
    h.check(
        "... with its solid",
        ref.FrozenShape.Solids and abs(ref.FrozenShape.BoundBox.XLength - 60) < 1e-3,
    )
    h.check("... drawn faint again", r.ghost_drawn(ref))
    h.check("... not in the browser", ref.Label not in r.browser_labels())
    h.check("... not in the timeline", ref.Name not in r.timeline_names())
    target = rebuild.target_of(ref)
    h.check("... pointing at the rebuild", target is not None and target.Name == s["target_name"])
    mesh = App.ActiveDocument.getObject(ref.SourceName)
    h.check("the mesh is still hidden", mesh is not None and not r.shown(mesh))
    s["ref"] = ref
    r.utilities_menu("Compare with Reference")


def d_compare():
    box = r.dialog("SciForgeRebuildCompare")
    h.check(
        "Compare works after reopening",
        box is not None and "Match 9" in box.headline.text(),
        box.headline.text() if box else h.popups(),
    )
    if box is not None:
        r.click_button(box, "SciForgeRebuildCompareClose")


def finish():
    r.close_dialogs()
    h.expect_no_errors("the mesh / reopen scenario")


h.run(
    "rebuild_mesh_reopen",
    [
        setup,
        a_refused,
        a_said,
        b_mesh,
        b_started,
        c_base,
        c_esc,
        c_closed,
        d_save,
        d_describe,
        d_close,
        d_reopen,
        d_reopened,
        d_compare,
        finish,
    ],
    paced_by="state",
)
