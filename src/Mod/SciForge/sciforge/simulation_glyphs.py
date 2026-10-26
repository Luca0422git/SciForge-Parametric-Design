# SPDX-License-Identifier: LGPL-2.1-or-later
"""The constraints and loads of the active study drawn on the model, like Fusion's glyphs
(research 3.12): small cones standing on a Fixed face (a ground symbol), cones pointing at the
axis of a Pin, balls rolling on a Frictionless face, arrows along a Prescribed Displacement,
arrows pushing on a Force's faces along its direction, a field of short arrows into a
Pressure's faces, a curved arrow around a Moment's axis, a big arrow for gravity. They keep
the same size on the screen whatever the zoom, and are only drawn: Coin nodes in the 3D view,
never document properties (nothing in the file, nothing in the undo history), never picked (a
click goes through them to the face behind). Shown only in the SIMULATION workspace.

A dialog that is open draws its preview with preview() (the same glyphs, lighter) and takes it
away with clear_preview(). sim-results can hide them while results show: set_visible(False).
"""

import math

import FreeCAD as App
import FreeCADGui as Gui

from . import bodies, warn
from . import simulation_setup_core as score

# colours (r, g, b) of each family of glyphs (SciForge's own palette)
HOLD = (0.10, 0.62, 0.66)  # constraints: teal
HOLD_PART = (0.38, 0.78, 0.82)  # a Fixed that holds only some directions
PUSH = (0.96, 0.52, 0.10)  # forces, moments, bearing loads
PRESS = (0.90, 0.30, 0.22)  # pressure
WEIGHT = (0.58, 0.40, 0.88)  # gravity
LOST = (0.85, 0.15, 0.15)
MESH = (0.30, 0.80, 0.35)  # local mesh controls: green dots (Fusion previews them so)

STATE = {
    "root": None,  # SoSeparator in the view's scene graph
    "view": None,  # the view it is in
    "doc": None,
    "scale": None,  # the SoScale every glyph shares (screen size)
    "size": None,  # mm of a glyph now
    "key": None,  # what was drawn (the study and its items)
    "preview": None,  # SoSeparator of the open dialog's preview
    "visible": True,
    "counts": {},  # item name -> number of glyphs drawn (tests)
    "preview_count": 0,
}


def _coin():
    from pivy import coin

    return coin


# -- placing the root ------------------------------------------------------------------------
def _view(doc):
    try:
        gdoc = Gui.getDocument(doc.Name) if doc is not None else None
        view = gdoc.ActiveView if gdoc is not None else None
        if view is None or not hasattr(view, "getSceneGraph"):
            return None
        return view
    except Exception:
        return None


def _ensure_root(doc):
    coin = _coin()
    view = _view(doc)
    if view is None:
        return None
    if STATE["root"] is not None and STATE["view"] is view:
        return STATE["root"]
    clear()
    root = coin.SoSeparator()
    root.setName("SciForgeSimGlyphs")
    pick = coin.SoPickStyle()
    pick.style = coin.SoPickStyle.UNPICKABLE
    root.addChild(pick)
    switch = coin.SoSwitch()
    switch.whichChild = coin.SO_SWITCH_ALL if STATE["visible"] else coin.SO_SWITCH_NONE
    root.addChild(switch)
    STATE["scale"] = coin.SoScale()
    try:
        view.getSceneGraph().addChild(root)
    except Exception as exc:
        warn("simulation glyphs: %s" % exc)
        return None
    STATE["root"], STATE["view"], STATE["doc"] = root, view, doc.Name
    STATE["key"] = None
    _set_size(doc)
    return root


def _content():
    root = STATE["root"]
    return root.getChild(1) if root is not None else None


def clear():
    """Take every glyph away (leaving the workspace, another design in front)."""
    clear_preview()
    root, view = STATE["root"], STATE["view"]
    STATE["root"] = STATE["view"] = STATE["doc"] = None
    STATE["key"] = None
    STATE["counts"] = {}
    if root is None or view is None:
        return
    try:
        view.getSceneGraph().removeChild(root)
    except Exception:
        pass  # the view went with its document


