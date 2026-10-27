# SPDX-License-Identifier: LGPL-2.1-or-later
"""The VEX journey (scenarios/journey_vex*.py): a piece of a VEX V5 robot built the way a team
member builds it in Fusion, only with real clicks and keys (code only makes the test files
and reads results). Not a scenario (kept outside scenarios/).

The parts are SciForge's own VEX-like parts (SciForgeTests/fixtures/vex/vex_parts.py, from
VEX's published numbers, never VEX's files) written as STEP files, plus three made here as
test data with the same builders: a 5 in standoff and a 6 in square shaft (VEX sells 5 in
standoffs; teams cut 12 in shafts to length), and a plain 2.75 in wheel (a disc with a square
hole, not in the generator).

The design (inches; hole (i, j) of a 1x2x1x25 rail: i along it, j across; all by hand):
  square holes 0.182 in on a 0.500 in grid: hole (i, j)'s centre at x = 0.25 + 0.5 i,
  y = 0.25 + 0.5 j; the aluminium is t = 0.064 in thick (the web's top face at z = t).
  Rail 1 ("c_channel_1x2x1x25") stays where Insert STEP put it, web down, flanges up.
  Rail 2 ("c_channel_1x2x1x25_round", the same channel with rounded hole corners): Align, its
      hole (0, 1) onto rail 1's hole (0, 0), web on web: it lies face down on rail 1 over the
      same footprint (turned half a turn about the rail's length: its row 1 over row 0); then
      Move 5 in up: its web's inside face at z = t + 5, every hole (i, 1 - j) of it over rail
      1's hole (i, j): x = 0.25 + 0.5 i, the webs' inside faces 5 in apart.
"""

import math
import os
import time

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtWidgets
from PySide6 import QtTest

from SciForgeTests.fixtures.vex import vex_parts as vp
from SciForgeTests.gui import bodies_steps as bs
from SciForgeTests.gui import component2_steps as c2
from SciForgeTests.gui import dialog_input as di
from SciForgeTests.gui import harness as h
from SciForgeTests.gui import joints_steps as js
from SciForgeTests.gui import timeline_input as ti
from SciForgeTests.gui import vex_steps as vx
from SciForgeTests.gui import viewcube_input as vc

V = App.Vector
IN = vp.IN
T = vp.AL  # 0.064 in: the rails' web thickness
PITCH = vp.PITCH
EPS = 1e-3  # mm

RAIL1 = "c_channel_1x2x1x25"
RAIL2 = "c_channel_1x2x1x25_round"
STANDOFF = "standoff_5in"
SCREW = "screw_8_32_x_0_5"
NUT = "keps_nut"
SHAFT = "shaft_6in"
BEARING = "bearing_flat"
WHEEL = "wheel_2_75in"
GENERATED = [RAIL1, RAIL2, SCREW, NUT, BEARING]
OWN = {  # made here with the generator's own builders (test data)
    STANDOFF: lambda: vp.standoff(5.0),
    SHAFT: lambda: vp.shaft(6.0),
    WHEEL: lambda: wheel(),
}
PICKED = [RAIL1, RAIL2, STANDOFF, SCREW, NUT, SHAFT, BEARING, WHEEL]
GAP = 5.0 * IN  # between the rails' webs (inside faces)
WHEEL_D = 2.75 * IN
WHEEL_T = 0.5 * IN
WHEEL_HOLE = 0.13 * IN

S = {}  # what the steps share: components by role, numbers measured on the way


def step(fn, name, wait_ms=None):
    fn.__name__ = name
    if wait_ms is not None:
        fn.wait_ms = wait_ms
    return fn


def doc():
    return App.ActiveDocument


def wheel():
    """A plain 2.75 in wheel, 0.5 in wide: a disc on Z = 0 .. 0.5 in with a 0.13 in square hole
    through its middle (a VEX wheel's square insert for a 1/8 in shaft)."""
    import Part

    disc = Part.makeCylinder(WHEEL_D / 2.0, WHEEL_T)
    side = WHEEL_HOLE
    hole = Part.makeBox(side, side, WHEEL_T + 2.0, V(-side / 2.0, -side / 2.0, -1.0))
    return disc.cut(hole)


def files():
    """Every part's STEP file in one folder (the team's parts folder): {name: path}."""
    folder = vp.default_folder()
    out = vp.write_all(folder, GENERATED)
    for name, make in OWN.items():
        path = os.path.join(folder, name + ".step")
        if not os.path.isfile(path):
            vp.write_step(make(), name, path)
        out[name] = path
    return out


# -- reading results ---------------------------------------------------------------------------
def comps():
    from sciforge import components

    return components.list_components(doc())


def comp(label):
    for c in comps():
        if c.Label == label:
            return c
    return None


def body_of(component):
    return vx.body_of(component)


def bbox(component):
    return vx.bbox(component)


def hole(name, i, j, top=True):
    """Hole (i, j)'s centre on the top (web's inside, z = t) or bottom face of rail `name`
    (S key "rail1" / "rail2"), in design coordinates."""
    return vx.hole_centre(i, j, top=top, origin=S[name].Placement)


def grid(i, j):
    """Rail 1's hole (i, j) by hand: (0.25 + 0.5 i, 0.25 + 0.5 j) in, on its web's top."""
    return V((0.25 + 0.5 * i) * IN, (0.25 + 0.5 * j) * IN, T)


def fmt(v):
    return "(%.4f, %.4f, %.4f) in" % (v.x / IN, v.y / IN, v.z / IN)


def same(a, b, tol=EPS):
    return (a - b).Length < tol


def places():
    """Every component's placement now (to check what moved)."""
    return {c.Name: App.Placement(c.Placement) for c in comps()}


def moved_since(before, tol=1e-6):
    out = []
    for c in comps():
        was = before.get(c.Name)
        if was is not None and not c.Placement.isSame(was, tol):
            out.append(c.Label)
    return out


def errors_free(where):
    bad = [o.Label for o in doc().Objects if "Invalid" in o.State or "Error" in o.State]
    return h.check("%s: every object computed" % where, not bad, bad)


# -- the file dialog ---------------------------------------------------------------------------
def answer_file_dialog(paths, report):
    """When the file dialog opens (Qt's own dialog, as under xvfb): type the folder into its
    file name box and Enter (it goes there), then the file names in quotes (several files at
    once, as Ctrl-clicking them does) and Enter."""
    folder = os.path.dirname(paths[0])
    names = " ".join('"%s"' % os.path.basename(p) for p in paths)

    def look(tries=0):
        dlg = QtWidgets.QApplication.activeModalWidget()
        if not isinstance(dlg, QtWidgets.QFileDialog):
            if tries < 100:
                QtCore.QTimer.singleShot(100, lambda: look(tries + 1))
            else:
                report["error"] = "no file dialog came (%r)" % (dlg,)
            return
        report["title"] = dlg.windowTitle()
        report["mode"] = int(dlg.fileMode().value) if hasattr(dlg.fileMode(), "value") else 0
        edit = dlg.findChild(QtWidgets.QLineEdit, "fileNameEdit")
        if edit is None:
            report["error"] = "no file name box"
            dlg.reject()
            return
        edit.setFocus()
        QtTest.QTest.keyClicks(edit, folder)
        QtTest.QTest.keyClick(edit, QtCore.Qt.Key_Return)
        QtCore.QTimer.singleShot(600, lambda: type_names(dlg, edit))

    def type_names(dlg, edit):
        try:
            edit.setFocus()
            QtTest.QTest.keyClick(edit, QtCore.Qt.Key_A, QtCore.Qt.ControlModifier)
            # one file: its bare name (quotes are for several)
            QtTest.QTest.keyClicks(edit, names if len(paths) > 1 else os.path.basename(paths[0]))
            report["typed"] = names
            report["folder"] = dlg.directory().absolutePath()
            QtTest.QTest.keyClick(edit, QtCore.Qt.Key_Return)
            report["done"] = True
        except Exception as exc:  # never leave the dialog open
            report["error"] = str(exc)
            dlg.reject()

    QtCore.QTimer.singleShot(300, look)


