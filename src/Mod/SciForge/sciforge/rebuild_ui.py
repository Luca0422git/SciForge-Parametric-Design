# SPDX-License-Identifier: LGPL-2.1-or-later
"""Auto Timeline in the window (beta 3, builder at-tools): a person's way into a rebuild.
Beyond Fusion. Spec: docs/sciforge/parity/auto-timeline.md ("The command a person uses").

  * Rebuild with Timeline (AI)... : a body's right-click in the browser, the 3D view's
    right-click when a body is under the mouse, UTILITIES > AI. It starts the rebuild (the
    body becomes the reference, a new empty body "<name> (rebuilt)" is made active), then
    opens the AI panel's chat with a ready message (not sent: the person reads it and
    presses Send) when SciForge's own chat has an AI set up; otherwise a small window says
    how to ask an AI app (Claude Desktop, Gemini CLI...) and copies the message for it.
  * Compare with Reference: the numbers (match, missing / extra material, faces) and the
    differences in the 3D view (missing material red, extra green), so a person can rebuild
    by hand too.
  * Finish Rebuild: the rebuild takes the original's name and place; the original is
    deleted or kept hidden, as the person chooses. One undo step.

The reference is drawn faint and see-through by its view provider (Coin nodes only: nothing
in the document changes, nothing lands in the undo history); clicks go through it. The red /
green overlay hangs under the same view provider, so it goes with the reference.
"""

import FreeCAD as App
import FreeCADGui as Gui

from . import commands, log, rebuild, rebuild_core, ui_icon_path, warn
from .compat import QtCore, QtGui, QtWidgets

GHOST = (0.55, 0.68, 0.85)  # a faint blue-grey: the original, under the rebuild
GHOST_GLOW = (0.16, 0.20, 0.26)
GHOST_TRANSPARENCY = 0.82
GHOST_EDGE = (0.62, 0.70, 0.80)
MISSING = (0.95, 0.22, 0.20)  # material the rebuild lacks: red
MISSING_GLOW = (0.45, 0.06, 0.05)
EXTRA = (0.25, 0.80, 0.35)  # material the rebuild has too much: green
EXTRA_GLOW = (0.06, 0.32, 0.10)
OVERLAY_TRANSPARENCY = 0.45


# -- drawing ---------------------------------------------------------------------------------------
def _mesh(coin, shape, color, glow, transparency, offset, edge, edge_transparency=0.0):
    """A see-through picture of `shape`: its faces and its edges, unpickable. offset > 0
    draws it behind faces lying on it (the ghost under the rebuild), < 0 in front (the
    red / green differences)."""
    node = coin.SoSeparator()
    pick = coin.SoPickStyle()
    pick.style = coin.SoPickStyle.UNPICKABLE  # clicks reach what is behind
    node.addChild(pick)
    shift = coin.SoPolygonOffset()
    shift.factor = offset
    shift.units = offset
    node.addChild(shift)
    hints = coin.SoShapeHints()
    hints.vertexOrdering = coin.SoShapeHints.UNKNOWN_ORDERING
    hints.shapeType = coin.SoShapeHints.UNKNOWN_SHAPE_TYPE  # lit from both sides
    node.addChild(hints)
    size = max(shape.BoundBox.DiagonalLength, 1e-3)
    material = coin.SoMaterial()
    material.diffuseColor.setValue(*color)
    material.emissiveColor.setValue(*glow)
    material.transparency.setValue(transparency)
    node.addChild(material)
    try:
        points, triangles = shape.tessellate(max(0.002 * size, 0.005))
    except Exception:
        points, triangles = [], []
    if triangles:
        coords = coin.SoCoordinate3()
        coords.point.setValues(0, len(points), [(p.x, p.y, p.z) for p in points])
        node.addChild(coords)
        faces = coin.SoIndexedFaceSet()
        index = []
        for a, b, c in triangles:
            index += [a, b, c, -1]
        faces.coordIndex.setValues(0, len(index), index)
        node.addChild(faces)
    lines = coin.SoSeparator()
    style = coin.SoDrawStyle()
    style.lineWidth = 1.0
    lines.addChild(style)
    ink = coin.SoMaterial()
    ink.diffuseColor.setValue(*edge)
    ink.emissiveColor.setValue(*edge)
    ink.transparency.setValue(edge_transparency)
    lines.addChild(ink)
    found, counts = [], []
    for e in shape.Edges:
        try:
            line = e.discretize(Deflection=max(0.002 * size, 0.005))
        except Exception:
            continue
        if len(line) < 2:
            continue
        found += [(p.x, p.y, p.z) for p in line]
        counts.append(len(line))
    if counts:
        coords = coin.SoCoordinate3()
        coords.point.setValues(0, len(found), found)
        lines.addChild(coords)
        strip = coin.SoLineSet()
        strip.numVertices.setValues(0, len(counts), counts)
        lines.addChild(strip)
    node.addChild(lines)
    return node