def set_visible(on):
    """Show or hide the glyphs (sim-results hides them while results show, if it wants)."""
    STATE["visible"] = bool(on)
    content = _content()
    if content is not None:
        coin = _coin()
        content.whichChild = coin.SO_SWITCH_ALL if on else coin.SO_SWITCH_NONE


def visible():
    return bool(STATE["visible"])


# -- the size on the screen ----------------------------------------------------------------------
def _model_centre(doc):
    try:
        box = None
        for body in bodies.solid_bodies(doc, visible_only=True):
            b = bodies.global_shape(body, copy=False).BoundBox
            if box is None:
                box = b
            else:
                box.add(b)
        if box is not None:
            return App.Vector(box.Center), box.DiagonalLength
    except Exception:
        pass
    return App.Vector(0, 0, 0), 100.0


def _set_size(doc):
    from . import taskui

    view = STATE["view"]
    if view is None:
        return False
    centre, _diag = _model_centre(doc)
    size = score.glyph_size(taskui.mm_per_pixel(view, centre))
    old = STATE["size"]
    if old is not None and abs(size - old) <= 0.03 * old:
        return False
    STATE["size"] = size
    if STATE["scale"] is not None:
        STATE["scale"].scaleFactor.setValue(size, size, size)
    return True


def follow_zoom():
    """The view zoomed: the glyphs keep their size on the screen."""
    try:
        if STATE["root"] is None:
            return
        doc = App.getDocument(STATE["doc"]) if STATE["doc"] else None
        if doc is not None:
            _set_size(doc)
    except Exception:
        pass


def size():
    """The length of a glyph now (mm)."""
    return STATE["size"]


# -- building glyphs (unit models; one shared SoScale gives them their size) ----------------------
def _material(color, transparency=0.0):
    coin = _coin()
    mat = coin.SoMaterial()
    mat.diffuseColor.setValue(*color)
    mat.emissiveColor.setValue(*[c * 0.45 for c in color])
    mat.transparency.setValue(transparency)
    return mat


def _place(point, direction, model, scaled=True):
    """A glyph `model` (drawn along local -Y, its tip at the origin) at `point` turned so local
    -Y runs along `direction`."""
    coin = _coin()
    sep = coin.SoSeparator()
    transform = coin.SoTransform()
    transform.translation.setValue(point.x, point.y, point.z)
    d = App.Vector(direction)
    if d.Length > 1e-12:
        d.normalize()
        transform.rotation.setValue(
            coin.SbRotation(coin.SbVec3f(0.0, -1.0, 0.0), coin.SbVec3f(d.x, d.y, d.z))
        )
    sep.addChild(transform)
    if scaled and STATE["scale"] is not None:
        sep.addChild(STATE["scale"])
    sep.addChild(model)
    return sep


def _cylinder(y0, y1, radius):
    coin = _coin()
    sep = coin.SoSeparator()
    t = coin.SoTranslation()
    t.translation.setValue(0.0, (y0 + y1) / 2.0, 0.0)
    cyl = coin.SoCylinder()
    cyl.radius.setValue(radius)
    cyl.height.setValue(abs(y1 - y0))
    sep.addChild(t)
    sep.addChild(cyl)
    return sep


def _cone_down(tip_y, height, radius):
    """A cone whose tip is at (0, tip_y, 0) pointing to -Y."""
    coin = _coin()
    sep = coin.SoSeparator()
    t = coin.SoTransform()
    t.translation.setValue(0.0, tip_y + height / 2.0, 0.0)
    t.rotation.setValue(coin.SbVec3f(1.0, 0.0, 0.0), math.pi)
    cone = coin.SoCone()
    cone.bottomRadius.setValue(radius)
    cone.height.setValue(height)
    sep.addChild(t)
    sep.addChild(cone)
    return sep


def _sphere(y, radius):
    coin = _coin()
    sep = coin.SoSeparator()
    t = coin.SoTranslation()
    t.translation.setValue(0.0, y, 0.0)
    ball = coin.SoSphere()
    ball.radius.setValue(radius)
    sep.addChild(t)
    sep.addChild(ball)
    return sep


_MODELS = {}


