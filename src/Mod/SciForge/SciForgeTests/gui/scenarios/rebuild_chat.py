# SPDX-License-Identifier: LGPL-2.1-or-later
"""Auto Timeline through SciForge's own chat (beta 3, builder at-tools), with real clicks:
a person's whole rebuild with an AI, against a fake AI provider (a local server in this test
that answers like Ollama / LM Studio, as scenario ai_chat does). Spec:
docs/sciforge/parity/auto-timeline.md.

The fake model is a small agent that reads only what SciForge answers it: describe_reference,
then every step of the plan as its tool call, compare_to_reference, the calls compare offers
while it is not done, finish_rebuild, and a last answer in words.

A  The chat has an AI set up (a local model's address); the imported plate's right-click >
   Rebuild with Timeline (AI)... opens the AI panel's chat with the message, not sent.
B  Send: the model gets the four rebuild tools among the 48 a local model takes, and rebuilds
   the plate: every step is one undo step named "AI: ...", the plate becomes a part with a
   timeline (sketches, an extrude, holes, a fillet), under the original's name and in its
   component; the original and the reference are gone; the AI's last answer is shown.
"""

import http.server
import json
import threading

import FreeCAD as App

from SciForgeTests.gui import harness as h
from SciForgeTests.gui import rebuild_steps as r
from SciForgeTests.gui import widget_input as wi

s = {"requests": [], "log": []}
ENTRY = "Rebuild with Timeline (AI)..."
TOOLS = ("start_rebuild", "describe_reference", "compare_to_reference", "finish_rebuild")


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


def _json_in(text):
    start = (text or "").find("{")
    try:
        return json.loads(text[start:]) if start >= 0 else None
    except ValueError:
        return None


def _history(request):
    """[[tool, args, answer text]] of the calls made so far in this conversation."""
    calls = []
    for message in request.get("messages", []):
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


def _fixes(result):
    found = [g["fix"] for g in result.get("groups", []) if g.get("fix")]
    if not found:
        for side in ("extra", "missing"):
            found += [x["fix"] for x in result.get(side, []) if x.get("fix")]
    return found


def decide(request):
    """The fake model's next answer: the rebuild loop, read from SciForge's answers."""
    calls = _history(request)
    n = len(calls) + 1
    if not calls:
        return _call("describe_reference", {}, n)
    last = calls[-1]
    if last[0] == "finish_rebuild":
        if last[2] and last[2].startswith("Done"):
            return _final("The plate is rebuilt with a timeline: %s" % last[2][:120])
        return _final("finish_rebuild refused: %s" % (last[2] or "")[:200])
    data = _json_in(calls[0][2]) or {}
    plan = data.get("plan") or []
    compares = [i for i, c in enumerate(calls) if c[0] == "compare_to_reference"]
    if not compares:
        done_steps = len(calls) - 1
        if done_steps < len(plan):
            step = plan[done_steps]
            return _call(step["tool"], step["args"], n)
        return _call("compare_to_reference", {"show": True}, n)
    k = compares[-1]
    result = _json_in(calls[k][2]) or {}
    if result.get("done"):
        return _call("finish_rebuild", {}, n)
    if len(compares) >= 4:
        return _final("Not done after 4 comparisons: %s" % result.get("verdict", "")[:200])
    fixes = _fixes(result)
    applied = len(calls) - k - 1
    if applied < len(fixes):
        fix = fixes[applied]
        return _call(fix["tool"], fix["args"], n)
    return _call("compare_to_reference", {"show": True}, n)


class _Fake(http.server.BaseHTTPRequestHandler):
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
            answer = _final("the fake model failed: %s" % exc)
        s["log"].append(answer["choices"][0]["message"])
        self._json(answer)


def chat():
    from sciforge import ai_panel_ui

    page = ai_panel_ui.panel()
    return page.chat if page is not None else None


# -- A ------------------------------------------------------------------------------------------
def setup():
    import signal

    from sciforge.ai import chat_ui

    signal.signal(signal.SIGPIPE, signal.SIG_IGN)  # (as the bridge does: bridge.py)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Fake)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    s["server"] = server
    r.drop_fake_key()
    prefs = App.ParamGet(chat_ui.PREFS)
    prefs.SetString("ChatAddress", "http://127.0.0.1:%d/v1" % server.server_address[1])
    prefs.SetString("ChatModel_openai_compat", "qwen3:8b")
    prefs.SetString("ChatProvider", "openai_compat")
    s["doc"] = r.new_design("RebuildChat")
    s["plate"] = r.insert_step(s["doc"], r.write_step("plate"))
    s["label"] = s["plate"].Label
    s["plate_name"] = s["plate"].Name
    s["component"] = s["plate"].getParentGeoFeatureGroup()
    s["doc"].recompute()
    h.fit()