class ViewProviderReference:
    """Draws a rebuild's reference faint and see-through, and the last comparison's red /
    green differences. Saved in files as "sciforge.rebuild_ui.ViewProviderReference": keep
    the name."""

    def __init__(self, vobj):
        vobj.Proxy = self

    def attach(self, vobj):
        from pivy import coin

        self.Object = vobj.Object
        self.root = coin.SoSeparator()
        self.root.setName("SciForgeRebuildReference")
        self.ghost = coin.SoSwitch()
        self.ghost.setName("SciForgeRebuildGhost")
        self.root.addChild(self.ghost)
        self.overlay = coin.SoSeparator()
        self.overlay.setName("SciForgeRebuildOverlay")
        self.root.addChild(self.overlay)
        self.shown_regions = {"missing": 0, "extra": 0}
        vobj.addDisplayMode(self.root, "Ghost")
        self._update(vobj.Object)

    def _update(self, obj):
        from pivy import coin

        try:
            self.ghost.removeAllChildren()
            self.motion = None
            shape = getattr(obj, rebuild.SHAPE, None)
            if shape is not None and not shape.isNull():
                group = coin.SoSeparator()
                self.motion = coin.SoTransform()  # (the rebuild's component moved: follow it)
                group.addChild(self.motion)
                group.addChild(
                    _mesh(
                        coin,
                        shape,
                        GHOST,
                        GHOST_GLOW,
                        GHOST_TRANSPARENCY,
                        1.0,
                        GHOST_EDGE,
                        0.55,
                    )
                )
                self.ghost.addChild(group)
                self.follow(obj)
            self.ghost.whichChild = 0 if getattr(obj, "Shown", True) else -1
        except Exception as exc:
            warn("rebuild: the reference is not drawn (%s)" % exc)

    def follow(self, obj):
        """The ghost where the reference stands now (moved with the rebuilt body's
        component since it was frozen)."""
        from pivy import coin

        motion = getattr(self, "motion", None)
        if motion is None:
            return
        try:
            place = rebuild.moved_by(obj) or App.Placement()
            motion.translation.setValue(place.Base.x, place.Base.y, place.Base.z)
            q = place.Rotation.Q
            motion.rotation.setValue(coin.SbRotation(q[0], q[1], q[2], q[3]))
        except Exception as exc:
            warn("rebuild: %s" % exc)

    def moved(self):
        """Where the ghost is drawn now: the placement its picture is moved by (tests)."""
        motion = getattr(self, "motion", None)
        if motion is None:
            return None
        t = motion.translation.getValue()
        return App.Vector(t[0], t[1], t[2])

    def show_differences(self, missing, extra):
        """The comparison's regions: missing material red, extra green (design
        coordinates); replaces what was shown."""
        from pivy import coin

        self.clear_differences()
        try:
            for shape in missing:
                self.overlay.addChild(
                    _mesh(coin, shape, MISSING, MISSING_GLOW, OVERLAY_TRANSPARENCY, -1.0, MISSING)
                )
            for shape in extra:
                self.overlay.addChild(
                    _mesh(coin, shape, EXTRA, EXTRA_GLOW, OVERLAY_TRANSPARENCY, -1.0, EXTRA)
                )
            self.shown_regions = {"missing": len(missing), "extra": len(extra)}
        except Exception as exc:
            warn("rebuild: the differences are not drawn (%s)" % exc)

    def clear_differences(self):
        try:
            self.overlay.removeAllChildren()
        except Exception:
            pass
        self.shown_regions = {"missing": 0, "extra": 0}

    def ghost_shown(self):
        try:
            return self.ghost.whichChild.getValue() == 0 and self.ghost.getNumChildren() > 0
        except Exception:
            return False

    def getDisplayModes(self, vobj):
        return ["Ghost"]

    def getDefaultDisplayMode(self):
        return "Ghost"

    def setDisplayMode(self, mode):
        return mode

    def updateData(self, obj, prop):
        if prop in (rebuild.SHAPE, "Shown"):
            self._update(obj)
        elif prop in ("FrozenFrame", "TargetName"):
            self.follow(obj)

    def onChanged(self, vobj, prop):
        pass

    def getIcon(self):
        return ui_icon_path("rebuild_ai")

    def canDelete(self, obj):
        return True

    def dumps(self):
        return None

    def loads(self, state):
        return None

    __getstate__ = dumps
    __setstate__ = loads


def attach_view(ref):
    """Give a new reference its view provider (rebuild.start calls it in the window)."""
    try:
        vobj = ref.ViewObject
        if vobj is not None and not isinstance(getattr(vobj, "Proxy", None), ViewProviderReference):
            ViewProviderReference(vobj)
    except Exception as exc:
        warn("rebuild: %s" % exc)


def view_of(ref):
    try:
        proxy = ref.ViewObject.Proxy
        return proxy if isinstance(proxy, ViewProviderReference) else None
    except Exception:
        return None


def _listener(event, ref, data):
    """rebuild.compare / finish: the red / green differences in the 3D view."""
    view = view_of(ref)
    if view is None:
        return
    if event == "moved":
        view.follow(ref)
    elif event == "compare":
        view.follow(ref)
        view.show_differences(data.get("missing", []), data.get("extra", []))
    else:
        view.clear_differences()