def _model(name):
    """The unit model of a glyph (made once, shared by every glyph of that kind)."""
    found = _MODELS.get(name)
    if found is not None:
        return found
    coin = _coin()
    model = coin.SoSeparator()
    if name == "arrow":  # length 1, tip at the origin
        model.addChild(_cone_down(0.0, 0.28, 0.09))
        model.addChild(_cylinder(0.26, 1.0, 0.03))
    elif name == "short_arrow":
        model.addChild(_cone_down(0.0, 0.2, 0.07))
        model.addChild(_cylinder(0.18, 0.55, 0.022))
    elif name == "big_arrow":
        model.addChild(_cone_down(0.0, 0.5, 0.16))
        model.addChild(_cylinder(0.45, 2.0, 0.06))
        model.addChild(_sphere(2.1, 0.16))
    elif name == "ground":  # Fixed: a cone standing on the face with a plate on top
        model.addChild(_cone_down(0.0, 0.3, 0.14))
        model.addChild(_cylinder(0.3, 0.34, 0.2))
    elif name == "pin":
        model.addChild(_cone_down(0.0, 0.26, 0.1))
        model.addChild(_cylinder(0.26, 0.42, 0.035))
        model.addChild(_sphere(0.46, 0.07))
    elif name == "dot":
        model.addChild(_sphere(0.0, 0.07))
    elif name == "roller":  # Frictionless: a ball on the face with a plate on top
        model.addChild(_sphere(0.12, 0.12))
        model.addChild(_cylinder(0.24, 0.28, 0.2))
    model.ref()  # kept for the session (Coin deletes an unreferenced node)
    _MODELS[name] = model
    return model


def _polyline(points, color, width=3.0):
    coin = _coin()
    sep = coin.SoSeparator()
    sep.addChild(_material(color))
    style = coin.SoDrawStyle()
    style.lineWidth.setValue(width)
    sep.addChild(style)
    coords = coin.SoCoordinate3()
    coords.point.setValues(0, len(points), [tuple(p) for p in points])
    sep.addChild(coords)
    lines = coin.SoLineSet()
    lines.numVertices.setValue(len(points))
    sep.addChild(lines)
    return sep


# -- where the glyphs go -------------------------------------------------------------------------
def _element(obj, sub):
    try:
        element = bodies.global_shape(obj, copy=False).getElement(sub.split(".")[-1])
        if element is None or element.isNull():
            return None
        return element
    except Exception:
        return None


def _length_along(face, fixed, along_u, a, b, steps=6):
    """Length of the curve on `face` from parameter a to b along u (or v) at `fixed`."""
    total = 0.0
    last = None
    for i in range(steps + 1):
        t = a + (b - a) * i / float(steps)
        point = face.valueAt(t, fixed) if along_u else face.valueAt(fixed, t)
        if last is not None:
            total += (point - last).Length
        last = point
    return total


def _face_samples(face, spacing, most=4):
    """[(point, outward normal)] spread over a face."""
    out = []
    try:
        u0, u1, v0, v1 = face.ParameterRange
        extent_u = _length_along(face, (v0 + v1) / 2.0, True, u0, u1)
        extent_v = _length_along(face, (u0 + u1) / 2.0, False, v0, v1)
        nu = score.samples_per_side(extent_u, spacing, most)
        nv = score.samples_per_side(extent_v, spacing, most)
        for fu in score.grid_fractions(nu):
            for fv in score.grid_fractions(nv):
                u, v = u0 + (u1 - u0) * fu, v0 + (v1 - v0) * fv
                if not face.isPartOfDomain(u, v):
                    continue
                out.append((face.valueAt(u, v), face.normalAt(u, v)))
    except Exception:
        pass
    if not out:
        try:
            centre = face.CenterOfMass
            u, v = face.Surface.parameter(centre)
            out.append((centre, face.normalAt(u, v)))
        except Exception:
            pass
    return out


def _edge_samples(edge, count=3):
    out = []
    try:
        a, b = edge.FirstParameter, edge.LastParameter
        for f in score.grid_fractions(count):
            out.append(edge.valueAt(a + (b - a) * f))
    except Exception:
        pass
    return out


