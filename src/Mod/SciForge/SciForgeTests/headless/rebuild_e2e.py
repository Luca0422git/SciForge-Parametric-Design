# SPDX-License-Identifier: LGPL-2.1-or-later
"""Auto Timeline's proof (beta 3, builder at-tools): parts without a timeline rebuilt WITH a
timeline only through the AI tools, the way an AI does it.

For every part below: its golden model is built with the tools in a design of its own,
exported (STEP, or STL for the meshed plate), and brought into a new design with import_file:
a body without a timeline (or a mesh body). Then, only through the tools, as an AI would:
start_rebuild, describe_reference (the features and the plan), every plan step as its tool
call, compare_to_reference after them, and while it is not done, the calls compare's verdict
offers (groups[].fix / extra[].fix: a hole, a fillet of exactly those edges), compare again;
finish_rebuild. Required: match >= 0.999 with every face matched (done), the timeline holding
real steps (sketches, extrudes, holes, fillets... not one imported shape), check_design ok,
and an edit of one early value (the base extrude's distance, else the first hole's diameter)
rebuilding cleanly. Where a plan step fails, the report shows what the AI read in the answer.

Two ways to run it:

    freecadcmd -c "from SciForgeTests.headless import rebuild_e2e; rebuild_e2e.main()"
        every part, in-process (sciforge/ai/headless.py: the executor the AI bridge uses);
        writes rebuild-e2e-report.json / .md to SCIFORGE_HEADLESS_OUT
    python3 rebuild_e2e.py --mcp [--out DIR] [-- SERVER COMMAND...]
        one part through the real MCP server an AI app starts (tools/sciforge/sciforge-cli
        mcp --headless, as agent_e2e.py); writes rebuild-mcp-report.json / .md

tools/sciforge/run_tests.sh runs both with --only headless / base. SCIFORGE_REBUILD_FILTER
runs only the parts whose id contains that text. The agent below is plain Python: it reads
only the tools' answers (the in-process run adds nothing FreeCAD would tell it).
"""

import json
import os
import re
import sys
import tempfile
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
TOP = {"normal": [0, 0, 1], "at": {"axis": "z", "value": "max"}, "count": 1}


def c(tool, **args):
    return {"tool": tool, "args": args}