if _listener not in rebuild.LISTENERS:
    rebuild.LISTENERS.append(_listener)


def clear_differences(doc=None):
    doc = doc or App.ActiveDocument
    for ref in rebuild.references(doc):
        view = view_of(ref)
        if view is not None:
            view.clear_differences()


# -- which body, which reference ----------------------------------------------------------------
def _selected_source():
    """The body (or mesh body) selected, else None."""
    from . import bodies, hole_common, insert

    try:
        found = Gui.Selection.getSelectionEx()
    except Exception:
        return None
    for sel in found:
        obj = sel.Object
        names = list(sel.SubElementNames) or [""]
        for name in names:
            target, _short = hole_common.resolve(obj, name)
            if target is None:
                continue
            if insert.is_mesh_body(target):
                return target
            body = target if bodies.is_body(target) else bodies.body_of(target)
            if body is not None:
                return body
    return None


def current_reference(doc=None, quiet=False):
    """The reference of the active body's rebuild, else the only one; None (said) when
    there is none."""
    from . import bodies

    doc = doc or App.ActiveDocument
    if doc is None:
        return None
    try:
        body = _selected_source() or bodies.active_body(doc)
        ref = rebuild.find(doc, body)
    except rebuild.RebuildError as exc:
        if not quiet:
            going = rebuild.active_references(doc)
            if len(going) > 1:  # (the AI's words name ids; a person picks a body)
                targets = [rebuild.target_of(r) for r in going]
                commands.tell(
                    "%d rebuilds are going on (%s): select the rebuilt body you mean first."
                    % (len(going), ", ".join(t.Label for t in targets if t is not None))
                )
            else:
                commands.tell(rebuild_core.person_words(str(exc)))
        return None
    if ref is None and not quiet:
        commands.tell(
            "No rebuild is going on: right-click a body > Rebuild with Timeline (AI)... first."
        )
    return ref


# -- Rebuild with Timeline (AI)... ------------------------------------------------------------
def start_for(source):
    """Start a rebuild of `source` (one undo step) and offer the AI the message. A body
    already being rebuilt is not started again: its message is offered."""
    doc = source.Document
    if not commands.finish_open_dialog():
        return None
    existing = rebuild.reference_for(source)
    going = existing is not None and getattr(existing, "Shown", True)
    if going and rebuild.target_of(existing) is not None:
        offer_message(existing)
        return existing
    doc.openTransaction("Rebuild with Timeline")
    try:
        ref = _busy(rebuild.start, doc, source)
    except rebuild.RebuildError as exc:
        doc.abortTransaction()
        _say_refused(rebuild_core.person_words(str(exc)))
        return None
    except Exception:
        doc.abortTransaction()
        raise
    doc.commitTransaction()
    doc.recompute()
    log("Rebuild with Timeline (AI): %s" % ref.SourceLabel)
    offer_message(ref)
    return ref


_LAST = {"refused": None, "message": None, "dialog": None}


def _busy(fn, *args):
    """fn(*args) under the wait cursor: a mesh made into a solid, or a compare of a big part,
    takes seconds."""
    shown = False
    try:
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        shown = True
    except Exception:
        pass
    try:
        return fn(*args)
    finally:
        if shown:
            QtWidgets.QApplication.restoreOverrideCursor()


def _say_refused(text):
    """A refusal said where it is seen: a small window (the reason and what to do)."""
    _LAST["refused"] = text
    log("Rebuild with Timeline refused: %s" % text)
    box = QtWidgets.QMessageBox(Gui.getMainWindow())
    box.setObjectName("SciForgeRebuildRefused")
    box.setWindowTitle("Rebuild with Timeline")
    box.setIcon(QtWidgets.QMessageBox.Information)
    box.setText(text)
    box.setStandardButtons(QtWidgets.QMessageBox.Ok)
    from . import versions_ui

    versions_ui._show(box, "rebuild-refused")
    return box


def message_for(ref):
    target = rebuild.target_of(ref)
    return rebuild_core.chat_message(
        ref.SourceLabel,
        target.Label if target is not None else None,
        mesh=getattr(ref, "SourceKind", "") == "mesh",
    )


def chat_ready():
    """True when SciForge's own chat has an AI set up (a key kept, or a local model)."""
    try:
        from . import ai_panel_ui

        return any(e["kind"] == "chat" for e in ai_panel_ui.entries())
    except Exception as exc:
        warn("rebuild: %s" % exc)
        return False