def insert_step(names, report):
    """INSERT > Insert STEP, the files picked in the file dialog."""
    from sciforge import insert_ui

    insert_ui.FILE_PICKER = None  # the real dialog
    answer_file_dialog([S["files"][n] for n in names], report)
    t0 = time.perf_counter()
    vx.menu("INSERT", "Insert STEP")
    report["seconds"] = time.perf_counter() - t0
    keys_to_window()


def move_panel():
    from sciforge import component_move_ui, taskui

    p = taskui.current()
    return p if isinstance(p, component_move_ui.ComponentMovePanel) else None


# == 1. a new design in inches, the parts in ==================================================
def start_steps(name):
    def new():
        Gui.activateWorkbench("SciForgeWorkbench")
        S.clear()
        t0 = time.perf_counter()
        S["files"] = files()
        S["made_files"] = time.perf_counter() - t0
        App.newDocument(name)
        h.fit()
        h.check("the parts folder: %d STEP files" % len(PICKED), len(S["files"]) == len(PICKED))

    def units():
        h.click_empty()
        ti.click_row("Units: mm")

    def inch():
        from sciforge import browser_ui

        panel = browser_ui.UnitsPanel.last
        if not h.check("Change Active Units opens", panel is not None and not panel._closed):
            return
        combo = panel.form.findChild(QtWidgets.QComboBox, "SciForgeUnitType")
        di.choose(combo, "Inch")
        h.task_button("OK")

    def inches():
        h.check(
            "the design is in inches",
            doc().UnitSystem.startswith("Imperial decimal"),
            doc().UnitSystem,
        )
        h.check("the browser says so", ti.tree().row("Units: in") is not None, ti.labels()[:6])

    return [
        step(new, "j1_new_design", 1500),
        step(units, "j1_units_row", 800),
        step(inch, "j1_inch", 800),
        step(inches, "j1_inches"),
    ]


def insert_steps():
    def insert():
        S["dialog"] = {}
        insert_step(PICKED, S["dialog"])

    def inserted():
        d = S.get("dialog", {})
        h.check("the file dialog: Insert STEP", d.get("title") == "Insert STEP", d)
        h.check("eight files picked at once in it", d.get("done") and not d.get("error"), d)
        print("[SciForge] journey_vex: eight STEP files inserted in %.2f s" % d.get("seconds", -1))
        S["insert_s"] = d.get("seconds", -1)
        labels = sorted(c.Label for c in comps())
        h.check("one component per file, named after it", labels == sorted(PICKED), labels)
        boxes = sorted((bbox(c) for c in comps()), key=lambda b: b.XMin)
        apart = all(boxes[k].XMax < boxes[k + 1].XMin + 1e-6 for k in range(len(boxes) - 1))
        h.check("side by side along X (none on top of another)", apart and len(boxes) == 8)
        p = move_panel()
        if h.check("the Move dialog places them", p is not None, p):
            picked = p.options.get("components") or []
            h.check("... all eight", len(picked) == 8, picked)
        h.shot("1-inserted")
        vx.ok()

    def placed():
        h.check("OK: the Move dialog closed", move_panel() is None)
        for key, label in (
            ("rail1", RAIL1),
            ("rail2", RAIL2),
            ("standoff", STANDOFF),
            ("screw", SCREW),
            ("nut", NUT),
            ("shaft", SHAFT),
            ("bearing", BEARING),
            ("wheel", WHEEL),
        ):
            S[key] = comp(label)
        h.check("every part found", all(S.get(k) is not None for k in ("rail1", "rail2", "wheel")))
        errors_free("inserted")
        # Rail 1 stays where it came in: its holes by hand
        if S.get("rail1") is not None:
            S["rail1_place"] = App.Placement(S["rail1"].Placement)
            h.check(
                "rail 1 came in at the origin, as in the file",
                S["rail1"].Placement.isSame(App.Placement(), 1e-9),
                S["rail1"].Placement,
            )
            for i, j in ((0, 0), (12, 1), (24, 0)):
                h.check(
                    "rail 1's hole (%d, %d) at %s (0.5 in grid)" % (i, j, fmt(grid(i, j))),
                    same(hole("rail1", i, j), grid(i, j)),
                    fmt(hole("rail1", i, j)),
                )

    return [
        step(insert, "j1_insert_step", 3000),
        step(inserted, "j1_inserted", 1200),
        step(placed, "j1_placed"),
    ]


# == 2. rail 2 aligned onto rail 1, then 5 in up ===============================================
def next_to(name, i, j, top=True):
    """A point on the metal 3.6 mm in +X from a hole of a rail (where its centre lights)."""
    c = hole(name, i, j, top)
    return V(c.x + 3.6, c.y, c.z)


def align_snaps():
    p = vx.panel()
    return getattr(p, "snaps", None) if p is not None else None