# -- the parts -------------------------------------------------------------------------------------
# Each: id, what it is, the golden model's calls (after new_design), the file kind.
PARTS = [
    {
        "id": "bracket",
        "title": "an L bracket with holes in both legs, an inside fillet and an outside chamfer",
        "file": "step",
        "calls": [
            c(
                "create_sketch",
                plane="YZ",
                geometry=[{"polyline": [[0, 0], [40, 0], [40, 5], [5, 5], [5, 40], [0, 40]]}],
            ),
            c("extrude", profile="Sketch1", distance=60),
            c(
                "fillet",
                edges={
                    "type": "line",
                    "parallel": [1, 0, 0],
                    "at": [{"axis": "y", "value": 5}, {"axis": "z", "value": 5}],
                    "count": 1,
                },
                radius=4,
            ),
            c(
                "chamfer",
                edges={
                    "type": "line",
                    "parallel": [1, 0, 0],
                    "at": [{"axis": "y", "value": "min"}, {"axis": "z", "value": "min"}],
                    "count": 1,
                },
                distance=2,
            ),
            c(
                "create_sketch",
                plane="XY",
                offset=5,
                geometry=[{"circle": [15, 25, 3.25]}, {"circle": [45, 25, 3.25]}],
            ),
            c("hole", sketch="Sketch2", diameter=6.5, through_all=True),
            c(
                "create_sketch",
                plane="XZ",
                geometry=[{"circle": [15, 28, 3.25]}, {"circle": [45, 28, 3.25]}],
            ),
            c("hole", sketch="Sketch3", diameter=6.5, through_all=True),
        ],
    },
    {
        "id": "hole_grid",
        "title": "a plate with a 4 x 3 grid of holes",
        "file": "step",
        "calls": [
            c("create_sketch", plane="XY", geometry=[{"rect": [0, 0, 80, 60]}]),
            c("extrude", profile="Sketch1", distance=8),
            c(
                "create_sketch",
                plane="XY",
                offset=8,
                geometry=[
                    {"circle": [10 + 20 * i, 10 + 20 * j, 2.5]} for i in range(4) for j in range(3)
                ],
            ),
            c("hole", sketch="Sketch2", diameter=5, through_all=True),
        ],
    },
    {
        "id": "flange",
        "title": "a turned flange with a hub, a bore and six bolt holes on a circle",
        "file": "step",
        "calls": [
            c(
                "create_sketch",
                plane="XZ",
                geometry=[{"polyline": [[10, 0], [50, 0], [50, 10], [20, 10], [20, 30], [10, 30]]}],
            ),
            c("revolve", profile="Sketch1", axis="Z"),
            c("create_sketch", plane="XY", offset=10, geometry=[{"circle": [35, 0, 1]}]),
            c("hole", sketch="Sketch2", diameter=9, through_all=True),
            c("circular_pattern", features=["Hole1"], axis="Z", quantity=6),
        ],
    },
    {
        "id": "knob",
        "title": "a revolved knob with a chamfered top and a blind bore from below",
        "file": "step",
        "calls": [
            c(
                "create_sketch",
                plane="XZ",
                geometry=[{"polyline": [[0, 0], [20, 0], [20, 12], [15, 18], [0, 18]]}],
            ),
            c("revolve", profile="Sketch1", axis="Z"),
            c("create_sketch", plane="XY", geometry=[{"circle": [0, 0, 1]}]),
            c("hole", sketch="Sketch2", diameter=6, depth=12),
        ],
    },
    {
        "id": "pocket_boss",
        "title": "a block with a round boss on top and a rectangular pocket",
        "file": "step",
        "calls": [
            c("create_sketch", plane="XY", geometry=[{"rect": [0, 0, 70, 50]}]),
            c("extrude", profile="Sketch1", distance=10),
            c("create_sketch", plane="XY", offset=10, geometry=[{"circle": [20, 25, 8]}]),
            c("extrude", profile="Sketch2", distance=8),
            c("create_sketch", plane="XY", offset=10, geometry=[{"rect": [40, 15, 62, 35]}]),
            c("extrude", profile="Sketch3", distance=4, operation="cut", flip=True),
        ],
    },
    {
        "id": "meshed_plate",
        "title": "a plate with two holes, from an STL mesh",
        "file": "stl",
        "calls": [
            c("create_sketch", plane="XY", geometry=[{"rect": [0, 0, 60, 40]}]),
            c("extrude", profile="Sketch1", distance=8),
            c(
                "create_sketch",
                plane="XY",
                offset=8,
                geometry=[{"circle": [15, 20, 4]}, {"circle": [45, 20, 4]}],
            ),
            c("hole", sketch="Sketch2", diameter=8, through_all=True),
        ],
    },
]
MCP_PART = "hole_grid"
FIX_ROUNDS = 6


# -- every rebuild tool once, for SciForgeTests/headless/runner.py (its session format) ---------
def _hole_fix(answer, run):
    data = json_in(answer["text"]) or {}
    fixes = [r.get("fix") for r in data.get("extra", []) if r.get("fix")]
    if not fixes or fixes[0]["tool"] != "hole" or fixes[0]["args"].get("diameter") != 6:
        return "no ready hole call for the 6 mm hole: %s" % data.get("extra")
    if data.get("done") or abs(data.get("match", 0) - 0.97700) > 1e-3:
        return "match %s (expected about 0.977)" % data.get("match")
    return None


def _original_shown(shown):
    def check(answer, run):
        doc = run.doc()
        original = doc.getObject("Body001")
        refs = [o for o in doc.Objects if getattr(o, "SciForgeType", "") == "RebuildReference"]
        if original is None:
            return "the original Body001 is gone"
        if bool(original.Visibility) != shown:
            return "the original is %s" % ("hidden" if shown else "shown")
        if bool(refs) == shown:
            return "references: %s" % [r.Name for r in refs]
        return None

    return check