def _anchors(refs, spacing, most=4):
    """[(point, normal or None, kind)] of every pick: faces give several points with their
    normals, edges a few points, corners one."""
    from . import simulation

    out = []
    for obj, sub in simulation._picks(refs):
        element = _element(obj, sub)
        if element is None:
            continue
        name = sub.split(".")[-1]
        if name.startswith("Face"):
            out += [(p, n, "face") for p, n in _face_samples(element, spacing, most)]
        elif name.startswith("Edge"):
            out += [(p, None, "edge") for p in _edge_samples(element)]
        elif name.startswith("Vertex"):
            out.append((element.Point, None, "vertex"))
    return out


def _round_axis(refs):
    """(centre, axis, radius) of the first cylindrical face picked, or None."""
    from . import simulation

    for obj, sub in simulation._picks(refs):
        face = _element(obj, sub)
        try:
            surface = face.Surface
            if "Cylinder" not in surface.TypeId:
                continue
            axis = App.Vector(surface.Axis)
            centre = App.Vector(surface.Center)
            # the middle of the face along the axis
            mid = face.CenterOfMass
            centre = centre + axis * (mid - centre).dot(axis)
            return centre, axis, surface.Radius
        except Exception:
            continue
    return None


def _centroid(refs):
    from . import simulation

    points = []
    for obj, sub in simulation._picks(refs):
        element = _element(obj, sub)
        if element is None:
            continue
        try:
            points.append(element.CenterOfMass)
        except Exception:
            try:
                points.append(element.Point)
            except Exception:
                pass
    if not points:
        return None
    total = App.Vector(0, 0, 0)
    for p in points:
        total = total + p
    return total * (1.0 / len(points))


def _spacing(doc):
    _centre, diag = _model_centre(doc)
    size = STATE["size"] or diag / 20.0
    return max(size * 1.4, diag / 14.0)


def glyphs_for(doc, category, kind, opts, refs, color=None, transparency=0.0, lost=False):
    """An SoSeparator with the glyphs of one constraint / load, and how many were drawn."""
    from . import simulation_core as core

    coin = _coin()
    sep = coin.SoSeparator()
    opts = core.options(category, kind, opts) if kind else dict(opts or {})
    spacing = _spacing(doc)
    count = 0
    if category == "mesh":
        # a local mesh control: green dots on its faces and edges, closer where it is finer
        sep.addChild(_material(LOST if lost else (color or MESH), transparency))
        for p, _n, _k in _anchors(refs, spacing * 0.5, most=6):
            sep.addChild(_place(p, App.Vector(0, 0, -1), _model("dot")))
            count += 1
        return sep, count
    if category == "constraint":
        base = HOLD
        if kind == "fixed" and not all(opts.get(a) for a in ("x", "y", "z")):
            base = HOLD_PART
        sep.addChild(_material(LOST if lost else (color or base), transparency))
        if kind == "pin":
            found = _round_axis(refs)
            if found is not None:
                centre, axis, radius = found
                for p, n, _k in _anchors(refs, spacing):
                    if n is None:
                        continue
                    sep.addChild(
                        _place(p, n * -1.0 if _inward(p, n, centre, axis) else n, _model("pin"))
                    )
                    count += 1
                count += _pin_rod(sep, centre, axis, refs)
        else:
            model = {"fixed": "ground", "frictionless": "roller"}.get(kind, "ground")
            for p, n, _k in _anchors(refs, spacing):
                if kind == "displacement":
                    for axis_name, axis in (("x", (1, 0, 0)), ("y", (0, 1, 0)), ("z", (0, 0, 1))):
                        value = opts.get(axis_name)
                        if value is None:
                            continue
                        d = App.Vector(*axis) * (1.0 if float(value) >= 0 else -1.0)
                        sep.addChild(_place(p, d, _model("short_arrow")))
                        count += 1
                    continue
                d = n * -1.0 if n is not None else App.Vector(0, 0, -1)
                sep.addChild(_place(p, d, _model(model)))
                count += 1
        return sep, count
    # loads
    base = PRESS if kind == "pressure" else PUSH
    sep.addChild(_material(LOST if lost else (color or base), transparency))
    if kind == "pressure":
        pull = bool(opts.get("flip")) != (float(opts.get("magnitude") or 0) < 0)
        for p, n, _k in _anchors(refs, spacing * 0.7, most=5):
            if n is None:
                continue
            sep.addChild(_push(p, n, n if pull else n * -1.0, "short_arrow", 0.55))
            count += 1
        return sep, count
    if kind == "moment":
        centre = _centroid(refs)
        if centre is not None:
            axis = App.Vector(*(opts.get("vector") or [0, 0, 1]))
            if opts.get("direction") == "normal":
                normal = _first_normal(refs)
                if normal is not None:
                    axis = normal
            if opts.get("flip"):
                axis = axis * -1.0
            if float(opts.get("magnitude") or 0) < 0:
                axis = axis * -1.0
            count += _moment(sep, centre, axis)
        return sep, count
    if kind == "remote_force":
        point = App.Vector(*(opts.get("point") or [0, 0, 0]))
        d = _load_direction(opts)
        sep.addChild(_place(point, d, _model("arrow")))
        centre = _centroid(refs)
        if centre is not None:
            sep.addChild(_polyline([tuple(point), tuple(centre)], color or base, 1.5))
        return sep, 1
    # force, bearing and anything else that pushes along a direction
    d = None if opts.get("direction") == "normal" else _load_direction(opts)
    pull = bool(opts.get("flip")) != (float(opts.get("magnitude") or 0) < 0)
    for p, n, _k in _anchors(refs, spacing):
        if d is None:
            if n is None:
                continue
            sep.addChild(_push(p, n, n if pull else n * -1.0, "arrow", 1.0))
        else:
            if kind == "bearing" and n is not None and n.dot(d) > -0.2:
                continue  # a bearing load only pushes on the side it presses on
            sep.addChild(_push(p, n, d, "arrow", 1.0))
        count += 1
    return sep, count