def offer_message(ref):
    """The chat with the ready message (not sent), or the window for AI apps."""
    text = message_for(ref)
    _LAST["message"] = text
    if chat_ready():
        try:
            from . import ai_panel_ui

            ai_panel_ui.show("chat")
            page = ai_panel_ui.panel()
            chat = page.chat
            configured = [e["id"] for e in ai_panel_ui.entries() if e["kind"] == "chat"]
            if chat.provider_name() not in configured and configured:
                index = chat.provider.findData(configured[0])
                if index >= 0:
                    chat.provider.setCurrentIndex(index)
            chat.input.setPlainText(text)
            chat.input.setFocus()
            cursor = chat.input.textCursor()
            cursor.movePosition(QtGui.QTextCursor.End)
            chat.input.setTextCursor(cursor)
            # (beta 3 QA: nothing said the message waits for the person; a beginner waited)
            commands.tell(
                "The message for the AI is ready in the chat (AI panel): read it, then press "
                "Send."
            )
            return "chat"
        except Exception as exc:
            warn("rebuild: the chat could not be prepared (%s)" % exc)
    from . import versions_ui

    _LAST["dialog"] = versions_ui._show(NoChatDialog(ref, text), "rebuild-no-ai")
    return "dialog"


class NoChatDialog(QtWidgets.QDialog):
    """No AI in SciForge's chat: how to ask an AI app, with the message on the clipboard."""

    def __init__(self, ref, text):
        super().__init__(Gui.getMainWindow())
        self.setObjectName("SciForgeRebuildNoAI")
        self.setWindowTitle("Rebuild with Timeline (AI)")
        self.setMinimumWidth(520)
        column = QtWidgets.QVBoxLayout(self)
        target = rebuild.target_of(ref)
        intro = QtWidgets.QLabel(
            "%s is now the reference (shown faint), and the empty body %s is ready for the "
            "new steps.\n\nNo AI is set up in SciForge's chat. To let an AI app rebuild it "
            "(Claude Desktop, Gemini CLI, Claude Code...):\n"
            "  1. Add the app (Add an AI...) and turn AI control on in the AI panel.\n"
            "  2. Paste this message into the app (it is already copied). You can change it."
            % (ref.SourceLabel, target.Label if target is not None else "(rebuilt)")
        )
        intro.setWordWrap(True)
        intro.setObjectName("SciForgeRebuildNoAIText")
        column.addWidget(intro)
        self.text = QtWidgets.QPlainTextEdit(text)
        self.text.setObjectName("SciForgeRebuildMessage")
        self.text.setMinimumHeight(130)
        column.addWidget(self.text)
        row = QtWidgets.QHBoxLayout()
        self.copy_button = QtWidgets.QPushButton("Copy Message")
        self.copy_button.setObjectName("SciForgeRebuildCopy")
        self.copy_button.clicked.connect(self.copy)
        row.addWidget(self.copy_button)
        self.add_button = QtWidgets.QPushButton("Add an AI...")
        self.add_button.setObjectName("SciForgeRebuildAddAI")
        self.add_button.clicked.connect(self._add_ai)
        row.addWidget(self.add_button)
        row.addStretch(1)
        self.close_button = QtWidgets.QPushButton("Close")
        self.close_button.setObjectName("SciForgeRebuildClose")
        self.close_button.setDefault(True)
        self.close_button.clicked.connect(self.accept)
        row.addWidget(self.close_button)
        column.addLayout(row)
        self.copy(quiet=True)

    def copy(self, quiet=False):
        try:
            QtWidgets.QApplication.clipboard().setText(self.text.toPlainText())
            if not quiet:
                commands.tell("Copied: paste it into the AI app.")
        except Exception as exc:
            warn("rebuild: %s" % exc)

    def _add_ai(self):
        try:
            self.accept()
            QtCore.QTimer.singleShot(0, _open_add_ai)
        except Exception as exc:
            warn("rebuild: %s" % exc)


def _open_add_ai():
    try:
        from . import ai_ui

        ai_ui.add_ai()
    except Exception as exc:
        warn("Add an AI App: %s" % exc)


# -- Compare with Reference ---------------------------------------------------------------------
def _pct(value):
    return "%s %%" % rebuild_core.num(100.0 * float(value or 0.0), 3)


