# SPDX-License-Identifier: LGPL-2.1-or-later
"""Drag a joint to set its limits (Luca, 2026-10-26, for 0.1.0-beta.2.2: "Joints should have
a way to drag them to drive them. especially for setting a min and max. I should be able to
drag it where i want it to max and min. simple as that.").

While a joint dialog shows its limits (the Joint dialog's Motion tab, Edit Joint Limits,
As-Built Joint), a drag handle stands on the joint's motion: Fusion's angle disc round the
joint's axis for a turn, a blue arrow along it for a slide. Dragging it, or the moving part
itself, drives the joint live. The limit row whose box is the current one (ticked or
clicked into last) follows the drag, as in Fusion, where the manipulator of the limit being
edited sets it; with no such row the drag only moves the part, stopping at the limits. A
faint ghost of the moving part shows where each limit is. Everything happens inside the
dialog's own undo step: Cancel puts it all back, OK is one step.
"""

import time

import FreeCAD as App
import FreeCADGui as Gui

from . import hover_ghost, joints, joints_core as core, warn
from .compat import QtCore

GHOST_COLOUR = (0.95, 0.75, 0.35)
GHOST_TRANSPARENCY = 0.8


class LimitDrag:
    """The drag handle and the limit ghosts of one joint dialog (its `angle_limits` and
    `slide_limits` are taskui _Limits rows)."""

    def __init__(self, panel):
        self.panel = panel
        self.handle = None
        self.kind = None  # "angle" or "slide": what the handle drives
        self.focus = None  # (unit, key) of the limit row the drag sets
        self.ghosts = []  # Coin nodes in the view
        self._ghost_key = None
        self._dragging = False
        self._last_drag = 0.0  # time.time() of the last drag step
        self.trace = []  # the last drag steps: (value, released, the joint's angle after)
        self._filters = []
        for limits in self._limit_sets():
            for key, (check, field) in limits.rows.items():
                check.toggled.connect(lambda on, u=limits.unit, k=key: self._ticked(u, k, on))
                watch = _FocusWatch(lambda u=limits.unit, k=key: self._focused(u, k))
                field.widget.installEventFilter(watch)
                self._filters.append((field.widget, watch))

    # -- which row the drag sets -------------------------------------------------------------
    def _limit_sets(self):
        panel = self.panel
        found = (getattr(panel, "angle_limits", None), getattr(panel, "slide_limits", None))
        return [x for x in found if x]

    def _rows(self, unit):
        for limits in self._limit_sets():
            if limits.unit == unit:
                return limits
        return None

    def _ticked(self, unit, key, on):
        if on:
            self.focus = (unit, key)
        elif self.focus == (unit, key):
            self.focus = None

    def _focused(self, unit, key):
        limits = self._rows(unit)
        if limits is not None and limits.rows[key][0].isChecked():
            self.focus = (unit, key)

    def focus_row(self):
        """(unit, key) of the row a drag sets, or None (tests)."""
        return self.focus

    # -- the handle ----------------------------------------------------------------------------
    def wanted(self):
        """"angle" / "slide" when the dialog shows that kind of limits for a joint, else None."""
        panel = self.panel
        joint = getattr(panel, "joint", None)
        if joint is None or getattr(panel, "_closed", False):
            return None
        tabs = getattr(panel, "tabs", None)
        if tabs is not None and tabs.currentIndex() != 1:
            return None
        try:
            kind = joints.fusion_type(joint)
        except Exception:
            return None
        # isHidden, not isVisible: the dialog is not on the screen yet when it opens
        if kind in core.ANGLE_LIMITS and not panel.angle_limits.caption.isHidden():
            return "angle"
        if kind in core.LENGTH_LIMITS and not panel.slide_limits.caption.isHidden():
            return "slide"
        return None

    def update(self):
        """Show, move or take away the handle and the ghosts for the dialog as it is now.
        Never raises."""
        if self._dragging:
            return
        try:
            kind = self.wanted()
            if kind is None:
                self.remove()
                return
            if self.handle is None or self.kind != kind:
                self._remove_handle()
                self._make_handle(kind)
            else:
                self._place_handle()
            self.refresh_ghosts()
        except Exception as exc:
            warn("joint limits drag: %s" % exc)

    def _frames(self):
        joint = self.panel.joint
        return joints.jcs_global(joint, 0), joints.jcs_global(joint, 1)

    def _size(self, at):
        from .taskui import handle_size_at

        view = Gui.ActiveDocument.ActiveView
        return handle_size_at(view, at, pixels=90, lo=1.0)

    def _make_handle(self, kind):
        joint = self.panel.joint
        jcs1, jcs2 = self._frames()
        angle, slide = joints.value(joint)
        self.kind = kind
        if kind == "angle":
            from .revolve_ui import AngleHandle

            axis = jcs2.Rotation.multVec(App.Vector(0, 0, 1))
            zero = jcs2.Rotation.multVec(App.Vector(1, 0, 0))
            radius = self._size(jcs1.Base)
            self.handle = AngleHandle(
                jcs1.Base,
                axis,
                zero,
                radius,
                angle,
                radius * 0.35,
                on_drag=lambda v: self._dragged(v),
                on_release=lambda v: self._dragged(v, True),
            )
        else:
            from .taskui import ArrowDragger

            direction = jcs2.Rotation.multVec(_axis_vector(joints.slide_axis(joint)))
            origin = jcs1.Base - direction * slide  # where the slide reads 0
            self.handle = ArrowDragger(
                origin,
                direction,
                slide,
                self._size(jcs1.Base),
                on_drag=lambda d: self._dragged(d),
                on_release=lambda d: self._dragged(d, True),
            )

    def _place_handle(self):
        """The joint moved without the handle (a typed value, Undo inside the dialog)."""
        angle, slide = joints.value(self.panel.joint)
        try:
            if self.kind == "angle":
                if abs(self.handle.angle() - angle) > 1e-6:
                    self.handle.set_angle(angle)
            elif abs(self.handle.distance() - slide) > 1e-6:
                self.handle.set_distance(slide)
        except Exception:
            pass

    def _remove_handle(self):
        handle, self.handle = self.handle, None
        if handle is not None:
            try:
                handle.remove()
            except Exception:
                pass

    def handle_now(self):
        """The handle shown, or None (tests)."""
        return self.handle

    def busy(self, seconds=0.6):
        """True while the handle is dragged and just after: the click FreeCAD's selection
        also saw there is the handle's, not a pick."""
        from . import handles3d

        if self._dragging or time.time() - self._last_drag < seconds or handles3d.just_used():
            return True
        try:
            return self.handle is not None and hasattr(self.handle, "busy") and self.handle.busy()
        except Exception:
            return False

    # -- dragging ------------------------------------------------------------------------------
    def _dragged(self, value, released=False):
        """The handle moved: the joint goes there; the current limit row (if any) takes the
        value, else the joint stops at its limits."""
        panel = self.panel
        joint = panel.joint
        if joint is None:
            return
        try:
            self._dragging = not released
            self._last_drag = time.time()
            panel.stop_animation()
            value = round(float(value), 2 if self.kind == "slide" else 1)
            unit = "deg" if self.kind == "angle" else "mm"
            row = self.focus if self.focus is not None and self.focus[0] == unit else None
            if row is not None:
                limits = self._rows(unit)
                _check, field = limits.rows[row[1]]
                if abs(field.value() - value) > 1e-9:
                    field.set_value(value)
                self._drive(value, clamp=False)
                if released:
                    panel.changed()  # the limits go onto the joint (apply)
            else:
                self._drive(value, clamp=True)
            self.trace = (self.trace + [(value, released, joints.value(joint))])[-40:]
            if released:
                self._place_handle()
                self._ghost_key = None
                self.refresh_ghosts()
        except Exception as exc:
            warn("joint limits drag: %s" % exc)
        finally:
            if released:
                self._dragging = False

    def _drive(self, value, clamp):
        joint = self.panel.joint
        angle = value if self.kind == "angle" else None
        slide = value if self.kind == "slide" else None
        if clamp:
            angle, slide = joints.clamp_values(joint, angle, slide)
        part, side = joints.driven_part(joint)
        joints.place_joint(joint, angle, slide, side, part)
        joints.follow_links(joint)
        joints.solve(joint.Document)

    # -- where the limits are --------------------------------------------------------------------
    def _limit_values(self):
        unit = "deg" if self.kind == "angle" else "mm"
        limits = self._rows(unit)
        if limits is None:
            return []
        out = []
        for key in ("min", "max"):
            check, field = limits.rows[key]
            if check.isChecked():
                out.append((key, field.value()))
        return out

    def refresh_ghosts(self):
        """A faint ghost of the moving part at each limit that is on (kept while the limits,
        the joint and the parts stay as they are)."""
        try:
            joint = self.panel.joint
            values = self._limit_values() if joint is not None and self.kind else []
            jcs1, jcs2 = self._frames() if values else (None, None)
            key = (
                tuple(values),
                self.kind,
                tuple(jcs1.toMatrix().A) if jcs1 is not None else None,
                tuple(jcs2.toMatrix().A) if jcs2 is not None else None,
            )
            if key == self._ghost_key:
                return
            self._ghost_key = key
            self._remove_ghosts()
            if not values:
                return
            part, side = joints.driven_part(joint)
            movers = [part] + joints.downstream(part, joint)
            view = Gui.ActiveDocument.ActiveView
            for _key, value in values:
                T = core.drive_transform(
                    joints.to_frame(jcs1),
                    joints.to_frame(jcs2),
                    value if self.kind == "angle" else None,
                    value if self.kind == "slide" else None,
                    joints.slide_axis(joint),
                )
                if side == 1:
                    T = core.inverse(T)
                move = joints.from_frame(T)
                pieces = []
                for mover in joints.top_movers(movers):
                    for shape in hover_ghost.placed_pieces(mover):
                        shape.Placement = move.multiply(shape.Placement)
                        pieces.append(shape)
                node = hover_ghost.build(pieces, GHOST_COLOUR, GHOST_TRANSPARENCY)
                if node is not None:
                    view.getSceneGraph().addChild(node)
                    self.ghosts.append((view, node))
        except Exception as exc:
            warn("joint limits ghost: %s" % exc)

    def ghost_count(self):
        return len(self.ghosts)

    def _remove_ghosts(self):
        ghosts, self.ghosts = self.ghosts, []
        for view, node in ghosts:
            try:
                view.getSceneGraph().removeChild(node)
            except Exception:
                pass

    def remove(self):
        """Take the handle and the ghosts away (the dialog closes or the limits are hidden)."""
        self._dragging = False
        self._remove_handle()
        self._remove_ghosts()
        self._ghost_key = None
        self.kind = None

    def close(self):
        self.remove()
        for widget, watch in self._filters:
            try:
                widget.removeEventFilter(watch)
            except Exception:
                pass
        self._filters = []