def align_steps():
    def open_align():
        h.click_empty()
        vx.fit()
        vx.menu("MODIFY", "Align")

    def components():
        p = vx.panel()
        if h.check("Align dialog", p is not None and p.title == "Align", p):
            from SciForgeTests.gui import direct_steps as d

            d.choose("objects", "Components")
        # the ViewCube's TOP: the web's holes next to the flanges show (from the front, the
        # front flange hides row 0)
        h.check("ViewCube TOP", vc.click("top"))

    def hover_from():
        vx.look_at(hole("rail2", 0, 1), 40.0)
        S["pt"] = next_to("rail2", 0, 1)
        vx.hover(S["pt"])

    def click_from():
        vx.lit(align_snaps(), "From: rail 2 next to its hole (0, 1)", "loop", hole("rail2", 0, 1))
        h.click(S["pt"])

    def hover_to():
        p = vx.panel()
        h.check("rail 2 moves", p is not None and p.moving is S["rail2"], p and p.moving)
        vx.look_at(hole("rail1", 0, 0), 40.0)
        S["pt"] = next_to("rail1", 0, 0)
        vx.hover(S["pt"])

    def click_to():
        vx.lit(align_snaps(), "To: rail 1 next to its hole (0, 0)", "loop", grid(0, 0))
        h.click(S["pt"])

    def reversed_first():
        # Align turns the part over about some line in the face (its smallest turn): here it
        # comes out pointing the other way (along -X) and half a rail to the side
        along = S["rail2"].Placement.Rotation.multVec(V(1, 0, 0))
        S["first_along"] = along
        print("[SciForge] journey_vex: Align first gives rail 2 along %s" % along, flush=True)
        p = vx.panel()
        if h.check("Align dialog still open", p is not None and p.title == "Align", p):
            from SciForgeTests.gui import widget_input as wi

            # Angle twice: half a turn about the hole's axis (a person turns it round)
            wi.click(p.angle_button)

    def angle_again():
        p = vx.panel()
        if p is not None:
            from SciForgeTests.gui import widget_input as wi

            wi.click(p.angle_button)

    def preview():
        p = vx.panel()
        h.check(
            "the dialog says: turned 180 degrees",
            p is not None and "turned 180" in p.state.text(),
            p and p.state.text(),
        )
        on_rail1("Align preview", 0.0)
        h.shot("2-align-preview")
        vx.ok()

    def aligned():
        from sciforge import align

        h.check("Align closed", vx.panel() is None)
        found = [o for o in doc().Objects if align.is_align(o)]
        h.check("one Align step", len(found) == 1, [o.Label for o in found])
        on_rail1("aligned", 0.0)
        h.check(
            "rail 1 did not move",
            S["rail1"].Placement.isSame(S["rail1_place"], 1e-9),
            S["rail1"].Placement,
        )

    def select_rail2():
        h.click_empty()
        ti.click_row(RAIL2)

    def press_m():
        keys_to_window()
        h.fit()
        h.press("m")

    def type_up():
        p = c2.component_panel()
        from sciforge import commands

        told = (getattr(commands, "_TOLD", None) or {}).get("msg")
        sel = [(o.Object.Label, o.SubElementNames) for o in Gui.Selection.getSelectionEx()]
        from sciforge import shortcuts

        focus = QtWidgets.QApplication.focusWidget()
        diag = (
            c2.panel(),
            told,
            sel,
            "m" in shortcuts._bound or "M" in shortcuts._bound,
            focus and focus.metaObject().className(),
            Gui.Control.activeDialog(),
        )
        if not h.check("M on rail 2's row: the components dialog", p is not None, diag):
            # a person tries the ribbon then: MODIFY > Move/Copy
            vx.menu("MODIFY", "Move/Copy")
            p = c2.component_panel()
            h.check("MODIFY > Move/Copy: the components dialog", p is not None, c2.panel())
        if p is not None:
            h.check(
                "rail 2 picked at once",
                p.options.get("components") == [S["rail2"]],
                p.options.get("components"),
            )
            c2.type_value(p, "dz", "5")

    def moved():
        p = c2.component_panel()
        text = c2.field(p, "dz").text() if p is not None else ""
        h.check(
            "Z Distance reads 5 in (a plain 5 in an inch design)",
            "5" in text and "in" in text,
            text,
        )
        on_rail1("Move preview", GAP)
        vx.ok()

    def apart():
        h.check("the Move dialog closed", c2.panel() is None)
        on_rail1("moved", GAP)
        S["frame_places"] = places()
        h.shot("2-rails")

    return [
        step(open_align, "j2_align", 1000),
        step(components, "j2_components"),
        step(hover_from, "j2_hover_from"),
        step(click_from, "j2_click_from", 500),
        step(hover_to, "j2_hover_to"),
        step(click_to, "j2_click_to", 1500),
        step(reversed_first, "j2_reversed_first", 1200),
        step(angle_again, "j2_angle_again", 1200),
        step(preview, "j2_preview", 1200),
        step(aligned, "j2_aligned", 800),
        step(select_rail2, "j2_select_rail2", 600),
        step(press_m, "j2_press_m", 1200),
        step(type_up, "j2_type_up", 1500),
        step(moved, "j2_moved", 1500),
        step(apart, "j2_apart"),
    ]


def on_rail1(where, up):
    """Rail 2 lies face down over rail 1's footprint, `up` (mm) above it: its hole (i, 1 - j)
    over rail 1's hole (i, j) (by hand on the 0.5 in grid), parallel to it."""
    plc = S["rail2"].Placement
    ok = True
    worst = 0.0
    for i, j in ((0, 0), (0, 1), (12, 0), (24, 1)):
        a = vx.hole_centre(i, 1 - j, top=True, origin=plc)
        b = grid(i, j) + V(0, 0, up)
        worst = max(worst, (a - b).Length)
        ok = ok and same(a, b)
    h.check(
        "%s: every hole of rail 2 over rail 1's (x = 0.25 + 0.5 i in), %g in above"
        % (where, up / IN),
        ok,
        "worst %.5f mm; rail 2 at %s" % (worst, plc),
    )
    along = plc.Rotation.multVec(V(1, 0, 0))
    h.check("%s: parallel to rail 1 (along X)" % where, abs(along.x) > 0.999999, along)
    face = plc.Rotation.multVec(V(0, 0, 1))
    h.check("%s: rail 2 face down (its flanges toward rail 1)" % where, face.z < -0.999999, face)
    if up > 0:
        inside = bbox(S["rail2"]).ZMax - T  # its web's inside face
        h.check(
            "%s: the webs' inside faces %.3f in apart (5 in)" % (where, (inside - T) / IN),
            abs((inside - T) - up) < EPS,
            inside,
        )


# == helpers for the joints ====================================================================
def look(kind):
    """The camera, as a person turns the view (the ViewCube / orbit): "iso", "top", "bottom", or
    a direction to look along (from the camera into the design)."""
    v = h.view()
    if kind == "iso":
        h.fit()
    elif kind == "top":
        v.viewTop()
    elif kind == "bottom":
        v.viewBottom()
    else:
        v.setViewDirection(tuple(kind))
    vx.wait(120)


UNDER_FRONT = (-1.0, 1.0, 1.0)  # looking up from below, front right (into the rails' gap)


def joint_panel():
    return vx.joint_panel()


def hovering():
    """The snap hover of the open dialog (a joint dialog's `hover`, Align's `snaps`)."""
    p = vx.panel()
    if p is None:
        return None
    return getattr(p, "hover", None) or getattr(p, "snaps", None)


def keys_to_window():
    """xvfb has no window manager: after a file dialog closes nothing gives the main window the
    keyboard back (a desktop's window manager does), so a key (J, M) would go nowhere."""
    mw = Gui.getMainWindow()
    if QtWidgets.QApplication.activeWindow() is not mw:
        print("[SciForge] journey_vex: the main window takes the keyboard back", flush=True)
        mw.raise_()
        mw.activateWindow()
        vx.wait(150)


def aim(where, point_fn, dot_fn, kinds, view="iso", size=40.0, label=""):
    """Two steps: the view turned and zoomed, the mouse onto the point (on the metal next to
    the dot); then the dot checked lit and clicked."""

    def hover():
        look(view)
        S["dot"] = dot_fn()
        S["pt"] = point_fn()
        vx.look_at(S["dot"], size)
        vx.hover(S["pt"])

    def click():
        kinds_ = (kinds,) if isinstance(kinds, str) else kinds
        for wiggle in (QtCore.QPoint(1, 0), QtCore.QPoint(0, 1), QtCore.QPoint(-1, -1)):
            hov = hovering()
            hot = getattr(hov, "hot", None) if hov is not None else None
            if (
                hot is not None
                and hot["kind"] in kinds_
                and (hot["point"] - S["dot"]).Length < 1e-5
            ):
                break
            # the dot is not lit (yet): a person moves the mouse a little until it is
            print(
                "[SciForge] journey_vex: %s: the mouse moved again (lit: %s)"
                % (where, hot and hot["kind"]),
                flush=True,
            )
            vx.hover_pixel(h.screen_point(S["pt"]) + wiggle)
        vx.lit(hovering(), "%s: %s" % (where, label), kinds, S["dot"])
        h.click(S["pt"])

    return [hover, click]


def ring(centre, r, view_dir=None):
    """A point `r` mm from `centre` on a horizontal face, toward the camera (so the part does
    not hide it)."""
    d = V(view_dir) if view_dir is not None else vx.view_direction()
    flat = V(d.x, d.y, 0)
    if flat.Length < 1e-9:
        flat = V(0, 1, 0)
    flat.normalize()
    return centre - flat * r