class CompareDialog(QtWidgets.QDialog):
    """The comparison's numbers and verdict; the differences show in the 3D view while it
    is open (closing it clears them)."""

    def __init__(self, ref):
        super().__init__(Gui.getMainWindow())
        self.setObjectName("SciForgeRebuildCompare")
        self.setWindowTitle("Compare with Reference")
        self.setMinimumWidth(480)
        self.ref = ref
        self.data = None
        column = QtWidgets.QVBoxLayout(self)
        self.headline = QtWidgets.QLabel("")
        self.headline.setObjectName("SciForgeRebuildMatch")
        font = self.headline.font()
        font.setPointSize(font.pointSize() + 3)
        font.setBold(True)
        self.headline.setFont(font)
        column.addWidget(self.headline)
        self.numbers = QtWidgets.QLabel("")
        self.numbers.setObjectName("SciForgeRebuildNumbers")
        self.numbers.setTextFormat(QtCore.Qt.RichText)
        column.addWidget(self.numbers)
        self.verdict = QtWidgets.QLabel("")
        self.verdict.setObjectName("SciForgeRebuildVerdict")
        self.verdict.setWordWrap(True)
        column.addWidget(self.verdict)
        self.table = QtWidgets.QTreeWidget()
        self.table.setObjectName("SciForgeRebuildDifferences")
        self.table.setColumnCount(3)
        self.table.setHeaderLabels(["", "What", "Volume"])
        self.table.setRootIsDecorated(False)
        self.table.setMinimumHeight(140)
        column.addWidget(self.table)
        row = QtWidgets.QHBoxLayout()
        self.again = QtWidgets.QPushButton("Compare Again")
        self.again.setObjectName("SciForgeRebuildCompareAgain")
        self.again.clicked.connect(self.refresh)
        row.addWidget(self.again)
        self.finish_button = QtWidgets.QPushButton("Finish Rebuild...")
        self.finish_button.setObjectName("SciForgeRebuildCompareFinish")
        self.finish_button.clicked.connect(self._finish)
        row.addWidget(self.finish_button)
        row.addStretch(1)
        self.close_button = QtWidgets.QPushButton("Close")
        self.close_button.setObjectName("SciForgeRebuildCompareClose")
        self.close_button.clicked.connect(self.reject)
        row.addWidget(self.close_button)
        column.addLayout(row)
        self.finished.connect(self._closed)
        self.refresh()

    def refresh(self):
        try:
            self.data = _busy(rebuild.compare, self.ref, None, {"show": True})
        except rebuild.RebuildError as exc:
            self.data = None
            self.headline.setText("Cannot compare")
            self.verdict.setText(rebuild_core.person_words(str(exc)))
            self.table.clear()
            self._closed()  # (the last differences drawn no longer stand)
            return
        except Exception as exc:
            warn("Compare with Reference: %s" % exc)
            return
        data = self.data
        faces = data["faces"]
        volume = data["volume"]
        self.headline.setText(
            ("Done: the rebuild matches. " if data["done"] else "")
            + "Match %s" % _pct(data["match"])
        )
        rows = [
            ("Original", "%s mm3" % rebuild_core.num(volume["reference"], 3)),
            ("Rebuild", "%s mm3" % rebuild_core.num(volume["rebuilt"], 3)),
            (
                "<span style='color:#f0605a'>Missing (red)</span>",
                "%s mm3" % rebuild_core.num(volume["missing"], 3),
            ),
            (
                "<span style='color:#5ad06e'>Extra (green)</span>",
                "%s mm3" % rebuild_core.num(volume["extra"], 3),
            ),
            ("Faces matched", "%d of %d" % (faces["matched"], faces["reference"])),
        ]
        deviation = data.get("deviation") or {}
        if deviation.get("max") is not None:
            rows.append(("Largest gap", "%s mm" % rebuild_core.about(deviation["max"])))
        self.numbers.setText(
            "<table>%s</table>"
            % "".join("<tr><td>%s&nbsp;&nbsp;</td><td>%s</td></tr>" % r for r in rows)
        )
        self.verdict.setText(rebuild_core.person_words(data["verdict"]))
        self.table.clear()
        for group in data.get("groups", []):
            item = QtWidgets.QTreeWidgetItem(
                [
                    "Missing" if group["side"] == "missing" else "Extra",
                    group["says"],
                    "%s mm3" % rebuild_core.num(group["volume"], 3),
                ]
            )
            colour = QtGui.QColor("#f0605a" if group["side"] == "missing" else "#5ad06e")
            item.setForeground(0, QtGui.QBrush(colour))
            item.setToolTip(1, group["says"])
            self.table.addTopLevelItem(item)
        self.table.resizeColumnToContents(0)

    def _finish(self):
        ref = self.ref
        self.reject()
        QtCore.QTimer.singleShot(0, lambda: _open_finish_later(ref))

    def _closed(self, *_args):
        try:
            clear_differences(self.ref.Document)
        except Exception:
            pass


def open_compare(ref):
    from . import versions_ui

    return versions_ui._show(CompareDialog(ref), "rebuild-compare")


