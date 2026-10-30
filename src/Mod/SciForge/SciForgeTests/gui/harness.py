# SPDX-License-Identifier: LGPL-2.1-or-later
"""Helpers for GUI scenario tests that use SciForge like a person does.

A scenario is a Python file run by the FreeCAD GUI (CI: under xvfb-run) that does

    from SciForgeTests.gui import harness as h
    h.run("my-scenario", [step_a, step_b, ...])

Each step is a plain function. Steps run one at a time. Use the helpers below to act:
click(App.Vector) / drag / press(key) / ribbon(label) / menu_item(group, label).
Use check(name, ok, detail) to assert.

Pacing: wait for the app's state, never for the clock (docs/sciforge/dev/gui-tests.md).
A converted scenario runs with h.run(..., paced_by="state"): a step starts once the app
has settled after the one before (nothing recomputing, no input still being played, no
work SciForge posted for a moment later, every pointer move seen by Qt) and once its own
`ready` holds; the next starts once its `done` holds and the app has settled again.
    step.ready = lambda: ...   what must be true before the step's input
    step.done = lambda: ...    what proves the step worked
    step.timeout_s = 120       a longer upper bound for both (a solve); bounds only catch hangs
    step.while_busy = True     the step acts while something plays on purpose (an animation
                               runs, a solve goes on): no waiting for a quiet app around it,
                               only for its ready / done
Inside a step, wait_for(condition, what) and settle() do the same. A wait that runs into
its bound fails a check named after what it waited for, with what was seen instead and a
screenshot, closes any modal dialog or open menu and stops the scenario at once.
Scenarios not converted yet (paced_by="timer", the default) still wait a fixed wait_ms
(default STEP_MS) after each step; tools/sciforge/check_waits.py counts them down to zero.

Every error FreeCAD prints (Report view: C++ and Python, SciForge or not), every
Python traceback and every SciForge warning fails the scenario, because those are
exactly what a user sees as "errors everywhere". A crash fails it too: the result
file is only written at the end.

The result goes to $SCIFORGE_SMOKE_OUT/<name>-result.json, screenshots to
$SCIFORGE_SMOKE_OUT/<name>-*.png.
"""

import json
import os
import re
import time
import traceback
import weakref

import FreeCAD as App
import FreeCADGui as Gui

from PySide import QtCore, QtGui, QtWidgets
from PySide6 import QtTest

OUT_DIR = os.environ.get("SCIFORGE_SMOKE_OUT") or App.getUserAppDataDir()
# the fixed wait after each step of a scenario not converted yet (paced_by="timer")
STEP_MS = int(os.environ.get("SCIFORGE_STEP_MS", "700"))
# Upper bounds. They only catch hangs: a wait that reaches one means something is broken,
# never that the machine was slow. Never lower one to make a run faster, never raise one to
# make a test pass (a step that needs longer, a solve, says so with step.timeout_s).
WAIT_S = 30.0
STEP_LIMIT_S = float(os.environ.get("SCIFORGE_STEP_LIMIT_S", "300"))
POLL_MS = 15  # how often a wait looks at the app again (the event loop runs in between)
# A speed limit in a check (the window never froze longer than 4 s) is multiplied by this:
# 1, except under run_tests.sh --stress, which slows the machine down on purpose by about
# this much. It never changes a wait.
SLOWDOWN = float(os.environ.get("SCIFORGE_SLOWDOWN") or 1)
checks = []
state = {"name": "scenario", "errors_seen": 0}
# Report-view lines that are not problems (start-up chatter of stock FreeCAD).
IGNORED_ERRORS = (
    re.compile(r"Migrating Start Workbench"),
    re.compile(r"Cannot find icon"),
    # FreeCAD 1.1.4's sketch areas give up on a line through a circle inside another
    # area; SciForge adds the areas then (sciforge/sketch_area_fill.py, which warns if it
    # cannot)
    re.compile(r"<WireJoiner>"),
    re.compile(r"Failed to make face for sketch"),
    # the harness's own progress line (a step called g1_error is not an error)
    re.compile(r"\[SciForge\] [\w.-]+ step: \w+ \([\d.]+ s\)"),
)


def check(name, ok, detail=""):
    if not ok and state.get("last_click"):
        detail = "%s [last click: %s]" % (detail, state["last_click"])
    checks.append(
        {"name": name, "ok": bool(ok), "detail": str(detail)[:4000], "step": state.get("step")}
    )
    return bool(ok)


def speed_check(name, ok, detail=""):
    """A check of how SciForge keeps up in real time that no limit can scale (no exact
    rebuild between the moves of a drag at a hand's pace). Under run_tests.sh --stress the
    machine is slowed down on purpose and the answer says nothing about SciForge: there it is
    printed, not counted. On every normal run it counts like any check. (A limit that scales
    is written limit * SLOWDOWN instead.)"""
    if SLOWDOWN > 1 and not ok:
        print(
            "[SciForge] %s: not counted under --stress (a speed check): %s %s"
            % (state["name"], name, str(detail)[:300]),
            flush=True,
        )
        return True
    return check(name, ok, detail)


def shot(label):
    # Only safe characters: GitHub refuses to upload artifacts with ':' '>' etc. in a name.
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", "%s-%s" % (state["name"], label)).strip("_")
    path = os.path.join(OUT_DIR, safe + ".png")
    QtWidgets.QApplication.primaryScreen().grabWindow(0).save(path)


# -- errors -----------------------------------------------------------------------
def report_text():
    for widget in Gui.getMainWindow().findChildren(QtWidgets.QTextEdit):
        if widget.metaObject().className() == "Gui::DockWnd::ReportOutput":
            return widget.toPlainText()
    return ""


class _ConsoleTap:
    """Catches errors/warnings printed through App.Console from Python."""

    def __init__(self):
        self.lines = []
        self._error = App.Console.PrintError
        self._warning = App.Console.PrintWarning
        App.Console.PrintError = self._on_error
        App.Console.PrintWarning = self._on_warning

    def _on_error(self, msg):
        self.lines.append("ERROR " + str(msg).strip())
        self._error(msg)

    def _on_warning(self, msg):
        if "[SciForge]" in str(msg):
            self.lines.append("WARNING " + str(msg).strip())
        self._warning(msg)


_tap = None


def _report_errors():
    """Error lines of the Report view (FreeCAD shows errors in red with 'Error'/'<Exception>')."""
    found = []
    for line in report_text().splitlines():
        low = line.lower()
        if any(p.search(line) for p in IGNORED_ERRORS):
            continue
        if (
            "error" in low
            or "exception" in low
            or "traceback" in low
            or "failed" in low
            or "invalid" in low
            or "[sciforge] warning" in low
        ):
            found.append(line.strip())
    return found


def new_errors():
    """Errors that appeared since the last call (Report view + console tap)."""
    lines = _report_errors() + (_tap.lines if _tap else [])
    fresh = lines[state["errors_seen"] :]
    state["errors_seen"] = len(lines)
    return fresh


def expect_no_errors(where):
    fresh = new_errors()
    return check("No errors after %s" % where, not fresh, fresh)


# -- work the app has posted for a moment later -----------------------------------
# SciForge's dialogs debounce their previews and post follow-ups (QTimer.singleShot(0, ...),
# a single-shot QTimer restarted on every change). Until they have run, what the screen
# shows is not the effect of the last input yet. Every such timer started from Python is
# tracked here, so "the app has settled" can be a state instead of a guessed wait.
_ORIGINAL = getattr(QtCore.QTimer, "_sciforge_original", None)
if _ORIGINAL is None:  # (the harness imported a second time must not wrap its own wrappers)
    _ORIGINAL = QtCore.QTimer._sciforge_original = (
        QtCore.QTimer.singleShot,
        QtCore.QTimer.start,
    )
