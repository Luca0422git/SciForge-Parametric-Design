# SPDX-License-Identifier: LGPL-2.1-or-later
"""The actions of the simulate AI tools (beta 3, builder sim-core; the catalogue is
sciforge/ai/catalog/simulate_tools.py): Static Stress studies set up, solved and read with the
same engine as the SIMULATION workspace (sciforge/simulation.py). Setting a study up is one
undo step per call; a solve is none (its results are not part of the design's history)."""

from .. import bridge_core
from ..executor import UserError, json_result
from . import action


def _sim():
    from ... import simulation

    return simulation


def _core():
    from ... import simulation_core

    return simulation_core


def _study(ctx, ident=None):
    """The study an id or name names; without one the newest study."""
    sim = _sim()
    doc = ctx.need_doc()
    found = sim.studies(doc)
    if not found:
        raise UserError("The design has no simulation study yet: call create_study first.")
    if not ident:
        return found[-1]
    for study in found:
        if ident in (study.Name, study.Label):
            return study
    raise UserError(
        "There is no study %r: the studies are %s."
        % (ident, ", ".join("%s (id %s)" % (s.Label, s.Name) for s in found))
    )


def _body(ctx, ident):
    from ... import bodies

    if ident:
        return ctx.body_of(ident)
    body = ctx.host.find_body(ctx.need_doc())
    if body is None or not bodies.has_solid(body):
        raise UserError('There is no active body with a solid: give the pick an "of".')
    return body


def _refs(ctx, picks, bodies_too=False):
    """[(body, "Face3"...)] of the tool's picks (a whole body: (body, ""))."""
    from .. import geometry_facts as gf
    from ..ops import selectors

    refs = []
    for i, pick in enumerate(picks or []):
        where = "on[%d]" % i
        if "body" in pick:
            if not bodies_too:
                raise UserError("%s: pick faces, edges or corners, not a whole body." % where)
            refs.append((ctx.body_of(pick["body"]), ""))
            continue
        body = _body(ctx, pick.get("of"))
        tip = getattr(body, "Tip", None)
        source = tip if tip is not None and not tip.Shape.isNull() else body
        shape = source.Shape
        try:
            if "face" in pick:
                names = selectors.select(shape, pick["face"], "faces")
            elif "edge" in pick:
                names = selectors.select(shape, pick["edge"], "edges")
            elif "vertex" in pick:
                names = gf.select_vertices(shape, pick["vertex"])
            else:
                raise UserError("%s: give face, edge or vertex." % where)
        except (selectors.SelectionError, KeyError, ValueError) as exc:
            raise UserError("%s: the selector does not fit body %s: %s." % (where, body.Name, exc))
        if not names:
            raise UserError(
                "%s picked nothing on body %s: query_geometry shows what is there."
                % (where, body.Name)
            )
        refs += [(body, name) for name in names]
    return refs


def _add(ctx, args, category, kind, opts, bodies_too=False):
    sim = _sim()
    study = _study(ctx, args.get("study"))
    refs = _refs(ctx, args.get("on"), bodies_too)

    def work():
        return sim.add_item(study, category, kind, refs, opts, args.get("label"))

    try:
        item = ctx.change(work)
    except _core().SimulationError as exc:
        raise UserError(str(exc))
    text = _core().describe(category, kind, sim.item_data(item)["options"])
    where = ", ".join("%s.%s" % (b.Name, s) if s else b.Name for b, s in refs)
    return item, study, text, where


@action("create_study")
def create_study(ctx, args):
    sim = _sim()
    doc = ctx.need_doc()
    chosen = [ctx.body_of(b) for b in args.get("bodies") or []]
    try:
        study = ctx.change(
            lambda: sim.create_study(doc, "static_stress", args.get("label"), chosen or None)
        )
    except _core().SimulationError as exc:
        raise UserError(str(exc))
    names = ", ".join(b.Label for b in sim.study_bodies(study)) or "no body yet"
    return bridge_core.result(
        "Done: new Static Stress study %r (id %r) of %s. Next: add_constraint (where it is "
        "held), add_load (what pushes on it), then solve_study." % (study.Label, study.Name, names)
    )


@action("add_constraint")
def add_constraint(ctx, args):
    kind = args["kind"]
    opts = {}
    if kind == "fixed":
        opts = {axis: bool(args.get(axis, True)) for axis in ("x", "y", "z")}
    elif kind == "displacement":
        opts = {axis: args.get(axis) for axis in ("x", "y", "z")}
    elif kind == "pin":
        opts = {
            "radial": bool(args.get("radial", True)),
            "axial": bool(args.get("axial", True)),
            "tangential": bool(args.get("tangential", False)),
        }
    item, study, text, where = _add(ctx, args, "constraint", kind, opts)
    return bridge_core.result(
        "Done: %s %r (id %r) in %s, on %s." % (text, item.Label, item.Name, study.Label, where)
    )


