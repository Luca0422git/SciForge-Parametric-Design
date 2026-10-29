#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Counts the fixed waits left in the GUI tests, and fails when there are more than allowed.

    tools/sciforge/check_waits.py            the counts; exit 1 when one is over its allowance
    tools/sciforge/check_waits.py --list     also every place counted, file by file
    tools/sciforge/check_waits.py --update   write today's counts as the new allowance

A GUI scenario waits for the app's state, never for the clock (docs/sciforge/dev/gui-tests.md).
What still waits a fixed time, in src/Mod/SciForge/SciForgeTests/gui:
  - a step's wait_ms (`step.wait_ms = 1500`, or wait_ms passed to a function that sets it),
  - QTest.qWait(...), QTimer.singleShot(...) and time.sleep(...), and a call to a helper that
    only waits the time it is given (st.wait(600)),
  - a scenario still paced by timers: h.run(...) without paced_by="state" (each of its steps
    waits harness.STEP_MS).
A line may say why its timer is not a wait for the app, and is then not counted:
  "# wait primitive: ..." (the polling inside wait_for), "# input pace: ..." (input whose
  timing the app measures: a person's double-click, a hand's drag speed) or
  "# ... on purpose (the app under test)" (a deliberately slow part).

The allowance (tools/sciforge/check_waits.json) only goes down: lower it whenever a batch of
scenarios is converted (--update), until both numbers are zero.
"""

import ast
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GUI = os.path.join(REPO, "src", "Mod", "SciForge", "SciForgeTests", "gui")
ALLOWANCE = os.path.join(REPO, "tools", "sciforge", "check_waits.json")
EXEMPT = ("wait primitive", "input pace", "on purpose")
TIMER_CALLS = {"qWait", "singleShot", "sleep"}


def _files():
    for root, _dirs, names in os.walk(GUI):
        for name in sorted(names):
            if name.endswith(".py"):
                yield os.path.join(root, name)


def _call_name(node):
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _wait_ms_functions(trees):
    """{function name: position of its wait_ms parameter} for every function of the GUI
    tests that takes one (step factories such as step(fn, name, wait_ms=None))."""
    found = {}
    for tree in trees.values():
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                names = [a.arg for a in node.args.args]
                if "wait_ms" in names:
                    found[node.name] = names.index("wait_ms")
    return found


def _delay_functions(trees, lines):
    """Names of the helpers that only wait a time they are given (def wait(ms): qWait(ms)):
    a call to one is a fixed wait at the caller. (One whose timer line says why it is not a
    wait for the app, an input pace, is not.)"""
    found = set()
    for path, tree in trees.items():
        source = lines[path]
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            params = {a.arg for a in node.args.args}
            for inner in ast.walk(node):
                if (
                    isinstance(inner, ast.Call)
                    and _call_name(inner) in TIMER_CALLS
                    and inner.args
                    and isinstance(inner.args[0], ast.Name)
                    and inner.args[0].id in params
                    and not any(word in source[inner.lineno - 1] for word in EXEMPT)
                ):
                    found.add(node.name)
    return found


def _is_none(node):
    return isinstance(node, ast.Constant) and node.value is None


def count():
    trees, lines = {}, {}
    for path in _files():
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        trees[path] = ast.parse(text, path)
        lines[path] = text.splitlines()
    takes_wait = _wait_ms_functions(trees)
    delays = _delay_functions(trees, lines)
    waits, timer_paced = [], []
    for path, tree in trees.items():
        rel = os.path.relpath(path, REPO)
        source = lines[path]

        def exempt(node):
            line = source[node.lineno - 1] if node.lineno - 1 < len(source) else ""
            return any(word in line for word in EXEMPT)

        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Attribute) and target.attr == "wait_ms" and not exempt(node):
                        waits.append((rel, node.lineno, "wait_ms"))
            elif isinstance(node, ast.Call):
                name = _call_name(node)
                if name in TIMER_CALLS and not exempt(node):
                    waits.append((rel, node.lineno, name))
                elif (
                    name in delays
                    and (node.args or node.keywords)
                    and (isinstance(node.func, ast.Name) or isinstance(node.func.value, ast.Name))
                    and not exempt(node)
                ):
                    # (a module's helper: st.wait(600); not self.proc.wait(10))
                    waits.append((rel, node.lineno, "%s()" % name))
                elif name in takes_wait:
                    given = None
                    index = takes_wait[name]
                    if len(node.args) > index:
                        given = node.args[index]
                    for keyword in node.keywords:
                        if keyword.arg == "wait_ms":
                            given = keyword.value
                    if given is not None and not _is_none(given) and not exempt(node):
                        waits.append((rel, node.lineno, "%s(wait_ms)" % name))
                if (
                    name == "run"
                    and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id in ("h", "harness")
                    and "/scenarios/" in path.replace(os.sep, "/")
                ):
                    paced = [k for k in node.keywords if k.arg == "paced_by"]
                    if not (paced and isinstance(paced[0].value, ast.Constant) and paced[0].value.value == "state"):
                        timer_paced.append((rel, node.lineno, "timer-paced"))
    return waits, timer_paced


def main(argv):
    waits, timer_paced = count()
    counts = {"fixed_waits": len(waits), "timer_paced_scenarios": len(timer_paced)}
    if "--update" in argv:
        with open(ALLOWANCE, "w", encoding="utf-8") as handle:
            json.dump(counts, handle, indent=2)
            handle.write("\n")
        print("[SciForge] check_waits: allowance set to %s" % counts)
        return 0
    if "--list" in argv:
        per_file = {}
        for rel, line, kind in waits + timer_paced:
            per_file.setdefault(rel, []).append("%d %s" % (line, kind))
        for rel in sorted(per_file, key=lambda r: -len(per_file[r])):
            print("%4d  %s: %s" % (len(per_file[rel]), rel, ", ".join(per_file[rel][:12])))
    try:
        with open(ALLOWANCE, encoding="utf-8") as handle:
            allowed = json.load(handle)
    except (OSError, ValueError) as exc:
        print("[SciForge] check_waits: no allowance (%s); counts %s" % (exc, counts))
        return 1
    failed = False
    for key, value in counts.items():
        limit = allowed.get(key, 0)
        word = key.replace("_", " ")
        if value > limit:
            failed = True
            print(
                "::error title=Fixed waits in the GUI tests::%d %s, %d allowed: wait for the"
                " app's state instead (harness.wait_for, step.done; docs/sciforge/dev/gui-tests.md)."
                " tools/sciforge/check_waits.py --list shows where." % (value, word, limit)
            )
        elif value < limit:
            print(
                "[SciForge] check_waits: %d %s, %d allowed: lower the allowance"
                " (tools/sciforge/check_waits.py --update)" % (value, word, limit)
            )
        print("[SciForge] check_waits: %s %d (allowed %d)" % (word, value, limit))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