def _kept(answer, run):
    doc = run.doc()
    labels = sorted(o.Label for o in doc.Objects if o.TypeId == "PartDesign::Body")
    if "Body001 (original)" not in labels or "Body001" not in labels:
        return "bodies after finish: %s" % labels
    return None


RUNNER_SESSION = [
    {"tool": "new_design", "args": {"name": "RebuildTools"}},
    {
        "tool": "create_sketch",
        "args": {"plane": "XY", "geometry": [{"rect": [0, 0, 40, 30]}]},
        "save": "rb_sk1",
    },
    {"tool": "extrude", "args": {"profile": "$rb_sk1", "distance": 10}},
    {
        "tool": "create_sketch",
        "args": {"plane": "XY", "offset": 10, "geometry": [{"circle": [20, 15, 3]}]},
        "save": "rb_sk2",
    },
    {"tool": "hole", "args": {"sketch": "$rb_sk2", "diameter": 6, "through_all": True}},
    {"tool": "export", "args": {"format": "step", "path": "{tmp}/rebuild_tools.step"}},
    {"tool": "new_design", "args": {"name": "RebuildToolsImported"}},
    {"tool": "describe_reference", "args": {}, "expect": "error", "contains": ["start_rebuild"]},
    {"tool": "compare_to_reference", "args": {}, "expect": "error", "contains": ["start_rebuild"]},
    {"tool": "finish_rebuild", "args": {}, "expect": "error", "contains": ["start_rebuild"]},
    {"tool": "import_file", "args": {"path": "{tmp}/rebuild_tools.step"}},
    {
        "tool": "start_rebuild",
        "args": {"body": "NoSuchBody"},
        "expect": "error",
        "contains": ["NoSuchBody"],
    },
    {
        "tool": "start_rebuild",
        "args": {"body": "Body"},
        "expect": "error",
        "contains": ["no solid"],
    },
    {
        "tool": "start_rebuild",
        "args": {"body": "Body001"},
        "save": "rb_rebuilt",
        "contains": ["is the reference now", "(rebuilt)"],
    },
    {
        "tool": "start_rebuild",
        "args": {"body": "Body001"},
        "expect": "error",
        "contains": ["already being rebuilt"],
    },
    # undo takes the start back and shows the original again; redo hides it again
    {"tool": "undo", "args": {}, "contains": ["Start rebuild"], "check": _original_shown(True)},
    {"tool": "redo", "args": {}, "check": _original_shown(False)},
    {"tool": "describe_reference", "args": {}, "contains": ['"plan"', "Body001"]},
    {"tool": "describe_reference", "args": {"detail": "summary"}, "contains": ['"summary"']},
    {"tool": "compare_to_reference", "args": {}, "contains": ["still empty"]},
    {"tool": "finish_rebuild", "args": {}, "expect": "error", "contains": ["Not finished"]},
    {
        "tool": "create_sketch",
        "args": {"plane": "XY", "geometry": [{"rect": [0, 0, 40, 30]}]},
        "save": "rb_sk3",
    },
    {"tool": "extrude", "args": {"profile": "$rb_sk3", "distance": 10}},
    {
        "tool": "compare_to_reference",
        "args": {"detail": "full", "show": False},
        "contains": ["not cut yet", "groups[0].fix"],
        "check": _hole_fix,
    },
    {
        "tool": "finish_rebuild",
        "args": {"even_if_different": True, "keep_original": True, "keep_reference": True},
        "contains": ["kept hidden", "the reference kept hidden"],
        "check": _kept,
    },
    # the rebuilt body deleted while the rebuild goes on: said, and a new start makes a new one
    {"tool": "new_design", "args": {"name": "RebuildGone"}},
    {
        "tool": "create_sketch",
        "args": {"plane": "XY", "geometry": [{"rect": [0, 0, 20, 20]}]},
        "save": "rg_sk",
    },
    {"tool": "extrude", "args": {"profile": "$rg_sk", "distance": 5}},
    {"tool": "start_rebuild", "args": {"body": "Body"}, "save": "rg_rebuilt"},
    {"tool": "delete_bodies", "args": {"bodies": ["$rg_rebuilt"]}},
    {"tool": "compare_to_reference", "args": {}, "expect": "error", "contains": ["is gone"]},
    {"tool": "start_rebuild", "args": {"body": "Body"}, "contains": ["is the reference now"]},
    {"tool": "compare_to_reference", "args": {}, "contains": ["still empty"]},
]


