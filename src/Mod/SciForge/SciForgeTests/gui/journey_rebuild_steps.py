# SPDX-License-Identifier: LGPL-2.1-or-later
"""The REBUILD journey (scenarios/journey_rebuild*.py, beta 3): parts that came without a
timeline (a STEP file from a stranger, a meshed STL) rebuilt as real parametric parts with
Auto Timeline, then used in the rest of SciForge (edits, a joint, SIMULATION, save / reopen).
Only real clicks and keys; code sets up the test files, plays the AI (a fake local model
that reads only SciForge's answers, as scenario rebuild_chat does) and reads results. Not a
scenario (kept outside scenarios/).

The bracket (written to bracket.step by code, as a stranger would send it): a plate
100 x 60 x 10 (x 0..100, y 0..60, z 0..10) with
  - four counterbored holes, d 6 through, counterbore d 10 x 4 deep, at (12, 15), (12, 45),
    (32, 15), (32, 45): the mounting end;
  - a pocket 30 x 30 x 5 deep at x 55..85, y 15..45;
  - the top edge of the mounting end (x = 0) chamfered 2 mm;
  - the two vertical corners of the far end (x = 100) rounded 8 mm.
  Volume, by hand:
    plate        100 * 60 * 10                          = 60000
    holes        4 * (pi 3^2 * 10 + pi (5^2 - 3^2) * 4)  = 4 * 154 pi = 1935.221
    pocket       30 * 30 * 5                            = 4500
    chamfer      2 * 2 / 2 * 60                         = 120
    fillets      2 * (8^2 - pi 8^2 / 4) * 10            = 274.690
    BRACKET      60000 - 1935.221 - 4500 - 120 - 274.690 = 53170.089
  Made 2 mm thicker (the base extrude 10 -> 12; everything on the top face follows it: the
  pocket stays 5 deep, the counterbores 4 deep, the holes go through):
    72000 - 4 * (pi 9 * 12 + pi 16 * 4) - 4500 - 120 - 2 * (64 - 16 pi) * 12
    = 72000 - 688 pi - 4500 - 120 - 329.628                  = 64888.955
    (+ 2 * (6000 - 4 * 9 pi - 2 * (64 - 16 pi)) = + 11718.866)
  Then the hole d 6 -> 6.5 (the counterbore stays d 10: only the bore under it, 8 long):
    - 4 * pi (3.25^2 - 3^2) * 8 = - 50 pi = - 157.080        = 64731.875

The clamp (clamp.step, the other part of the joint): a block 24 x 24 x 6 with a d 6 hole
through its middle, at x 150..174, y 0..24 in its file. Joined (Rigid) by its hole's bottom
to the top of the counterbored hole at (32, 45): it sits on the bracket's top, z 10..16,
x 20..44, y 33..57; on the thicker bracket z 12..18.

The meshed plate (plate.stl, triangles written by code from the exact plate): 80 x 48 x 8
with two d 10 holes at (20, 24) and (60, 24): 30720 - 2 * pi * 25 * 8 = 29463.363 (every
corner and centre on the sketch grid's 2 mm lines). Rebuilt by hand: a rectangle typed
80 x 48, E 8 (30720); Compare says two round holes about 10 mm across at (20, 24) and
(60, 24) are not cut yet; two circles typed d 10 on the top face, E with them picked, -8,
Extent All (a cut through): 29463.363; made 10 thick: 38400 - 2 pi 25 10 = 36829.204.

SIMULATION (sim_steps): Fixed on the four counterbores' floors, 1000 N straight down on the
far end face. By hand, the bending stress at the weakest section, through the pocket (x = 55,
45 mm from the far end: two walls 15 x 10 and the floor 30 x 5; area 450, centroid z 4.1667,
I = 3437.5 mm4, c = 5.8333): 1000 * 45 * 5.8333 / 3437.5 = 76.36 MPa; 2 mm thicker (walls
15 x 12, floor 30 x 7: I = 6006.5 mm4, c = 6.921): 51.85 MPa, 0.68 of it.
"""

import json
import math
import os
import re

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtWidgets

from SciForgeTests.gui import harness as h
from SciForgeTests.gui import widget_input as wi

V = App.Vector
s = {}

HOLES = ((12, 15), (12, 45), (32, 15), (32, 45))
BRACKET = 60000 - 616 * math.pi - 4500 - 120 - 2 * (64 - 16 * math.pi) * 10
THICK = 72000 - 688 * math.pi - 4500 - 120 - 2 * (64 - 16 * math.pi) * 12
THICK_HOLE = THICK - 50 * math.pi
CLAMP = 24 * 24 * 6 - math.pi * 9 * 6
CLAMP_AT = (32, 45)
PLATE = 80 * 48 * 8 - 2 * math.pi * 25 * 8
PLATE_HOLES = ((20, 24), (60, 24))
ENTRY = "Rebuild with Timeline (AI)..."
# joint snaps at a hole's centre: a face's centre (the clamp's hole is in its middle), a round
# edge's centre, SciForge's hole snaps
CENTRES = ("centre", "circle", "loop", "hole_top", "hole_mid", "hole_bottom")
FINISH_WORDS = "Yes, finish the rebuild."


def near(a, b, tol=1e-6):
    return a is not None and b is not None and abs(a - b) <= tol * max(1.0, abs(b))


def step(fn, name):
    fn.__name__ = name
    return fn


def doc():
    return App.ActiveDocument


def volume(obj):
    try:
        return obj.Shape.Volume if obj is not None and not obj.Shape.isNull() else None
    except Exception:
        return None


def box(obj):
    """The body's box where it is in the design (its component's place included)."""
    try:
        shape = obj.Shape.copy()
        parent = obj.getGlobalPlacement().multiply(obj.Placement.inverse())
        shape.Placement = parent.multiply(shape.Placement)
        b = shape.BoundBox
        return [round(v, 4) for v in (b.XMin, b.YMin, b.ZMin, b.XMax, b.YMax, b.ZMax)]
    except Exception:
        return None


def same_box(a, b, tol=1e-3):
    return a is not None and b is not None and all(abs(x - y) <= tol for x, y in zip(a, b))


# -- the test files (code: a stranger's files) ---------------------------------------------------
def folder():
    path = os.path.join(h.OUT_DIR, "journey_rebuild")
    os.makedirs(path, exist_ok=True)
    return path


def _vertical(shape, x, y):
    found = []
    for e in shape.Edges:
        if e.Curve.TypeId != "Part::GeomLine":
            continue
        a, b = e.Vertexes[0].Point, e.Vertexes[-1].Point
        if all(abs(p.x - x) < 1e-6 and abs(p.y - y) < 1e-6 for p in (a, b)):
            found.append(e)
    return found


def bracket_shape():
    import Part

    plate = Part.makeBox(100, 60, 10)
    cuts = []
    for x, y in HOLES:
        cuts.append(Part.makeCylinder(3, 10, V(x, y, 0)))
        cuts.append(Part.makeCylinder(5, 4, V(x, y, 6)))
    cuts.append(Part.makeBox(30, 30, 5, V(55, 15, 5)))
    shape = plate.cut(Part.makeCompound(cuts)).removeSplitter()
    top_end = [
        e
        for e in shape.Edges
        if e.Curve.TypeId == "Part::GeomLine"
        and all(abs(v.Point.x) < 1e-6 and abs(v.Point.z - 10) < 1e-6 for v in e.Vertexes)
    ]
    shape = shape.makeChamfer(2, top_end)
    return shape.makeFillet(8, _vertical(shape, 100, 0) + _vertical(shape, 100, 60))


def clamp_shape():
    import Part

    block = Part.makeBox(24, 24, 6, V(150, 0, 0))
    return block.cut(Part.makeCylinder(3, 6, V(162, 12, 0))).removeSplitter()


def plate_shape():
    import Part

    plate = Part.makeBox(80, 48, 8)
    holes = [Part.makeCylinder(5, 8, V(x, y, 0)) for x, y in PLATE_HOLES]
    return plate.cut(Part.makeCompound(holes)).removeSplitter()