# -- Finish Rebuild --------------------------------------------------------------------------------
class FinishDialog(QtWidgets.QDialog):
    """Finish: the original deleted or kept hidden, the reference kept or not."""

    def __init__(self, ref):
        super().__init__(Gui.getMainWindow())
        self.setObjectName("SciForgeRebuildFinish")
        self.setWindowTitle("Finish Rebuild")
        self.setModal(True)
        self.ref = ref
        self.result_body = None
        column = QtWidgets.QVBoxLayout(self)
        target = rebuild.target_of(ref)
        self.state = QtWidgets.QLabel("")
        self.state.setObjectName("SciForgeRebuildFinishState")
        self.state.setWordWrap(True)
        column.addWidget(self.state)
        try:
            data = _busy(
                rebuild.compare,
                ref,
                None,
                {"selectors": False, "deviation": False, "show": False},
            )
            if data.get("empty"):
                words = "%s is still empty: build the part first." % (
                    target.Label if target is not None else "The rebuilt body"
                )
            elif data["done"]:
                words = (
                    "%s matches %s (match %s, all %d faces). It takes the original's name "
                    "and place."
                    % (
                        target.Label,
                        ref.SourceLabel,
                        _pct(data["match"]),
                        data["faces"]["reference"],
                    )
                )
            else:
                words = (
                    "%s does not match %s yet (match %s, %d of %d faces). You can finish "
                    "it as it is anyway."
                    % (
                        target.Label,
                        ref.SourceLabel,
                        _pct(data["match"]),
                        data["faces"]["matched"],
                        data["faces"]["reference"],
                    )
                )
        except rebuild.RebuildError as exc:
            words = rebuild_core.person_words(str(exc))
        except Exception as exc:  # (OpenCASCADE: the window still opens, Finish still works)
            warn("Finish Rebuild: the comparison did not run (%s)" % exc)
            words = "The comparison did not run; you can finish the rebuild as it is."
        self.state.setText(words)
        self.delete_original = QtWidgets.QRadioButton(
            "Delete the original body (%s)" % ref.SourceLabel
        )
        self.delete_original.setObjectName("SciForgeRebuildDeleteOriginal")
        self.keep_original = QtWidgets.QRadioButton(
            'Keep the original, hidden (as "%s (original)")' % ref.SourceLabel
        )
        self.keep_original.setObjectName("SciForgeRebuildKeepOriginal")
        self.delete_original.setChecked(True)
        column.addWidget(self.delete_original)
        column.addWidget(self.keep_original)
        self.keep_reference = QtWidgets.QCheckBox("Keep the reference (hidden)")
        self.keep_reference.setObjectName("SciForgeRebuildKeepReference")
        column.addWidget(self.keep_reference)
        buttons = QtWidgets.QDialogButtonBox()
        self.ok = buttons.addButton("Finish", QtWidgets.QDialogButtonBox.AcceptRole)
        self.ok.setObjectName("SciForgeRebuildFinishOK")
        self.cancel = buttons.addButton("Cancel", QtWidgets.QDialogButtonBox.RejectRole)
        self.cancel.setObjectName("SciForgeRebuildFinishCancel")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        column.addWidget(buttons)
        self.ok.setEnabled(target is not None and _has_solid(target))

    def _accept(self):
        try:
            self.result_body = finish(
                self.ref,
                keep_original=self.keep_original.isChecked(),
                keep_reference=self.keep_reference.isChecked(),
            )
        except Exception as exc:
            warn("Finish Rebuild: %s" % exc)
        self.accept()


def _has_solid(body):
    from . import bodies

    return bodies.has_solid(body)


def finish(ref, keep_original=False, keep_reference=False):
    """Finish Rebuild as one undo step; a refusal is said."""
    doc = ref.Document
    if not commands.finish_open_dialog():
        return None
    name, original = ref.Name, ref.SourceLabel
    doc.openTransaction("Finish Rebuild")
    try:
        body = _busy(
            lambda: rebuild.finish(
                ref, None, keep_reference=keep_reference, keep_original=keep_original
            )
        )
    except rebuild.RebuildError as exc:
        doc.abortTransaction()
        commands.tell(rebuild_core.person_words(str(exc)))
        return None
    except Exception:
        doc.abortTransaction()
        raise
    doc.commitTransaction()
    doc.recompute()
    try:
        from . import components

        components.activate_body(body)
    except Exception:
        pass
    report = rebuild.FINISHED.get(name) or {}
    if report.get("followed"):
        log("Finish Rebuild: now on %s: %s" % (body.Label, ", ".join(report["followed"])))
    if report.get("kept_because") and not keep_original:
        users = report["kept_because"]
        commands.tell(
            '%s was kept, hidden, as "%s (original)" instead of deleted: %s still use%s it.'
            % (
                original,
                original,
                ", ".join(users[:3]) + (" ..." if len(users) > 3 else ""),
                "" if len(users) > 1 else "s",
            )
        )
    return body


def open_finish(ref):
    from . import versions_ui

    return versions_ui._show(FinishDialog(ref), "rebuild-finish")


def _open_finish_later(ref):
    """Compare's Finish Rebuild... (from a timer: nothing may escape it)."""
    from . import bodies

    try:
        if bodies.alive(ref) and rebuild.is_reference(ref) and getattr(ref, "Shown", True):
            open_finish(ref)
    except Exception as exc:
        warn("Finish Rebuild: %s" % exc)