def _inward(point, normal, centre, axis):
    """True when the face normal at `point` points away from the axis (an outer cylinder)."""
    radial = point - centre
    radial = radial - axis * radial.dot(axis)
    return radial.dot(normal) > 0


def _pin_rod(sep, centre, axis, refs):
    """A rod along the pin's axis through the picked hole."""
    from . import simulation

    length = 0.0
    for obj, sub in simulation._picks(refs):
        face = _element(obj, sub)
        if face is None:
            continue
        try:
            for v in face.Vertexes:
                length = max(length, abs((v.Point - centre).dot(axis)) * 2.0)
        except Exception:
            pass
    length = max(length, 1.0)
    a = centre - axis * (length * 0.6)
    b = centre + axis * (length * 0.6)
    sep.addChild(_polyline([tuple(a), tuple(b)], HOLD, 4.0))
    return 1


def _push(point, normal, direction, model, length):
    """An arrow along `direction` touching the face at `point`: its tip on the face when it
    pushes in, its tail on the face when it pulls out."""
    d = App.Vector(direction)
    if d.Length < 1e-12:
        d = App.Vector(0, 0, -1)
    d.normalize()
    if normal is not None and d.dot(normal) > 1e-9 and STATE["size"]:
        point = point + d * (STATE["size"] * length)  # pulling: the tail on the face
    return _place(point, d, _model(model))


def _load_direction(opts):
    from . import simulation_core as core

    try:
        d = App.Vector(*core.unit_vector(opts.get("vector") or [0, 0, -1]))
    except Exception:
        d = App.Vector(0, 0, -1)
    if opts.get("flip"):
        d = d * -1.0
    if float(opts.get("magnitude") or 0) < 0:
        d = d * -1.0
    return d


def _first_normal(refs):
    for p, n, _k in _anchors(refs, 1e9, most=1):
        if n is not None:
            return n
    return None


def _moment(sep, centre, axis):
    size = STATE["size"] or 5.0
    pts = score.arc_points(tuple(centre), tuple(axis), size * 0.6, 270.0, 24)
    sep.addChild(_polyline(pts, PUSH, 3.0))
    end = App.Vector(*pts[-1])
    tangent = App.Vector(*(score.arc_tangent(tuple(axis), pts[-1], tuple(centre)) or (1, 0, 0)))
    sep.addChild(_place(end + tangent * (size * 0.18), tangent, _model("short_arrow")))
    sep.addChild(
        _place(
            centre + App.Vector(axis).normalize() * (size * 0.7),
            App.Vector(axis),
            _model("short_arrow"),
        )
    )
    return 1