def write_step(name, shape, label):
    """A STEP file whose part is called `label` (as another CAD program writes it)."""
    import Import

    path = os.path.join(folder(), name + ".step")
    scratch = App.newDocument("JourneyRebuildFile_" + name, hidden=True)
    try:
        part = scratch.addObject("Part::Feature", label)
        part.Label = label
        part.Shape = shape
        scratch.recompute()
        Import.export([part], path)
    finally:
        App.closeDocument(scratch.Name)
    return path


def write_stl(name, shape):
    import MeshPart

    path = os.path.join(folder(), name + ".stl")
    mesh = MeshPart.meshFromShape(Shape=shape, LinearDeflection=0.05, AngularDeflection=0.2)
    mesh.write(path)
    return path


# -- the window -----------------------------------------------------------------------------------
def use_file(path):
    from SciForgeTests.gui import insert_steps as ins

    ins.use_file(path)


def menu(group, label):
    from SciForgeTests.gui import insert_steps as ins

    return ins.menu(group, label)


def press_esc():
    h.press(QtCore.Qt.Key_Escape)


def ctrl(letter):
    from SciForgeTests.gui import timeline_input as t

    t.ctrl(letter)


def bodies():
    from SciForgeTests.gui import bodies_steps as bs

    return bs.bodies()


def body_labelled(label):
    found = [b for b in bodies() if b.Label == label]
    return found[0] if found else None


def references():
    from sciforge import rebuild

    return rebuild.references(doc()) if doc() is not None else []


def target_of(ref):
    from sciforge import rebuild

    return rebuild.target_of(ref) if ref is not None else None


def dialog(name):
    for widget in QtWidgets.QApplication.topLevelWidgets():
        if widget.objectName() == name and widget.isVisible():
            return widget
    return None


def browser_menu(label, entry):
    from SciForgeTests.gui import timeline_input as t

    return t.row_menu(label, entry)


def utilities_menu(label):
    from SciForgeTests.gui import sketch_input as si

    tab("utilities")
    return si.menu_item("AI", label)


def tab(tab_id):
    from sciforge import shell

    wi.click(shell.ribbon().tab_buttons[tab_id])


def chat():
    from sciforge import ai_panel_ui

    page = ai_panel_ui.panel()
    return page.chat if page is not None else None


def timeline_kinds(body):
    """The types of the timeline steps of `body`, in timeline order."""
    from sciforge import bodies as bodies_mod, timeline_ops

    out = []
    for item in timeline_ops.timeline(doc()).items:
        obj = doc().getObject(item.name)
        if obj is not None and bodies_mod.body_of(obj) is body:
            out.append(obj.TypeId.split("::")[-1])
    return out


def broken():
    return [o.Label for o in doc().Objects if "Invalid" in o.State or "Error" in o.State]


def joint_list():
    from sciforge import joints

    return joints.joints(doc())


def joint_subs(joint):
    """The element paths of a joint's two references ("Body001.Hole1.Face3", ...)."""
    out = []
    for prop in ("Reference1", "Reference2"):
        ref = getattr(joint, prop, None)
        if ref:
            out += list(ref[1])
    return out


def holds(joint, body_name):
    """The joint picks an element of this body."""
    return any(("%s." % body_name) in sub for sub in joint_subs(joint))


# -- the fake AI (a local model's address, as rebuild_chat): reads only SciForge's answers ------
def _call(name, args, n):
    return {
        "id": "chatcmpl-%d" % n,
        "object": "chat.completion",
        "model": "qwen3:8b",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_%d" % n,
                            "index": 0,
                            "type": "function",
                            "function": {"name": name, "arguments": json.dumps(args)},
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
    }


def _final(text):
    return {
        "id": "chatcmpl-final",
        "object": "chat.completion",
        "model": "qwen3:8b",
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}
        ],
    }


def json_in(text):
    start = (text or "").find("{")
    try:
        return json.loads(text[start:]) if start >= 0 else None
    except ValueError:
        return None


def _history(messages):
    """[[tool, args, answer text]] of the calls made in these messages."""
    calls = []
    for message in messages:
        if message.get("role") == "assistant":
            for c in message.get("tool_calls") or []:
                fn = c.get("function", {})
                calls.append([fn.get("name"), json.loads(fn.get("arguments") or "{}"), None])
        elif message.get("role") == "tool":
            for c in calls:
                if c[2] is None:
                    c[2] = message.get("content") or ""
                    break
    return calls


def _made_id(text):
    found = re.search(r"Its id is '([^']+)'", text or "")
    return found.group(1) if found else None


def _swap(value, old, new):
    if isinstance(value, str):
        return new if value == old else value
    if isinstance(value, list):
        return [_swap(v, old, new) for v in value]
    if isinstance(value, dict):
        return {k: _swap(v, old, new) for k, v in value.items()}
    return value


def _fixes(result):
    found = [g["fix"] for g in result.get("groups", []) if g.get("fix")]
    if not found:
        for side in ("extra", "missing"):
            found += [x["fix"] for x in result.get(side, []) if x.get("fix")]
    return found


def _user_text(message):
    content = message.get("content")
    if isinstance(content, list):
        return " ".join(part.get("text", "") for part in content if isinstance(part, dict))
    return content or ""


def decide(request):
    """The fake model's next answer. It follows the recipe (docs/ai/recipes/
    reverse-engineer.md) reading only SciForge's answers: describe_reference, every plan step
    (with the ids the answers give), compare_to_reference after every feature (not after a
    sketch), the calls compare offers while it is not done, then it asks the person before
    finishing; finish_rebuild when the person says so."""
    messages = request.get("messages", [])
    last = messages[-1] if messages else {}
    users = [m for m in messages if m.get("role") == "user"]
    calls = _history(messages)
    n = len(calls) + 1
    if last.get("role") == "user" and len(users) > 1:
        if "finish" in _user_text(last).lower():
            return _call("finish_rebuild", {}, n)
        return _final("I can only rebuild the part; say 'finish' to finish it.")
    if calls and calls[-1][0] == "finish_rebuild":
        answer = calls[-1][2] or ""
        if answer.startswith("Done"):
            return _final("Finished: %s" % answer[:200])
        return _final("finish_rebuild refused: %s" % answer[:300])
    if not calls:
        return _call("describe_reference", {}, n)
    data = json_in(calls[0][2]) or {}
    plan = data.get("plan") or []
    if not plan:
        return _final("describe_reference gave no plan: %s" % (calls[0][2] or "")[:300])
    planned = {st.get("step"): st.get("id") for st in plan}
    made = {}
    pos = 1
    for st in plan:
        if st["tool"] == s.get("forget"):
            continue  # (a sloppy AI: compare's verdict has to bring it back)
        args = json.loads(json.dumps(st.get("args") or {}))
        for key, number in (st.get("uses") or {}).items():
            old, new = planned.get(number), made.get(number)
            if old and new and old != new:
                args = _swap(args, old, new)
        if pos >= len(calls):
            return _call(st["tool"], args, n)
        made[st.get("step")] = _made_id(calls[pos][2]) or st.get("id")
        pos += 1
        if st["tool"] != "create_sketch":
            if pos >= len(calls):
                return _call("compare_to_reference", {}, n)
            pos += 1
    compares = [i for i, c in enumerate(calls) if c[0] == "compare_to_reference"]
    k = compares[-1]
    result = json_in(calls[k][2]) or {}
    if result.get("done"):
        return _final(
            "The rebuild matches the original (match %s, every face). Shall I finish it? "
            "(I keep the original until you say so.)" % result.get("match")
        )
    if len([i for i in compares if i >= pos - 1]) >= 4:
        return _final("Not done after 4 comparisons: %s" % result.get("verdict", "")[:300])
    fixes = _fixes(result)
    applied = len(calls) - k - 1
    if applied < len(fixes):
        fix = fixes[applied]
        return _call(fix["tool"], fix["args"], n)
    if not fixes:
        return _final("compare says: %s" % result.get("verdict", "")[:300])
    return _call("compare_to_reference", {}, n)


