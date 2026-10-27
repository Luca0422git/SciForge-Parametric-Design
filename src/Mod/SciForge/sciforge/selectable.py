# SPDX-License-Identifier: LGPL-2.1-or-later
"""Selectable / Unselectable on bodies, mesh bodies and components (Fusion's browser
right-click > Selectable/Unselectable): an unselectable body, and every body in an
unselectable component, can no longer be picked in the 3D view, so the parts around it are
easy to click (a VEX robot's frame while its screws are jointed). The browser still selects
it, and draws a small no-entry mark on its row's icon.

Stored in the design: a `SciForgeSelectable` property on the body, mesh body or component,
so it is saved with the file and one Ctrl+Z takes a change back. What makes it unpickable is
FreeCAD's Selectable switch on the views: on the body's own view AND on each of its steps'
views. A body's own switch alone is not enough inside a component: FreeCAD draws a body
through its steps, and each step's pick style undoes the body's (checked on FreeCAD 1.1.4:
a body in a component stayed clickable). apply() puts the switches in line with the design;
bodies_gui.sync() calls it after every recompute, undo and redo, so a new step in an
unselectable body is unselectable at once.
"""

import FreeCAD as App

from . import bodies, components, log, warn

PROP = "SciForgeSelectable"
MENU_TEXT = "Selectable/Unselectable"
_OFF = {}  # document name -> names of the bodies apply() switched off last time


# -- reading -------------------------------------------------------------------------------------
def supports(obj):
    """Bodies, mesh bodies and components have Selectable/Unselectable."""
    if obj is None:
        return False
    if bodies.is_body(obj) or components.is_component(obj):
        return True
    from . import mesh

    return mesh.is_mesh(obj)


def get(obj):
    """The switch set on `obj` itself (True when none was set)."""
    try:
        if obj is not None and PROP in obj.PropertiesList:
            return bool(getattr(obj, PROP))
    except Exception:
        pass
    return True


def selectable(obj):
    """Whether `obj` can be picked in the 3D view: its own switch and its components'."""
    return get(obj) and all(get(c) for c in components.ancestors(obj))


def _managed(chain):
    return any(PROP in getattr(o, "PropertiesList", ()) for o in chain)


# -- changing ------------------------------------------------------------------------------------
def _ensure(obj):
    if PROP not in obj.PropertiesList:
        obj.addProperty(
            "App::PropertyBool",
            PROP,
            "SciForge",
            "Selectable/Unselectable: off = it cannot be picked in the 3D view",
            4,  # hidden from FreeCAD's property editor
        )
        setattr(obj, PROP, True)


def set_selectable(objects, on):
    """Make bodies / mesh bodies / components selectable (on) or not, one undo step. Returns
    the objects changed."""
    on = bool(on)
    objects = [o for o in objects if supports(o) and bodies.alive(o)]
    if not objects:
        return []
    doc = objects[0].Document
    # Added before the undo step opens: undoing the first change then gives the property
    # its True back (and the body its switches) instead of taking the property away.
    for obj in objects:
        _ensure(obj)
    changed = [o for o in objects if get(o) != on]
    if changed:
        doc.openTransaction("Selectable" if on else "Unselectable")
        try:
            for obj in changed:
                setattr(obj, PROP, on)
        except Exception:
            doc.abortTransaction()
            raise
        doc.commitTransaction()
        log(
            "%s: %s"
            % ("selectable" if on else "unselectable", ", ".join(o.Label for o in changed)),
        )
    apply(doc)
    return changed


def toggle(objects):
    """Fusion's one menu entry: the first object's switch turned over, for all of them."""
    objects = [o for o in objects if supports(o)]
    if not objects:
        return []
    return set_selectable(objects, not get(objects[0]))


# -- on screen -----------------------------------------------------------------------------------
def _views(obj):
    """The view objects whose Selectable switch decides whether `obj` can be picked: a body's
    own and its steps' (FreeCAD shows a body through them; an inserted STEP part through its
    base step), a mesh body's."""
    views = []
    vobj = getattr(obj, "ViewObject", None)
    if vobj is not None and "Selectable" in vobj.PropertiesList:
        views.append(vobj)
    if bodies.is_body(obj):
        for step in obj.Group:
            try:
                if not step.isDerivedFrom("PartDesign::Feature"):
                    continue
                svobj = step.ViewObject
                if svobj is not None and "Selectable" in svobj.PropertiesList:
                    views.append(svobj)
            except Exception:
                continue
    return views


def _switch(obj, on):
    for vobj in _views(obj):
        try:
            if bool(vobj.Selectable) != on:
                vobj.Selectable = on
        except Exception:
            continue


def _meshes(doc):
    from . import mesh

    return [o for o in doc.Objects if mesh.is_mesh(o)]


def apply(doc):
    """Every body and mesh body of the design gets the pick switches its own and its
    components' Selectable say (GUI only). Bodies nobody switched (nor a component they are
    in) are left as they are."""
    if not App.GuiUp or doc is None:
        return
    try:
        shapes = bodies.list_bodies(doc) + _meshes(doc)
        units = shapes + components.list_components(doc)
        if not _OFF.get(doc.Name) and not _managed(units):
            return  # (nothing was ever switched: the common case, kept cheap)
        off_now = set()
        for obj in shapes:
            chain = [obj] + components.ancestors(obj)
            if not _managed(chain):
                if obj.Name in _OFF.get(doc.Name, ()):
                    _switch(obj, True)  # its switch was taken away (undo): pickable again
                continue
            on = all(get(c) for c in chain)
            _switch(obj, on)
            if not on:
                off_now.add(obj.Name)
        _OFF[doc.Name] = off_now
    except Exception as exc:
        warn("selectable: %s" % exc)


def forget(doc_name):
    _OFF.pop(doc_name, None)
