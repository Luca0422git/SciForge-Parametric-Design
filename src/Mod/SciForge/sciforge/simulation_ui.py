# SPDX-License-Identifier: LGPL-2.1-or-later
"""Fusion's SIMULATION workspace (Static Stress): entering and leaving it, its SETUP tab's
commands and dialogs. Owner: builder sim-ui (beta 3); the engine is simulation.py, the RESULTS
tab is simulation_results_ui.py (builder sim-results). Spec: docs/sciforge/parity/simulation.md.

Scaffold (orchestrator): the workspace switch only. ribbon_ui's workspace menu calls
enter_workspace() / leave_workspace(); RibbonWidget.set_simulation_mode shows the SETUP and
RESULTS tabs instead of the design's.
"""

from . import log, warn

STATE = {"on": False}


def _ribbon():
    try:
        from . import shell

        return shell.ribbon()
    except Exception:
        return None


def active():
    """True while the SIMULATION workspace is shown."""
    return bool(STATE["on"])


def enter_workspace(tab=None):
    try:
        ribbon = _ribbon()
        if ribbon is not None and hasattr(ribbon, "set_simulation_mode"):
            ribbon.set_simulation_mode(True, tab)
        STATE["on"] = True
        log("simulation workspace")
    except Exception as exc:
        warn("simulation workspace: %s" % exc)


def leave_workspace():
    try:
        if not STATE["on"]:
            return
        ribbon = _ribbon()
        if ribbon is not None and hasattr(ribbon, "set_simulation_mode"):
            ribbon.set_simulation_mode(False)
        STATE["on"] = False
        log("design workspace")
    except Exception as exc:
        warn("simulation workspace: %s" % exc)


COMMANDS = {}