def local(key, x, y, z):
    """A point of component S[key] given in its part's own coordinates (mm)."""
    return S[key].Placement.multVec(V(x, y, z))


def axis_at(key):
    box = bbox(S[key])
    return V((box.XMin + box.XMax) / 2.0, (box.YMin + box.YMax) / 2.0, 0)


def joint_named(prefix):
    return [o for o in vx.joints_list() if o.Label.startswith(prefix)]


def press_j():
    def press():
        S["joints_before"] = len(vx.joints_list())
        keys_to_window()
        h.click_empty()
        h.fit()
        h.press("j")

    return press


def type_offset(text):
    def typed():
        p = joint_panel()
        if h.check("the Joint dialog stays open", p is not None, p):
            bs.type_value(p.offset_fields["z"].widget, text)

    return typed


def joint_steps(prefix, first, second, offset=None, revolute=False, check=None):
    """J; `first` = (where, point_fn, dot_fn, kinds, view, size) of the part that moves, then
    `second` the same for where it goes; Offset Z typed, Motion Revolute; OK; `check(where)`."""

    def opened():
        p = joint_panel()
        if p is not None:
            return
        from sciforge import commands

        app = QtWidgets.QApplication
        focus = app.focusWidget()
        diag = {
            "told": (getattr(commands, "_TOLD", None) or {}).get("msg"),
            "popup": app.activePopupWidget(),
            "modal": app.activeModalWidget(),
            "focus": focus and focus.metaObject().className(),
            "window": app.activeWindow() and app.activeWindow().metaObject().className(),
            "dialog": Gui.Control.activeDialog(),
            "task": vx.panel(),
        }
        h.check("%s: J opened the Joint dialog" % prefix, False, diag)
        js.menu("Joint")  # a person then takes ASSEMBLE > Joint

    out = [step(press_j(), prefix + "_j", 900), step(opened, prefix + "_opened", 900)]
    names = ("first", "second")
    for n, (where, point_fn, dot_fn, kinds, view, size) in enumerate((first, second)):
        hover, click = aim(prefix, point_fn, dot_fn, kinds, view, size, where)
        out.append(step(hover, "%s_hover_%s" % (prefix, names[n])))
        out.append(step(click, "%s_click_%s" % (prefix, names[n]), 500 if n == 0 else 1500))
    if offset is not None:
        out.append(step(type_offset(offset), prefix + "_offset", 1500))
    if revolute:

        def motion():
            p = joint_panel()
            if h.check("%s: the Joint dialog" % prefix, p is not None):
                js.click_tab(p, "Motion")
                js.choose_type(p, "Revolute")

        out.append(step(motion, prefix + "_revolute", 2600))

    def preview():
        if check is not None:
            check(prefix + " preview")
        vx.ok()

    def made():
        h.check("%s: OK closed the Joint dialog" % prefix, joint_panel() is None)
        h.check(
            "%s: one more joint" % prefix,
            len(vx.joints_list()) == S["joints_before"] + 1,
            [o.Label for o in vx.joints_list()],
        )
        if check is not None:
            check(prefix)

    out.append(step(preview, prefix + "_preview", 1500))
    out.append(step(made, prefix + "_made", 800))
    return out


def dup_panel():
    from sciforge import duplicate_joints_ui

    p = duplicate_joints_ui.DuplicatePanel.last
    return None if p is None or p._closed else p


def duplicate_steps(prefix, key, targets, check=None):
    """Select S[key]'s row, ASSEMBLE > Duplicate With Joints; each target = (where, point_fn,
    dot_fn, kinds, view, size): a click there makes a joined copy; OK."""

    def pick():
        h.click_empty()
        Gui.Selection.clearSelection()
        ti.click_row(S[key].Label)

    def open_dialog():
        vx.menu("ASSEMBLE", "Duplicate With Joints")

    def ready():
        p = dup_panel()
        if not h.check("%s: Duplicate With Joints open" % prefix, p is not None):
            return
        h.check(
            "%s: Components: %s" % (prefix, S[key].Label),
            [m.Label for m in p.members] == [S[key].Label],
            [m.Label for m in p.members],
        )
        joint, _side = p.chosen()
        h.check("%s: its joint taken by itself" % prefix, joint is not None, p.joint_box.count())
        h.check("%s: the Position box waits" % prefix, p.active == "position", p.active)
        S["copies0"] = len(copies(key))

    out = [
        step(pick, prefix + "_pick", 600),
        step(open_dialog, prefix + "_open", 1200),
        step(ready, prefix + "_ready"),
    ]
    for n, (where, point_fn, dot_fn, kinds, view, size) in enumerate(targets):
        hover, click = aim(prefix, point_fn, dot_fn, kinds, view, size, where)
        out.append(step(hover, "%s_hover_%d" % (prefix, n + 1)))
        out.append(step(click, "%s_click_%d" % (prefix, n + 1), 1500))

    def counted():
        p = dup_panel()
        n = len(targets)
        h.check(
            "%s: %d copies made" % (prefix, n),
            len(copies(key)) == S["copies0"] + n,
            [c.Label for c in copies(key)],
        )
        if p is not None:
            h.check(
                "%s: the dialog counts them" % prefix,
                "%d cop" % n in p.count.text(),
                p.count.text(),
            )
        vx.ok()

    def kept():
        h.check("%s: OK closed the dialog" % prefix, dup_panel() is None)
        if check is not None:
            check(prefix)

    out.append(step(counted, prefix + "_counted", 1000))
    out.append(step(kept, prefix + "_kept", 800))
    return out


def copies(key):
    """S[key] and its occurrences (Duplicate With Joints, the same file again)."""
    from sciforge import instances

    return [S[key]] + list(instances.instances_of(S[key]))


# == 3. standoffs between the rails ============================================================
STANDOFF_HOLES = [(2, 1), (22, 1)]  # rail 1's holes (row 1: the front flange hides row 0)


def standoff_top():
    box = bbox(S["standoff"])
    return V((box.XMin + box.XMax) / 2.0, (box.YMin + box.YMax) / 2.0, box.ZMax)


def standoffs_ok(where):
    found = copies("standoff")
    ok = len(found) == 2
    for c in found:
        box = bbox(c)
        mid = V((box.XMin + box.XMax) / 2.0, (box.YMin + box.YMax) / 2.0, 0)
        on = any(vx.near_xy(mid, grid(i, j), EPS) for i, j in STANDOFF_HOLES)
        ok = ok and on and abs(box.ZMin - T) < EPS and abs(box.ZMax - (T + GAP)) < EPS
    h.check(
        "%s: two standoffs on rail 1's holes %s, from its web up to rail 2's (5 in)"
        % (where, STANDOFF_HOLES),
        ok,
        [(c.Label, bbox(c)) for c in found],
    )