def json_in(text):
    start = text.find("{")
    if start < 0:
        return None
    try:
        return json.loads(text[start:])
    except ValueError:
        return None


def made_id(text):
    found = re.search(r"Its id is '([^']+)'", text) or re.search(r"\(id '([^']+)'\)", text)
    return found.group(1) if found else None


# -- the agent: reads only the tools' answers ----------------------------------------------------------
class Agent:
    """Rebuilds one part as an AI would; call(tool, args) -> (text, is_error)."""

    def __init__(self, call, folder):
        self.raw_call = call
        self.folder = folder
        self.checks = []
        self.log = []

    def call(self, tool, args=None):
        args = args or {}
        began = time.time()
        text, error = self.raw_call(tool, args)
        self.log.append(
            {
                "tool": tool,
                "args": args,
                "error": bool(error),
                "seconds": round(time.time() - began, 3),
                "answer": text[:600],
            }
        )
        return text, error

    def check(self, name, ok, detail=""):
        self.checks.append({"check": name, "ok": bool(ok), "detail": str(detail)[:1500]})
        return bool(ok)

    # -- one part ------------------------------------------------------------------------------
    def rebuild(self, part):
        pid = part["id"]
        out = {"id": pid, "title": part["title"], "plan": 0, "failed_steps": [], "rounds": 0}
        # the golden model, exported
        text, error = self.call("new_design", {"name": "Golden_" + pid})
        for call in part["calls"]:
            text, error = self.call(call["tool"], call["args"])
            if error:
                self.check("%s: the golden model's %s" % (pid, call["tool"]), False, text)
                return out
        ext = part["file"]
        path = os.path.join(self.folder, "%s.%s" % (pid, ext))
        args = {"format": ext, "path": path}
        if ext == "stl":
            args["refinement"] = "High"
        text, error = self.call("export", args)
        if not self.check("%s: exported as %s" % (pid, ext.upper()), not error, text):
            return out
        # into a new design: a part without a timeline
        self.call("new_design", {"name": "Rebuild_" + pid})
        text, error = self.call("import_file", {"path": path})
        if not self.check("%s: imported" % pid, not error, text):
            return out
        source = self._imported_body(text, ext)
        if not self.check("%s: the imported body is found" % pid, source, text):
            return out
        # 1. start
        text, error = self.call("start_rebuild", {"body": source})
        if not self.check("%s: start_rebuild" % pid, not error, text):
            return out
        rebuilt = made_id(text)
        # 2. describe
        text, error = self.call("describe_reference", {})
        data = json_in(text) if not error else None
        if not self.check("%s: describe_reference" % pid, data is not None, text[:500]):
            return out
        plan = data.get("plan") or []
        out["plan"] = len(plan)
        out["features"] = len(data.get("features") or [])
        out["confidence"] = data.get("confidence")
        # 3. the plan, step by step (ids as the answers give them)
        made = {}
        for step in plan:
            args = self._with_ids(step, made, plan)
            text, error = self.call(step["tool"], args)
            if error:
                out["failed_steps"].append(
                    {"step": step.get("step"), "tool": step["tool"], "answer": text[:400]}
                )
                continue
            ident = made_id(text)
            if ident:
                made[step.get("step")] = ident
        # 4. compare, fix what the verdict offers, compare again
        result = None
        for _round in range(FIX_ROUNDS):
            text, error = self.call("compare_to_reference", {})
            result = json_in(text) if not error else None
            if result is None:
                self.check("%s: compare_to_reference answers" % pid, False, text[:500])
                return out
            if result.get("done"):
                break
            fixes = self._fixes(result)
            if not fixes:
                break
            out["rounds"] += 1
            for fix in fixes:
                text, error = self.call(fix["tool"], fix["args"])
                if error:
                    out["failed_steps"].append(
                        {"step": "fix", "tool": fix["tool"], "answer": text[:400]}
                    )
        out["match"] = result.get("match") if result else None
        out["faces"] = (
            "%s/%s" % (result["faces"]["matched"], result["faces"]["reference"]) if result else ""
        )
        out["verdict"] = result.get("verdict") if result else ""
        done = bool(result and result.get("done"))
        self.check(
            "%s: the rebuild matches (match >= 0.999, every face): %s" % (pid, out["match"]),
            done,
            out["verdict"],
        )
        if not done:
            return out
        # 5. finish
        text, error = self.call("finish_rebuild", {})
        if not self.check("%s: finish_rebuild" % pid, not error, text):
            return out
        body = made_id(text) or rebuilt
        # 6. a real timeline
        text, error = self.call("get_timeline", {})
        timeline = json_in(text) or {}
        steps = [s for s in timeline.get("steps", []) if s.get("body") == body]
        kinds = [s.get("kind") for s in steps]
        out["timeline"] = kinds
        self.check(
            "%s: the timeline holds real steps (%s)" % (pid, ", ".join(kinds)),
            len(steps) >= 2 and "insert_step" not in kinds and "sketch" in kinds,
            kinds,
        )
        text, error = self.call("check_design", {"interference": False})
        report = json_in(text) or {}
        self.check("%s: check_design ok" % pid, report.get("ok") is True, text[:500])
        # 7. one early value edited: the design rebuilds cleanly
        self._edit_early(pid, steps, out)
        return out

    def _imported_body(self, text, ext):
        """The id of what import_file brought in: the mesh body, or the STEP's body."""
        if ext == "stl":
            return made_id(text)
        answer, error = self.call("get_design", {})
        data = json_in(answer) or {}
        found = [b["id"] for b in data.get("bodies", []) if b.get("volume_mm3")]
        return found[-1] if found else None

    def _with_ids(self, step, made, plan):
        """A plan step's arguments with the ids the earlier steps really got."""
        args = json.loads(json.dumps(step.get("args") or {}))
        planned = {s.get("step"): s.get("id") for s in plan}
        for key, number in (step.get("uses") or {}).items():
            old, new = planned.get(number), made.get(number)
            if not old or not new or old == new or key not in args:
                continue
            args[key] = _swap(args[key], old, new)
        return args

    def _fixes(self, result):
        """The calls compare offers: one per group when it has one, else per region."""
        found = []
        for group in result.get("groups", []):
            if group.get("fix"):
                found.append(group["fix"])
        if found:
            return found
        for side in ("extra", "missing"):
            for region in result.get(side, []):
                if region.get("fix"):
                    found.append(region["fix"])
        return found

    def _edit_early(self, pid, steps, out):
        target = None
        for s in steps:
            values = s.get("values") or {}
            if s.get("kind") == "extrude" and "Distance" in values:
                target = (s["id"], {"distance": values["Distance"] + 2.0})
                break
        if target is None:
            for s in steps:
                values = s.get("values") or {}
                if s.get("kind") == "hole" and "Diameter" in values:
                    target = (s["id"], {"diameter": values["Diameter"] + 0.5})
                    break
        if target is None:
            self.check("%s: an early value to edit" % pid, False, [s.get("kind") for s in steps])
            return
        text, error = self.call("edit_step", {"step": target[0], "set": target[1]})
        out["edit"] = "%s %s" % (target[0], target[1])
        self.check("%s: edit %s %s" % (pid, target[0], target[1]), not error, text[:400])
        text, error = self.call("check_design", {"interference": False})
        report = json_in(text) or {}
        self.check(
            "%s: after the edit every step rebuilds (check_design ok)" % pid,
            report.get("ok") is True,
            text[:600],
        )
        self.call("undo", {})


