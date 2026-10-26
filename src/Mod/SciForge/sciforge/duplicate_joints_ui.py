# SPDX-License-Identifier: LGPL-2.1-or-later
"""Fusion's Duplicate With Joints (ASSEMBLE > Duplicate With Joints): the dialog and the
command. The document side is duplicate_joints.py; the spec docs/sciforge/parity/vex-assembly.md.

Components: click the jointed components to copy (a screw; a screw and its nut), in the view
or the browser (a click on a picked one drops it). Joint: the joint that goes from them to a
component outside them (taken by itself when there is one; a list when there are several).
Position: Mode Simple or Between Two Faces, then click where a copy goes (a hole's centre, a
round edge...): each click adds a copy joined there, the same way the original is. OK keeps
them all (one undo step), Cancel / Esc takes them all back.
"""

import FreeCAD as App

from . import commands, duplicate_joints as dj, joints, joints_ui, log, ui_icon_path, warn
from .compat import QtWidgets


class DuplicatePanel(joints_ui._JointsPanel):
    title = "Duplicate With Joints"
    icon = "duplicate_joints"
    needs_pick = (joints_ui.NeedsPick,)
    hover_boxes = ("position",)
    last = None

    def __init__(self, doc):
        self.members = []
        self.choices = []  # [(joint, side)] the open joints of the members
        self.copies = []  # occurrences made (all of them, every click)
        self.made_joints = []
        super().__init__(doc, "Duplicate With Joints")
        DuplicatePanel.last = self
        self.activate("components")
        self.start_from_selection()
        self.dirty = True
        self._timer.stop()
        self._recompute()

    # -- form ------------------------------------------------------------------------------------
    def build_form(self):
        self.form_box(self.layout, "components", "Components", "Select")
        self.joint_box = QtWidgets.QComboBox()
        self.joint_box.setObjectName("SciForgeDuplicateJoint")
        self.joint_box.currentIndexChanged.connect(lambda *_: self._guarded(self._joint_changed))
        self.joint_caption = QtWidgets.QLabel("Joint")
        self.layout.addRow(self.joint_caption, self.joint_box)
        self.slots = {"position": joints_ui.PositionSlot(self, self.layout, "position", "Position")}
        # (Fusion's Duplicate With Joints offers Simple and Between Two Faces)
        combo = self.slots["position"].combo
        for i in range(combo.count() - 1, -1, -1):
            if combo.itemData(i) == "twoedges":
                combo.removeItem(i)
        self.count = QtWidgets.QLabel("")
        self.count.setObjectName("SciForgeDuplicateCount")
        self.layout.addRow(self.count)

    def _fill_joints(self):
        self.choices = dj.open_joints(self.members) if self.members else []
        self._quiet = True
        try:
            self.joint_box.clear()
            for joint, side in self.choices:
                other = joints.part2(joint) if side == 0 else joints.part1(joint)
                self.joint_box.addItem("%s (to %s)" % (joint.Label, other.Label))
        finally:
            self._quiet = False
        shown = len(self.choices) > 1
        self.joint_box.setVisible(shown)
        self.joint_caption.setVisible(shown)

    def _joint_changed(self):
        self.changed()

    def chosen(self):
        if not self.choices:
            return None, 0
        index = max(0, self.joint_box.currentIndex())
        return self.choices[min(index, len(self.choices) - 1)]

    # -- picks -----------------------------------------------------------------------------------
    def allow_object(self, obj):
        return self.active == "components" and joints.part_of(obj) is not None

    def allow_pick(self, pick):
        if self.slot_of(self.active) is not None:
            return all(pick.part is not m for m in self.members)
        return True

    def allow_click(self, pick):
        return pick.part is not None

    def picked_raw(self, root, sub, point):
        pick = joints.resolve_selection(root, sub, point)
        part = pick.part if pick is not None else joints.part_of(root)
        if part is None:
            return
        slot_box = self.active if self.slot_of(self.active) is not None else None
        if slot_box:
            if pick is None or not (pick.element or pick.is_datum()):
                self.info.setText("Click a snap point where the copy goes.")
                return
            if any(part is m for m in self.members):
                self.refuse("Click where the copy goes, not on %s itself." % part.Label)
                return
            taken = self.take_position("position", slot_box, pick, point)
            if taken is None:
                return
            self._duplicate(*taken)
            return
        self._toggle(part)
        self._advance()
        self.changed()

    def _toggle(self, part):
        if any(part is m for m in self.members):
            self.members = [m for m in self.members if m is not part]
        else:
            self.members.append(part)
        self.fields["components"].set_text(dj.label_of(self.members))
        self._fill_joints()
        self.took()

    def _advance(self):
        """With a single open joint left (a screw alone; a screw and its nut), the Position
        box waits; with several the Joint list says which (or click the Position box)."""
        joint, side = self.chosen()
        if len(self.choices) == 1 and not dj.check(self.members, joint, side):
            self.activate(self.slots["position"].first_box())

    def start_from_selection(self):
        """Components picked before the command (the view or the browser) are the ones to
        duplicate, all of them."""
        entries = joints_ui._selection_entries(self.doc)
        self._syncing = True
        try:
            joints_ui.Gui.Selection.clearSelection()
        finally:
            self._syncing = False
        for root, sub, point in entries:
            try:
                pick = joints.resolve_selection(root, sub, point)
                part = pick.part if pick is not None else joints.part_of(root)
                if part is not None and all(part is not m for m in self.members):
                    self._toggle(part)
            except Exception as exc:
                warn("Duplicate With Joints pick: %s" % exc)
        self._advance()
        return bool(entries)

    def _duplicate(self, pick, snap):
        joint, side = self.chosen()
        try:
            copies, made = dj.duplicate(self.doc, self.members, joint, side, pick, snap)
        except dj.DuplicateError as exc:
            self.refuse(str(exc))
            return
        except Exception as exc:
            warn("Duplicate With Joints: %s" % exc)
            self.refuse("The copy could not be made: %s" % exc)
            return
        self.copies.extend(copies)
        self.made_joints.extend(made)
        self.took()
        n = self.copy_count()
        self.count.setText("%d cop%s made" % (n, "y" if n == 1 else "ies"))
        try:
            joints_ui.attach_views(self.doc)
        except Exception:
            pass
        # the next click makes another copy (Between Two Faces: two faces of the next hole)
        slot = self.slots["position"]
        for box in (slot.name + "_a", slot.name + "_b"):
            slot.clear(box)
        self.activate(slot.first_box())
        self.changed()

    def copy_count(self):
        return len(self.copies) // max(1, len(self.members))

    def cleared(self, name):
        if name == "components":
            self.members = []
            self.fields["components"].set_text("")
            self._fill_joints()
        elif name != "position":
            self.slots["position"].clear(name)

    # -- the preview -------------------------------------------------------------------------------
    def apply(self):
        if not self.members:
            raise joints_ui.NeedsPick(
                "Click the jointed components to copy (a screw, or a screw and its nut)."
            )
        joint, side = self.chosen()
        why = dj.check(self.members, joint, side)
        if why:
            raise joints_ui.NeedsPick(why)
        if not self.copies:
            raise joints_ui.NeedsPick(
                "Click where each copy goes (a hole's centre, a round edge): each click adds a "
                "copy joined there like %s." % joint.Label
            )

    def can_finish(self):
        return "" if self.copies else "Click where a copy goes first (or Cancel)."


class DuplicateWithJointsCommand:
    def GetResources(self):
        return {
            "MenuText": "Duplicate With Joints",
            "ToolTip": "Copy jointed components (a screw, a screw and its nut) to new places: "
            "each click makes a copy joined there like the original",
            "Pixmap": ui_icon_path("duplicate_joints"),
        }

    def IsActive(self):
        return App.ActiveDocument is not None

    def Activated(self):
        try:
            if App.ActiveDocument is None:
                commands.tell("Open or start a design first.")
                return
            if not joints.joints(App.ActiveDocument):
                commands.tell(
                    "Duplicate With Joints copies a jointed component: make a joint first "
                    "(ASSEMBLE > Joint)."
                )
                return
            joints_ui._start(DuplicatePanel)
            log("Duplicate With Joints started")
        except Exception as exc:
            warn("Duplicate With Joints could not start: %s" % exc)


COMMANDS = {"SciForge_DuplicateWithJoints": DuplicateWithJointsCommand}