def standoff_steps():
    first = (
        "the standoff's top end",
        lambda: ring(standoff_top(), 2.6),
        standoff_top,
        ("centre", "loop"),
        "iso",
        25.0,
    )
    i, j = STANDOFF_HOLES[0]
    second = (
        "rail 1 next to its hole (%d, %d)" % (i, j),
        lambda: next_to("rail1", i, j),
        lambda: grid(i, j),
        "loop",
        "iso",
        40.0,
    )

    def one(where):
        box = bbox(S["standoff"])
        mid = V((box.XMin + box.XMax) / 2.0, (box.YMin + box.YMax) / 2.0, 0)
        h.check(
            "%s: the standoff on rail 1's hole (2, 1) at %s" % (where, fmt(grid(2, 1))),
            vx.near_xy(mid, grid(2, 1), EPS),
            fmt(mid),
        )
        h.check(
            "%s: it stands from rail 1's web (z %.3f in) up 5 in" % (where, T / IN),
            abs(box.ZMin - T) < EPS and abs(box.ZMax - (T + GAP)) < EPS,
            box,
        )

    i2, j2 = STANDOFF_HOLES[1]
    target = (
        "rail 1 next to its hole (%d, %d)" % (i2, j2),
        lambda: next_to("rail1", i2, j2),
        lambda: grid(i2, j2),
        "loop",
        "iso",
        40.0,
    )
    return joint_steps("j3_standoff", first, second, check=one) + duplicate_steps(
        "j3_standoff_dup", "standoff", [target], check=standoffs_ok
    )


# == 4. bearing flats (Align), screws (J, Duplicate With Joints), Keps nuts ====================
BEARING_T = 0.1 * IN
SHAFT_HOLE = (12, 1)  # rail 1's hole the shaft goes through (rail 2's (12, 0) above it)
SCREW_HEAD = 0.08 * IN
SCREW_LEN = 0.5 * IN
NUT_H = 0.15 * IN


def align_part_steps(prefix, first, second, check=None, angle=0):
    """MODIFY > Align, Objects: Components; From `first`, To `second` (aim tuples); Angle
    `angle` times; OK; `check(where)`."""

    def open_align():
        h.click_empty()
        vx.fit()
        vx.menu("MODIFY", "Align")

    def components():
        p = vx.panel()
        if h.check("%s: Align dialog" % prefix, p is not None and p.title == "Align", p):
            from SciForgeTests.gui import direct_steps as d

            if p.objects.currentText() != "Components":
                d.choose("objects", "Components")

    out = [step(open_align, prefix + "_align", 1000), step(components, prefix + "_components")]
    for n, (where, point_fn, dot_fn, kinds, view, size) in enumerate((first, second)):
        hover, click = aim(prefix, point_fn, dot_fn, kinds, view, size, where)
        out.append(step(hover, "%s_hover_%d" % (prefix, n + 1)))
        out.append(step(click, "%s_click_%d" % (prefix, n + 1), 500 if n == 0 else 1500))
    for k in range(angle):

        def turn():
            from SciForgeTests.gui import widget_input as wi

            p = vx.panel()
            if p is not None:
                wi.click(p.angle_button)

        out.append(step(turn, "%s_angle_%d" % (prefix, k + 1), 1200))

    def preview():
        if check is not None:
            check(prefix + " preview")
        vx.ok()

    def done():
        h.check("%s: Align closed" % prefix, vx.panel() is None)
        if check is not None:
            check(prefix)

    out.append(step(preview, prefix + "_preview", 1200))
    out.append(step(done, prefix + "_done", 800))
    return out


def bearing_on(key, where, centre, below):
    """Bearing S[key] lies flat on a rail, its bore on the hole `centre`, under the rail
    (`below`) or on top of it, its two mounting holes on the next holes along the rail."""
    box = bbox(S[key])
    bore = S[key].Placement.multVec(V(0, 0, 0))
    h.check(
        "%s: the bore on the hole at %s" % (where, fmt(centre)),
        vx.near_xy(bore, centre, EPS),
        fmt(bore),
    )
    if below:
        flat = abs(box.ZMax - centre.z) < EPS and abs(box.ZMin - (centre.z - BEARING_T)) < EPS
    else:
        flat = abs(box.ZMin - centre.z) < EPS and abs(box.ZMax - (centre.z + BEARING_T)) < EPS
    h.check("%s: flat %s the rail" % (where, "under" if below else "on"), flat, box)
    holes = sorted(S[key].Placement.multVec(V(x, 0, 0)).x for x in (-PITCH, PITCH))
    want = [centre.x - PITCH, centre.x + PITCH]
    h.check(
        "%s: its mounting holes on the rail's holes at x %.2f and %.2f in"
        % (where, want[0] / IN, want[1] / IN),
        all(abs(a - b) < EPS for a, b in zip(holes, want)),
        holes,
    )


def bottom_hole():
    """Rail 1's shaft hole on its bottom face (z = 0)."""
    i, j = SHAFT_HOLE
    return V(grid(i, j).x, grid(i, j).y, 0.0)


def top_hole():
    """Rail 2's hole over it, on rail 2's outer face (z = 2t + 5 in)."""
    i, j = SHAFT_HOLE
    return V(grid(i, j).x, grid(i, j).y, 2 * T + GAP)


def bearing1_steps():
    i, j = SHAFT_HOLE
    first = (
        "the bearing's top next to its bore",
        lambda: local("bearing", 0, -3.2, BEARING_T),
        lambda: local("bearing", 0, 0, BEARING_T),
        ("loop", "centre", "circle"),
        "iso",
        25.0,
    )
    second = (
        "rail 1's underside next to its hole (%d, %d)" % (i, j),
        lambda: next_to("rail1", i, j, top=False),
        bottom_hole,
        "loop",
        "bottom",
        40.0,
    )
    return align_part_steps(
        "j4_bearing1",
        first,
        second,
        check=lambda where: bearing_on("bearing", where, bottom_hole(), True),
    )


def bearing2_steps():
    def insert():
        S["dialog2"] = {}
        insert_step([BEARING], S["dialog2"])

    def occurrence():
        from sciforge import instances

        d = S.get("dialog2", {})
        h.check("j4: the bearing's file picked again", d.get("done") and not d.get("error"), d)
        second = comp(BEARING + ":2")
        h.check(
            "j4: the bearing again is another occurrence (bearing_flat:2)",
            second is not None
            and instances.is_instance(second)
            and instances.source_of(second) is S["bearing"],
            [c.Label for c in comps()],
        )
        S["bearing2"] = second
        vx.ok()

    first = (
        "the second bearing's top next to its bore",
        lambda: local("bearing2", 0, -3.2, BEARING_T),
        lambda: local("bearing2", 0, 0, BEARING_T),
        ("loop", "centre", "circle"),
        "iso",
        25.0,
    )
    i, j = SHAFT_HOLE
    second = (
        "rail 2's outer face next to its hole (%d, %d)" % (i, 1 - j),
        lambda: next_to("rail2", i, 1 - j, top=False),
        top_hole,
        "loop",
        "iso",
        40.0,
    )
    return [
        step(insert, "j4_insert_bearing_again", 2500),
        step(occurrence, "j4_occurrence", 1200),
    ] + align_part_steps(
        "j4_bearing2",
        first,
        second,
        check=lambda where: bearing_on("bearing2", where, top_hole(), False),
    )


def screw_places():
    """Where the six screws go, by hand: (axis x, y, the face the head sits on, the way the
    shank points (+1 up, -1 down))."""
    b, t = bottom_hole(), top_hole()
    out = []
    for dx in (-PITCH, PITCH):  # the bottom bearing's mounting holes: heads under it
        out.append((b.x + dx, b.y, -BEARING_T, 1))
    for i, j in STANDOFF_HOLES:  # under rail 1, into the standoffs
        out.append((grid(i, j).x, grid(i, j).y, 0.0, 1))
    for dx in (-PITCH, PITCH):  # the top bearing's mounting holes: heads on it
        out.append((t.x + dx, t.y, t.z + BEARING_T, -1))
    return out