def _swap(value, old, new):
    if isinstance(value, str):
        return new if value == old else value
    if isinstance(value, list):
        return [_swap(v, old, new) for v in value]
    if isinstance(value, dict):
        return {k: _swap(v, old, new) for k, v in value.items()}
    return value


# -- in-process (FreeCAD) --------------------------------------------------------------------------
def run_in_process(parts=None, folder=None):
    from sciforge.ai import headless

    host = headless.HeadlessHost(allow_overwrite=True)
    folder = folder or tempfile.mkdtemp(prefix="sciforge-rebuild-e2e-")

    def call(tool, args):
        answer = headless.call(tool, args, host)
        return answer["text"], answer["is_error"]

    agent = Agent(call, folder)
    rows = []
    for part in parts or PARTS:
        began = time.time()
        try:
            row = agent.rebuild(part)
        except Exception as exc:
            agent.check("%s: the run" % part["id"], False, traceback.format_exc())
            row = {"id": part["id"], "title": part["title"], "error": str(exc)}
        row["seconds"] = round(time.time() - began, 2)
        rows.append(row)
        _close_all()
    return agent, rows


def _close_all():
    try:
        import FreeCAD as App

        from sciforge.ai import executor

        for name in list(App.listDocuments()):
            App.closeDocument(name)
        executor._BUILDERS.clear()
        executor.MODIFIED.clear()
    except Exception:
        pass