# -- dragging the part itself ----------------------------------------------------------------
def part_drag(gl, view, pos):
    """A drag starting at widget pixel `pos` on the part a joint dialog's limits move: it
    drives the joint like the handle does (selection_ui hands a drag inside a dialog here;
    outside dialogs it is joints_drag's Component Drag). A PartDrag, or None when the press
    is not on that part or no limits handle is shown."""
    try:
        from . import joints_drag, taskui

        panel = taskui.current()
        drag = getattr(panel, "limit_drag", None)
        joint = getattr(panel, "joint", None)
        if drag is None or joint is None or drag.handle is None or drag.kind is None:
            return None
        part, grab = joints_drag._pick_at(view, gl, pos)
        if part is None or grab is None:
            return None
        moving, side = joints.driven_part(joint)
        if part not in [moving] + joints.downstream(moving, joint):
            return None
        return PartDrag(drag, view, gl, grab, side)
    except Exception as exc:
        warn("joint limits drag: %s" % exc)
        return None


class PartDrag:
    """One press-move-release on the moving part while the limits are shown: the part turns
    (or slides) with the pointer as in a Component Drag, and the joint's value goes through
    the dialog's LimitDrag (the current limit row follows, the ghosts move). Esc puts it back."""

    def __init__(self, drag, view, gl, grab, side):
        self.drag = drag
        self.view = view
        self.gl = gl
        self.grab = App.Vector(grab)
        joint = drag.panel.joint
        self.sign = 1.0 if side == 0 else -1.0
        self.start = joints.value(joint)
        jcs2 = joints.jcs_global(joint, 1)
        self.center = jcs2.Base
        self.axis = jcs2.Rotation.multVec(App.Vector(0, 0, 1))
        self.slide_dir = jcs2.Rotation.multVec(_axis_vector(joints.slide_axis(joint)))
        self.previous = 0.0
        self.value = None
        self.done = False
        row = drag.focus
        limits = drag._rows(row[0]) if row is not None else None
        self.row_before = (row, limits.rows[row[1]][1].value()) if limits is not None else None

    def follow(self, pos):
        if self.done:
            return
        try:
            from . import joints_drag, motion_core

            o, d = joints_drag.ray(self.view, self.gl, pos)
            o, d = joints_drag._t(o), joints_drag._t(d)
            t = joints_drag._t
            if self.drag.kind == "angle":
                turn = motion_core.turn_from_ray(
                    t(self.center), t(self.axis), t(self.grab), o, d, previous=self.previous
                )
                if turn is None:
                    return
                self.previous = turn
                value = self.start[0] + self.sign * turn
            else:
                shift = motion_core.slide_from_ray(t(self.grab), t(self.slide_dir), o, d)
                if shift is None:
                    return
                value = self.start[1] + self.sign * shift
            self.value = value
            self.drag._dragged(value)
            self.drag._place_handle()  # the handle goes round with the part
        except Exception as exc:
            warn("joint limits drag: %s" % exc)

    def finish(self):
        """The button came up: the joint stays there (the dialog's OK keeps it)."""
        if self.done:
            return
        self.done = True
        if self.value is not None:
            self.drag._dragged(self.value, True)

    def cancel(self):
        """Esc while dragging: the part and the limit row go back."""
        if self.done:
            return
        self.done = True
        try:
            if self.row_before is not None:
                (unit, key), value = self.row_before
                self.drag._rows(unit).rows[key][1].set_value(value)
            start = self.start[0] if self.drag.kind == "angle" else self.start[1]
            self.drag._dragged(start, True)
        except Exception as exc:
            warn("joint limits drag: %s" % exc)


def _axis_vector(name):
    return {"x": App.Vector(1, 0, 0), "y": App.Vector(0, 1, 0)}.get(name, App.Vector(0, 0, 1))


class _FocusWatch(QtCore.QObject):
    """Calls back when a limit's value box gets the keyboard (clicked into)."""

    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def eventFilter(self, obj, event):
        try:
            if event.type() == QtCore.QEvent.FocusIn:
                self.callback()
        except Exception:
            pass
        return False