# -- Stop Rebuild (beta 3 QA: there was no way back but Undo, none in a design opened again) --
class StopDialog(QtWidgets.QDialog):
    """Stop Rebuild: the original shown again, the reference gone; the rebuilt body deleted
    or kept."""

    def __init__(self, ref):
        super().__init__(Gui.getMainWindow())
        self.setObjectName("SciForgeRebuildStop")
        self.setWindowTitle("Stop Rebuild")
        self.setModal(True)
        self.ref = ref
        self.result = None
        column = QtWidgets.QVBoxLayout(self)
        target = rebuild.target_of(ref)
        original = rebuild.source_of(ref)
        if original is not None:
            text = (
                "Stop rebuilding %s? The original is shown again, as it was, and the "
                "rebuild's reference goes." % ref.SourceLabel
            )
        else:  # (the original was deleted meanwhile: the rebuild is all there is)
            text = (
                "Stop rebuilding %s? The original is gone (deleted); the rebuild's reference "
                "goes." % ref.SourceLabel
            )
        words = QtWidgets.QLabel(text)
        words.setObjectName("SciForgeRebuildStopState")
        words.setWordWrap(True)
        column.addWidget(words)
        name = target.Label if target is not None else "the rebuilt body"
        self.delete_rebuilt = QtWidgets.QRadioButton("Delete %s and its steps" % name)
        self.delete_rebuilt.setObjectName("SciForgeRebuildStopDelete")
        self.keep_rebuilt = QtWidgets.QRadioButton("Keep %s as a body of its own" % name)
        self.keep_rebuilt.setObjectName("SciForgeRebuildStopKeep")
        if original is None and target is not None:
            self.keep_rebuilt.setChecked(True)
        else:
            self.delete_rebuilt.setChecked(True)
        self.keep_rebuilt.setEnabled(target is not None)
        column.addWidget(self.delete_rebuilt)
        column.addWidget(self.keep_rebuilt)
        buttons = QtWidgets.QDialogButtonBox()
        self.ok = buttons.addButton("Stop Rebuild", QtWidgets.QDialogButtonBox.AcceptRole)
        self.ok.setObjectName("SciForgeRebuildStopOK")
        self.cancel = buttons.addButton("Cancel", QtWidgets.QDialogButtonBox.RejectRole)
        self.cancel.setObjectName("SciForgeRebuildStopCancel")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        column.addWidget(buttons)

    def _accept(self):
        try:
            self.result = stop(self.ref, keep_rebuilt=self.keep_rebuilt.isChecked())
        except Exception as exc:
            warn("Stop Rebuild: %s" % exc)
        self.accept()


def stop(ref, keep_rebuilt=False):
    """Stop Rebuild as one undo step; a refusal is said. Returns the original (or None)."""
    doc = ref.Document
    if not commands.finish_open_dialog():
        return None
    for widget in QtWidgets.QApplication.topLevelWidgets():  # (its compare window: stale)
        try:
            if isinstance(widget, CompareDialog) and widget.isVisible() and widget.ref is ref:
                widget.close()
        except Exception:
            pass
    doc.openTransaction("Stop Rebuild")
    try:
        source = rebuild.stop(ref, keep_rebuilt=keep_rebuilt)
    except rebuild.RebuildError as exc:
        doc.abortTransaction()
        commands.tell(rebuild_core.person_words(str(exc)))
        return None
    except Exception:
        doc.abortTransaction()
        raise
    doc.commitTransaction()
    doc.recompute()
    return source


def open_stop(ref):
    from . import versions_ui

    return versions_ui._show(StopDialog(ref), "rebuild-stop")


# -- the 3D view's right-click ------------------------------------------------------------------
_PENDING = {"doc": None, "name": None}


def _under_mouse(global_pos):
    """The body or mesh body under the mouse in the active 3D view, or None."""
    from . import bodies, hole_common, insert

    gdoc = Gui.ActiveDocument
    if gdoc is None or gdoc.ActiveView is None:
        return None
    widget = QtWidgets.QApplication.widgetAt(global_pos)
    if widget is None or widget.metaObject().className() != "QOpenGLWidget":
        return None
    local = widget.mapFromGlobal(global_pos)
    ratio = widget.devicePixelRatioF()
    try:
        info = gdoc.ActiveView.getObjectInfo(
            (local.x() * ratio, (widget.height() - local.y()) * ratio)
        )
    except Exception:
        return None
    if not info or not info.get("Object"):
        return None
    doc = gdoc.Document
    obj = doc.getObject(info["Object"])
    if obj is None:
        return None
    obj, _short = hole_common.resolve(obj, info.get("Component", "") or "")
    if obj is None:
        return None
    if insert.is_mesh_body(obj):
        return obj
    return bodies.body_of(obj)


def marking_entries(global_pos):
    """The 3D view's right-click list: Rebuild with Timeline (AI)... when a body is under
    the mouse (Compare / Finish when it is a rebuild in progress)."""
    from . import ribbon_config as cfg

    body = _under_mouse(global_pos)
    if body is None or rebuild.is_reference(body):
        return []
    _PENDING.update(doc=body.Document.Name, name=body.Name)
    ref = rebuild.reference_for(body)
    going = ref is not None and getattr(ref, "Shown", True)
    if going and getattr(ref, "TargetName", "") == body.Name:
        return [
            cfg.SEP,
            cfg.item("Compare with Reference", "SciForge_CompareReference", "rebuild_compare"),
            cfg.item("Finish Rebuild", "SciForge_FinishRebuild", "rebuild_finish"),
            cfg.item("Stop Rebuild...", "SciForge_StopRebuildUnderMouse", "cancel"),  # (QA)
        ]
    return [
        cfg.SEP,
        cfg.item("Rebuild with Timeline (AI)...", "SciForge_RebuildUnderMouse", "rebuild_ai"),
    ]