def _gravity(sep, doc, direction):
    centre, diag = _model_centre(doc)
    d = App.Vector(*direction)
    if d.Length < 1e-12:
        return 0
    d.normalize()
    size = STATE["size"] or diag / 10.0
    # beside the model, on the side the weight comes from
    point = centre - d * (diag * 0.5 + size * 0.2)
    sep.addChild(_material(WEIGHT))
    sep.addChild(_place(point, d, _model("big_arrow")))
    return 1


# -- drawing the study ---------------------------------------------------------------------------
def _study_key(doc, study):
    from . import simulation

    if study is None:
        return (doc.Name if doc else None,)
    parts = [doc.Name, study.Name, getattr(study, simulation.STUDY_PROP, "")]
    for item in simulation.items(study):
        refs = [(o.Name, s) for o, s in simulation._picks(item.References)]
        parts.append(
            (item.Name, getattr(item, simulation.ITEM_PROP, ""), tuple(refs), item.Suppressed)
        )
    return tuple(parts)


def refresh(doc, study, force=False):
    """Draw the glyphs of `study` (the active study of the design `doc`): every constraint and
    load that is not suppressed, and gravity when it is on."""
    try:
        if doc is None:
            clear()
            return
        root = _ensure_root(doc)
        if root is None:
            return
        _set_size(doc)
        key = (_study_key(doc, study), STATE["size"])
        if not force and key == STATE["key"]:
            return
        STATE["key"] = key
        content = _content()
        content.removeAllChildren()
        STATE["counts"] = {}
        if study is None:
            return
        from . import simulation

        lost = {i.Name for i in simulation.lost_items(study)}
        for item in simulation.items(study):
            if item.Suppressed:
                continue
            data = simulation.item_data(item)
            try:
                sep, count = glyphs_for(
                    doc,
                    data["category"],
                    data["kind"],
                    data["options"],
                    item.References,
                    lost=item.Name in lost,
                )
            except Exception as exc:
                warn("glyphs of %s: %s" % (item.Label, exc))
                continue
            sep.setName("SimGlyph_" + item.Name)
            content.addChild(sep)
            STATE["counts"][item.Name] = count
        gravity = simulation.settings(study)["gravity"]
        if gravity.get("on"):
            coin = _coin()
            sep = coin.SoSeparator()
            STATE["counts"]["gravity"] = _gravity(sep, doc, gravity.get("direction") or [0, 0, -1])
            content.addChild(sep)
    except Exception as exc:
        warn("simulation glyphs: %s" % exc)


def counts():
    """{item name (or "gravity"): number of glyphs drawn} (tests)."""
    return dict(STATE["counts"])


def shown_in(doc):
    """True when glyphs are in the 3D view of `doc` now."""
    return STATE["root"] is not None and doc is not None and STATE["doc"] == doc.Name


# -- a dialog's preview --------------------------------------------------------------------------
def preview(doc, category, kind, opts, refs):
    """The glyphs of what an open dialog would make (lighter), replacing its previous preview."""
    try:
        clear_preview()
        if doc is None or not refs or not kind:
            return 0
        root = _ensure_root(doc)
        if root is None:
            return 0
        _set_size(doc)
        sep, count = glyphs_for(doc, category, kind, opts, refs, transparency=0.25)
        coin = _coin()
        holder = coin.SoSeparator()
        holder.setName("SciForgeSimPreview")
        holder.addChild(sep)
        root.addChild(holder)
        STATE["preview"] = holder
        STATE["preview_count"] = count
        return count
    except Exception as exc:
        warn("glyph preview: %s" % exc)
        return 0


def clear_preview():
    holder, STATE["preview"] = STATE["preview"], None
    STATE["preview_count"] = 0
    root = STATE["root"]
    if holder is None or root is None:
        return
    try:
        root.removeChild(holder)
    except Exception:
        pass


def preview_count():
    """How many glyphs the open dialog's preview shows (tests)."""
    return STATE["preview_count"] if STATE["preview"] is not None else 0