_SINGLE_SHOT, _START = _ORIGINAL
# A longer delay is not work about to happen but a display time or a decision: a refusal
# shown for 2.5 s, a long press, an update check. Waiting for it would undo the very state a
# step checks (the timeline's refusal hint is gone after 2.5 s).
HORIZON_MS = 1000


def _alive(obj):
    try:
        import shiboken6

        return shiboken6.isValid(obj)
    except Exception:
        return True


def _label(fn):
    owner = getattr(fn, "__self__", None)
    name = getattr(fn, "__qualname__", None) or getattr(fn, "__name__", None) or repr(fn)
    module = getattr(fn, "__module__", None) or ""
    if owner is not None and not isinstance(owner, type) and "." not in name:
        name = "%s.%s" % (type(owner).__name__, name)
    return "%s.%s" % (module.rsplit(".", 1)[-1], name) if module else name


class _Posted:
    """QTimer.singleShot calls and single-shot QTimers started from Python, still due."""

    def __init__(self):
        self.calls = {}  # token -> (due, label, context)
        self.timers = weakref.WeakValueDictionary()  # id -> QTimer started from Python
        self.own = set()  # ids of the harness's own timers (pacing, watchdog)
        self.running = []  # labels of the posted calls running now

    def single_shot(self, *args, **kwargs):
        fn = args[-1] if args else None
        try:
            msec = int(args[0])
        except Exception:
            msec = None
        if (
            kwargs
            or msec is None
            or msec > HORIZON_MS
            or not callable(fn)
            or type(fn).__name__ in ("SignalInstance", "Signal")
        ):
            return _SINGLE_SHOT(*args, **kwargs)
        label = _label(fn)
        if label in self.running:
            # posted again from its own run: a poll waiting for something (the scratch design
            # to close, a sketch to be left), not work about to finish; a step that needs what
            # it waits for says so with a `done`
            return _SINGLE_SHOT(*args, **kwargs)
        token = object()
        context = args[1] if len(args) == 3 and isinstance(args[1], QtCore.QObject) else None
        self.calls[token] = (time.monotonic() + msec / 1000.0, label, context)

        def fire(*a):
            self.calls.pop(token, None)
            owner = getattr(fn, "__self__", None)
            if isinstance(owner, QtCore.QObject) and not _alive(owner):
                return None  # what Qt does when the receiver is gone
            self.running.append(label)
            try:
                return fn(*a)
            finally:
                self.running.remove(label)

        return _SINGLE_SHOT(*(args[:-1] + (fire,)))

    def start(self, timer, *args):
        try:
            if id(timer) not in self.own:
                self.timers[id(timer)] = timer
        except Exception:
            pass
        return _START(timer, *args)

    def due(self):
        """What is still due, as labels for a failure message; empty when nothing is."""
        now = time.monotonic()
        found = []
        for token, (due, label, context) in list(self.calls.items()):
            # a call whose context object died never runs; one long overdue was dropped by Qt
            if (context is not None and not _alive(context)) or now > due + 10.0:
                self.calls.pop(token, None)
                continue
            found.append(label)
        for timer in list(self.timers.values()):
            try:
                if (
                    id(timer) not in self.own
                    and _alive(timer)
                    and timer.isActive()
                    and timer.isSingleShot()
                    and timer.interval() <= HORIZON_MS
                ):
                    parent = timer.parent()
                    found.append(
                        "a %d ms timer of %s"
                        % (timer.interval(), type(parent).__name__ if parent else "Python")
                    )
            except RuntimeError:
                pass
        return found


_posted = _Posted()
QtCore.QTimer.singleShot = staticmethod(_posted.single_shot)
QtCore.QTimer.start = lambda timer, *args: _posted.start(timer, *args)


def _later(ms, fn):
    """The harness's own scheduling (pacing, polling): never counted as the app's work."""
    _SINGLE_SHOT(ms, fn)


# -- the pointer as Qt knows it ---------------------------------------------------
class _PointerTap(QtCore.QObject):
    """The global position of the last mouse move Qt delivered to one of its windows. QTest
    moves the real (X) pointer and the X server tells Qt a moment later: a click sent
    before that lands where Qt still thinks the pointer is, and two moves told together are
    folded into one (CI #285 - #287: ribbon menu entries clicked and nothing ran)."""

    def __init__(self):
        super().__init__()
        self.last = None
        self.expected = None
        self.menus_shown = 0  # menus that appeared (a right-click's may come and go at once)
        self.last_press = 0.0  # when the last mouse button went down (time.monotonic)

    def eventFilter(self, obj, event):
        try:
            kind = event.type()
            if kind == QtCore.QEvent.MouseMove and isinstance(obj, QtGui.QWindow):
                self.last = event.globalPosition().toPoint()
            elif kind == QtCore.QEvent.Show and isinstance(obj, QtWidgets.QMenu):
                self.menus_shown += 1
            elif kind == QtCore.QEvent.MouseButtonPress and isinstance(obj, QtWidgets.QWidget):
                self.last_press = time.monotonic()
        except Exception:
            pass
        return False


def click_gap():
    """The shortest time the app wants between two clicks in the 3D view, as it measures it:
    FreeCAD's double-click interval (the sketcher times two presses itself: a second one
    within it is a double-click), and SciForge's click windows: for OVERLAY_CLICK_S (0.6 -
    0.8 s) after an overlay took a click (the move triad's axes, pattern axes, Split's and
    Align's planes) the selection a click makes is ignored, to drop the one FreeCAD makes
    behind the overlay with the same click; the pickers' clicked_recently() (0.6 s: profile,
    axis, plane, cell and point picks) and the Move triad's busy() after a drag (0.6 s) do the
    same. A second click within one of them is lost too."""
    import importlib

    found = [QtWidgets.QApplication.doubleClickInterval() / 1000.0]
    for name in ("move_ui", "pattern_ui", "split_ui", "modify_common"):
        try:
            found.append(float(importlib.import_module("sciforge." + name).OVERLAY_CLICK_S))
        except Exception:
            pass
    return max(found)


def press_pace():
    """Before a click in the 3D view: the next press comes once click_gap() has passed since
    the last one, as a person's next click does (an input pace the app measures, not a wait
    for the app). Without fixed waits two clicks came 0.4 s apart and the second was lost
    (inspect_qa4: the face after the Center of Mass dot)."""
    _install_pointer_tap()
    left = _pointer.last_press + click_gap() - time.monotonic()
    if left > 0:
        QtTest.QTest.qWait(int(left * 1000) + 10)  # input pace: the app times the gap between clicks


def _in_3d_view(target):
    """True for a 3D view's GL widget (where a press in the 3D view goes)."""
    try:
        return (
            isinstance(target, QtWidgets.QWidget)
            and target.metaObject().className() == "QOpenGLWidget"
        )
    except Exception:
        return False


# Every press in the 3D view comes at press_pace(), whoever sends it: the input helpers and
# the scenarios' own QTest.mousePress for a drag alike (92 files press there themselves).
_QTEST = getattr(QtTest.QTest, "_sciforge_original", None)
if _QTEST is None:  # (imported a second time: do not wrap the wrappers)
    _QTEST = QtTest.QTest._sciforge_original = {
        name: getattr(QtTest.QTest, name) for name in ("mousePress", "mouseClick", "mouseDClick")
    }


def _paced(original):
    def press(target, *args, **kwargs):
        if _in_3d_view(target):
            press_pace()
        return original(target, *args, **kwargs)

    return staticmethod(press)


