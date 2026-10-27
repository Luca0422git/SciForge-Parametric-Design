# SPDX-License-Identifier: LGPL-2.1-or-later
"""No undo step is left open by a design closed under one of its dialogs.

FreeCAD's undo step is application-wide: `doc.openTransaction(name)` names the step that the
next change in ANY design goes into, and a design joins the step only with its first change.
A design that joined it closes it as it goes (FreeCAD commits it into the closed design). A
design closed while its dialog had changed nothing yet (Hole waiting for a face, Extrude for a
profile) left the step open: App.getActiveTransaction() still named it, the next design's
changes went into a step named after the closed design's dialog (its first changes undone
together with its next edit, under the other design's name), and a simulation solve waited for
it forever (found by the simulation builder; simulation_ui._close_leftover_step).

One watch for every dialog (install(): the shell at start-up, every taskui.Panel), FreeCAD's
"a design is closing" signal (the design and its dialog still there):

- A step is open that the closing design has not joined, and the dialog open is that
  design's (SciForge's current dialog, or a FreeCAD task dialog of that design): the step is
  closed at once, before anything else can change. Nothing is in it (taken back, so nothing is
  kept); a design still open that had changes in it keeps them (closed keeping them).
- A dialog is open and whose it is cannot be told: the step is closed once no dialog is open
  any more (the closed design's dialog goes a moment later) if it is still the open step and
  no open design has changes in it; given up after a few seconds or once it is known to be
  another design's dialog (that dialog's step).
- A dialog of another design is open, or no dialog at all (a command's or a script's own
  step, a throw-away document closed in the middle of it): left alone.

decide() holds the rule (pure Python, unit tested: test_undo_leftover.py)."""

CLOSE = "close"  # close now: nothing is in the step
CLOSE_KEEP = "close_keep"  # close now, keeping what an open design has in it
WAIT = "wait"  # a dialog is open whose design is unknown: look again once it went
LEAVE = "leave"  # not a leftover of the closing design (or nothing to do)

POLL_MS = 200
GIVE_UP_S = 5.0

_state = {"observer": None, "pending": None}


def decide(closing, step, closing_joined, others_joined, dialog_open, dialog_doc):
    """What to do with the open undo step when the design `closing` (its Name) closes.

    step: App.getActiveTransaction() ((name, id) or None). closing_joined: the closing
    design has changes in the step (FreeCAD then closes it itself). others_joined: a design
    staying open has changes in it. dialog_open: a task dialog is open. dialog_doc: the Name of
    the design that dialog belongs to ("" when it cannot be told)."""
    if not step or closing_joined or not dialog_open:
        return LEAVE
    if not dialog_doc:
        return WAIT
    if dialog_doc != closing:
        return LEAVE  # the step of a dialog still open in another design
    return CLOSE_KEEP if others_joined else CLOSE


def decide_later(remembered, step, others_joined, dialog_open, dialog_doc, closed_name):
    """The step remembered (its id) when a design closed under a dialog that could not be told:
    LEAVE (stop looking), WAIT, or CLOSE."""
    if not step or step[1] != remembered:
        return LEAVE  # closed, or another step opened since
    if others_joined:
        return LEAVE  # a design has changes in it: whoever opened it closes it
    if dialog_open:
        if dialog_doc and dialog_doc != closed_name:
            return LEAVE  # another design's dialog: its step
        return WAIT
    return CLOSE


# -- FreeCAD ------------------------------------------------------------------------------
def _active_step():
    import FreeCAD as App

    try:
        return App.getActiveTransaction()
    except Exception:
        return None


def _joined(skip=None):
    """True when a design (other than `skip`, a Name) has changes in the open step."""
    import FreeCAD as App

    for name, doc in App.listDocuments().items():
        if name == skip:
            continue
        try:
            if doc.HasPendingTransaction:
                return True
        except Exception:
            continue
    return False


def _dialog():
    """(a task dialog is open, the Name of its design or "")."""
    import FreeCADGui as Gui

    try:
        if not Gui.Control.activeDialog():
            return False, ""
    except Exception:
        return False, ""
    try:  # SciForge's own dialogs (their task dialog has no design name); one that has
        # already let go of its design (_closed) tells nothing
        from . import taskui

        current = taskui._OPEN.get("dialog")
        if current is not None and not getattr(current, "_closed", False):
            doc = getattr(current, "doc", None)
            if doc is not None:
                return True, doc.Name
    except Exception:
        pass
    try:  # FreeCAD's (a feature or sketch in edit)
        task = Gui.Control.activeTaskDialog()
        name = task.getDocumentName() if task is not None else ""
        return True, name or ""
    except Exception:
        return True, ""


def _close(step, keep, why):
    import FreeCAD as App

    from . import log

    App.closeActiveTransaction(not keep, step[1])
    log(
        "undo step %r closed: %s%s"
        % (step[0], why, " (kept by the designs that changed in it)" if keep else "")
    )


def design_closing(doc):
    """FreeCAD is closing `doc` (its dialog may still be open). Never raises."""
    try:
        step = _active_step()
        if not step:
            return
        name = doc.Name
        joined = bool(getattr(doc, "HasPendingTransaction", False))
        dialog_open, dialog_doc = _dialog()
        action = decide(name, step, joined, _joined(skip=name), dialog_open, dialog_doc)
        if action in (CLOSE, CLOSE_KEEP):
            _close(step, action == CLOSE_KEEP, "%s closed under its dialog" % doc.Label)
        elif action == WAIT:
            _later(step[1], name, doc.Label)
    except Exception as exc:
        _quiet_warn("undo step of a closed design: %s" % exc)


def _later(step_id, name, label):
    import time

    from .compat import QtCore

    _state["pending"] = {"id": step_id, "name": name, "label": label, "since": time.time()}
    QtCore.QTimer.singleShot(0, _look_again)


def _look_again():
    import time

    from .compat import QtCore

    try:
        pending = _state["pending"]
        if pending is None:
            return
        step = _active_step()
        dialog_open, dialog_doc = _dialog()
        action = decide_later(
            pending["id"], step, _joined(), dialog_open, dialog_doc, pending["name"]
        )
        if action == CLOSE:
            _state["pending"] = None
            _close(step, False, "%s closed under its dialog, now gone" % pending["label"])
        elif action == WAIT and time.time() - pending["since"] < GIVE_UP_S:
            QtCore.QTimer.singleShot(POLL_MS, _look_again)
        else:
            _state["pending"] = None
    except Exception as exc:
        _state["pending"] = None
        _quiet_warn("undo step of a closed design: %s" % exc)


def _quiet_warn(text):
    try:
        from . import warn

        warn(text)
    except Exception:
        pass


class _Watch:
    def slotDeletedDocument(self, doc):
        design_closing(doc)


def install():
    """Watch every design closing (once). Never raises."""
    try:
        import FreeCAD as App

        if _state["observer"] is None:
            _state["observer"] = _Watch()
            App.addDocumentObserver(_state["observer"])
    except Exception as exc:
        _quiet_warn("undo step watch: %s" % exc)