@action("add_load")
def add_load(ctx, args):
    kind = args["kind"]
    opts = {"magnitude": float(args["magnitude"]), "flip": bool(args.get("flip", False))}
    if kind in ("force", "moment"):
        opts["direction"] = args.get("direction") or ("vector" if "vector" in args else "normal")
        opts["per_entity"] = bool(args.get("per_entity", False))
    if "vector" in args:
        opts["vector"] = [float(c) for c in args["vector"]]
    if kind == "remote_force":
        opts["point"] = [float(c) for c in args["point"]]
    item, study, text, where = _add(ctx, args, "load", kind, opts)
    return bridge_core.result(
        "Done: %s %r (id %r) in %s, on %s." % (text, item.Label, item.Name, study.Label, where)
    )


@action("local_mesh_control")
def local_mesh_control(ctx, args):
    item, study, text, where = _add(
        ctx, args, "mesh", "local", {"size": float(args["size"])}, bodies_too=True
    )
    return bridge_core.result(
        "Done: %s %r (id %r) in %s, on %s." % (text, item.Label, item.Name, study.Label, where)
    )


def _material_row(name, props, source):
    keys = ("youngs_mpa", "poisson", "density", "yield_mpa", "ultimate_mpa")
    row = {"material": name, "from": "this study" if source == "study" else "the body"}
    row.update({k: props.get(k) for k in keys})
    if props.get("filled"):
        row["filled_in"] = list(props["filled"])
    return row


@action("set_study_material")
def set_study_material(ctx, args):
    from ... import material

    sim = _sim()
    study = _study(ctx, args.get("study"))
    body = ctx.body_of(args["body"])
    if body not in sim.study_bodies(study):
        raise UserError("%s is not in %s." % (body.Label, study.Label))
    key = args["material"]
    if key == "same_as_model":
        key = None
    elif material.entry(key) is None:
        keys = [row[0] for row in material.LIBRARY]
        raise UserError("There is no material %r: use one of %s." % (key, ", ".join(keys)))

    def work():
        sim.set_study_material(study, body, key)
        if args.get("safety_basis"):
            sim.set_settings(study, {"safety_basis": args["safety_basis"]})

    try:
        ctx.change(work)
    except _core().SimulationError as exc:
        raise UserError(str(exc))
    name, props, source = sim.study_material(study, body)
    row = _material_row(name, props, source)
    row["safety_basis"] = sim.settings(study)["safety_basis"]
    return json_result(
        row, "Done: %s is %s in %s (units MPa, kg/m3)." % (body.Label, name, study.Label)
    )


_SETTING_KEYS = {
    "mesh_size": ("mesh", "size_pct"),
    "mesh_size_mm": ("mesh", "size_mm"),
    "element_order": ("mesh", "order"),
    "curved_elements": ("mesh", "curved"),
    "remove_rigid_body_modes": (None, "remove_rigid"),
    "contact_tolerance": (None, "contact_tolerance"),
    "safety_basis": (None, "safety_basis"),
    "keep_results": (None, "keep_results"),
}


@action("study_settings")
def study_settings(ctx, args):
    sim = _sim()
    study = _study(ctx, args.get("study"))
    change = {}
    for key, (group, name) in _SETTING_KEYS.items():
        if key in args:
            value = args[key]
            if group:
                change.setdefault(group, {})[name] = value
            else:
                change[name] = value
    if "gravity" in args:
        change.setdefault("gravity", {})["on"] = bool(args["gravity"])
    if "gravity_direction" in args:
        try:
            change.setdefault("gravity", {})["direction"] = _core().unit_vector(
                args["gravity_direction"]
            )
        except _core().SimulationError as exc:
            raise UserError(str(exc))
    if change:
        ctx.change(lambda: sim.set_settings(study, change))
        text = "Done: %s's settings changed." % study.Label
    else:
        text = "%s's settings (nothing changed)." % study.Label
    s = sim.settings(study)
    out = {
        "study": study.Label,
        "id": study.Name,
        "mesh_size": s["mesh"]["size_pct"],
        "mesh_size_mm": s["mesh"]["size_mm"],
        "element_order": s["mesh"]["order"],
        "curved_elements": s["mesh"]["curved"],
        "gravity": s["gravity"]["on"],
        "gravity_direction": s["gravity"]["direction"],
        "remove_rigid_body_modes": s["remove_rigid"],
        "contact_tolerance": s["contact_tolerance"],
        "safety_basis": s["safety_basis"],
        "keep_results": s["keep_results"],
        "local_mesh_controls": [i.Label for i in sim.items(study, "mesh")],
    }
    return json_result(out, text)


@action("precheck_study")
def precheck_study(ctx, args):
    sim = _sim()
    study = _study(ctx, args.get("study"))
    checks = sim.precheck(study)
    levels = [level for level, _text in checks]
    verdict = "cannot solve" if "error" in levels else ("caution" if levels else "ready")
    out = {
        "study": study.Label,
        "id": study.Name,
        "verdict": verdict,
        "messages": [{"level": level, "text": text} for level, text in checks],
        "constraints": [i.Label for i in sim.items(study, "constraint") if not i.Suppressed],
        "loads": [i.Label for i in sim.items(study, "load") if not i.Suppressed],
        "gravity": sim.settings(study)["gravity"]["on"],
        "bodies": [b.Label for b in sim.study_bodies(study)],
        "contacts": [[a.Label, b.Label, kind] for a, b, kind in sim.contacts(study)],
    }
    words = {
        "ready": "ready to solve",
        "caution": "it can solve, but read the warnings",
        "cannot solve": "it cannot solve yet",
    }[verdict]
    return json_result(out, "%s: %s." % (study.Label, words))