def start_fake_ai():
    """A local model's address in SciForge's chat settings, answered by decide()."""
    import http.server
    import signal
    import threading

    from sciforge.ai import chat_ui

    s.setdefault("requests", [])
    s.setdefault("log", [])

    class Fake(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def _json(self, data):
            body = json.dumps(data).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path.endswith("/models"):
                self._json({"object": "list", "data": [{"id": "qwen3:8b", "object": "model"}]})
            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            request = json.loads(self.rfile.read(length) or b"{}")
            s["requests"].append(request)
            try:
                answer = decide(request)
            except Exception as exc:  # (a test bug: said in the transcript)
                answer = _final("the fake model failed: %r" % exc)
            s["log"].append(answer["choices"][0]["message"])
            self._json(answer)

    signal.signal(signal.SIGPIPE, signal.SIG_IGN)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    s["server"] = server
    from SciForgeTests.gui import rebuild_steps as r

    r.drop_fake_key()
    prefs = App.ParamGet(chat_ui.PREFS)
    prefs.SetString("ChatAddress", "http://127.0.0.1:%d/v1" % server.server_address[1])
    prefs.SetString("ChatModel_openai_compat", "qwen3:8b")
    prefs.SetString("ChatProvider", "openai_compat")


def stop_fake_ai():
    from sciforge import ai_panel_ui
    from sciforge.ai import chat_ui

    prefs = App.ParamGet(chat_ui.PREFS)
    prefs.RemString("ChatAddress")
    prefs.RemString("ChatProvider")
    try:
        if ai_panel_ui.is_shown():
            ai_panel_ui.toggle()
    except Exception:
        pass
    server = s.pop("server", None)
    if server is not None:
        try:
            server.shutdown()
        except Exception:
            pass


def ai_calls():
    return [m["tool_calls"][0]["function"]["name"] for m in s.get("log", []) if m.get("tool_calls")]


def wait_chat(name, seconds=240):
    """A step that waits until the chat is no longer busy (at most `seconds`)."""

    def wait():
        pass

    def idle():
        panel = chat()
        return panel is None or not panel.busy()

    wait.__name__ = name
    wait.done = idle
    wait.done_what = "the AI chat to finish"
    wait.timeout_s = seconds
    return wait


# -- 1. the part as a stranger sends it: INSERT > Insert STEP --------------------------------------
def insert_steps(with_clamp=True):
    def new_design():
        Gui.activateWorkbench("SciForgeWorkbench")
        s["bracket_file"] = write_step("bracket", bracket_shape(), "Bracket")
        s["clamp_file"] = write_step("clamp", clamp_shape(), "Clamp")
        App.newDocument("JourneyRebuild")
        h.fit()

    def insert_bracket():
        use_file(s["bracket_file"])
        menu("INSERT", "Insert STEP")

    def bracket_in():
        found = [b for b in bodies() if near(volume(b), BRACKET, 1e-6)]
        h.check("Insert STEP: the bracket came in as one body", len(found) == 1, volume_list())
        if not found:
            return
        bracket = found[0]
        s["label"] = bracket.Label
        s["original"] = bracket.Name
        s["component"] = bracket.getParentGeoFeatureGroup()
        s["component_name"] = s["component"].Name if s["component"] is not None else None
        s["placement"] = bracket.getGlobalPlacement()
        h.check(
            "... 53170.09 mm3 by hand",
            near(volume(bracket), BRACKET, 1e-6),
            (volume(bracket), BRACKET),
        )
        h.check("... 100 x 60 x 10", same_box(box(bracket), [0, 0, 0, 100, 60, 10]), box(bracket))
        h.check(
            "... with no timeline: one Insert STEP step",
            timeline_kinds(bracket) in (["Feature"], ["FeatureBase"], [])
            or len(bracket.Group) <= 2,
            timeline_kinds(bracket),
        )
        press_esc()  # the Move dialog of Fusion's Initial Position: it stays where it came in

    def insert_clamp():
        use_file(s["clamp_file"])
        menu("INSERT", "Insert STEP")

    def clamp_in():
        found = [b for b in bodies() if near(volume(b), CLAMP, 1e-6)]
        h.check("Insert STEP: the clamp came in", len(found) == 1, volume_list())
        if found:
            s["clamp"] = found[0].Name
            s["clamp_component"] = found[0].getParentGeoFeatureGroup().Name
        press_esc()
        h.fit()

    steps = [new_design, insert_bracket, bracket_in]
    if with_clamp:
        steps += [insert_clamp, clamp_in]
    return steps


def volume_list():
    return [(b.Label, round(volume(b) or 0, 3)) for b in bodies()]


def bracket():
    """The bracket body a person sees now (the original, or the rebuilt one after Finish)."""
    found = doc().getObject(s.get("original") or "-")
    if found is not None and not s.get("finished"):
        return found
    return doc().getObject(s.get("rebuilt") or "-")


def clamp():
    return doc().getObject(s.get("clamp") or "-")


# -- the joint made before the rebuild (ASSEMBLE > Joint, two clicks) ------------------------------
def joint_steps():
    from SciForgeTests.gui import joints_steps as js

    def press_j():
        js.press_j()

    def first():
        # the clamp's bottom face, near its hole: the snap is the hole's centre there
        c = clamp()
        h.check("the clamp is there", c is not None)
        h.view().viewBottom()
        h.view().fitAll()
        QtWidgets.QApplication.processEvents()
        js.hover(V(157.5, 12, 0))
        p = js.joint_panel()
        h.check("Joint: its dialog is open", p is not None)
        s["first_kind"] = js.hot_kind(p) if p is not None else None
        h.click(V(157.5, 12, 0))

    def second():
        # as a person does: the mouse moved around the counterbore's rim until its centre
        # lights up, then the click
        h.view().viewIsometric()
        h.view().fitAll()
        QtWidgets.QApplication.processEvents()
        x, y = CLAMP_AT
        centre = V(x, y, 10)
        tried = []
        for radius in (5.0, 6.0, 7.0):
            for angle in range(0, 360, 30):
                a = math.radians(angle)
                point = V(x + radius * math.cos(a), y + radius * math.sin(a), 10)
                js.hover(point)
                p = js.joint_panel()
                hot = getattr(getattr(p, "hover", None), "hot", None)
                kind = hot.get("kind") if hot else None
                at = hot.get("point") if hot else None
                tried.append((radius, angle, kind))
                if kind in CENTRES and at is not None and (V(at) - centre).Length < 1e-6:
                    s["second_kind"] = kind
                    h.click(point)
                    return
        h.check("the counterbore's centre lights up somewhere on its rim", False, tried)

    def ok():
        js.ok()

    def joined():
        found = joint_list()
        h.check("a joint was made", len(found) == 1, [j.Label for j in found])
        h.check(
            "it snapped to the holes (hole centres)",
            s.get("first_kind") in CENTRES and s.get("second_kind") in CENTRES,
            (s.get("first_kind"), s.get("second_kind")),
        )
        c = clamp()
        x, y = CLAMP_AT
        expect = [x - 12, y - 12, 10, x + 12, y + 12, 16]
        h.check("the clamp sits on the bracket over the hole", same_box(box(c), expect), box(c))
        if found:
            s["joint"] = found[0].Name
            h.check(
                "... joined to the original bracket body",
                holds(found[0], s["original"]),
                joint_subs(found[0]),
            )
        h.fit()

    return [
        step(press_j, "joint_press_j"),
        step(first, "joint_click_clamp"),
        step(second, "joint_click_bracket"),
        step(ok, "joint_ok"),
        step(joined, "joint_made"),
    ]


# -- 2. Rebuild with Timeline (AI): the chat, Send, the AI's work ----------------------------------
def rebuild_steps():
    def right_click():
        start_fake_ai()
        browser_menu(s["label"], ENTRY)

    def ready():
        from sciforge import ai_panel_ui

        refs = references()
        h.check("the rebuild started (one reference)", len(refs) == 1, refs)
        target = target_of(refs[0]) if refs else None
        h.check("... a new empty body to build in", target is not None)
        s["rebuilt"] = target.Name if target is not None else None
        h.check(
            "... named '<name> (rebuilt)'",
            target is not None and target.Label == s["label"] + " (rebuilt)",
            target.Label if target is not None else None,
        )
        h.check("the AI panel shows", ai_panel_ui.is_shown())
        panel = chat()
        if not h.check("... on its chat", panel is not None):
            return
        text = panel.input.toPlainText()
        h.check("the ready message is in the box", s["label"] in text and text.strip(), text)
        h.check("... not sent yet", not s.get("requests") and not panel.busy())
        s["undo_before"] = len(doc().UndoNames)
        h.shot("rebuild-ready")

    def send():
        panel = chat()
        if panel is not None:
            wi.click(panel.send_button)

    def built():
        panel = chat()
        names = ai_calls()
        h.check("the chat ended", panel is not None and not panel.busy(), names)
        h.check("the AI described the part first", names[:1] == ["describe_reference"], names)
        tools = [t.get("function", t).get("name") for t in s["requests"][0].get("tools", [])]
        h.check(
            "... it was given the rebuild tools",
            all(t in tools for t in ("describe_reference", "compare_to_reference")),
            tools[:40],
        )
        plan = (json_in(first_answer("describe_reference")) or {}).get("plan") or []
        s["plan"] = plan
        h.check("describe_reference gave a plan", len(plan) >= 6, len(plan))
        features = [st for st in plan if st["tool"] != "create_sketch"]
        h.check(
            "the AI compared after every feature",
            names.count("compare_to_reference") >= len(features),
            names,
        )
        h.check("... and did not finish by itself", "finish_rebuild" not in names, names)
        forgot = s.get("forget")
        if forgot:
            # the AI left the plan's chamfer out; compare named it with the call ready and
            # the AI made it from the verdict
            calls = _history(s["requests"][-1].get("messages", []))
            at = [i for i, c in enumerate(calls) if c[0] == forgot]
            told = [
                c[2]
                for c in calls[: at[0]]
                if at and c[0] == "compare_to_reference" and forgot in (c[2] or "")
            ]
            h.check(
                "the AI forgot the %s; compare's verdict named it and the AI made it" % forgot,
                len(at) == 1 and bool(told) and calls[at[0] + 1][0] == "compare_to_reference",
                [c[0] for c in calls],
            )
        last = (s["log"][-1].get("content") or "") if s.get("log") else ""
        h.check("it asks whether to finish", "Shall I finish it?" in last, last)
        text = panel.transcript.toPlainText() if panel is not None else ""
        h.check(
            "... and the person reads it in the chat", "Shall I finish it?" in text, text[-400:]
        )
        target = doc().getObject(s["rebuilt"] or "-")
        h.check(
            "the rebuilt body holds the bracket: 53170.09 mm3",
            near(volume(target), BRACKET, 1e-6),
            (volume(target), BRACKET),
        )
        kinds = timeline_kinds(target)
        s["kinds"] = kinds
        h.check(
            "the timeline holds real steps in Fusion's order",
            kinds
            == [
                "SketchObject",
                "Pad",
                "SketchObject",
                "Pocket",
                "SketchObject",
                "Hole",
                "MultiTransform",
                "Chamfer",
                "Fillet",
            ]
            or _fusion_order(kinds),
            kinds,
        )
        undo = list(doc().UndoNames)[: len(doc().UndoNames) - s["undo_before"]]
        h.check(
            "every AI step is one undo step named 'AI: ...'",
            undo and all(u.startswith("AI: ") for u in undo),
            undo,
        )
        h.check("nothing broken", not broken(), broken())
        h.shot("rebuilt-by-ai")

    return [
        step(right_click, "rebuild_right_click"),
        step(ready, "rebuild_ready_message"),
        step(send, "rebuild_send"),
        wait_chat("rebuild_ai_working"),
        step(built, "rebuild_built"),
    ]


def _fusion_order(kinds):
    """Base first (a sketch and an extrude), holes before patterns, chamfers and fillets last."""
    rank = {"SketchObject": None, "Pad": 0, "Pocket": 1, "Hole": 2}
    order = []
    for k in kinds:
        if k in ("Chamfer", "Fillet"):
            order.append(4)
        elif "Pattern" in k or k == "MultiTransform":
            order.append(3)
        elif rank.get(k) is not None:
            order.append(rank[k])
    return bool(order) and order[0] == 0 and order == sorted(order) and kinds[0] == "SketchObject"


def first_answer(tool):
    """SciForge's answer to the AI's first call of `tool` (from the last request sent)."""
    if not s.get("requests"):
        return None
    for name, _args, answer in _history(s["requests"][-1].get("messages", [])):
        if name == tool:
            return answer
    return None


# -- Compare with Reference (UTILITIES > AI): 100 % ------------------------------------------------
def compare_steps():
    def open_compare():
        utilities_menu("Compare with Reference")

    def hundred():
        box_ = dialog("SciForgeRebuildCompare")
        if not h.check("Compare with Reference opened its window", box_ is not None, h.popups()):
            return
        head = box_.headline.text()
        h.check("it shows 100 %", "100 %" in head, head)
        numbers = box_.numbers.text()
        h.check("... every face matched", "26 of 26" in numbers, numbers)
        h.check("... and says it is done", "Finish" in box_.verdict.text(), box_.verdict.text())
        h.shot("compare-100")
        wi.click(box_.close_button)

    def closed():
        h.check("the window closed", dialog("SciForgeRebuildCompare") is None)

    return [
        step(open_compare, "compare_open"),
        step(hundred, "compare_hundred"),
        step(closed, "compare_closed"),
    ]


# -- Finish: the person tells the AI; the name, the place, one Ctrl+Z ------------------------------
def finish_steps(with_joint=True, with_undo=True):
    def tell():
        panel = chat()
        if not h.check("the chat is still there", panel is not None):
            return
        wi.type_text(panel.input, FINISH_WORDS)
        wi.click(panel.send_button)

    def finished():
        from sciforge import components

        names = ai_calls()
        h.check("the AI finished the rebuild", names[-1:] == ["finish_rebuild"], names)
        last = (s["log"][-1].get("content") or "") if s.get("log") else ""
        h.check("... and said so", last.startswith("Finished: Done"), last)
        target = doc().getObject(s["rebuilt"] or "-")
        s["finished"] = True
        h.check(
            "Finish gave the rebuilt body the original's name",
            target is not None and target.Label == s["label"],
            target.Label if target is not None else None,
        )
        h.check(
            "... its component",
            target is not None
            and components.container_of(target) is doc().getObject(s["component_name"] or "-"),
        )
        h.check(
            "... and its place",
            target is not None and target.getGlobalPlacement().isSame(s["placement"], 1e-9),
            target.getGlobalPlacement() if target is not None else None,
        )
        h.check("the original is gone", doc().getObject(s["original"]) is None)
        h.check("the reference is gone", not references())
        h.check("the bracket: 53170.09 mm3", near(volume(target), BRACKET, 1e-6), volume(target))
        s["undo_names"] = list(doc().UndoNames)
        h.check(
            "the finish is one undo step",
            s["undo_names"][:1] == ["AI: Finish rebuild"],
            s["undo_names"][:3],
        )
        if with_joint:
            _joint_on_rebuild("after Finish", 10)

    def undo():
        ctrl("z")

    def undone():
        original = doc().getObject(s["original"])
        target = doc().getObject(s["rebuilt"] or "-")
        h.check("Ctrl+Z: the original is back", original is not None)
        h.check(
            "... the rebuilt body is '(rebuilt)' again",
            target is not None and target.Label == s["label"] + " (rebuilt)",
            target.Label if target is not None else None,
        )
        h.check("... the reference is back", len(references()) == 1, references())
        if with_joint:
            found = joint_list()
            h.check(
                "... the joint holds the original again",
                found and holds(found[0], s["original"]),
                [joint_subs(j) for j in found],
            )
        h.check("... one step: the AI's steps are still there", near(volume(target), BRACKET))

    def redo():
        ctrl("y")

    def redone():
        target = doc().getObject(s["rebuilt"] or "-")
        h.check(
            "Ctrl+Y: finished again",
            doc().getObject(s["original"]) is None
            and target is not None
            and target.Label == s["label"]
            and not references(),
        )
        if with_joint:
            _joint_on_rebuild("after Ctrl+Y", 10)

    def closed():
        stop_fake_ai()

    steps = [
        step(tell, "finish_tell_ai"),
        wait_chat("finish_ai_working", 60),
        step(finished, "finish_done"),
        h.idle_step("finish_idle"),
    ]
    if with_undo:
        steps += [
            step(undo, "finish_undo"),
            step(undone, "finish_undone"),
            step(redo, "finish_redo"),
            step(redone, "finish_redone"),
        ]
    return steps + [step(closed, "finish_chat_closed")]


def _joint_on_rebuild(where, top):
    found = joint_list()
    if not h.check("%s: the joint is still there" % where, len(found) == 1, found):
        return
    h.check(
        "%s: ... on the rebuilt bracket" % where,
        holds(found[0], s["rebuilt"]) and not holds(found[0], s["original"]),
        joint_subs(found[0]),
    )
    x, y = CLAMP_AT
    expect = [x - 12, y - 12, top, x + 12, y + 12, top + 6]
    h.check(
        "%s: the clamp still sits on the bracket's top (z %g)" % (where, top),
        same_box(box(clamp()), expect),
        box(clamp()),
    )
    h.check("%s: nothing broken" % where, not broken(), broken())


# -- 3. edit the rebuilt part like a person ---------------------------------------------------
def edit_steps(with_joint=True):
    from SciForgeTests.gui import dialog_input as ui
    from SciForgeTests.gui import timeline_input as t

    def base_title():
        for title in t.titles():
            obj = t.obj(title)
            if obj is not None and obj.TypeId == "PartDesign::Pad":
                return title
        return None

    def hole_title():
        for title in t.titles():
            obj = t.obj(title)
            if obj is not None and obj.TypeId == "PartDesign::Hole":
                return title
        return None

    def open_base():
        title = base_title()
        h.check("the base extrude is in the timeline", title is not None, t.titles())
        if title:
            t.double_click(title)

    def thicker():
        from sciforge import extrude_ui

        panel = extrude_ui.ExtrudePanel.last
        if not h.check(
            "double-click opened the Extrude dialog", panel is not None and not panel._closed
        ):
            return
        h.check("... at 10 mm", "10" in panel.distance.widget.text(), panel.distance.widget.text())
        ui.type_into(panel.distance.widget, "12")
        QtWidgets.QApplication.processEvents()

    def ok():
        h.task_button("OK")

    def thick():
        target = bracket()
        h.check(
            "2 mm thicker: 64888.95 mm3 by hand (the pocket and the holes stay on top)",
            near(volume(target), THICK, 1e-6),
            (volume(target), THICK),
        )
        shells = len(target.Shape.Shells) if target is not None else None
        h.check("... one shell: no pocket or hole closed inside the part", shells == 1, shells)
        h.check("... 100 x 60 x 12", same_box(box(target), [0, 0, 0, 100, 60, 12]), box(target))
        h.check("... every step after it rebuilt", not broken(), broken())
        if with_joint:
            _joint_on_rebuild("after the base got thicker", 12)
        h.shot("thicker")

    def open_hole():
        title = hole_title()
        h.check("the hole is in the timeline", title is not None, t.titles())
        if title:
            t.double_click(title)

    def wider():
        from SciForgeTests.gui import hole_steps as hs

        panel = hs.hole_panel()
        if not h.check("double-click opened the Hole dialog", panel is not None):
            return
        h.check("... at d 6", "6" in panel.diameter.widget.text(), panel.diameter.widget.text())
        ui.type_into(panel.diameter.widget, "6.5")
        QtWidgets.QApplication.processEvents()

    def hole_ok():
        h.task_button("OK")

    def wide():
        target = bracket()
        h.check(
            "the holes d 6.5 (all four: the pattern follows): 64731.88 mm3 by hand",
            near(volume(target), THICK_HOLE, 1e-6),
            (volume(target), THICK_HOLE),
        )
        h.check("... every step after it rebuilt", not broken(), broken())
        if with_joint:
            _joint_on_rebuild("after the holes got wider", 12)
        h.shot("wider-holes")

    return [
        step(open_base, "edit_open_base"),
        step(thicker, "edit_thicker"),
        step(ok, "edit_ok"),
        h.idle_step("edit_idle"),
        step(thick, "edit_thick"),
        step(open_hole, "edit_open_hole"),
        step(wider, "edit_wider"),
        step(hole_ok, "edit_hole_ok"),
        h.idle_step("edit_hole_idle"),
        step(wide, "edit_wide"),
    ]


def finish_scenario(where):
    def done():
        stop_fake_ai()
        h.expect_no_errors(where)

    return step(done, "journey_end")


# -- 5. SIMULATION on the rebuilt part ------------------------------------------------------------
FORCE = 1000.0  # N, down on the far end face (x = 100)
# The bending stress by hand where the part is weakest, the section through the pocket
# (x = 55, 45 mm from the far end): two side walls 15 x 10 and the floor 30 x 5 under the
# pocket: area 450, centroid z 4.1667, I = 3437.5 mm4, c = 5.8333 (the top of the walls):
# sigma = 1000 * 45 * 5.8333 / 3437.5 = 76.36 MPa. Made 2 mm thicker (walls 15 x 12, floor
# 30 x 7): I = 6006.5 mm4, c = 6.921: 51.85 MPa (0.68 of it).
POCKET_STRESS = FORCE * 45 * (10 - 1875.0 / 450) / 3437.5
POCKET_STRESS_THICK = 51.85


def click_ring(body_obj, face_name):
    """Click a counterbore's floor (a ring 2 mm wide) half way across, on the side away
    from its seam corners (a click 1 mm from a corner picks the corner)."""
    face = body_obj.Shape.getElement(face_name)
    c = face.CenterOfMass
    for point in (V(c.x - 4, c.y, c.z), V(c.x, c.y + 4, c.z), V(c.x, c.y - 4, c.z)):
        hit = h.under_mouse(point)
        if hit and hit[1] == face_name:
            h.click(point)
            return True
    h.check("the floor %s can be clicked" % face_name, False)
    return False


def sim_steps():
    from SciForgeTests.gui import simsetup_steps as ss

    def body_now():
        return doc().getObject(s.get("rebuilt") or "-")

    def shoulders(body_obj):
        """The four counterbores' floors (flat rings facing up, a bolt head sits there)."""
        out = []
        for i, face in enumerate(body_obj.Shape.Faces):
            if face.Surface.TypeId != "Part::GeomPlane":
                continue
            n = face.normalAt(0, 0)
            c = face.CenterOfMass
            if n.z > 0.999 and any(abs(c.x - x) < 1e-6 and abs(c.y - y) < 1e-6 for x, y in HOLES):
                out.append("Face%d" % (i + 1))
        return out

    def far_end(body_obj):
        for i, face in enumerate(body_obj.Shape.Faces):
            if face.Surface.TypeId == "Part::GeomPlane" and abs(face.CenterOfMass.x - 100) < 1e-6:
                return "Face%d" % (i + 1)
        return None

    def enter():
        h.fit()
        ss.workspace("Simulation")

    def create():
        dialog = ss.new_study_dialog()
        h.check("SIMULATION: New Study opens by itself", dialog is not None)
        ss.click_widget(dialog.create_button if dialog is not None else None)

    def constraints():
        study = ss.active_study()
        h.check("a Static Stress study", study is not None, ss.studies())
        h.ribbon("Structural Constraints")

    def hold():
        p = ss.item_panel()
        if not h.check("Structural Constraints opened", p is not None):
            return
        h.check("Fixed by default", p.type_box.currentText() == "Fixed", p.type_box.currentText())
        target = body_now()
        faces = shoulders(target)
        s["held"] = faces
        h.check("the four counterbores' floors", len(faces) == 4, faces)
        # seen from the top (the ViewCube's TOP): from the side the walls hide the floors
        h.view().viewTop()
        h.view().fitAll()
        QtWidgets.QApplication.processEvents()
        for face in faces:
            click_ring(target, face)
        h.fit()

    def hold_ok():
        p = ss.item_panel()
        if p is not None:
            picked = sorted(sub for _b, sub in p.picks)
            h.check("the counterbores picked", picked == sorted(s.get("held", [])), picked)
        ss.ok()

    def loads():
        h.check("Fixed 1 made", [i.Label for i in ss.items("constraint")] == ["Fixed 1"])
        h.ribbon("Structural Loads")

    def push():
        p = ss.item_panel()
        if not h.check("Structural Loads opened", p is not None):
            return
        h.check("Force by default", p.type_box.currentText() == "Force", p.type_box.currentText())
        target = body_now()
        face = far_end(target)
        s["pushed"] = face
        h.check("the far end face", face is not None)
        if face is not None:
            ss.click_face(target, face)
        ss.choose("SciForgeSim_direction", "Vector")
        ss.type_in("SciForgeSim_fx", "0 N")
        ss.type_in("SciForgeSim_fy", "0 N")
        ss.type_in("SciForgeSim_fz", "-%g N" % FORCE)

    def push_ok():
        p = ss.item_panel()
        if p is not None:
            h.check("the far end picked", [sub for _b, sub in p.picks] == [s.get("pushed")])
        ss.ok()

    def loaded():
        found = ss.items("load")
        h.check("Force 1 made", [i.Label for i in found] == ["Force 1"], [i.Label for i in found])
        if found:
            data = ss.sim().item_data(found[0])
            opts = data.get("options", {})
            h.check("... 1000 N straight down", opts.get("direction") == "vector", opts)
        h.ribbon("Solve")

    def go():
        dialog = ss.solve_dialog()
        if h.check("the Solve dialog opened", dialog is not None):
            h.check("Solve 1 Study", dialog.go.text() == "Solve 1 Study", dialog.go.text())
            ss.click_widget(dialog.go)

    def solved():
        from SciForgeTests.gui import simres_steps as sr

        study = ss.active_study()
        summary = ss.sim().summary(study) if study is not None else {}
        stats = (summary or {}).get("stats", {})
        vm = stats.get("von_mises", {}).get("max")
        sf = stats.get("safety", {}).get("min")
        s["vm"], s["sf"] = vm, sf
        h.check("solved: a stress", vm is not None and vm > 0, stats.keys())
        h.check(
            "the largest stress is at least the bending stress by hand at the pocket (76 MPa)",
            vm is not None and vm >= 0.9 * POCKET_STRESS,
            (vm, POCKET_STRESS),
        )
        h.check("... and not wildly more (under 4 x)", vm is not None and vm < 4 * POCKET_STRESS)
        h.check("a safety factor under Fusion's cap of 15", sf is not None and 0 < sf < 15, sf)
        shown = sr.legend_text("SciForgeSimLegendMin")
        h.check("RESULTS shows the safety factor", shown.startswith("Min:"), shown)
        h.check("not out of date", not ss.sim().out_of_date(study))
        h.shot("sim-first")

    def design():
        ss.workspace("Design")

    def back():
        h.check("DESIGN again: the timeline is back", ss.timeline_visible())

    edits = edit_steps(with_joint=False)[:5]  # double-click the base extrude, 12, OK, check

    def again():
        ss.workspace("Simulation")

    def stale():
        study = ss.active_study()
        h.check("the study is out of date", study is not None and ss.sim().out_of_date(study))
        h.ribbon("Solve")

    def resolved():
        study = ss.active_study()
        summary = ss.sim().summary(study) if study is not None else {}
        stats = (summary or {}).get("stats", {})
        vm = stats.get("von_mises", {}).get("max")
        sf = stats.get("safety", {}).get("min")
        h.check("solved again: up to date", study is not None and not ss.sim().out_of_date(study))
        h.check(
            "the stress drops (by hand to 0.68 at the pocket)",
            vm is not None and s.get("vm") and vm < 0.9 * s["vm"],
            (vm, s.get("vm")),
        )
        h.check(
            "... the safety factor rises",
            sf is not None and s.get("sf") and sf > s["sf"],
            (sf, s.get("sf")),
        )
        h.shot("sim-thicker")

    return (
        [
            step(enter, "sim_enter"),
            step(create, "sim_create_study"),
            step(constraints, "sim_constraints"),
            step(hold, "sim_hold_counterbores"),
            step(hold_ok, "sim_hold_ok"),
            step(loads, "sim_loads"),
            step(push, "sim_push_far_end"),
            step(push_ok, "sim_push_ok"),
            step(loaded, "sim_solve"),
            step(go, "sim_solve_go"),
            ss.wait_solved("sim_solving", 400),
            step(solved, "sim_solved"),
            step(design, "sim_to_design"),
            step(back, "sim_design_back"),
        ]
        + edits
        + [
            step(again, "sim_again"),
            step(stale, "sim_out_of_date"),
            step(go, "sim_solve_again"),
            ss.wait_solved("sim_solving_again", 400),
            step(resolved, "sim_resolved"),
        ]
    )


# -- 6. the mesh path, by hand; 7. save, close, open again half way and after Finish ------------
def mesh_steps():
    from SciForgeTests.gui import arrow_input as ai
    from SciForgeTests.gui import insert_steps as ins
    from SciForgeTests.gui import plane_input as pl
    from SciForgeTests.gui import sketch_input as si

    def new_design():
        from SciForgeTests.gui import rebuild_steps as r

        stop_fake_ai()
        r.drop_fake_key()  # no AI set up: the window for AI apps
        Gui.activateWorkbench("SciForgeWorkbench")
        s["stl"] = write_stl("plate", plate_shape())
        App.newDocument("JourneyRebuildMesh")
        h.fit()

    def insert():
        use_file(s["stl"])
        h.ribbon("Insert Mesh")

    def inserted():
        p = ins.panel()
        h.check(
            "the Insert Mesh dialog", p is not None and getattr(p, "title", "") == "Insert Mesh"
        )
        meshes = ins.mesh_bodies()
        h.check("a mesh body", len(meshes) == 1, meshes)
        if meshes:
            s["mesh"], s["mesh_label"] = meshes[0].Name, meshes[0].Label
        h.task_button("OK")

    def right_click():
        browser_menu(s["mesh_label"], ENTRY)

    def no_ai():
        box_ = dialog("SciForgeRebuildNoAI")
        h.check("no AI set up: a window says how to ask an AI app", box_ is not None, h.popups())
        refs = references()
        h.check("the mesh is the reference now", len(refs) == 1, refs)
        target = target_of(refs[0]) if refs else None
        s["rebuilt"] = target.Name if target is not None else None
        h.check(
            "... and a new body '<name> (rebuilt)' to build in",
            target is not None and target.Label == s["mesh_label"] + " (rebuilt)",
            target.Label if target is not None else None,
        )
        if box_ is not None:
            close = box_.findChild(QtWidgets.QAbstractButton, "SciForgeRebuildClose")
            if h.check("its Close button", close is not None):
                wi.click(close)

    def sketch():
        h.check("the window closed", dialog("SciForgeRebuildNoAI") is None)
        h.fit()
        h.ribbon("Create Sketch")

    def pick_xy():
        pl.click_square("XY_Plane")

    def rect_key():
        s["sk"] = h.in_sketch()
        h.check("a sketch on XY", s["sk"] is not None)
        h.press("r")

    def corner():
        si.click(V(0, 0, 0))

    def size():
        si.move_towards(V(12, 9, 0), V(1, 1, 0) * 0.7)
        si.type_text("80", enter=False)
        si.tab()
        si.type_text("48")

    def rect_drawn():
        h.press(QtCore.Qt.Key_Escape)
        sk = s.get("sk")
        xs, ys = [], []
        for _i, g in si.lines(sk) if sk is not None else []:
            xs += [g.StartPoint.x, g.EndPoint.x]
            ys += [g.StartPoint.y, g.EndPoint.y]
        h.check(
            "a rectangle 80 x 48 from the origin",
            xs
            and near(min(xs), 0)
            and near(max(xs), 80)
            and near(min(ys), 0)
            and near(max(ys), 48),
            (xs, ys),
        )
        h.press("e")  # Extrude, straight from the sketch

    def distance():
        h.check("Extrude opened", ai.give_distance("8"))

    def ok():
        h.task_button("OK")

    def plate_made():
        target = doc().getObject(s.get("rebuilt") or "-")
        h.check("the plate 80 x 48 x 8: 30720 mm3", near(volume(target), 30720.0), volume(target))

    def compare():
        utilities_menu("Compare with Reference")

    def says_holes():
        box_ = dialog("SciForgeRebuildCompare")
        if not h.check("Compare with Reference opened", box_ is not None, h.popups()):
            return
        verdict = box_.verdict.text()
        h.check(
            "it says two round holes about 10 mm across are not cut yet",
            "2 round holes about 10 mm across" in verdict,
            verdict,
        )
        h.check("... at (20, 24) and (60, 24)", "(20, 24)" in verdict and "(60, 24)" in verdict)
        h.shot("mesh-compare-holes")
        wi.click(box_.close_button)

    def finish_early():
        h.check("the window closed", dialog("SciForgeRebuildCompare") is None)
        utilities_menu("Finish Rebuild")

    def keeps_original():
        box_ = dialog("SciForgeRebuildFinish")
        if not h.check("Finish Rebuild opened (too early)", box_ is not None, h.popups()):
            return
        text = box_.state.text()
        h.check("it says the plate does not match yet", "does not match" in text, text)
        h.check(
            "... and keeps the original by default (nothing lost by an early Finish)",
            box_.keep_original.isChecked() and not box_.delete_original.isChecked(),
        )
        wi.click(box_.cancel)

    def sketch_top():
        h.check("Cancel closed it", dialog("SciForgeRebuildFinish") is None)
        h.check("... and nothing was finished", len(references()) == 1, references())
        h.fit()
        tab("solid")  # (Compare was in UTILITIES)
        h.ribbon("Create Sketch")

    def click_top():
        h.click(V(40, 40, 8))

    def circle_key():
        s["sk2"] = h.in_sketch()
        h.check("a sketch on the plate's top", s["sk2"] is not None)
        h.press("c")

    def c1():
        si.click(V(20, 24, 8))

    def r1():  # the diameter typed, as in Fusion
        si.move_towards(V(26, 24.3, 8), V(1, 0, 0))
        si.type_text("10")

    def c2():
        si.click(V(60, 24, 8))

    def r2():
        si.move_towards(V(66, 24.3, 8), V(1, 0, 0))
        si.type_text("10")

    def circles_drawn():
        h.press(QtCore.Qt.Key_Escape)
        sk = s.get("sk2")
        found = si.circles(sk, construction=False) if sk is not None else []
        got = sorted(
            (round(g.Center.x, 6), round(g.Center.y, 6), round(g.Radius, 6)) for _i, g in found
        )
        h.check(
            "two circles of radius 5 at (20, 24) and (60, 24)",
            got == [(20.0, 24.0, 5.0), (60.0, 24.0, 5.0)],
            got,
        )
        h.press("e")

    def pick_circles():
        # the sketch on the face holds the face's outline too (projected, as Fusion does), so
        # nothing is picked yet: a click inside each circle picks it
        from sciforge import extrude_ui

        panel = extrude_ui.ExtrudePanel.last
        if h.check("Extrude opened", panel is not None and not panel._closed):
            s["profiles_before"] = list(panel.profiles)
            si.click(V(20, 24, 8))

    def pick_second():
        si.click(V(60, 24, 8))

    def depth():
        from sciforge import extrude_ui

        panel = extrude_ui.ExtrudePanel.last
        if panel is None or panel._closed:
            h.check("the Extrude dialog is still open", False)
            return
        subs = sorted(sub for _obj, sub in panel.profiles)
        h.check("the two circles are the profiles", len(subs) == 2, (subs, s["profiles_before"]))
        ai.give_distance("-8")
        h.check(
            "going down into the plate makes it a Cut",
            panel.operation.currentData() == "cut",
            panel.operation.currentData(),
        )
        # holes go through: Extent All (they still do when the plate gets thicker)
        from SciForgeTests.gui import dialog_input as ui

        h.check("Extent: All", ui.choose(panel.extent, "All"))

    def cut_made():
        target = doc().getObject(s.get("rebuilt") or "-")
        h.check(
            "the two holes cut: 29463.36 mm3 by hand",
            near(volume(target), PLATE, 1e-6),
            (volume(target), PLATE),
        )

    def compare_done():
        box_ = dialog("SciForgeRebuildCompare")
        if not h.check("Compare with Reference opened again", box_ is not None, h.popups()):
            return
        verdict = box_.verdict.text()
        h.check("it says done (Finish Rebuild)", "Finish Rebuild" in verdict, verdict)
        h.check("the match", "Match 99.99" in box_.headline.text(), box_.headline.text())
        h.shot("mesh-compare-done")
        wi.click(box_.finish_button)

    def finish_ok():
        box_ = dialog("SciForgeRebuildFinish")
        if not h.check("Finish Rebuild asks", box_ is not None, h.popups()):
            return
        h.check("... delete the original by default", box_.delete_original.isChecked())
        wi.click(box_.ok)

    def finished():
        target = doc().getObject(s.get("rebuilt") or "-")
        h.check(
            "the rebuilt plate took the mesh body's name",
            target is not None and target.Label == s["mesh_label"],
            target.Label if target is not None else None,
        )
        h.check("the mesh body is gone", doc().getObject(s["mesh"]) is None)
        h.check("the reference is gone", not references())
        kinds = timeline_kinds(target)
        h.check(
            "a timeline: sketch, extrude, sketch, cut",
            kinds == ["SketchObject", "Pad", "SketchObject", "Pocket"],
            kinds,
        )
        h.check("29463.36 mm3", near(volume(target), PLATE, 1e-6), volume(target))
        h.check("one undo step 'Finish Rebuild'", doc().UndoNames[:1] == ["Finish Rebuild"])

    return [
        step(new_design, "mesh_new_design"),
        step(insert, "mesh_insert"),
        step(inserted, "mesh_inserted"),
        step(right_click, "mesh_right_click"),
        step(no_ai, "mesh_no_ai_window"),
        step(sketch, "mesh_create_sketch"),
        step(pick_xy, "mesh_pick_xy"),
        step(rect_key, "mesh_rect_key"),
        step(corner, "mesh_rect_corner"),
        step(size, "mesh_rect_size"),
        step(rect_drawn, "mesh_rect_drawn"),
        step(distance, "mesh_distance"),
        step(ok, "mesh_extrude_ok"),
        step(plate_made, "mesh_plate_made"),
        step(compare, "mesh_compare"),
        step(says_holes, "mesh_compare_holes"),
    ], [
        step(finish_early, "mesh_finish_too_early"),
        step(keeps_original, "mesh_finish_keeps_original"),
        step(sketch_top, "mesh_sketch_top"),
        step(click_top, "mesh_click_top"),
        step(circle_key, "mesh_circle_key"),
        step(c1, "mesh_circle1_centre"),
        step(r1, "mesh_circle1_radius"),
        step(c2, "mesh_circle2_centre"),
        step(r2, "mesh_circle2_radius"),
        step(circles_drawn, "mesh_circles_drawn"),
        step(pick_circles, "mesh_cut_pick_circle1"),
        step(pick_second, "mesh_cut_pick_circle2"),
        step(depth, "mesh_cut_depth"),
        step(ok, "mesh_cut_ok"),
        step(cut_made, "mesh_cut_made"),
        step(compare, "mesh_compare_again"),
        step(compare_done, "mesh_compare_done"),
        step(finish_ok, "mesh_finish_ok"),
        h.idle_step("mesh_finish_idle"),
        step(finished, "mesh_finished"),
    ]


def reopen_steps(name, check):
    """Ctrl+S (the Save dialog of a new design, or the version prompt), the design's tab
    closed, the file opened again; then `check()`."""
    from SciForgeTests.gui import polish2_steps as p2
    from SciForgeTests.gui import versions_input as vi

    def save():
        s.setdefault("files", {})
        h.press(QtCore.Qt.Key_S, QtCore.Qt.ControlModifier)

    def save_dialog():
        if vi.save_dialog() is not None:
            s["files"][name] = os.path.join(folder(), name + ".FCStd")
            if os.path.exists(s["files"][name]):
                os.remove(s["files"][name])
            vi.fill_save_dialog(name, folder())
            vi.click_save()
        else:
            s["files"][name] = doc().FileName
            h.check("%s: the version prompt" % name, vi.accept_save())

    def close():
        path = s["files"].get(name)
        h.check("%s: saved" % name, path and os.path.isfile(path), (path, h.popups()))
        p2.close_tab(doc())

    def reopen():
        h.check(
            "%s: the design closed" % name,
            App.ActiveDocument is None
            or not any(d.FileName == s["files"].get(name) for d in App.listDocuments().values()),
        )
        App.openDocument(s["files"][name])  # (File > Open's system dialog)
        h.fit()

    return [
        step(save, "%s_save" % name),
        step(save_dialog, "%s_save_dialog" % name),
        step(close, "%s_close" % name),
        step(reopen, "%s_reopen" % name),
        step(check, "%s_reopened" % name),
    ]


def mesh_reopened_half_way():
    from sciforge import bodies as bodies_mod, rebuild_ui

    refs = references()
    h.check("half way, opened again: the reference is there", len(refs) == 1, refs)
    target = doc().getObject(s.get("rebuilt") or "-")
    h.check("... the plate built so far", near(volume(target), 30720.0), volume(target))
    h.check(
        "... the rebuilt body is the active body",
        target is not None and bodies_mod.active_body(doc()) is target,
        getattr(bodies_mod.active_body(doc()), "Label", None),
    )
    view = rebuild_ui.view_of(refs[0]) if refs else None
    h.check("... its ghost is drawn", view is not None and view.ghost_shown())
    mesh = doc().getObject(s.get("mesh") or "-")
    h.check("... the mesh body hidden", mesh is not None and not mesh.ViewObject.Visibility)


def mesh_reopened_finished():
    target = doc().getObject(s.get("rebuilt") or "-")
    h.check("finished, opened again: the plate", near(volume(target), PLATE, 1e-6), volume(target))
    h.check(
        "... under the mesh body's name", target is not None and target.Label == s["mesh_label"]
    )
    h.check("... no reference", not references())
    kinds = timeline_kinds(target)
    h.check("... its timeline", kinds == ["SketchObject", "Pad", "SketchObject", "Pocket"], kinds)
    h.check("... nothing broken", not broken(), broken())


def mesh_edit_steps():
    """After opening it again: the plate's extrude double-clicked, 8 -> 10: the holes go
    through (they were sketched on the top face): 80 * 48 * 10 - 2 * pi * 25 * 10."""
    from SciForgeTests.gui import dialog_input as ui
    from SciForgeTests.gui import timeline_input as t

    def open_pad():
        for title in t.titles():
            obj = t.obj(title)
            if obj is not None and obj.TypeId == "PartDesign::Pad":
                t.double_click(title)
                return
        h.check("the plate's extrude in the timeline", False, t.titles())

    def thicker():
        from sciforge import extrude_ui

        panel = extrude_ui.ExtrudePanel.last
        if h.check("the Extrude dialog", panel is not None and not panel._closed):
            ui.type_into(panel.distance.widget, "10")

    def ok():
        h.task_button("OK")

    def thick():
        target = doc().getObject(s.get("rebuilt") or "-")
        want = 80 * 48 * 10 - 2 * math.pi * 25 * 10
        h.check(
            "10 thick, the holes still through: 36829.20 mm3",
            near(volume(target), want, 1e-6),
            (volume(target), want),
        )
        shells = len(target.Shape.Shells) if target is not None else None
        h.check("... one shell", shells == 1, shells)

    return [
        step(open_pad, "mesh_edit_open"),
        step(thicker, "mesh_edit_thicker"),
        step(ok, "mesh_edit_ok"),
        h.idle_step("mesh_edit_idle"),
        step(thick, "mesh_edit_thick"),
    ]


# -- 7 (the AI's path): saved half way, finished by hand after opening again ---------------------
def bracket_reopened_half_way():
    from sciforge import bodies as bodies_mod, rebuild_ui

    refs = references()
    h.check("half way, opened again: the reference is there", len(refs) == 1, refs)
    target = doc().getObject(s.get("rebuilt") or "-")
    h.check("... the AI's rebuild: 53170.09 mm3", near(volume(target), BRACKET, 1e-6))
    h.check(
        "... the rebuilt body is the active body",
        target is not None and bodies_mod.active_body(doc()) is target,
        getattr(bodies_mod.active_body(doc()), "Label", None),
    )
    view = rebuild_ui.view_of(refs[0]) if refs else None
    h.check("... its ghost is drawn", view is not None and view.ghost_shown())
    original = doc().getObject(s.get("original") or "-")
    h.check("... the original hidden", original is not None and not original.ViewObject.Visibility)
    found = joint_list()
    h.check(
        "... the joint still holds the original",
        len(found) == 1 and holds(found[0], s["original"]),
        [joint_subs(j) for j in found],
    )


def finish_by_hand_steps():
    """UTILITIES > AI > Compare with Reference (100 %) > Finish Rebuild... > Finish."""

    def compare():
        utilities_menu("Compare with Reference")

    def hundred():
        box_ = dialog("SciForgeRebuildCompare")
        if not h.check("Compare with Reference opened", box_ is not None, h.popups()):
            return
        h.check("100 %", "100 %" in box_.headline.text(), box_.headline.text())
        wi.click(box_.finish_button)

    def finish():
        box_ = dialog("SciForgeRebuildFinish")
        if h.check("Finish Rebuild asks", box_ is not None, h.popups()):
            wi.click(box_.ok)

    def finished():
        target = doc().getObject(s.get("rebuilt") or "-")
        s["finished"] = True
        h.check(
            "finished by hand: the bracket's name",
            target is not None and target.Label == s["label"],
            target.Label if target is not None else None,
        )
        h.check("... the original and the reference are gone", not references())
        h.check("... one undo step 'Finish Rebuild'", doc().UndoNames[:1] == ["Finish Rebuild"])
        _joint_on_rebuild("finished by hand", 10)

    return [
        step(compare, "hand_compare"),
        step(hundred, "hand_compare_hundred"),
        step(finish, "hand_finish"),
        h.idle_step("hand_finish_idle"),
        step(finished, "hand_finished"),
    ]


def bracket_reopened_finished():
    target = doc().getObject(s.get("rebuilt") or "-")
    h.check("finished, opened again: the bracket", near(volume(target), BRACKET, 1e-6))
    h.check("... under its name", target is not None and target.Label == s["label"])
    h.check("... no reference", not references())
    kinds = timeline_kinds(target)
    h.check("... its timeline of real steps", _fusion_order(kinds) and len(kinds) == 9, kinds)
    _joint_on_rebuild("finished, opened again", 10)