def markdown(title, agent, rows):
    passed = all(c["ok"] for c in agent.checks) and bool(agent.checks)
    lines = [
        "# %s" % title,
        "",
        "%d checks, %s." % (len(agent.checks), "all passed" if passed else "FAILED"),
        "",
        "| Part | Plan steps | Failed steps | Fix rounds | Match | Faces | Timeline | Edit | s |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            "| %s | %s | %s | %s | %s | %s | %s | %s | %s |"
            % (
                r["id"],
                r.get("plan", ""),
                len(r.get("failed_steps", [])),
                r.get("rounds", ""),
                r.get("match", ""),
                r.get("faces", ""),
                " ".join(r.get("timeline", [])),
                r.get("edit", ""),
                r.get("seconds", ""),
            )
        )
    failed = [r for r in rows if r.get("failed_steps")]
    if failed:
        lines += ["", "## What an AI read where a step failed", ""]
        for r in failed:
            for f in r["failed_steps"]:
                lines.append(
                    "- %s, step %s (%s): %s"
                    % (r["id"], f["step"], f["tool"], f["answer"].replace("\n", " ")[:300])
                )
    lines += ["", "## Checks", ""]
    for chk in agent.checks:
        lines.append(
            "- %s %s%s"
            % (
                "PASS" if chk["ok"] else "FAIL",
                chk["check"],
                "" if chk["ok"] else ": " + chk["detail"].replace("\n", " ")[:400],
            )
        )
    return "\n".join(lines) + "\n", passed