def _verdict(stats, bodies_out, target):
    """(lowest safety factor, body, point, sentence) of a solve summary."""
    core = _core()
    safety = stats.get("safety") or {}
    low = safety.get("min")
    if low is None:
        return (
            None,
            None,
            None,
            (
                "No safety factor: the study's materials have no strength for its safety basis "
                "(yield or ultimate tensile)."
            ),
        )
    at = safety.get("min_at")
    if low >= core.SAFETY_CAP:
        return (
            low,
            None,
            None,
            (
                "The safety factor is %s or more everywhere (shown capped at %s): the part carries "
                "almost no load for its strength; meets %s."
                % (core.fmt(core.SAFETY_CAP), core.fmt(core.SAFETY_CAP), core.fmt(target, 3))
            ),
        )
    body = None
    for label, row in (bodies_out or {}).items():
        value = row.get("safety_min")
        if value is not None and abs(value - low) <= 1e-9 * max(1.0, abs(low)):
            body = label
            break
    where = "(%s)" % ", ".join(core.fmt(c, 4) for c in at) if at else "(?)"
    text = "Lowest safety factor %s at %s mm%s: %s %s." % (
        core.fmt(low, 3),
        where,
        (" on %s" % body) if body else "",
        "meets" if low >= target else "below",
        core.fmt(target, 3),
    )
    if low < 1.0:
        text += " Below 1 the part would yield (bend for good) there: add material or choose a "
        text += "stronger material."
    return low, body, at, text


@action("solve_study")
def solve_study(ctx, args):
    sim = _sim()
    core = _core()
    study = _study(ctx, args.get("study"))
    timeout = float(args.get("timeout", 600))
    job = sim.Job(study)
    state = job.wait(timeout)
    if state != "done":
        raise UserError("Not solved: %s" % job.message)
    summary = job.summary
    stats = summary["stats"]
    low, body, at, verdict = _verdict(stats, summary.get("bodies"), 2.0)
    vm = stats.get("von_mises", {})
    disp = stats.get("displacement", {})
    text = (
        "Done: %s solved (%d nodes, %d elements). %s Largest von Mises stress %s MPa, "
        "largest displacement %s mm. study_results has every number."
        % (
            study.Label,
            summary["mesh"]["nodes"],
            summary["mesh"]["elements"],
            verdict,
            core.fmt(vm.get("max"), 4),
            core.fmt(disp.get("max"), 4),
        )
    )
    if summary.get("notes"):
        text += " Notes: " + " ".join(summary["notes"])
    return bridge_core.result(text)


@action("study_results")
def study_results(ctx, args):
    sim = _sim()
    core = _core()
    doc = ctx.need_doc()
    if not args.get("study") and len(sim.studies(doc)) > 1:
        rows = [
            {
                "study": s.Label,
                "id": s.Name,
                "solved": bool(sim.summary(s)),
                "out_of_date": sim.out_of_date(s),
            }
            for s in sim.studies(doc)
        ]
        return json_result(
            {"studies": rows}, "The design has %d studies: give study for its results." % len(rows)
        )
    study = _study(ctx, args.get("study"))
    summary = sim.summary(study)
    if not summary:
        raise UserError("%s has not been solved yet: call solve_study first." % study.Label)
    target = float(args.get("target", 2.0))
    wanted = args.get("results") or [k for k, _t, _u in core.RESULTS]
    results = {}
    for key in wanted:
        st = summary["stats"].get(key)
        if not st:
            continue
        results[key] = {
            "title": core.result_title(key),
            "unit": core.result_unit(key),
            "min": st["min"],
            "min_at": st.get("min_at"),
            "max": st["max"],
            "max_at": st.get("max_at"),
        }
    low, body, at, verdict = _verdict(summary["stats"], summary.get("bodies"), target)
    out = {
        "study": study.Label,
        "id": study.Name,
        "solved": True,
        "out_of_date": sim.out_of_date(study),
        "verdict": verdict,
        "safety": {"lowest": low, "at": at, "body": body, "target": target},
        "results": results,
        "bodies": summary.get("bodies", {}),
        "reactions": summary.get("reactions", {}),
        "mesh": summary.get("mesh", {}),
        "safety_basis": summary.get("safety_basis"),
        "notes": summary.get("notes", []),
        "units": "mm, N, MPa",
    }
    text = verdict
    if out["out_of_date"]:
        text = "OUT OF DATE (the design or the study changed since the solve: solve again). " + text
    return json_result(out, text)


@action("delete_study")
def delete_study(ctx, args):
    sim = _sim()
    study = _study(ctx, args["study"])
    label = study.Label
    ctx.change(lambda: sim.delete_study(study))
    return bridge_core.result("Done: %s deleted with its constraints, loads and results." % label)