def screw_ok(c):
    """(ok, detail): screw component `c` on one of the six places, its head on the face."""
    box = bbox(c)
    mid = V((box.XMin + box.XMax) / 2.0, (box.YMin + box.YMax) / 2.0, 0)
    seen = False
    for x, y, face, way in screw_places():  # (the two bearings' screws share x and y)
        if not vx.near_xy(mid, V(x, y, 0), EPS):
            continue
        seen = True
        if way > 0:
            ok = (
                abs(box.ZMin - (face - SCREW_HEAD)) < EPS
                and abs(box.ZMax - (face + SCREW_LEN)) < EPS
            )
        else:
            ok = (
                abs(box.ZMax - (face + SCREW_HEAD)) < EPS
                and abs(box.ZMin - (face - SCREW_LEN)) < EPS
            )
        if ok:
            return True, (c.Label, fmt(mid), box.ZMin / IN, box.ZMax / IN)
    return False, (c.Label, fmt(mid), box.ZMin / IN, box.ZMax / IN, "" if seen else "on no hole")


def screws_ok(where, count=6):
    found = copies("screw")
    h.check("%s: %d screws" % (where, count), len(found) == count, [c.Label for c in found])
    spots = set()
    for c in found:
        ok, detail = screw_ok(c)
        h.check("%s: %s sits on a hole centre, its head on the face" % (where, c.Label), ok, detail)
        box = bbox(c)
        spots.add((round((box.XMin + box.XMax) / 2.0, 3), round(box.ZMin, 2)))
    h.check("%s: no two screws in one hole" % where, len(spots) == len(found), sorted(spots))


def screw_steps():
    places = screw_places()

    def bearing_hole(key, x, z):
        return lambda: local(key, x, 0, z)

    def beside(key, x, z):  # 3 mm from the mounting hole's centre, toward the bore
        return lambda: local(key, x - math.copysign(3.0, x), 0, z)

    first = (
        "the screw head's underside",
        lambda: ring(local("screw", 0, 0, 0), 2.75),
        lambda: local("screw", 0, 0, 0),
        ("centre", "loop"),
        "bottom",
        25.0,
    )
    second = (
        "the bottom bearing's mounting hole",
        beside("bearing", -PITCH, 0.0),
        bearing_hole("bearing", -PITCH, 0.0),
        ("loop", "centre", "circle"),
        "bottom",
        30.0,
    )

    def one(where):
        c = S["screw"]
        ok, detail = screw_ok(c)
        x, y, face, _way = places[0]
        h.check(
            "%s: the screw in the bearing's hole at (%.2f, %.2f) in, its head under the bearing"
            % (where, x / IN, y / IN),
            ok and abs((bbox(c).XMin + bbox(c).XMax) / 2.0 - x) < EPS,
            detail,
        )

    targets = [
        (
            "the bottom bearing's other mounting hole",
            beside("bearing", PITCH, 0.0),
            bearing_hole("bearing", PITCH, 0.0),
            ("loop", "centre", "circle"),
            "bottom",
            30.0,
        )
    ]
    for i, j in STANDOFF_HOLES:
        targets.append(
            (
                "rail 1's underside next to its hole (%d, %d) (under a standoff)" % (i, j),
                lambda i=i, j=j: next_to("rail1", i, j, top=False),
                lambda i=i, j=j: V(grid(i, j).x, grid(i, j).y, 0.0),
                "loop",
                "bottom",
                40.0,
            )
        )
    for x in (-PITCH, PITCH):
        targets.append(
            (
                "the top bearing's mounting hole",
                beside("bearing2", x, 0.0),
                bearing_hole("bearing2", x, 0.0),
                ("loop", "centre", "circle"),
                "top",
                30.0,
            )
        )
    return joint_steps("j3_screw", first, second, check=one) + duplicate_steps(
        "j3_screw_dup", "screw", targets, check=screws_ok
    )


def nut_places():
    """The four Keps nuts, by hand: on the bearing screws' ends inside the rails, the washer
    against the rail's inside face: (x, y, the face's z, +1 the nut stands up from it / -1
    hangs down)."""
    b = bottom_hole()
    out = [(b.x + dx, b.y, T, 1) for dx in (-PITCH, PITCH)]
    out += [(b.x + dx, b.y, T + GAP, -1) for dx in (-PITCH, PITCH)]
    return out


def nuts_ok(where, count=4):
    found = copies("nut")
    h.check("%s: %d Keps nuts" % (where, count), len(found) == count, [c.Label for c in found])
    for c in found:
        box = bbox(c)
        mid = V((box.XMin + box.XMax) / 2.0, (box.YMin + box.YMax) / 2.0, 0)
        ok = False
        for x, y, face, way in nut_places():  # (rail 1's and rail 2's share x and y)
            if vx.near_xy(mid, V(x, y, 0), EPS):
                if way > 0:
                    good = abs(box.ZMin - face) < EPS and abs(box.ZMax - (face + NUT_H)) < EPS
                else:
                    good = abs(box.ZMax - face) < EPS and abs(box.ZMin - (face - NUT_H)) < EPS
                ok = ok or good
        h.check(
            "%s: %s on a screw's end, against the rail's inside face" % (where, c.Label),
            ok,
            (fmt(mid), box.ZMin / IN, box.ZMax / IN),
        )


def nut_steps():
    b = bottom_hole
    i, j = SHAFT_HOLE
    first = (
        "the Keps nut's washer",
        lambda: ring(local("nut", 0, 0, 0), 3.5),
        lambda: local("nut", 0, 0, 0),
        ("centre", "loop"),
        "bottom",
        25.0,
    )
    second = (
        "rail 1's inside face next to its hole (%d, %d)" % (i - 1, j),
        lambda: next_to("rail1", i - 1, j),
        lambda: grid(i - 1, j),
        "loop",
        "iso",
        40.0,
    )

    def one(where):
        box = bbox(S["nut"])
        mid = V((box.XMin + box.XMax) / 2.0, (box.YMin + box.YMax) / 2.0, 0)
        h.check(
            "%s: the nut on the first screw's end, on rail 1's inside face" % where,
            vx.near_xy(mid, V(b().x - PITCH, b().y, 0), EPS)
            and abs(box.ZMin - T) < EPS
            and abs(box.ZMax - (T + NUT_H)) < EPS,
            (fmt(mid), box),
        )

    targets = [
        (
            "rail 1's inside face next to its hole (%d, %d)" % (i + 1, j),
            lambda: next_to("rail1", i + 1, j),
            lambda: grid(i + 1, j),
            "loop",
            "iso",
            40.0,
        )
    ]
    for side in (-1, 1):
        targets.append(
            (
                "rail 2's inside face next to its hole (%d, %d)" % (i + side, 1 - j),
                lambda side=side: next_to("rail2", i + side, 1 - j, top=True),
                lambda side=side: hole("rail2", i + side, 1 - j, top=True),
                "loop",
                UNDER_FRONT,
                40.0,
            )
        )
    return joint_steps("j3_nut", first, second, check=one) + duplicate_steps(
        "j3_nut_dup", "nut", targets, check=nuts_ok
    )


# == 4b. the shaft (revolute) and the wheel (rigid on it) ======================================
SHAFT_SIDE = 0.125 * IN
SHAFT_DOWN = 5.5 * IN  # Offset Z typed: from the top bearing's face down through everything
WHEEL_DOWN = 3.5 * IN  # Offset Z typed: from the shaft's top end down to between the rails


def shaft_top():
    box = bbox(S["shaft"])
    return V((box.XMin + box.XMax) / 2.0, (box.YMin + box.YMax) / 2.0, box.ZMax)