for _name, _original in _QTEST.items():
    setattr(QtTest.QTest, _name, _paced(_original))


def menus_shown():
    """How many menus have appeared so far (compare before and after an input)."""
    _install_pointer_tap()
    return _pointer.menus_shown


_pointer = _PointerTap()


def _install_pointer_tap():
    app = QtWidgets.QApplication.instance()
    if app is not None and not state.get("pointer_tap"):
        app.installEventFilter(_pointer)
        state["pointer_tap"] = True


def pointer_to(widget, pos, fresh=False):
    """Move the real pointer to `pos` (widget pixels) and wait until Qt has been told
    (rule 4: input reaches the app before the next input). A pointer already on that pixel
    makes no move at all, so it first steps one pixel aside. fresh: also when Qt already
    knows the pointer is there (a hand comes onto what it clicks: FreeCAD's sketch finds what
    is under the pointer on a move; a second double-click on the same dimension found
    nothing). Returns the global position."""
    _install_pointer_tap()
    target = widget.mapToGlobal(pos)
    if QtGui.QGuiApplication.screenAt(target) is None or QtWidgets.QApplication.topLevelAt(target) is None:
        # Off the screen or off every window of SciForge (a point of the model outside the
        # view): Qt is never told of a pointer there. The input that follows goes straight to
        # the widget, as it always has.
        if not state.get("offscreen_told"):
            state["offscreen_told"] = True
            print(
                "[SciForge] %s: %d, %d is outside SciForge's windows; the input goes to %s"
                % (state["name"], target.x(), target.y(), describe(widget)),
                flush=True,
            )
        return target
    if not fresh and QtGui.QCursor.pos() == target and _pointer.last == target:
        return target  # there already, and Qt knows
    _pointer_step(widget, pos)
    return target


def _pointer_step(widget, pos):
    target = widget.mapToGlobal(pos)
    now = QtGui.QCursor.pos()
    if now == target or _pointer.last == target:
        # A pointer sent to where it already is makes no move at all; and Qt folds moves told
        # together into the last one and drops it when that is where it last saw the pointer
        # (sketch_infer_tools: the scenario's own move one pixel off, then this one: nothing
        # came). So first a neighbouring pixel, seen by Qt.
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            aside = QtCore.QPoint(target.x() + dx, target.y() + dy)
            if aside != now and aside != _pointer.last:
                _warp(aside, widget)
                break
    _warp(target, widget)


def _warp(target, widget):
    """The real pointer to global `target`, then wait until Qt has been told."""
    _pointer.last = None
    _pointer.expected = target
    # The real pointer, always. (QTest.mouseMove only moves it while QTest thinks no button
    # is down; inside a menu that opened on a press, before that press's release, it sends
    # the widget a made-up move instead and the pointer stays where it was.)
    QtGui.QCursor.setPos(target)
    try:
        wait_for(
            lambda: _pointer.last == target,
            "Qt to see the pointer at %d, %d (%s)" % (target.x(), target.y(), describe(widget)),
        )
    finally:
        _pointer.expected = None


# -- waiting for a state ------------------------------------------------------------
class WaitTimeout(Exception):
    """A wait ran into its upper bound. The failed check is already recorded and the
    scenario stops after this step."""


def describe(widget):
    """A widget in a few words, for failure messages."""
    if widget is None:
        return "nothing"
    try:
        if not _alive(widget):
            return "a deleted widget"
        words = [widget.metaObject().className()]
        if widget.objectName():
            words.append("'%s'" % widget.objectName())
        for getter in ("windowTitle", "title", "text"):
            try:
                text = getattr(widget, getter)()
            except Exception:
                continue
            if isinstance(text, str) and text.strip():
                words.append('"%s"' % text.strip().replace("&", "")[:60])
                break
        return " ".join(words)
    except Exception as exc:
        return "a widget (%s)" % exc


def busy(since=None):
    """Why the app has not settled yet (empty when it has): what the last input set going
    and the screen does not show yet. since (a time.monotonic()): also a drag handle that
    has not polled since then (a handle keeps what Coin picks of it at the view's scale on
    its poll: a press right after a fit or a zoom missed the arrow, bodies_qa)."""
    reasons = []
    if since is not None:
        try:
            from sciforge import taskui

            stale = [x for x in taskui.live_handles() if getattr(x, "_polled_at", 0.0) < since]
            if stale:
                reasons.append("%d drag handles have not followed the view yet" % len(stale))
        except Exception:
            pass
    try:
        for doc in App.listDocuments().values():
            if getattr(doc, "Recomputing", False):
                reasons.append("%s is recomputing" % doc.Name)
    except Exception:
        pass
    if BUSY:
        reasons.append("input still being played (%d)" % len(BUSY))
    if _searching():
        reasons.append("a dialog is still looking for the largest value that fits")
    due = _posted.due()
    if due:
        reasons.append("work posted for a moment later: %s" % ", ".join(due[:6]))
    if _pointer.expected is not None:
        reasons.append("a pointer move Qt has not been told about")
    for name in _panels_behind():
        reasons.append("the %s has not read the latest change yet" % name)
    try:
        from sciforge import shell

        if shell.settling():
            reasons.append("SciForge is still arranging its window")
    except Exception:
        pass
    return reasons


def _panels_behind():
    """The browser and the timeline read the design on a poll (every 0.5 / 0.4 s) once it has
    changed (sciforge.doc_epoch); until then they show it as it was. Activating a component
    dims the rest of the design only with the browser's read: a click before it hit the
    root body that was about to turn see-through (components2_marker, on a slow machine). A
    panel waiting for the person (a name being typed, a drag) is not counted."""
    found = []
    try:
        from sciforge import browser_ui, doc_epoch, timeline_ui

        key = doc_epoch.key()
        if key is None:
            return found
        for name, panel, holds in (
            ("browser", browser_ui.widget(), ("_busy", "_renaming")),
            ("timeline", timeline_ui.widget(), ("_busy", "_drag", "_editor")),
        ):
            if panel is None or not _alive(panel):
                continue
            timer, gate = getattr(panel, "_timer", None), getattr(panel, "_gate", None)
            if gate is None or timer is None or not timer.isActive():
                continue
            if any(getattr(panel, attr, None) not in (None, False) for attr in holds):
                continue
            if gate.key != key:
                found.append(name)
    except Exception:
        pass
    try:
        # The RESULTS view follows the bodies' eyes on its own tick (every 6th of 70 ms):
        # hiding a body shows the results inside it only then (simres_workspace).
        from sciforge import simulation_results_ui

        session = simulation_results_ui.current()
        timer = getattr(session, "_timer", None)
        if session is not None and timer is not None and timer.isActive():
            if session._shown_key != session._visibility_key():
                found.append("simulation results view")
    except Exception:
        pass
    return found


def seen_now():
    """What the app shows now, for a failure message (rule 5)."""
    app = QtWidgets.QApplication
    parts = []
    try:
        pos = QtGui.QCursor.pos()
        told = _pointer.last
        parts.append(
            "pointer at %d, %d over %s (Qt was last told %s)"
            % (
                pos.x(),
                pos.y(),
                describe(app.widgetAt(pos)),
                "%d, %d" % (told.x(), told.y()) if told is not None else "nothing",
            )
        )
        parts.append("open menu: %s" % describe(app.activePopupWidget()))
        parts.append("modal: %s" % describe(app.activeModalWidget()))
        parts.append("dialogs: %s" % (popups() or "none"))
        parts.append("focus: %s" % describe(app.focusWidget()))
    except Exception as exc:
        parts.append("widgets: %s" % exc)
    try:
        task = Gui.Control.activeDialog()
        parts.append("task panel: %s" % ("open" if task else "none"))
    except Exception:
        pass
    try:
        docs = [
            "%s%s" % (d.Name, " (recomputing)" if getattr(d, "Recomputing", False) else "")
            for d in App.listDocuments().values()
        ]
        parts.append("designs: %s" % (", ".join(docs) or "none"))
        edit = Gui.ActiveDocument.getInEdit() if Gui.ActiveDocument else None
        if edit is not None:
            parts.append("editing %s" % edit.Object.Name)
    except Exception:
        pass
    parts.append("busy: %s" % ("; ".join(busy()) or "no"))
    return "; ".join(parts)