def a_start():
    r.browser_menu(s["label"], ENTRY)


a_start.wait_ms = 2000


def a_message():
    from sciforge import ai_panel_ui, rebuild

    refs = r.references()
    h.check("the rebuild started", len(refs) == 1, refs)
    h.check("the AI panel shows", ai_panel_ui.is_shown())
    panel = chat()
    if panel is None:
        return
    h.check(
        "the local model is the chat's AI",
        panel.provider_name() == "openai_compat",
        panel.provider_name(),
    )
    text = panel.input.toPlainText()
    h.check("the message is in the box", 'Rebuild the body "%s"' % s["label"] in text, text)
    h.check("... not sent", not s["requests"] and not panel.busy())
    s["target_name"] = rebuild.target_of(refs[0]).Name if refs else None
    s["undo_before"] = len(App.ActiveDocument.UndoNames)


# -- B ------------------------------------------------------------------------------------------
def b_send():
    panel = chat()
    if panel is not None:
        wi.click(panel.send_button)


b_send.wait_ms = 6000


def b_wait():
    panel = chat()
    if panel is not None and panel.busy():
        b_wait.waited = getattr(b_wait, "waited", 0) + 1


b_wait.wait_ms = 6000


def b_rebuilt():
    from sciforge import bodies, components

    panel = chat()
    h.check("the chat ended", panel is not None and not panel.busy())
    sent = [t.get("function", t).get("name") for t in s["requests"][0].get("tools", [])]
    h.check(
        "the model got the four rebuild tools (of the 48 a local model takes)",
        all(name in sent for name in TOOLS) and len(sent) == 48,
        (len(sent), sent[16:34]),
    )
    names = [m["tool_calls"][0]["function"]["name"] for m in s["log"] if m.get("tool_calls")]
    h.check(
        "it described, built the plan, compared and finished",
        names[:1] == ["describe_reference"]
        and "compare_to_reference" in names
        and names[-1:] == ["finish_rebuild"],
        names,
    )
    text = panel.transcript.toPlainText() if panel is not None else ""
    h.check(
        "the AI's last answer is shown", "The plate is rebuilt with a timeline" in text, text[-500:]
    )
    doc = App.ActiveDocument
    target = doc.getObject(s["target_name"] or "-")
    h.check(
        "the rebuild took the original's name",
        target is not None and target.Label == s["label"],
        target.Label if target else None,
    )
    h.check(
        "... in the original's component",
        target is not None and components.container_of(target) is s["component"],
    )
    h.check(
        "... the plate's volume",
        target is not None and abs(target.Shape.Volume - r.PLATE_VOLUME) < 1e-3,
        target.Shape.Volume if target else None,
    )
    h.check("the original is deleted", doc.getObject(s["plate_name"]) is None)
    h.check("the reference is gone", not r.references())
    steps = [n for n in r.timeline_names() if bodies.body_of(doc.getObject(n)) is target]
    kinds = [doc.getObject(n).TypeId for n in steps]
    h.check(
        "a timeline of real steps",
        any("Pad" in k for k in kinds)
        and any("Hole" in k for k in kinds)
        and any("Fillet" in k for k in kinds),
        kinds,
    )
    undo = list(doc.UndoNames)[: len(doc.UndoNames) - s["undo_before"]]
    h.check(
        "every step one undo step named after the AI's call",
        undo
        and all(u.startswith("AI: ") for u in undo)
        and len(undo)
        == len(names) - names.count("compare_to_reference") - names.count("describe_reference"),
        undo,
    )
    h.shot("chat-rebuilt")


def finish():
    from sciforge import ai_panel_ui
    from sciforge.ai import chat_ui

    prefs = App.ParamGet(chat_ui.PREFS)
    prefs.RemString("ChatAddress")
    prefs.RemString("ChatProvider")
    if ai_panel_ui.is_shown():
        ai_panel_ui.toggle()
    try:
        s["server"].shutdown()
    except Exception:
        pass
    h.expect_no_errors("the chat rebuild scenario")


h.run(
    "rebuild_chat",
    [setup, a_start, a_message, b_send, b_wait, b_wait, b_wait, b_rebuilt, finish],
)
