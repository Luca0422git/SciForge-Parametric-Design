#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Reads one GUI scenario's result (run_tests.sh, after the scenario ran) and says what failed.

    scenario_result.py OUT NAME [--attempt LABEL]

Prints each failed check to the job log. On GitHub Actions also:
  - one ::error:: line per failed check (the run page and the failure email list them, so
    nobody has to download the test-output artifact to see which scenario broke and where);
  - a table of the failures in the job's summary ($GITHUB_STEP_SUMMARY).
Exit code 0 when the scenario passed, 1 when not.
"""

import glob
import json
import os
import sys

MAX_ANNOTATIONS = 6  # per scenario (GitHub shows 10 per step); the summary has them all


def _escape_data(text):
    """A workflow command's message: GitHub reads %, CR and LF as escapes."""
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _escape_property(text):
    return _escape_data(text).replace(":", "%3A").replace(",", "%2C")


def _cell(text, limit=400):
    text = " ".join(str(text).split())
    if len(text) > limit:
        text = text[: limit - 3] + "..."
    return text.replace("|", "\\|") or " "


def _summary(lines):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n\n")
    except OSError as exc:
        print("  (could not write the job summary: %s)" % exc)


def _log_tail(log, count=40):
    try:
        with open(log, encoding="utf-8", errors="replace") as handle:
            return handle.read().splitlines()[-count:]
    except OSError:
        return []


def main(argv):
    out, name = argv[1], argv[2]
    attempt = ""
    if "--attempt" in argv:
        attempt = argv[argv.index("--attempt") + 1]
    log = os.path.join(out, "scenario-%s.log" % name)
    on_ci = bool(os.environ.get("GITHUB_ACTIONS"))
    ok, found = True, False
    failures = []  # (step, check, detail)
    for path in sorted(glob.glob(os.path.join(out, "*-result.json"))):
        try:
            with open(path, encoding="utf-8") as handle:
                result = json.load(handle)
        except (OSError, ValueError):
            continue
        if result.get("file") != name:
            continue
        found = True
        for c in result["checks"]:
            if not c["ok"]:
                step = c.get("step") or "?"
                print("  FAIL %s [%s]: %s %s" % (result["name"], step, c["name"], c["detail"][:600]))
                failures.append((step, c["name"], c["detail"]))
        if result.get("stopped"):
            not_run = result.get("not_run") or []
            print(
                "  %s stopped early: %s (%d steps not run%s)"
                % (
                    result["name"],
                    result["stopped"],
                    len(not_run),
                    ": " + ", ".join(not_run[:8]) + (" ..." if len(not_run) > 8 else "")
                    if not_run
                    else "",
                )
            )
        if not result.get("finished"):
            last = result.get("step") or "?"
            print("  %s did not finish (crash or hang? last step %s; see %s)" % (result["name"], last, log))
            failures.append((last, "the scenario finished", "it did not (crash or hang); log %s" % os.path.basename(log)))
            # its last lines in the job's own log: a CI artifact cannot always be fetched
            for line in _log_tail(log):
                print("    | %s" % line[:300])
        ok = ok and bool(result.get("passed"))
        print(
            "  %s: %s (%d checks)"
            % (result["name"], "PASS" if result.get("passed") else "FAIL", len(result["checks"]))
        )
    if not found:
        print("  %s: no result (FreeCAD crashed before the first step? see %s)" % (name, log))
        failures.append(("start", "the scenario started", "no result file (crash before the first step?)"))
        ok = False
    if not ok and on_ci:
        label = name + (" (%s)" % attempt if attempt else "")
        for step, check, detail in failures[:MAX_ANNOTATIONS]:
            print(
                "::error title=%s::%s"
                % (
                    _escape_property("Scenario %s, step %s" % (label, step)),
                    _escape_data("%s: %s" % (check, " ".join(str(detail).split())[:900])),
                )
            )
        if len(failures) > MAX_ANNOTATIONS:
            print("::error title=%s::%s" % (_escape_property("Scenario %s" % label), _escape_data(
                "%d more failed checks: see the job summary" % (len(failures) - MAX_ANNOTATIONS))))
        rows = ["#### Scenario `%s` failed%s" % (name, " (%s)" % attempt if attempt else ""), "",
                "| Step | Check | What happened |", "|---|---|---|"]
        for step, check, detail in failures[:60]:
            rows.append("| %s | %s | %s |" % (_cell(step, 80), _cell(check, 160), _cell(detail)))
        if len(failures) > 60:
            rows.append("| | %d more | see the test-output artifact |" % (len(failures) - 60))
        _summary(rows)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