def close_modals():
    """Close open menus and modal dialogs, so a scenario that failed ends in seconds instead of
    waiting in a dialog for the 15-minute kill (CI #283)."""
    app = QtWidgets.QApplication
    for _ in range(10):
        popup = app.activePopupWidget()
        if popup is None:
            break
        popup.close()
    for _ in range(10):
        modal = app.activeModalWidget()
        if modal is None:
            break
        if isinstance(modal, QtWidgets.QDialog):
            modal.reject()
        else:
            modal.close()
        app.processEvents()
    close_popups()


def _timed_out(what, limit, error=None):
    detail = "not after %.0f s; seen: %s" % (limit, seen_now())
    if error is not None:
        detail += "; reading the condition raised %r" % (error,)
    check("Waited for %s" % what, False, detail)
    print("[SciForge] %s: waited %.0f s for %s" % (state["name"], limit, what), flush=True)
    try:
        shot("timeout-" + what[:40])
    except Exception:
        pass
    state["stop"] = state.get("stop") or "waited for %s" % what
    close_modals()


def wait_for(condition, what, timeout_s=None):
    """Keep the app running until condition() is true; True then (rule 1: wait for state,
    never for time). `what` names the state, as a person would ("the Offset dialog is
    open"). A condition that raises is not true yet. After timeout_s (default WAIT_S; only a
    hang gets there) the check "Waited for <what>" fails with what was seen instead and a
    screenshot, open menus and modal dialogs are closed, and WaitTimeout is raised: the
    scenario stops after this step."""
    limit = WAIT_S if timeout_s is None else timeout_s
    end = time.monotonic() + limit
    error = None
    while True:
        try:
            if condition():
                return True
        except Exception as exc:
            error = exc
        if time.monotonic() >= end:
            break
        QtTest.QTest.qWait(POLL_MS)  # wait primitive: the event loop runs while it polls
    _timed_out(what, limit, error)
    raise WaitTimeout(what)


def _calm(ignore_input=False):
    """A condition that is true once the app has been quiet twice in a row (work that runs
    can post more). ignore_input: input still being played (a held drag asking whether the
    app has caught up with it) does not count."""
    quiet = {"n": 0}
    since = time.monotonic()

    def calm():
        reasons = busy(since)
        if ignore_input:
            reasons = [r for r in reasons if not r.startswith("input still being played")]
        quiet["n"] = 0 if reasons else quiet["n"] + 1
        return quiet["n"] >= 2

    return calm


def settle(what="the app to settle", timeout_s=None):
    """Wait until the app has finished what the last input set going (see busy())."""
    return wait_for(_calm(), what, timeout_s)


def caught_up(panel=None, what="the dialog's preview to catch up", extra=None):
    """Wait until a dialog's preview has caught up with the last input: its own preview timer
    done, nothing pending, no design recomputing (and extra() false: a dialog's own "still
    computing"), then the app settled. A closed dialog or none: only the settling."""

    def ready():
        if panel is not None and not getattr(panel, "_closed", False):
            timer = getattr(panel, "_timer", None)
            try:
                if timer is not None and timer.isSingleShot() and timer.isActive():
                    return False
            except RuntimeError:
                pass
            if getattr(panel, "_pending", False):
                return False
        if extra is not None and extra():
            return False
        return not _recomputing()

    wait_for(ready, what)
    return settle(what)


def when(condition, action, what, timeout_s=None):
    """Run action() once condition() holds, without blocking: for input into something
    that opens and runs its own loop (a menu, a modal dialog), set up before the call that
    opens it. After timeout_s: the failure as in wait_for, the menu or dialog closed."""
    limit = WAIT_S if timeout_s is None else timeout_s
    end = time.monotonic() + limit
    box = {"error": None, "cancelled": False}

    def look():
        if box["cancelled"]:
            return
        try:
            ok = condition()
        except Exception as exc:
            ok, box["error"] = False, exc
        if ok:
            try:
                action()
            except WaitTimeout:
                pass
            except Exception:
                check("No exception in the action after %s" % what, False, traceback.format_exc())
                close_modals()
        elif time.monotonic() >= end:
            _timed_out(what, limit, box["error"])
        else:
            _later(POLL_MS, look)

    _later(0, look)
    return box  # box["cancelled"] = True: never mind


# -- menus --------------------------------------------------------------------------
def entry_text(action):
    """A menu entry's words (no & mnemonic, no Tab and shortcut)."""
    return action.text().split("\t")[0].replace("&", "").strip()


def entries(menu):
    return [a for a in menu.actions() if not a.isSeparator()]


def find_entry(menu, label):
    """The entry of `menu` called `label` (a QAction is looked up as itself), or None."""
    for action in entries(menu):
        if isinstance(label, QtGui.QAction):
            if action is label:
                return action
        elif entry_text(action) == label or action.text().split("\t")[0] == label:
            return action
    return None


def submenu(menu, action):
    """The submenu an entry opens. (PySide's QAction.menu() can hand back a wrapper that
    deletes the submenu when it is dropped, so it is looked for among the menu's children.)"""
    subs = menu.findChildren(QtWidgets.QMenu)
    for sub in subs:
        try:
            if sub.menuAction() is action:
                return sub
        except RuntimeError:
            pass
    for sub in subs:
        if sub.title().replace("&", "").strip() == entry_text(action):
            return sub
    return action.menu()


def open_menu():
    """The innermost menu open on screen, or None."""
    popup = QtWidgets.QApplication.activePopupWidget()
    return popup if isinstance(popup, QtWidgets.QMenu) and popup.isVisible() else None


def close_menus():
    """Esc on every open menu, innermost first (as a person backs out)."""
    for _ in range(6):
        popup = QtWidgets.QApplication.activePopupWidget()
        if popup is None:
            return
        QtTest.QTest.keyClick(popup, QtCore.Qt.Key_Escape)


def light_entry(menu, action):
    """The pointer onto `action` until the open menu has lit it, every move seen by Qt
    first. A menu takes a click only on the entry it has lit, lights one only on a move it
    was told about, and ignores the first six moves near where it opened; so the pointer
    comes from a neighbouring pixel, and again, at most 8 times, before the wait."""
    for i in range(8):
        centre = menu.actionGeometry(action).center()
        side = 1 if i % 2 else -1
        pointer_to(menu, QtCore.QPoint(centre.x() + 3 * side, centre.y() - 2 * side))
        pointer_to(menu, centre)
        if menu.activeAction() is action:
            return True
    return wait_for(lambda: menu.activeAction() is action, "the menu to light %s" % entry_text(action))