def _install_marking():
    try:
        from . import marking_menu

        hooks = getattr(marking_menu, "CONTEXT_ITEMS", None)
        if hooks is not None and marking_entries not in hooks:
            hooks.append(marking_entries)
    except Exception as exc:
        warn("rebuild: no right-click entry in the 3D view (%s)" % exc)


# -- commands -------------------------------------------------------------------------------------
class RebuildCommand:
    def GetResources(self):
        return {
            "MenuText": "Rebuild with Timeline (AI)...",
            "ToolTip": "Rebuild the selected body (an imported STEP body, a mesh body...) as "
            "real timeline steps with an AI: SciForge keeps it as the reference and prepares "
            "the message for the AI",
            "Pixmap": ui_icon_path("rebuild_ai"),
        }

    def IsActive(self):
        return App.ActiveDocument is not None

    def Activated(self):
        try:
            source = _selected_source()
            if source is None:
                commands.tell(
                    "Select the body to rebuild first (or right-click it in the browser > "
                    "Rebuild with Timeline (AI)...)."
                )
                return
            start_for(source)
        except Exception as exc:
            warn("Rebuild with Timeline: %s" % exc)


class RebuildUnderMouseCommand(RebuildCommand):
    """The 3D view's right-click entry: the body that was under the mouse."""

    def GetResources(self):
        res = RebuildCommand.GetResources(self)
        res["ToolTip"] = "Rebuild the body under the mouse with an AI (Auto Timeline)"
        return res

    def Activated(self):
        try:
            doc = App.listDocuments().get(_PENDING.get("doc") or "")
            body = doc.getObject(_PENDING.get("name") or "") if doc is not None else None
            _PENDING.update(doc=None, name=None)
            if body is None:
                RebuildCommand.Activated(self)
                return
            start_for(body)
        except Exception as exc:
            warn("Rebuild with Timeline: %s" % exc)


class CompareCommand:
    def GetResources(self):
        return {
            "MenuText": "Compare with Reference",
            "ToolTip": "How far the rebuild is from the original: the numbers, and the "
            "differences in the 3D view (missing material red, extra green)",
            "Pixmap": ui_icon_path("rebuild_compare"),
        }

    def IsActive(self):
        return bool(rebuild.references(App.ActiveDocument))

    def Activated(self):
        try:
            ref = current_reference()
            if ref is not None:
                open_compare(ref)
        except Exception as exc:
            warn("Compare with Reference: %s" % exc)


class FinishCommand:
    def GetResources(self):
        return {
            "MenuText": "Finish Rebuild",
            "ToolTip": "The rebuild takes the original's name and place; the original is "
            "deleted or kept hidden",
            "Pixmap": ui_icon_path("rebuild_finish"),
        }

    def IsActive(self):
        return bool(rebuild.active_references(App.ActiveDocument))

    def Activated(self):
        try:
            if not commands.finish_open_dialog():
                return
            ref = current_reference()
            if ref is not None:
                open_finish(ref)
        except Exception as exc:
            warn("Finish Rebuild: %s" % exc)


class StopCommand:
    """(beta 3 QA: a rebuild could only be taken back with Undo)"""

    def GetResources(self):
        return {
            "MenuText": "Stop Rebuild...",
            "ToolTip": "Give the rebuild up: the original is shown again as it was; the "
            "rebuilt body is deleted or kept",
            "Pixmap": ui_icon_path("cancel"),
        }

    def IsActive(self):
        return bool(rebuild.active_references(App.ActiveDocument))

    def Activated(self):
        try:
            if not commands.finish_open_dialog():
                return
            ref = current_reference()
            if ref is not None:
                open_stop(ref)
        except Exception as exc:
            warn("Stop Rebuild: %s" % exc)


class StopUnderMouseCommand(StopCommand):
    """The 3D view's right-click entry: the rebuild of the body under the mouse (with
    several going on, not the active body's)."""

    def Activated(self):
        try:
            doc = App.listDocuments().get(_PENDING.get("doc") or "")
            body = doc.getObject(_PENDING.get("name") or "") if doc is not None else None
            _PENDING.update(doc=None, name=None)
            ref = rebuild.reference_for(body) if body is not None else None
            if ref is None or not getattr(ref, "Shown", True):
                StopCommand.Activated(self)
                return
            if commands.finish_open_dialog():
                open_stop(ref)
        except Exception as exc:
            warn("Stop Rebuild: %s" % exc)


COMMANDS = {
    "SciForge_RebuildWithTimeline": RebuildCommand,
    "SciForge_RebuildUnderMouse": RebuildUnderMouseCommand,
    "SciForge_CompareReference": CompareCommand,
    "SciForge_FinishRebuild": FinishCommand,
    "SciForge_StopRebuild": StopCommand,
    "SciForge_StopRebuildUnderMouse": StopUnderMouseCommand,
}

_install_marking()
