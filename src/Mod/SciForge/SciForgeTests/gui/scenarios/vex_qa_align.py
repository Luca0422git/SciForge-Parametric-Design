# SPDX-License-Identifier: LGPL-2.1-or-later
"""VEX QA (beta 3): Align a C-channel onto a C-channel, square hole onto square hole, both
ways round (Luca: "when i say align, i mean align. the align command. so yes we will need
center points on squares and such."). Only real input in the dialog. SciForge's own VEX-like
parts: a 1x2x1x5 aluminium C-channel A at the origin and a 1x2x1x5 with rounded hole corners
(B) in front of it.

  A  MODIFY > Align, Objects: Components. From: B's web next to its hole (1, 1) (the hole's
     centre lit); To: A's web next to its hole (3, 1). B comes onto A face to face: B's hole
     (1, 1) on A's hole (3, 1), B's web on A's web. OK: one Align step; Undo: B back.
  B  The other way round: From: the edge of A's hole (0, 1) (the hole's centre lit, along the
     hole); To: B's web next to its rounded hole (4, 1): A comes onto B face to face, A's hole
     (0, 1) on B's hole (4, 1). OK; Undo; Redo.
"""

import FreeCAD as App
import FreeCADGui as Gui

from SciForgeTests.gui import direct_steps as d
from SciForgeTests.gui import harness as h
from SciForgeTests.gui import timeline_input as t
from SciForgeTests.gui import vex_steps as vx

V = App.Vector
S = {}
B_AT = V(0, -45, 0)
EPS = 1e-4


def snaps():
    p = vx.panel()
    return getattr(p, "snaps", None) if p is not None else None


def aligns():
    from sciforge import align

    return [o for o in App.ActiveDocument.Objects if align.is_align(o)]


def centre(name, i, j):
    """Hole (i, j) of channel `name` on its web's top face, in design coordinates."""
    return vx.hole_centre(i, j, top=True, origin=S[name].Placement)


def next_to(name, i, j):
    c = centre(name, i, j)
    return V(c.x + 3.6, c.y, c.z)


def face_to_face(where, mover, hole, other, other_hole):
    """`mover` lies face down on `other`: its hole on the other's hole, its web on the other's."""
    a = centre(mover, *hole)
    b = centre(other, *other_hole)
    h.check(
        "%s: %s's hole %s on %s's hole %s"
        % (where, mover.upper(), hole, other.upper(), other_hole),
        (a - b).Length < EPS,
        (a, b),
    )
    up = S[mover].Placement.Rotation.multVec(V(0, 0, 1))
    h.check("%s: %s face down on %s" % (where, mover.upper(), other.upper()), up.z < -0.999, up)


def open_align():
    h.click_empty()
    vx.fit()
    vx.menu("MODIFY", "Align")


def components():
    p = vx.panel()
    if h.check("Align dialog", p is not None and p.title == "Align", p):
        d.choose("objects", "Components")


# -- setup -----------------------------------------------------------------------------------------
def setup():
    Gui.activateWorkbench("SciForgeWorkbench")
    App.newDocument("VexQaAlign")
    S["a"] = vx.insert("c_channel_1x2x1x5")
    S["b"] = vx.insert("c_channel_1x2x1x5_round", App.Placement(B_AT, App.Rotation()))
    vx.fit()
    S["b_place"] = App.Placement(S["b"].Placement)
    S["a_place"] = App.Placement(S["a"].Placement)


# -- A: B onto A ---------------------------------------------------------------------------------
def a_open():
    open_align()


def a_components():
    components()


def a_hover_from():
    vx.look_at(centre("b", 1, 1), 40.0)
    S["pt"] = next_to("b", 1, 1)
    vx.hover(S["pt"])


def a_click_from():
    vx.lit(snaps(), "From: B next to its hole (1, 1)", "loop", centre("b", 1, 1))
    h.click(S["pt"])


def a_hover_to():
    p = vx.panel()
    h.check("B moves", p is not None and p.moving is S["b"], p and p.moving)
    vx.look_at(centre("a", 3, 1), 40.0)
    S["pt"] = next_to("a", 3, 1)
    vx.hover(S["pt"])


def a_click_to():
    vx.lit(snaps(), "To: A next to its hole (3, 1)", "loop", centre("a", 3, 1))
    h.click(S["pt"])


def a_preview():
    face_to_face("preview", "b", (1, 1), "a", (3, 1))
    h.shot("A-preview")
    vx.ok()


def a_done():
    h.check("dialog closed", vx.panel() is None)
    h.check("one Align step", len(aligns()) == 1, aligns())
    face_to_face("OK", "b", (1, 1), "a", (3, 1))
    h.check("A did not move", S["a"].Placement.isSame(S["a_place"], 1e-9), S["a"].Placement)
    vx.undo()


def a_undone():
    h.check(
        "Undo: B back where it was", S["b"].Placement.isSame(S["b_place"], 1e-7), S["b"].Placement
    )
    h.check("Undo: no Align step", not aligns(), aligns())


# -- B: A onto B, from a hole's edge ---------------------------------------------------------------
def b_open():
    open_align()


def b_components():
    components()


def b_hover_edge():
    c = centre("a", 0, 1)
    vx.look_at(c, 40.0)
    # the hole's edge facing +X, 1 mm from its middle
    S["pt"] = V(c.x + vx.vp.HOLE / 2.0, c.y - 1.0, c.z)
    vx.hover_pixel(h.screen_point(S["pt"]))


def b_click_edge():
    sn = snaps()
    vx.lit(sn, "From: the edge of A's hole (0, 1)", "loop", centre("a", 0, 1))
    hot = sn.hot if sn is not None else None
    h.check(
        "with the hole's direction (up, out of A's web)",
        hot is not None and hot.get("axis") is not None and hot["axis"].z > 0.999,
        hot and hot.get("axis"),
    )
    h.click(S["pt"])


def b_hover_to():
    p = vx.panel()
    h.check("A moves", p is not None and p.moving is S["a"], p and p.moving)
    vx.look_at(centre("b", 4, 1), 40.0)
    S["pt"] = next_to("b", 4, 1)
    vx.hover(S["pt"])


def b_click_to():
    vx.lit(snaps(), "To: B next to its rounded hole (4, 1)", "loop", centre("b", 4, 1))
    h.click(S["pt"])


def b_preview():
    face_to_face("preview", "a", (0, 1), "b", (4, 1))
    h.shot("B-preview")
    vx.ok()


def b_done():
    h.check("dialog closed", vx.panel() is None)
    face_to_face("OK", "a", (0, 1), "b", (4, 1))
    h.check("B did not move", S["b"].Placement.isSame(S["b_place"], 1e-7), S["b"].Placement)
    vx.undo()


def b_undone():
    h.check(
        "Undo: A back at the origin", S["a"].Placement.isSame(S["a_place"], 1e-7), S["a"].Placement
    )
    vx.redo()


def b_redone():
    face_to_face("Redo", "a", (0, 1), "b", (4, 1))
    vx.no_popups("Align")


h.run(
    "vex_qa_align",
    t.watched(
        [
            setup,
            a_open,
            a_components,
            a_hover_from,
            a_click_from,
            a_hover_to,
            a_click_to,
            a_preview,
            a_done,
            a_undone,
            b_open,
            b_components,
            b_hover_edge,
            b_click_edge,
            b_hover_to,
            b_click_to,
            b_preview,
            b_done,
            b_undone,
            b_redone,
        ]
    ),
    paced_by="state",
)