def choose_path(menu, path, report=True):
    """With `menu` open, click through `path` (labels or QActions; a submenu opens when its
    entry is lit). True when the last entry was clicked. An entry missing or greyed out:
    every menu closed and False (and a failed check, unless report=False)."""
    for i, label in enumerate(path):
        action = find_entry(menu, label)
        if action is None or not action.isEnabled():
            if report:
                check(
                    "Menu entry %s is there and enabled"
                    % " > ".join(entry_text(p) if isinstance(p, QtGui.QAction) else p for p in path[: i + 1]),
                    False,
                    [(entry_text(a), a.isEnabled()) for a in entries(menu)],
                )
            close_menus()
            return False
        light_entry(menu, action)
        if i < len(path) - 1:
            sub = submenu(menu, action)
            wait_for(lambda: sub is not None and sub.isVisible(), "the submenu %s to open" % entry_text(action))
            menu = sub
            continue
        centre = menu.actionGeometry(action).center()
        QtTest.QTest.mouseClick(menu, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, centre)
        return True
    return False


def choose_from(open_it, path, what, report=True, read=None):
    """open_it() opens a menu (a button's, a right-click's; usually the menu runs its own
    loop until it closes), then the entries of `path` are clicked as in choose_path.
    read(menu), when given, sees the menu first (to list its entries); an empty path then
    closes the menu with Esc. True when the last entry was clicked. When open_it() opened
    no menu, once the app has settled: False (a failed check too when report)."""
    box = {"done": False, "ok": False}

    def pick():
        menu = open_menu()
        try:
            if read is not None:
                read(menu)
            if path:
                box["ok"] = choose_path(menu, path, report)
            else:
                close_menus()
        finally:
            box["done"] = True

    handle = when(lambda: open_menu() is not None, pick, what)
    try:
        open_it()
        if not box["done"]:
            # a menu that opens without a loop of its own is picked from here; none opened
            # once the app has settled: there is none (an entry that set an animation going
            # is never waited for here: box["done"] holds by then)
            wait_for(
                lambda: box["done"] or bool(state.get("stop")) or (open_menu() is None and not busy()),
                what,
            )
            if not box["done"] and open_menu() is not None:
                wait_for(lambda: box["done"] or bool(state.get("stop")), what)
    finally:
        handle["cancelled"] = True
    if not box["done"] and report:
        check("%s opened" % what, False, seen_now())
    return box["ok"]


# -- the 3D view ------------------------------------------------------------------
def gl_widget():
    area = Gui.getMainWindow().findChild(QtWidgets.QMdiArea)
    sub = area.activeSubWindow() or area.subWindowList()[-1]
    return [
        w
        for w in sub.findChildren(QtWidgets.QWidget)
        if w.metaObject().className() == "QOpenGLWidget"
    ][0]


def view():
    return Gui.ActiveDocument.ActiveView


def screen_point(point):
    """Widget pixel of a 3D point (Qt's y axis points down, Coin's up)."""
    widget = gl_widget()
    x, y = view().getPointOnViewport(point)
    ratio = widget.devicePixelRatioF()
    return QtCore.QPoint(int(x / ratio), int(widget.height() - y / ratio))


def move(pos):
    """The pointer onto widget pixel `pos` of the 3D view (always a move, as a hand comes
    onto what it clicks), seen by Qt before anything else."""
    pointer_to(gl_widget(), pos, fresh=True)


def view_drawn(what="the 3D view to draw what is under the pointer"):
    """Wait until the 3D view has drawn a frame from now on (one is asked for). FreeCAD's
    sketch finds what is under the pointer when it redraws after a move: a press before
    that frame found nothing (the pause a hand makes before pressing)."""
    widget = gl_widget()
    box = {"frames": 0}

    def frame():
        box["frames"] += 1

    widget.frameSwapped.connect(frame)
    try:
        widget.update()
        wait_for(lambda: box["frames"] > 0, what)
    finally:
        try:
            widget.frameSwapped.disconnect(frame)
        except Exception:
            pass


AIM = 6  # click_edge looks this many pixels around the point for the edge


def covered(pos):
    """The widget over the 3D view at widget pixel `pos` (a command dialog floats over the
    view and takes a click there), or None when the click reaches the view."""
    widget = gl_widget()
    top = QtWidgets.QApplication.widgetAt(widget.mapToGlobal(pos))
    return None if top is None or top is widget else top


def pan(dx, dy):
    """Slide what the view shows by (dx, dy) widget pixels, as a person pans."""
    widget = gl_widget()
    ratio = widget.devicePixelRatioF()
    cx, cy = widget.width() / 2.0, widget.height() / 2.0
    a = view().getPoint(int(cx * ratio), int((widget.height() - cy) * ratio))
    b = view().getPoint(int((cx + dx) * ratio), int((widget.height() - cy - dy) * ratio))
    camera = view().getCameraNode()
    p = camera.position.getValue()
    shift = App.Vector(*a) - App.Vector(*b)
    camera.position.setValue(p[0] + shift.x, p[1] + shift.y, p[2] + shift.z)
    QtWidgets.QApplication.processEvents()


def uncover(point):
    """Like a person whose target is under the command dialog: pan the view until the 3D
    point is clear of it (the dialog's width depends on the machine's fonts; on GitHub's
    runner it covered a box corner the local run could click). Only a covered point pans:
    a pan changes the view for the rest of the scenario (CI #142: panning when a dialog was
    merely near moved later clicks of sweep_loft_qa_web and pi5_case). True when it
    panned."""
    widget = gl_widget()
    pos = screen_point(point)
    if not covered(pos):
        return False
    margin = 30
    for step in range(1, 40):
        for dx, dy in ((-1, 0), (0, 1), (0, -1), (1, 0)):
            target = QtCore.QPoint(pos.x() + dx * 25 * step, pos.y() + dy * 25 * step)
            inside = margin < target.x() < widget.width() - margin
            inside = inside and margin < target.y() < widget.height() - margin
            if inside and not covered(target):
                pan(target.x() - pos.x(), target.y() - pos.y())
                print(
                    "[SciForge] %s: %s was under %s; panned the view %+d, %+d px"
                    % (
                        state.get("name"),
                        tuple(round(c, 3) for c in point),
                        covered(pos).metaObject().className() if covered(pos) else "a widget",
                        target.x() - pos.x(),
                        target.y() - pos.y(),
                    ),
                    flush=True,
                )
                return True
    return False


def click_context(pos):
    """What a click at widget pixel `pos` met, for failure messages: the widget on top
    there (a dialog floating over the view takes the click before the 3D view does), the
    view's size and what FreeCAD picks at that very pixel. A pick that differs from the
    pixel searched (another renderer, a moved camera) shows up here."""
    widget = gl_widget()
    try:
        top = QtWidgets.QApplication.widgetAt(widget.mapToGlobal(pos))
        on_top = "3D view" if top is widget else (top.metaObject().className() if top else None)
        ratio = widget.devicePixelRatioF()
        info = view().getObjectInfo((pos.x() * ratio, (widget.height() - pos.y()) * ratio))
        picked = info and (info.get("Object"), info.get("Component"))
        return "on top: %s; view %dx%d (Coin %s); picked there: %s" % (
            on_top,
            widget.width(),
            widget.height(),
            tuple(view().getSize()),
            picked,
        )
    except Exception as exc:
        return "click context: %s" % exc


def under_mouse(point):
    info = view().getObjectInfo(view().getPointOnViewport(point))
    return info and (info.get("Object"), info.get("Component"))


def click(point, modifiers=QtCore.Qt.NoModifier, button=QtCore.Qt.LeftButton):
    """Click on the 3D point; remembers what was under the mouse and what got selected."""
    uncover(point)
    pos = screen_point(point)
    press_pace()  # (before the move: the press follows the move at once)
    move(pos)
    hit = under_mouse(point)
    QtTest.QTest.mouseClick(gl_widget(), button, modifiers, pos)
    QtWidgets.QApplication.processEvents()
    selected = [(s.ObjectName, s.SubElementNames) for s in Gui.Selection.getSelectionEx()]
    state["last_click"] = "under mouse: %s; selected: %s; %s" % (hit, selected, click_context(pos))
    return hit