def main():
    import FreeCAD as App

    out_dir = os.environ.get("SCIFORGE_HEADLESS_OUT") or App.getUserAppDataDir()
    os.makedirs(out_dir, exist_ok=True)
    wanted = os.environ.get("SCIFORGE_REBUILD_FILTER", "")
    parts = [p for p in PARTS if wanted in p["id"]]
    agent, rows = run_in_process(parts)
    text, passed = markdown("Auto Timeline end to end (in-process)", agent, rows)
    report = {"passed": passed, "parts": rows, "checks": agent.checks, "calls": agent.log}
    with open(os.path.join(out_dir, "rebuild-e2e-report.json"), "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=1)
    with open(os.path.join(out_dir, "rebuild-e2e-report.md"), "w", encoding="utf-8") as handle:
        handle.write(text)
    for chk in agent.checks:
        App.Console.PrintMessage(
            "[SciForge] rebuild %s %s %s\n"
            % (
                "PASS" if chk["ok"] else "FAIL",
                chk["check"],
                "" if chk["ok"] else chk["detail"][:600],
            )
        )
    App.Console.PrintMessage(
        "[SciForge] rebuild summary: %d parts, %d checks, %d failed\n"
        % (len(rows), len(agent.checks), len([c for c in agent.checks if not c["ok"]]))
    )
    return report


# -- through the real MCP server (plain Python) ------------------------------------------------------
def run_over_mcp(command, out_dir=None):
    sys.path.insert(0, HERE)
    import agent_e2e

    client = agent_e2e.Mcp(command)
    folder = tempfile.mkdtemp(prefix="sciforge-rebuild-mcp-")
    agent = Agent(None, folder)
    rows = []
    try:
        client.request(
            "initialize",
            {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "sciforge-rebuild-test", "version": "1"},
            },
        )
        client.notify("notifications/initialized")
        tools = {t["name"]: t for t in client.request("tools/list")["result"]["tools"]}
        agent.check(
            "tools/list has the four rebuild tools",
            {"start_rebuild", "describe_reference", "compare_to_reference", "finish_rebuild"}
            <= set(tools),
            sorted(tools)[:8],
        )
        finish = tools.get("finish_rebuild", {})
        agent.check(
            "finish_rebuild is marked destructive, compare read-only",
            finish.get("annotations", {}).get("destructiveHint") is True
            and tools.get("compare_to_reference", {}).get("annotations", {}).get("readOnlyHint")
            is True,
            finish.get("annotations"),
        )

        def call(tool, args):
            answer = client.request("tools/call", {"name": tool, "arguments": args})
            if "error" in answer:
                return answer["error"]["message"], True
            result = answer["result"]
            return agent_e2e.text_of(result), bool(result.get("isError"))

        agent.raw_call = call
        agent.call("new_design", {"name": "Nothing"})
        text, error = agent.call("describe_reference", {})
        agent.check(
            "before start_rebuild, describe_reference says what to do",
            error and "start_rebuild" in text,
            text,
        )
        part = [p for p in PARTS if p["id"] == MCP_PART][0]
        began = time.time()
        row = agent.rebuild(part)
        row["seconds"] = round(time.time() - began, 2)
        rows.append(row)
    except Exception as exc:
        agent.check(
            "the MCP run",
            False,
            "%s; server said: %s" % (exc, " | ".join(client.stderr[-10:])),
        )
    finally:
        client.close()
    text, passed = markdown("Auto Timeline end to end (through MCP)", agent, rows)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "rebuild-mcp-report.json"), "w", encoding="utf-8") as fh:
            json.dump({"passed": passed, "parts": rows, "checks": agent.checks}, fh, indent=1)
        with open(os.path.join(out_dir, "rebuild-mcp-report.md"), "w", encoding="utf-8") as fh:
            fh.write(text)
    for chk in agent.checks:
        print(
            "[SciForge] rebuild-mcp %s %s %s"
            % (
                "PASS" if chk["ok"] else "FAIL",
                chk["check"],
                "" if chk["ok"] else chk["detail"][:600],
            )
        )
    print(
        "[SciForge] rebuild-mcp summary: %d checks, %d failed"
        % (len(agent.checks), len([c for c in agent.checks if not c["ok"]]))
    )
    return passed


def _main_mcp(argv):
    import argparse

    command = None
    if "--" in argv:
        command = argv[argv.index("--") + 1 :]
        argv = argv[: argv.index("--")]
    parser = argparse.ArgumentParser(description="Auto Timeline end to end through MCP")
    parser.add_argument("--mcp", action="store_true")
    parser.add_argument("--out", default=None)
    options = parser.parse_args(argv)
    sys.path.insert(0, HERE)
    import agent_e2e

    passed = run_over_mcp(command or agent_e2e.default_command(), options.out)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(_main_mcp(sys.argv[1:]))