def shaft_low():
    """By hand: the shaft's end on the top bearing's face (z = 2t + 5 + 0.1 in), pushed down
    5.5 in: from -0.272 in up 6 in to 5.728 in."""
    return top_hole().z + BEARING_T - SHAFT_DOWN


def shaft_ok(where, turned=0.0):
    box = bbox(S["shaft"])
    c = bottom_hole()
    h.check(
        "%s: the shaft on the holes' axis %s" % (where, fmt(V(c.x, c.y, 0))),
        vx.near_xy(axis_at("shaft"), c, EPS),
        fmt(axis_at("shaft")),
    )
    low = shaft_low()
    h.check(
        "%s: the shaft from z %.3f in up 6 in (through bearing, rail, rail, bearing)"
        % (where, low / IN),
        abs(box.ZMin - low) < EPS and abs(box.ZMax - (low + 6.0 * IN)) < EPS,
        (box.ZMin / IN, box.ZMax / IN),
    )
    h.check(
        "%s: it passes both bearings" % where,
        box.ZMin < -BEARING_T and box.ZMax > top_hole().z + BEARING_T,
        box,
    )
    a = math.radians(turned)
    wide = SHAFT_SIDE * (abs(math.cos(a)) + abs(math.sin(a)))
    h.check(
        "%s: the shaft's width %.4f in (turned %g degrees)" % (where, wide / IN, turned),
        abs(box.XLength - wide) < EPS and abs(box.YLength - wide) < EPS,
        (box.XLength / IN, box.YLength / IN),
    )


def wheel_low():
    """By hand: the wheel's face on the shaft's top end (5.728 in), 3.5 in down: 2.228 in, up
    0.5 in to 2.728 in: between the webs (0.064 .. 5.064 in) and clear of the flanges (rail 1's
    up to 0.5 in, rail 2's down to 4.628 in)."""
    return shaft_low() + 6.0 * IN - WHEEL_DOWN


def wheel_ok(where, turned=None):
    box = bbox(S["wheel"])
    c = bottom_hole()
    h.check(
        "%s: the wheel on the shaft's axis" % where,
        vx.near_xy(axis_at("wheel"), c, EPS),
        fmt(axis_at("wheel")),
    )
    low = wheel_low()
    h.check(
        "%s: the wheel from z %.3f to %.3f in, between the rails"
        % (where, low / IN, (low + WHEEL_T) / IN),
        abs(box.ZMin - low) < EPS
        and abs(box.ZMax - (low + WHEEL_T)) < EPS
        and box.ZMin > 0.5 * IN
        and box.ZMax < 2 * T + GAP - 0.5 * IN,
        (box.ZMin / IN, box.ZMax / IN),
    )


def shaft_steps():
    first = (
        "the shaft's top end",
        lambda: ring(shaft_top(), 0.6),
        shaft_top,
        ("centre",),
        "iso",
        15.0,
    )
    second = (
        "the top bearing next to its bore",
        lambda: local("bearing2", 0, -3.2, 0.0),
        lambda: local("bearing2", 0, 0, 0.0),
        ("loop", "centre", "circle"),
        "iso",
        25.0,
    )
    return joint_steps("j4_shaft", first, second, offset="-5.5", revolute=True, check=shaft_ok)


def wheel_steps():
    first = (
        "the wheel's face next to its square hole",
        lambda: local("wheel", 0, -2.4, WHEEL_T),
        lambda: local("wheel", 0, 0, WHEEL_T),
        ("loop", "centre", "circle"),
        "iso",
        20.0,
    )
    second = (
        "the shaft's top end",
        lambda: ring(shaft_top(), 0.6),
        shaft_top,
        ("centre",),
        "iso",
        15.0,
    )
    return joint_steps("j4_wheel", first, second, offset="-3.5", check=wheel_ok)


# == 5. Drive Joints, a Rigid Group for the frame =============================================
def revolute():
    found = joint_named("Revolute")
    return found[0] if found else None


def drive_steps(prefix, degrees, undo=True):
    def drive():
        h.click_empty()
        S["before_drive"] = places()
        S["wheel_rot"] = App.Rotation(S["wheel"].Placement.Rotation)
        joint = revolute()
        if h.check("%s: the revolute joint in the browser" % prefix, joint is not None):
            js.browser_menu(joint.Label, "Drive Joints")

    def type_angle():
        p = js.panel()
        h.check(
            "%s: Drive Joints on the revolute" % prefix,
            p is not None and getattr(p, "joint", None) is revolute(),
            p and getattr(p, "joint", None),
        )
        if p is not None:
            t0 = time.perf_counter()
            bs.type_value(p.angle.widget, "%g" % degrees)
            S["drive_s"] = time.perf_counter() - t0

    def turned():
        shaft_ok("%s: driven %g degrees" % (prefix, degrees), degrees)
        wheel_ok("%s: driven" % prefix)
        moved = sorted(moved_since(S["before_drive"]))
        h.check(
            "%s: only the shaft and the wheel moved" % prefix,
            moved == sorted([SHAFT, WHEEL]),
            moved,
        )
        turn = S["wheel"].Placement.Rotation.multiply(S["wheel_rot"].inverted())
        angle = math.degrees(turn.Angle)
        h.check(
            "%s: the wheel turned %g degrees about the shaft" % (prefix, degrees),
            abs(angle - degrees) < 1e-3 and abs(abs(turn.Axis.z) - 1.0) < 1e-6,
            (angle, turn.Axis),
        )
        print("[SciForge] journey_vex: Drive Joints step %.2f s" % S.get("drive_s", -1), flush=True)
        h.shot("%s-driven" % prefix)
        js.ok()

    out = [
        step(drive, prefix + "_drive", 1500),
        step(type_angle, prefix + "_type", 2500),
        step(turned, prefix + "_turned", 1200),
    ]
    if undo:

        def back():
            js.no_dialog("Drive OK")
            vx.undo()

        def square():
            shaft_ok("%s: Undo" % prefix, 0.0)
            moved = moved_since(S["before_drive"])
            h.check("%s: Undo: everything where it was" % prefix, not moved, moved)

        out += [step(back, prefix + "_undo", 1500), step(square, prefix + "_square")]
    return out


FRAME = ("rail1", "rail2", "standoff", "bearing", "bearing2")


def rigid_group_steps():
    def pick():
        h.click_empty()
        Gui.Selection.clearSelection()
        labels = [S[k].Label for k in FRAME] + [copies("standoff")[1].Label]
        S["frame_labels"] = labels
        ti.click_row(labels[0])
        for label in labels[1:]:
            ti.click_row(label, QtCore.Qt.ControlModifier)

    def open_group():
        js.menu("Rigid Group")

    def members():
        from sciforge import joints_ui

        p = joints_ui.RigidGroupPanel.last
        if not h.check("Rigid Group open", p is not None and not p._closed):
            return
        got = sorted(m.Label for m in p.members)
        h.check("the frame's six parts picked", got == sorted(S["frame_labels"]), got)
        js.ok()

    def made():
        from sciforge import joints

        groups = (
            [o for o in doc().Objects if joints.is_rigid_group(o)]
            if hasattr(joints, "is_rigid_group")
            else [o for o in doc().Objects if o.Label.startswith("Rigid Group")]
        )
        h.check("a Rigid Group for the frame", len(groups) == 1, [o.Label for o in groups])
        js.no_dialog("Rigid Group OK")

    return [
        step(pick, "j5_pick_frame", 800),
        step(open_group, "j5_rigid_group", 1200),
        step(members, "j5_members", 1200),
        step(made, "j5_group_made"),
    ]