def click_edge(point, modifiers=QtCore.Qt.NoModifier):
    """Click an edge at a 3D point on it. Edges are a few pixels wide and renderers round
    differently (the CI's software OpenGL picked the face next to an outline edge), so,
    like a person aiming until the edge lights up, try the pixels around the point and
    click the nearest one where an edge is under the mouse."""
    uncover(point)
    widget = gl_widget()
    ratio = widget.devicePixelRatioF()
    centre = screen_point(point)
    best = None
    for radius in range(0, AIM + 1):
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                if max(abs(dx), abs(dy)) != radius:
                    continue
                qx, qy = centre.x() + dx, centre.y() + dy
                info = view().getObjectInfo((qx * ratio, (widget.height() - qy) * ratio))
                if info and str(info.get("Component", "")).startswith("Edge"):
                    best = QtCore.QPoint(qx, qy)
                    break
            if best is not None:
                break
        if best is not None:
            break
    pos = best or centre
    press_pace()
    move(pos)
    QtTest.QTest.mouseClick(widget, QtCore.Qt.LeftButton, modifiers, pos)
    QtWidgets.QApplication.processEvents()
    selected = [(s.ObjectName, s.SubElementNames) for s in Gui.Selection.getSelectionEx()]
    state["last_click"] = "edge click %s (found: %s); selected: %s; %s" % (
        (pos.x(), pos.y()),
        best is not None,
        selected,
        click_context(pos),
    )
    return best is not None


def ensure_also_selected(point):
    """After a Ctrl+click meant to add the edge at `point` to the selection: if the click
    replaced the selection instead, add that edge directly and say so. GitHub's runner
    drops the Ctrl of synthesized clicks (it works on a desktop and in the local xvfb),
    and the scenario is about what the command does with a two-edge selection."""
    selected = Gui.Selection.getSelectionEx()
    if sum(len(x.SubElementNames) for x in selected) >= 2:
        return
    tip = body().Tip if body() is not None else None
    if tip is None:
        return
    import Part

    probe = Part.Vertex(point)
    for i, edge in enumerate(tip.Shape.Edges, start=1):
        if edge.distToShape(probe)[0] < 1e-6:
            Gui.Selection.addSelection(App.ActiveDocument.Name, tip.Name, "Edge%d" % i)
            print(
                "[SciForge] %s: Ctrl+click did not add Edge%d here; added directly"
                % (state["name"], i),
                flush=True,
            )
            return


def _empty_spot(widget):
    """A spot of the 3D view with nothing under it: the top left corner first (a big
    construction plane can reach into it when the view is framed tightly)."""
    w, hgt = widget.width(), widget.height()
    ratio = widget.devicePixelRatioF()
    for x, y in ((15, 15), (15, hgt // 2), (w // 3, 15), (15, hgt - 80), (w // 2, 15)):
        pos = QtCore.QPoint(x, y)
        try:
            if covered(pos):
                continue
            if not view().getObjectInfo((x * ratio, (hgt - y) * ratio)):
                return pos
        except Exception:
            break
    return QtCore.QPoint(15, 15)


def click_empty():
    """Click on empty background (clears the selection, like in Fusion)."""
    widget = gl_widget()
    pos = _empty_spot(widget)
    press_pace()
    move(pos)
    QtTest.QTest.mouseClick(widget, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, pos)
    QtWidgets.QApplication.processEvents()


def double_click(point):
    pos = screen_point(point)
    press_pace()
    move(pos)
    QtTest.QTest.mouseDClick(gl_widget(), QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, pos)
    QtWidgets.QApplication.processEvents()


def drag(
    start,
    end,
    steps=12,
    button=QtCore.Qt.LeftButton,
    modifiers=QtCore.Qt.NoModifier,
):
    """Press, move and release a mouse button (left by default; Shift + middle orbits),
    start/end in widget pixels."""
    widget = gl_widget()
    press_pace()
    move(start)
    QtTest.QTest.mousePress(widget, button, modifiers, start)
    for i in range(1, steps + 1):
        pos = QtCore.QPointF(
            start.x() + (end.x() - start.x()) * i / steps,
            start.y() + (end.y() - start.y()) * i / steps,
        )
        event = QtGui.QMouseEvent(
            QtCore.QEvent.MouseMove,
            pos,
            QtCore.QPointF(widget.mapToGlobal(pos.toPoint())),
            QtCore.Qt.NoButton,
            button,
            modifiers,
        )
        QtWidgets.QApplication.sendEvent(widget, event)
        QtWidgets.QApplication.processEvents()
    QtTest.QTest.mouseRelease(widget, button, modifiers, end)
    QtWidgets.QApplication.processEvents()


def drag_points(a, b):
    """Drag from 3D point a to 3D point b."""
    drag(screen_point(a), screen_point(b))


def press(key, modifiers=QtCore.Qt.NoModifier):
    """A key press on the 3D view. key: a Qt.Key or a one-letter string."""
    widget = gl_widget()
    widget.setFocus()
    if isinstance(key, str):
        QtTest.QTest.keyClicks(widget, key, modifiers)
    else:
        QtTest.QTest.keyClick(widget, key, modifiers)
    QtWidgets.QApplication.processEvents()


# input still being played over several timer ticks (arrow_input.HeldDrag): the next step
# waits for it to end
BUSY = set()


def fit(iso=True):
    if iso:
        view().viewIsometric()
    view().fitAll()
    QtWidgets.QApplication.processEvents()


# -- ribbon and dialogs -----------------------------------------------------------
def ribbon_buttons():
    from sciforge import shell

    ribbon = shell.ribbon()
    if ribbon is None:
        return []
    return [b for b in ribbon.findChildren(QtWidgets.QToolButton) if b.isVisible()]


def document_tabs():
    """The document tabs a person sees: SciForge's at the top (FreeCAD's own bar under the 3D
    view is hidden while SciForge is on), or FreeCAD's when SciForge is off."""
    try:
        from sciforge import shell

        ribbon = shell.ribbon()
        tabs = getattr(ribbon, "doc_tabs", None) if ribbon is not None else None
        if tabs is not None and tabs.isVisible():
            tabs.sync()
            return tabs
    except Exception:
        pass
    area = Gui.getMainWindow().findChild(QtWidgets.QMdiArea)
    return area.findChild(QtWidgets.QTabBar) if area is not None else None


def ribbon(label):
    """Click the big ribbon button with this label (as the user would)."""
    name = "SciForgeBig_" + label.replace(" ", "_")
    for button in ribbon_buttons():
        if button.objectName() == name:
            button.click()
            QtWidgets.QApplication.processEvents()
            return True
    check("Ribbon button %r exists" % label, False, [b.objectName() for b in ribbon_buttons()])
    return False


def task_button(text):
    """Click OK / Cancel / Close in the task panel (as the user would)."""
    main = Gui.getMainWindow()
    for button in main.findChildren(QtWidgets.QPushButton):
        if button.isVisible() and button.text().replace("&", "").strip() == text:
            button.click()
            QtWidgets.QApplication.processEvents()
            return True
    check("Task panel button %r exists" % text, False)
    return False


def popups():
    return [
        w.windowTitle() or w.metaObject().className()
        for w in QtWidgets.QApplication.topLevelWidgets()
        if w.isVisible() and isinstance(w, (QtWidgets.QDialog, QtWidgets.QMessageBox))
    ]


def close_popups():
    for w in QtWidgets.QApplication.topLevelWidgets():
        if w.isVisible() and isinstance(w, QtWidgets.QDialog):
            w.reject()


def in_sketch():
    edit = Gui.ActiveDocument.getInEdit() if Gui.ActiveDocument else None
    obj = edit.Object if edit is not None else None
    return obj if obj is not None and obj.TypeId == "Sketcher::SketchObject" else None


def body():
    from sciforge import commands

    return commands.find_body()


def solid_volume():
    b = body()
    if b is None or b.Shape.isNull():
        return 0.0
    try:
        return b.Shape.Volume
    except Exception:
        return 0.0


def body_visible():
    b = body()
    return b is not None and b.ViewObject.Visibility and not b.Shape.isNull()


def draw_rectangle(sketch, x0, y0, x1, y1):
    """Rectangle in sketch coordinates with Fusion's constraints (coincident, h/v)."""
    import Part
    import Sketcher

    pts = [
        App.Vector(x0, y0, 0),
        App.Vector(x1, y0, 0),
        App.Vector(x1, y1, 0),
        App.Vector(x0, y1, 0),
    ]
    first = sketch.GeometryCount
    for i in range(4):
        sketch.addGeometry(Part.LineSegment(pts[i], pts[(i + 1) % 4]))
    for i in range(4):
        sketch.addConstraint(
            Sketcher.Constraint("Coincident", first + i, 2, first + (i + 1) % 4, 1)
        )
    sketch.addConstraint(Sketcher.Constraint("Horizontal", first))
    sketch.addConstraint(Sketcher.Constraint("Horizontal", first + 2))
    sketch.addConstraint(Sketcher.Constraint("Vertical", first + 1))
    sketch.addConstraint(Sketcher.Constraint("Vertical", first + 3))
    App.ActiveDocument.recompute()


def draw_circle(sketch, cx, cy, r):
    import Part

    sketch.addGeometry(Part.Circle(App.Vector(cx, cy, 0), App.Vector(0, 0, 1), r))
    App.ActiveDocument.recompute()


def to_sketch(sketch, point):
    """Global 3D point -> sketch coordinates (x, y)."""
    local = sketch.getGlobalPlacement().inverse().multVec(point)
    return local.x, local.y


# -- running ----------------------------------------------------------------------
def _write(partial):
    name = state["name"]
    result = {
        "name": name,
        "file": os.environ.get("SCIFORGE_SCENARIO", name),
        "passed": (not partial) and all(c["ok"] for c in checks),
        "finished": not partial,
        "paced_by": state.get("paced_by"),
        "step": state.get("step"),
        "checks": checks,
    }
    if state.get("stop"):
        result["stopped"] = state["stop"]
        result["not_run"] = state.get("not_run", [])
    with open(os.path.join(OUT_DIR, "%s-result.json" % name), "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)


def _finish():
    name = state["name"]
    state["finished"] = True
    leftovers = new_errors()
    check("No errors at the end", not leftovers, leftovers)
    _write(partial=False)
    for c in checks:
        App.Console.PrintMessage(
            "[SciForge] %s %s: %s %s\n"
            % (name, "PASS" if c["ok"] else "FAIL", c["name"], "" if c["ok"] else c["detail"])
        )
    try:
        from sciforge import commands

        commands.leave_edit()
    except Exception:
        pass
    for doc in list(App.listDocuments()):
        App.closeDocument(doc)
    # quit once what closing the designs set going has run (at most 10 s: the result is
    # written already)
    calm, end = _calm(), time.monotonic() + 10

    def quit_when_calm():
        if calm() or time.monotonic() > end:
            QtWidgets.QApplication.instance().quit()
        else:
            _later(POLL_MS, quit_when_calm)

    _later(0, quit_when_calm)


def _last_resort():
    """A thread that ends FreeCAD when the event loop itself is stuck (a step that never
    returns to Qt, so _watchdog's timer cannot run): the stacks of every thread go to the
    log and the result is written, instead of the runner's kill 15 minutes later."""
    import faulthandler
    import sys
    import threading

    def watch():
        while not state.get("finished"):
            time.sleep(5)  # wait primitive: a thread of its own, it delays nothing in the app
            started = state.get("in_step")
            limit = state.get("step_limit", STEP_LIMIT_S) + 60
            idle = time.monotonic() - state.get("alive", time.monotonic())
            if (started is not None and time.monotonic() - started > limit) or idle > limit:
                print(
                    "[SciForge] %s: the app has not come back to the test for %.0f s (step %s);"
                    " every thread's stack:" % (state["name"], limit, state.get("step")),
                    flush=True,
                )
                faulthandler.dump_traceback(file=sys.stdout, all_threads=True)
                checks.append(
                    {
                        "name": "Step %s returned to the app within %.0f s" % (state.get("step"), limit),
                        "ok": False,
                        "detail": "the event loop was stuck; stacks in the log",
                        "step": state.get("step"),
                    }
                )
                state["stop"] = state.get("stop") or "the app was stuck in %s" % state.get("step")
                try:
                    _write(partial=False)
                finally:
                    os._exit(4)

    threading.Thread(target=watch, name="SciForge test watchdog", daemon=True).start()


def idle_step(name="wait_idle", tries=40):
    """A step that waits until no design is recomputing. A long recompute (an Undo that
    brings bodies and analyses back) lets Qt run the next step from inside it, where a menu
    click or a key is lost."""

    def step():
        pass

    step.__name__ = name
    step.done = lambda: not _recomputing()
    step.done_what = "no design recomputing"
    return step


def _recomputing():
    try:
        return any(getattr(d, "Recomputing", False) for d in App.listDocuments().values())
    except Exception:
        return False


def _searching():
    """A dialog still looking for the largest value that fits, one build per turn of the
    event loop (sciforge.value_limits.Background), or about to preview what it found: the
    next step waits for it, as for a recompute."""
    try:
        from sciforge import value_limits

        return value_limits.working()
    except Exception:
        return False


def add_steps(steps):
    """Append steps while running (e.g. one per command found at start-up)."""
    state["queue"].extend(steps)


def _condition_name(condition):
    doc = (getattr(condition, "__doc__", None) or "").strip()
    if doc and not doc.startswith("lambda"):
        return doc.splitlines()[0]
    name = getattr(condition, "__name__", "") or ""
    return "" if name == "<lambda>" else name.replace("_", " ")


def _wait_name(step, kind, condition):
    said = getattr(step, kind + "_what", None) or _condition_name(condition)
    return "%s (%s of %s)" % (said, kind, step.__name__) if said else "%s of %s" % (kind, step.__name__)


def _watchdog():
    """Ends a scenario whose step has not returned within STEP_LIMIT_S (a dialog waiting
    for an answer that never comes, a loop that never ends): the check says which step and
    what was on screen, the dialogs are closed so the step can return, and if it still has
    not after 20 s FreeCAD quits with the result written, well before the runner's kill."""
    started = state.get("in_step")
    if started is None or state.get("finished"):
        return
    step = state.get("step") or "?"
    limit = state.get("step_limit", STEP_LIMIT_S)
    now = time.monotonic()
    if not state.get("hung") and now - started > limit:
        state["hung"] = now
        check(
            "Step %s ended within %.0f s" % (step, limit),
            False,
            "still running (a hang?); seen: %s" % seen_now(),
        )
        print("[SciForge] %s: step %s still running after %.0f s" % (state["name"], step, limit), flush=True)
        try:
            shot("hang-" + step)
        except Exception:
            pass
        state["stop"] = state.get("stop") or "step %s did not end" % step
        state["not_run"] = [s.__name__ for s in state.get("queue", [])]
        close_modals()
    elif state.get("hung") and now - state["hung"] > 20:
        print("[SciForge] %s: step %s did not end after its dialogs were closed; quitting" % (state["name"], step), flush=True)
        state["finished"] = True
        _write(partial=False)
        os._exit(3)


def run(name, steps, check_errors_each_step=True, start_ms=2500, paced_by="timer"):
    """Run the steps one after another; errors are checked after every step.

    paced_by="state" (converted scenarios): no fixed waits. Each step's input waits for its
    `ready` and for the app to have settled; after it, the next step waits for its `done`
    and for the app to settle again. paced_by="timer" (not converted yet): a fixed
    `wait_ms` (default STEP_MS) after each step, then until nothing is recomputing, as
    before; a step of such a scenario that declares `done` is paced by state already."""
    global _tap
    state["name"] = name
    # SCIFORGE_PACED_BY=state tries a scenario not converted yet without its fixed waits
    # (converting one: which of its steps need a `done`?)
    paced_by = os.environ.get("SCIFORGE_PACED_BY") or paced_by
    state["paced_by"] = paced_by
    by_state = paced_by == "state"
    queue = state["queue"] = list(steps)

    def prepare():
        global _tap
        BUSY.clear()
        _install_pointer_tap()
        # FreeCAD animates camera moves; a click computed mid-animation misses.
        App.ParamGet("User parameter:BaseApp/Preferences/View").SetBool(
            "UseNavigationAnimations", False
        )
        # Each scenario starts in a fresh FreeCAD profile (run_tests.sh), so the choices
        # SciForge remembers between sessions (selection mode, display style, preferences,
        # keys, pins) are the defaults already: no reset needed for them.
        try:  # the first-start welcome line on Home shows once per profile: a fresh profile
            # would show it in every scenario (the welcome_line scenario asks for it)
            from sciforge import home_notices_ui

            home_notices_ui.reset_for_tests(True)
        except Exception as exc:
            print("[SciForge] welcome line reset failed: %s" % exc, flush=True)
        _tap = _ConsoleTap()
        new_errors()  # start-up messages are not the scenario's
        watchdog = state["watchdog"] = QtCore.QTimer()
        _posted.own.add(id(watchdog))
        watchdog.setInterval(1000)
        watchdog.timeout.connect(_watchdog)
        _START(watchdog)

    def poll_until(condition, what, timeout_s, then):
        """then() once condition() holds; after timeout_s the failure (rule 5), the scenario
        stopped, then() all the same (it sees state["stop"])."""
        end = time.monotonic() + timeout_s
        box = {"error": None}

        def look():
            state["alive"] = time.monotonic()
            try:
                ok = condition()
            except Exception as exc:
                ok, box["error"] = False, exc
            if ok:
                then()
            elif time.monotonic() >= end:
                _timed_out(what, timeout_s, box["error"])
                then()
            else:
                _later(POLL_MS, look)

        look()

    def stopped():
        left = [s.__name__ for s in queue]
        queue.clear()
        state["not_run"] = state.get("not_run") or left
        print(
            "[SciForge] %s stopped (%s); %d steps not run"
            % (state["name"], state["stop"], len(state["not_run"])),
            flush=True,
        )
        _finish()

    def next_step():
        if state.get("stop"):
            stopped()
            return
        if not queue:
            _finish()
            return
        if not by_state:
            # A long recompute keeps the GUI alive by running Qt's event loop from inside
            # it, so this timer can fire in the middle of it; FreeCAD's progress handling
            # then throws away every click and key the step sends (a drop-down that would
            # not open, a typed value lost). Wait until the document is done (at most 20 s),
            # and until input still being played (a held drag, BUSY) has ended: on a slow
            # machine it can outlast the step's wait_ms.
            if (_recomputing() or BUSY or _searching()) and state.get("waited", 0) < 200:
                state["waited"] = state.get("waited", 0) + 1
                state["held"] = state.get("held") or bool(BUSY)
                _later(100, next_step)
                return
            state["waited"] = 0
            BUSY.clear()  # ended, or given up on after 20 s
            if state.pop("held", False):
                # a drag that outlasted its step: what follows the release (the dialog's
                # own timers) gets the second the step's wait_ms would have given it
                _later(1000, next_step)
                return
        step = queue.pop(0)
        state["step"] = step.__name__
        limit = getattr(step, "timeout_s", WAIT_S)
        ready = getattr(step, "ready", None)
        if (by_state or ready is not None) and getattr(step, "while_busy", False):
            # a step that acts while something plays on purpose (an animation, a solve):
            # only its own precondition
            first = ready if ready is not None else (lambda: True)
            poll_until(first, _wait_name(step, "ready", ready) if ready else "nothing", limit,
                       lambda: perform(step))
        elif by_state or ready is not None:
            # the app settled after the step before, then the step's own precondition
            calm = _calm()
            first = (lambda: calm() and ready()) if ready is not None else calm
            poll_until(first, _wait_name(step, "ready", ready) if ready else
                       "the app to settle before %s" % step.__name__, limit,
                       lambda: perform(step))
        else:
            perform(step)

    def perform(step):
        if state.get("stop"):
            stopped()
            return
        # Progress on stdout and a partial result: a crash still shows where it happened.
        print(
            "[SciForge] %s step: %s (%.1f s)"
            % (state["name"], step.__name__, time.monotonic() - state["t0"]),
            flush=True,
        )
        _write(partial=True)
        state["in_step"] = state["alive"] = time.monotonic()
        state["step_limit"] = max(STEP_LIMIT_S, getattr(step, "timeout_s", 0) * 2)
        try:
            step()
        except WaitTimeout:
            pass  # (the failed check is recorded; the scenario stops)
        except Exception:
            check("No exception in %s" % step.__name__, False, traceback.format_exc())
        finally:
            state["in_step"] = None
            state["alive"] = time.monotonic()
        if state.get("stop"):
            errors_then_next(step)
            return
        done = getattr(step, "done", None)
        limit = getattr(step, "timeout_s", WAIT_S)
        if done is not None:
            poll_until(done, _wait_name(step, "done", done), limit, lambda: settled(step))
        elif by_state:
            settled(step)
        else:
            _later(getattr(step, "wait_ms", STEP_MS), lambda: errors_then_next(step))

    def settled(step):
        if state.get("stop") or getattr(step, "while_busy", False):
            errors_then_next(step)
            return
        poll_until(
            _calm(),
            "the app to settle after %s" % step.__name__,
            getattr(step, "timeout_s", WAIT_S),
            lambda: errors_then_next(step),
        )

    def errors_then_next(step):
        if check_errors_each_step:
            fresh = new_errors()
            if fresh and getattr(step, "known", False):
                # A known problem being fixed elsewhere: report it, do not fail. (The note
                # goes to the Report view too, so it must not look like an error line.)
                print(
                    "[SciForge] %s: known issue after %s (%d lines, see KNOWN)"
                    % (state["name"], step.__name__, len(fresh)),
                    flush=True,
                )
                new_errors()
            elif fresh:
                check("No errors after %s" % step.__name__, False, fresh)
                shot("error-" + step.__name__)
        next_step()

    def started():
        """FreeCAD's window is up and SciForge's start-up has run."""
        main = Gui.getMainWindow()
        return main is not None and main.isVisible() and not busy()

    def begin():
        state["t0"] = state["alive"] = time.monotonic()
        prepare()
        _last_resort()
        next_step()

    if by_state:
        _later(0, lambda: poll_until(started, "FreeCAD to start", 120, begin))
    else:
        _later(start_ms, begin)