# == 6. the screw's file again: another occurrence; the parts list ==============================
def parts_list():
    """{part: Qty} of a drawing's parts list of the whole design (drawing_core.parts_rows: what
    DRAWING's Parts List shows)."""
    from sciforge import drawing, drawing_core

    found = [b for b in doc().Objects if b.TypeId == "PartDesign::Body"]
    rows = drawing_core.parts_rows(drawing.components_of(found))
    return {r["PartNumber"]: r["Qty"] for r in rows}


def again_steps():
    def insert():
        S["labels_before"] = {c.Label for c in comps()}
        S["dialog3"] = {}
        insert_step([SCREW], S["dialog3"])

    def occurrence():
        from sciforge import instances

        d = S.get("dialog3", {})
        h.check("j6: the screw's file picked again", d.get("done") and not d.get("error"), d)
        new = [c for c in comps() if c.Label not in S["labels_before"]]
        h.check("j6: one new component", len(new) == 1, [c.Label for c in new])
        if not new:
            return
        S["screw7"] = new[0]
        h.check(
            "j6: an occurrence of the first screw (%s), not a second reading of the file"
            % new[0].Label,
            instances.is_instance(new[0]) and instances.source_of(new[0]) is S["screw"],
            new[0].Label,
        )
        h.check("j6: named after it, numbered on", new[0].Label == SCREW + ":7", new[0].Label)
        p = move_panel()
        if h.check("j6: its Move dialog", p is not None):
            c2.type_value(p, "dy", "-3")  # 3 in toward the front, clear of the frame

    def placed():
        vx.ok()

    def counted():
        qty = parts_list()
        want = {
            SCREW: 7,
            NUT: 4,
            STANDOFF: 2,
            BEARING: 2,
            RAIL1: 1,
            RAIL2: 1,
            SHAFT: 1,
            WHEEL: 1,
        }
        h.check(
            "j6: the parts list counts 7 screws in one row (and every other part)",
            qty == want,
            qty,
        )

    first = (
        "the new screw's head underside",
        lambda: ring(local("screw7", 0, 0, 0), 2.75),
        lambda: local("screw7", 0, 0, 0),
        ("centre", "loop", "circle"),
        "bottom",
        25.0,
    )
    i, j = STANDOFF_HOLES[0]
    second = (
        "rail 2's outer face next to its hole (%d, %d), over the standoff" % (i, 1 - j),
        lambda: next_to("rail2", i, 1 - j, top=False),
        lambda: V(grid(i, j).x, grid(i, j).y, 2 * T + GAP),
        "loop",
        "iso",
        40.0,
    )

    def on_standoff(where):
        box = bbox(S["screw7"])
        face = 2 * T + GAP
        h.check(
            "%s: the seventh screw through rail 2 into the standoff's top" % where,
            vx.near_xy(axis_at("screw7"), grid(i, j), EPS)
            and abs(box.ZMax - (face + SCREW_HEAD)) < EPS
            and abs(box.ZMin - (face - SCREW_LEN)) < EPS,
            (fmt(axis_at("screw7")), box.ZMin / IN, box.ZMax / IN),
        )

    return [
        step(insert, "j6_insert_screw_again", 2500),
        step(occurrence, "j6_occurrence", 1500),
        step(placed, "j6_placed", 1200),
        step(counted, "j6_parts_list"),
    ] + joint_steps("j6_screw7", first, second, check=on_standoff)


# == 7. save, close, reopen =====================================================================
KEYS = (
    "rail1",
    "rail2",
    "standoff",
    "screw",
    "nut",
    "shaft",
    "bearing",
    "bearing2",
    "wheel",
    "screw7",
)


def reopen_steps():
    def save():
        S["places"] = {c.Label: App.Placement(c.Placement) for c in comps()}
        S["joint_labels"] = sorted(o.Label for o in vx.joints_list())
        S["key_labels"] = {k: S[k].Label for k in KEYS if S.get(k) is not None}
        S["out"] = os.path.join(h.OUT_DIR, "journey_vex_design")
        os.makedirs(S["out"], exist_ok=True)
        S["file"] = os.path.join(S["out"], "JourneyVex.FCStd")
        if os.path.isfile(S["file"]):
            os.remove(S["file"])
        keys_to_window()
        h.click_empty()
        h.press(QtCore.Qt.Key_S, QtCore.Qt.ControlModifier)

    def save_dialog():
        from SciForgeTests.gui import versions_input as vi

        if h.check("Ctrl+S: the Save dialog", vi.save_dialog() is not None, h.popups()):
            vi.fill_save_dialog(name="JourneyVex", location=S["out"])
            t0 = time.perf_counter()
            vi.click_save()
            S["save_s"] = time.perf_counter() - t0

    def saved():
        h.check("JourneyVex.FCStd written", os.path.isfile(S["file"]), os.listdir(S["out"]))
        h.check("the design is that file", doc().FileName == S["file"], doc().FileName)
        print("[SciForge] journey_vex: saved in %.2f s" % S.get("save_s", -1), flush=True)
        from SciForgeTests.gui import polish2_steps as p2

        S["doc_name"] = doc().Name
        p2.close_tab(doc())

    def closed():
        h.check("the design closed", S["doc_name"] not in App.listDocuments(), App.listDocuments())
        S["dialog4"] = {}
        answer_file_dialog([S["file"]], S["dialog4"])
        keys_to_window()
        t0 = time.perf_counter()
        # (no design open: no 3D view; the key goes to the window)
        QtTest.QTest.keyClick(Gui.getMainWindow(), QtCore.Qt.Key_O, QtCore.Qt.ControlModifier)
        QtWidgets.QApplication.processEvents()
        S["open_s"] = time.perf_counter() - t0

    def reopened():
        d = S.get("dialog4", {})
        h.check("Ctrl+O: the Open dialog took the file", d.get("done") and not d.get("error"), d)
        h.check(
            "the design is open again",
            doc() is not None and doc().FileName == S["file"],
            doc() and doc().FileName,
        )
        print("[SciForge] journey_vex: reopened in %.2f s" % S.get("open_s", -1), flush=True)
        if doc() is None:
            return
        by = {c.Label: c for c in comps()}
        for k, label in S.get("key_labels", {}).items():
            S[k] = by.get(label)
        moved = [
            label
            for label, plc in S["places"].items()
            if by.get(label) is None or not by[label].Placement.isSame(plc, 1e-7)
        ]
        h.check(
            "every one of the %d components where it was" % len(S["places"]),
            not moved and len(by) == len(S["places"]),
            moved or sorted(by),
        )
        h.check(
            "every joint back",
            sorted(o.Label for o in vx.joints_list()) == S["joint_labels"],
            sorted(o.Label for o in vx.joints_list()),
        )
        h.check("the design is still in inches", doc().UnitSystem.startswith("Imperial decimal"))
        on_rail1("reopened", GAP)
        standoffs_ok("reopened")
        screws_ok("reopened", 7)
        nuts_ok("reopened")
        shaft_ok("reopened")
        wheel_ok("reopened")
        errors_free("reopened")
        h.shot("7-reopened")

    return [
        step(save, "j7_ctrl_s", 1500),
        step(save_dialog, "j7_save", 3000),
        step(saved, "j7_close", 2000),
        step(closed, "j7_ctrl_o", 6000),
        step(reopened, "j7_reopened", 1500),
    ] + drive_steps("j7_drive_reopened", 30.0)
