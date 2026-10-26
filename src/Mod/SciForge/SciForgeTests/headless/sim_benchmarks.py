# SPDX-License-Identifier: LGPL-2.1-or-later
"""Accuracy benchmarks of SciForge's Static Stress engine (sciforge/simulation.py) against hand
calculations: the evidence outline 0.8 and 7.18 ask for ("golden studies match hand
calculations within a few percent"). Every case is solved at the study's default mesh and at
a finer one, through the same code the SIMULATION workspace and the AI tools use, in real
FreeCAD without a window:

    freecadcmd -c "from SciForgeTests.headless import sim_benchmarks; sim_benchmarks.main()"

tools/sciforge/run_tests.sh runs it with --only sim (and base). It writes sim-benchmarks.json /
.md to SCIFORGE_HEADLESS_OUT (default: FreeCAD's user data folder); SCIFORGE_SIM_FILTER runs
only the cases whose name contains that text. The table is copied into
docs/sciforge/parity/simulation.md ("Benchmarks").

Each case builds its bodies (plain shapes as the base of PartDesign bodies), a study with its
constraints and loads, solves, and checks numbers against the formula with a tolerance:
the cantilever (beam theory), a plate with a hole in tension (Peterson's Kt, Remove rigid body
modes), a thick-walled ring under internal pressure (Lame; Frictionless symmetry planes), a
half model on a symmetry plane against the full model, two bonded materials in series, a
shaft twisted by a moment (tau = T r / J), a bar hanging under gravity (sigma = rho g L),
a remote force (tip deflection with its lever arm), a prescribed displacement (its reaction),
a beam held by two pins and a lug with a bearing load (reactions balance the load).
"""

import json
import math
import os
import platform
import time
import traceback

OMP = "1"  # one CalculiX thread: the timings compare between machines and runs


# -- building ---------------------------------------------------------------------------------
def make_body(doc, shape, label="Body"):
    """A PartDesign body whose solid is `shape` (the base feature of the body; a body takes
    its base feature's geometry without the feature's placement, so a moved shape is baked)."""
    from sciforge import bodies

    base = doc.addObject("Part::Feature", label + "Shape")
    base.Shape = bodies.baked(shape)
    body = doc.addObject("PartDesign::Body", label)
    body.BaseFeature = base
    doc.recompute()
    base.Visibility = False
    return body


def faces(body, pred):
    return ["Face%d" % i for i, f in enumerate(body.Shape.Faces, 1) if pred(f)]


def one_face(body, pred):
    found = faces(body, pred)
    if len(found) != 1:
        raise AssertionError("expected one face, found %d" % len(found))
    return found[0]


def vertex_at(body, point, tol=1e-6):
    import FreeCAD as App

    p = App.Vector(*point)
    for i, v in enumerate(body.Shape.Vertexes, 1):
        if (v.Point - p).Length < tol:
            return "Vertex%d" % i
    raise AssertionError("no corner at %s" % (point,))


def near(value, target, tol=1e-6):
    return abs(value - target) <= tol


def material(study, body):
    from sciforge import simulation as sim

    _name, props, _src = sim.study_material(study, body)
    return props


def shear_modulus(props):
    return props["youngs_mpa"] / (2.0 * (1.0 + props["poisson"]))


# -- reading ----------------------------------------------------------------------------------
def node_values(study, key):
    """[(point (x, y, z), value)] of a result at every node."""
    from sciforge import simulation as sim

    res = sim.results(study)
    values = res.values(key)
    return [((p.x, p.y, p.z), v) for p, v in zip(res.points, values) if p is not None]


def node_vectors(study):
    from sciforge import simulation as sim

    res = sim.results(study)
    return [((p.x, p.y, p.z), (d.x, d.y, d.z)) for p, d in zip(res.points, res.displacements())]


def mean(values):
    values = list(values)
    if not values:
        raise AssertionError("no nodes where the check reads")
    return sum(values) / len(values)


# -- the cases --------------------------------------------------------------------------------
# A case: (name, title, build(doc) -> (study, ctx), [(check name, expected(ctx), got(study,
# ctx, summary), tolerance %)], fine settings). Each runs at the default mesh and at `fine`.
CASES = []


def case(name, title, fine, local=None):
    def register(fn):
        CASES.append({"name": name, "title": title, "build": fn, "fine": fine, "local": local})
        return fn

    return register


@case("cantilever", "Cantilever 100 x 10 x 10 mm, steel, 100 N at the tip", {"size_pct": 3.0})
def cantilever(doc):
    import Part

    from sciforge import simulation as sim

    body = make_body(doc, Part.makeBox(100, 10, 10))
    study = sim.create_study(doc)
    sim.add_item(
        study, "constraint", "fixed", [(body, one_face(body, lambda f: near(f.CenterOfMass.x, 0)))]
    )
    sim.add_item(
        study,
        "load",
        "force",
        [(body, one_face(body, lambda f: near(f.CenterOfMass.x, 100)))],
        {"direction": "vector", "vector": [0, 0, -1], "magnitude": 100.0},
    )
    props = material(study, body)
    E, inertia, F, L, c = props["youngs_mpa"], 10.0 * 10.0**3 / 12.0, 100.0, 100.0, 5.0

    def bending(study, summary):
        # sigma_xx on the top face between 20 and 80 mm over M(x) c / I there (= 1)
        ratios = [
            v / (F * (L - p[0]) * c / inertia)
            for p, v in node_values(study, "sxx")
            if near(p[2], 10.0, 1e-6) and 20.0 <= p[0] <= 80.0
        ]
        return mean(ratios)

    checks = [
        (
            "tip deflection (mm)",
            F * L**3 / (3 * E * inertia),
            lambda s, m: m["stats"]["displacement"]["max"],
            3.0,
        ),
        ("bending stress / (M c / I), top face 20-80 mm", 1.0, bending, 3.0),
        ("reaction at the fixed end (N)", F, lambda s, m: m["reactions"]["Fixed 1"]["total"], 1.0),
    ]
    return study, checks


@case(
    "plate_hole",
    "Plate 200 x 100 x 5 mm with a 20 mm hole, 10 MPa tension both ends, Remove rigid body modes",
    {"size_pct": 5.0},
    local=1.0,
)
def plate_hole(doc):
    import FreeCAD as App
    import Part

    from sciforge import simulation as sim

    W, L, t, d, s = 100.0, 200.0, 5.0, 20.0, 10.0
    plate = Part.makeBox(L, W, t).cut(Part.makeCylinder(d / 2, t, App.Vector(L / 2, W / 2, 0)))
    body = make_body(doc, plate)
    study = sim.create_study(doc)
    sim.set_settings(study, {"remove_rigid": True})
    ends = faces(body, lambda f: near(f.CenterOfMass.x, 0) or near(f.CenterOfMass.x, L))
    sim.add_item(study, "load", "pressure", [(body, e) for e in ends], {"magnitude": -s})
    hole = one_face(body, lambda f: f.Surface.TypeId == "Part::GeomCylinder")
    sim.add_item(study, "mesh", "local", [(body, hole)], {"size": 1.0})
    ratio = d / W
    kt = 3.0 - 3.14 * ratio + 3.667 * ratio**2 - 1.527 * ratio**3  # Peterson / Heywood, net
    expected = kt * s * W / (W - d)
    checks = [
        (
            "max 1st principal stress at the hole (MPa), Kt %.3f on the net section" % kt,
            expected,
            lambda st, m: m["stats"]["principal_1"]["max"],
            5.0,
        ),
    ]
    return study, checks


@case(
    "thick_cylinder",
    "Thick ring, inner 20 / outer 40 mm, 10 MPa inside; quarter model on Frictionless planes",
    {"size_pct": 4.0},
)
def thick_cylinder(doc):
    import FreeCAD as App
    import Part

    from sciforge import simulation as sim

    ri, ro, h, p = 20.0, 40.0, 10.0, 10.0
    ring = Part.makeCylinder(ro, h, App.Vector(0, 0, 0), App.Vector(0, 0, 1), 90).cut(
        Part.makeCylinder(ri, h, App.Vector(0, 0, 0), App.Vector(0, 0, 1), 90)
    )
    body = make_body(doc, ring)
    study = sim.create_study(doc)
    planes = faces(
        body,
        lambda f: f.Surface.TypeId == "Part::GeomPlane",
    )  # the two cuts and both ends: symmetry and plane strain
    sim.add_item(study, "constraint", "frictionless", [(body, f) for f in planes])
    inner = one_face(
        body, lambda f: f.Surface.TypeId == "Part::GeomCylinder" and near(f.Surface.Radius, ri)
    )
    sim.add_item(study, "load", "pressure", [(body, inner)], {"magnitude": p})
    props = material(study, body)
    E, nu = props["youngs_mpa"], props["poisson"]
    hoop = p * (ro**2 + ri**2) / (ro**2 - ri**2)
    u_in = (1 + nu) * p * ri**2 / (E * (ro**2 - ri**2)) * ((1 - 2 * nu) * ri + ro**2 / ri)

    def inner_hoop(study, summary):
        vals = [
            v
            for pt, v in node_values(study, "principal_1")
            if near(math.hypot(pt[0], pt[1]), ri, 1e-3)
        ]
        return mean(vals)

    checks = [
        ("hoop stress at the bore (MPa), Lame", hoop, inner_hoop, 3.0),
        (
            "bore growth (mm), Lame plane strain",
            u_in,
            lambda st, m: m["stats"]["displacement"]["max"],
            3.0,
        ),
    ]
    return study, checks


@case(
    "symmetry_half",
    "Half cantilever on a Frictionless symmetry plane against the full model",
    {"size_pct": 3.0},
)
def symmetry_half(doc):
    import FreeCAD as App
    import Part

    from sciforge import simulation as sim

    full = make_body(doc, Part.makeBox(100, 10, 10), "Full")
    half_shape = Part.makeBox(100, 5, 10)
    half_shape.translate(App.Vector(0, 40, 0))
    half = make_body(doc, half_shape, "Half")
    a = sim.create_study(doc, study_bodies=[full])
    sim.add_item(
        a, "constraint", "fixed", [(full, one_face(full, lambda f: near(f.CenterOfMass.x, 0)))]
    )
    sim.add_item(
        a,
        "load",
        "force",
        [(full, one_face(full, lambda f: near(f.CenterOfMass.x, 100)))],
        {"direction": "vector", "vector": [0, 0, -1], "magnitude": 100.0},
    )
    b = sim.create_study(doc, study_bodies=[half])
    sim.add_item(
        b, "constraint", "fixed", [(half, one_face(half, lambda f: near(f.CenterOfMass.x, 0)))]
    )
    sim.add_item(
        b,
        "constraint",
        "frictionless",
        [(half, one_face(half, lambda f: near(f.CenterOfMass.y, 45)))],
    )
    sim.add_item(
        b,
        "load",
        "force",
        [(half, one_face(half, lambda f: near(f.CenterOfMass.x, 100)))],
        {"direction": "vector", "vector": [0, 0, -1], "magnitude": 50.0},
    )
    holder = {}

    def full_value(key):
        def read(study, summary):
            if "full" not in holder:
                holder["full"] = sim.solve(a, timeout=600)
            return holder["full"]["stats"][key]["max"]

        return read

    checks = [
        (
            "half model tip deflection = full model's (mm)",
            "full:displacement",
            lambda s, m: m["stats"]["displacement"]["max"],
            2.0,
        ),
        (
            "half model max von Mises = full model's (MPa)",
            "full:von_mises",
            lambda s, m: m["stats"]["von_mises"]["max"],
            4.0,
        ),
    ]
    return b, {"checks": checks, "reference": a, "settings_also": [a]}


@case(
    "bonded_bars",
    "Steel and aluminium bars glued end to end (one 0.05 mm apart), 10 kN pull",
    {"size_pct": 3.0},
)
def bonded_bars(doc):
    import FreeCAD as App
    import Part

    from sciforge import simulation as sim

    gap = 0.05
    steel = make_body(doc, Part.makeBox(50, 10, 10), "SteelBar")
    alu_shape = Part.makeBox(50, 10, 10)
    alu_shape.translate(App.Vector(50 + gap, 0, 0))
    alu = make_body(doc, alu_shape, "AluBar")
    study = sim.create_study(doc)
    sim.set_study_material(study, alu, "aluminium")
    sim.add_item(
        study,
        "constraint",
        "frictionless",
        [(steel, one_face(steel, lambda f: near(f.CenterOfMass.x, 0)))],
    )
    sim.add_item(study, "constraint", "fixed", [(steel, vertex_at(steel, (0, 0, 0)))], {"x": False})
    sim.add_item(
        study,
        "constraint",
        "fixed",
        [(steel, vertex_at(steel, (0, 10, 0)))],
        {"x": False, "y": False},
    )
    sim.add_item(
        study,
        "load",
        "force",
        [(alu, one_face(alu, lambda f: near(f.CenterOfMass.x, 100 + gap)))],
        {"direction": "vector", "vector": [1, 0, 0], "magnitude": 10000.0},
    )
    es, ea = material(study, steel)["youngs_mpa"], material(study, alu)["youngs_mpa"]
    F, A = 10000.0, 100.0
    stretch = F * 50 / (es * A) + F * (50 + gap) / (ea * A)

    def end_dx(study, summary):
        return mean(d[0] for p, d in node_vectors(study) if near(p[0], 100 + gap, 1e-4))

    def mid_stress(study, summary):
        return mean(v for p, v in node_values(study, "sxx") if 20 <= p[0] <= 30 or 70 <= p[0] <= 80)

    checks = [
        ("end of the bars moves (mm), two springs in series", stretch, end_dx, 3.0),
        ("stress in both bars (MPa) = F / A", F / A, mid_stress, 3.0),
        ("the two bodies are glued (one contact found)", 1, lambda s, m: len(sim.contacts(s)), 0.0),
    ]
    return study, checks


@case(
    "torsion",
    "Round shaft 20 mm x 100 mm twisted by 10 N m at its end (a Moment)",
    {"size_pct": 4.0},
)
def torsion(doc):
    import Part

    from sciforge import simulation as sim

    r, L, T = 10.0, 100.0, 10000.0
    body = make_body(doc, Part.makeCylinder(r, L))
    study = sim.create_study(doc)
    sim.add_item(
        study, "constraint", "fixed", [(body, one_face(body, lambda f: near(f.CenterOfMass.z, 0)))]
    )
    sim.add_item(
        study,
        "load",
        "moment",
        [(body, one_face(body, lambda f: near(f.CenterOfMass.z, L)))],
        {"direction": "vector", "vector": [0, 0, 1], "magnitude": T},
    )
    props = material(study, body)
    J = math.pi * (2 * r) ** 4 / 32.0
    tau = T * r / J
    twist = T * L / (shear_modulus(props) * J)

    def surface_vm(study, summary):
        return mean(
            v
            for p, v in node_values(study, "von_mises")
            if near(math.hypot(p[0], p[1]), r, 1e-3) and 30 <= p[2] <= 70
        )

    checks = [
        (
            "von Mises on the surface, 30-70 mm (MPa) = sqrt(3) T r / J",
            math.sqrt(3) * tau,
            surface_vm,
            3.0,
        ),
        (
            "rim turns (mm) = T L r / (G J)",
            twist * r,
            lambda s, m: m["stats"]["displacement"]["max"],
            3.0,
        ),
    ]
    return study, checks


@case(
    "hanging_bar",
    "Steel bar 20 x 20 x 200 mm hanging from its top, gravity only",
    {"size_pct": 4.0},
)
def hanging_bar(doc):
    import Part

    from sciforge import simulation as sim

    L = 200.0
    body = make_body(doc, Part.makeBox(20, 20, L))
    study = sim.create_study(doc)
    sim.set_settings(study, {"gravity": {"on": True, "direction": [0, 0, -1]}})
    top = one_face(body, lambda f: near(f.CenterOfMass.z, L))
    sim.add_item(study, "constraint", "frictionless", [(body, top)])
    sim.add_item(study, "constraint", "fixed", [(body, vertex_at(body, (0, 0, L)))], {"z": False})
    sim.add_item(
        study,
        "constraint",
        "fixed",
        [(body, vertex_at(body, (20, 0, L)))],
        {"x": False, "z": False},
    )
    props = material(study, body)
    rho = props["density"] * 1e-12  # kg/m3 -> t/mm3
    g = 9806.65
    E = props["youngs_mpa"]

    def top_stress(study, summary):
        return mean(v for p, v in node_values(study, "szz") if near(p[2], L, 1e-6))

    checks = [
        ("stress at the top (MPa) = rho g L", rho * g * L, top_stress, 3.0),
        (
            "the bottom drops (mm) = rho g L^2 / 2E",
            rho * g * L**2 / (2 * E),
            lambda s, m: m["stats"]["displacement"]["max"],
            3.0,
        ),
        (
            "the hold carries the weight (N) = rho g V",
            rho * g * L * 400.0,
            lambda s, m: m["reactions"]["Frictionless 1"]["total"],
            1.0,
        ),
    ]
    return study, checks


@case(
    "remote_force",
    "Cantilever with 100 N acting 50 mm beyond its tip (a Remote Force)",
    {"size_pct": 3.0},
)
def remote_force(doc):
    import Part

    from sciforge import simulation as sim

    body = make_body(doc, Part.makeBox(100, 10, 10))
    study = sim.create_study(doc)
    sim.add_item(
        study, "constraint", "fixed", [(body, one_face(body, lambda f: near(f.CenterOfMass.x, 0)))]
    )
    sim.add_item(
        study,
        "load",
        "remote_force",
        [(body, one_face(body, lambda f: near(f.CenterOfMass.x, 100)))],
        {"vector": [0, 0, -1], "magnitude": 100.0, "point": [150.0, 5.0, 5.0]},
    )
    props = material(study, body)
    E, inertia, F, L, a = props["youngs_mpa"], 10.0 * 10.0**3 / 12.0, 100.0, 100.0, 50.0
    tip = F * L**3 / (3 * E * inertia) + (F * a) * L**2 / (2 * E * inertia)

    def tip_dz(study, summary):
        return -mean(d[2] for p, d in node_vectors(study) if near(p[0], 100, 1e-6))

    checks = [
        ("tip deflection (mm) = F L^3 / 3EI + F a L^2 / 2EI", tip, tip_dz, 3.0),
        ("reaction (N)", F, lambda s, m: m["reactions"]["Fixed 1"]["total"], 1.0),
    ]
    return study, checks


@case(
    "prescribed",
    "Cantilever whose tip is pushed down 0.2 mm (a Prescribed Displacement)",
    {"size_pct": 3.0},
)
def prescribed(doc):
    import Part

    from sciforge import simulation as sim

    body = make_body(doc, Part.makeBox(100, 10, 10))
    study = sim.create_study(doc)
    sim.add_item(
        study, "constraint", "fixed", [(body, one_face(body, lambda f: near(f.CenterOfMass.x, 0)))]
    )
    sim.add_item(
        study,
        "constraint",
        "displacement",
        [(body, one_face(body, lambda f: near(f.CenterOfMass.x, 100)))],
        {"x": None, "y": None, "z": -0.2},
    )
    props = material(study, body)
    E, inertia, L = props["youngs_mpa"], 10.0 * 10.0**3 / 12.0, 100.0
    force = 3 * E * inertia * 0.2 / L**3
    checks = [
        (
            "force it takes (N) = 3 E I d / L^3",
            force,
            lambda s, m: m["reactions"]["Prescribed Displacement 1"]["total"],
            3.0,
        ),
        ("the tip moved 0.2 mm", 0.2, lambda s, m: m["stats"]["displacement"]["max"], 1.0),
    ]
    return study, checks


@case(
    "pinned_beam",
    "Beam 420 x 20 x 10 mm on two pins 400 mm apart, 1 N/mm on top",
    {"size_pct": 3.0},
)
def pinned_beam(doc):
    import FreeCAD as App
    import Part

    from sciforge import simulation as sim

    span, over, h, b, d, w = 400.0, 10.0, 20.0, 10.0, 6.0, 1.0
    total = span + 2 * over
    shape = Part.makeBox(total, b, h)
    for x in (over, over + span):
        shape = shape.cut(Part.makeCylinder(d / 2, b, App.Vector(x, 0, h / 2), App.Vector(0, 1, 0)))
    body = make_body(doc, shape)
    study = sim.create_study(doc)
    holes = faces(body, lambda f: f.Surface.TypeId == "Part::GeomCylinder")
    sim.add_item(study, "constraint", "pin", [(body, f) for f in holes])
    top = one_face(body, lambda f: near(f.CenterOfMass.z, h))
    sim.add_item(study, "load", "pressure", [(body, top)], {"magnitude": w / b})
    props = material(study, body)
    E, G = props["youngs_mpa"], shear_modulus(props)
    inertia = b * h**3 / 12.0
    bending = w * span**2 * (5 * span**2 - 24 * over**2) / (384 * E * inertia)
    # shear adds M / (kappa G A) between a support and the middle (M from the supports)
    shear = (w * span**2 / 8.0) / ((5.0 / 6.0) * G * b * h)

    def mid_dz(study, summary):
        return -mean(
            d[2]
            for p, d in node_vectors(study)
            if abs(p[0] - total / 2) <= 6 and near(p[2], 0, 1e-6)
        )

    def reactions(study, summary):
        return summary["reactions"]["Pin 1"]["total"]

    checks = [
        ("middle of the span drops (mm), bending + shear", bending + shear, mid_dz, 3.0),
        ("the pins carry the load (N)", w * total, reactions, 1.0),
    ]
    return study, checks


@case(
    "bearing_lug", "Lug fixed at its foot, 1 kN bearing load in its 10 mm hole", {"size_pct": 4.0}
)
def bearing_lug(doc):
    import FreeCAD as App
    import Part

    from sciforge import simulation as sim

    shape = Part.makeBox(40, 10, 60).cut(
        Part.makeCylinder(5, 10, App.Vector(20, 0, 40), App.Vector(0, 1, 0))
    )
    body = make_body(doc, shape)
    study = sim.create_study(doc)
    sim.add_item(
        study, "constraint", "fixed", [(body, one_face(body, lambda f: near(f.CenterOfMass.z, 0)))]
    )
    hole = one_face(body, lambda f: f.Surface.TypeId == "Part::GeomCylinder")
    sim.add_item(
        study, "load", "bearing", [(body, hole)], {"vector": [0, 0, 1], "magnitude": 1000.0}
    )

    def along(study, summary):
        return summary["reactions"]["Fixed 1"]["z"] * -1.0

    def across(study, summary):
        r = summary["reactions"]["Fixed 1"]
        return abs(r["x"]) + abs(r["y"])

    checks = [
        ("the foot holds the load (N, along it)", 1000.0, along, 1.0),
        ("nothing sideways (N)", 0.0, across, 1.0),
    ]
    return study, checks


# -- engine checks (not accuracy: what must hold around a solve) ------------------------------
# Each check(doc, out) appends (name, ok, detail) to `out`; they run after the accuracy cases.
ENGINE_CHECKS = []


def engine_check(name):
    def register(fn):
        ENGINE_CHECKS.append((name, fn))
        return fn

    return register


def _cantilever(doc, label="Body", placement=None, part=None, size_pct=10.0):
    import Part

    from sciforge import simulation as sim

    body = make_body(doc, Part.makeBox(100, 10, 10), label)
    if part is not None:
        part.addObject(body)
    if placement is not None:
        (part or body).Placement = placement
    doc.recompute()
    study = sim.create_study(doc, study_bodies=[body])
    sim.set_settings(study, {"mesh": {"size_pct": size_pct}})
    sim.add_item(
        study, "constraint", "fixed", [(body, one_face(body, lambda f: near(f.CenterOfMass.x, 0)))]
    )
    sim.add_item(
        study,
        "load",
        "force",
        [(body, one_face(body, lambda f: near(f.CenterOfMass.x, 100)))],
        {"direction": "vector", "vector": [0, 0, -1], "magnitude": 100.0},
    )
    return body, study


def _sim_objects(doc):
    from sciforge import simulation as sim

    return sorted(o.Name for o in doc.Objects if sim._type(o) in (sim.RUN, sim.MODEL, sim.HELPER))


@engine_check("cancel at every stage")
def check_cancel(doc, out):
    """Cancel just before each stage runs (the slow ones, mesh and solve, run in the
    background: cancel stops their program)."""
    from sciforge import simulation as sim

    body, study = _cantilever(doc, size_pct=3.0)
    first = sim.solve(study, timeout=600)
    kept = sim.result_object(study)
    objects = _sim_objects(doc)

    def background_done(job):
        return job._thread is None or not job._thread.is_alive()

    def results_step(job):
        step = getattr(job, "_results_step", None)
        return getattr(getattr(step, "func", None), "__name__", None)

    moments = (
        ("model", lambda job: True),  # before the first turn
        ("model's second turn", lambda job: job.stage == "model" and job._checked),
        ("mesh", lambda job: job.stage == "mesh" and not background_done(job)),
        ("input", lambda job: job.stage == "mesh" and background_done(job)),
        # (the input is written over two turns, the results read over three)
        ("input's second turn", lambda job: job.stage == "input" and job._getter is not None),
        ("solve", lambda job: job.stage == "solve" and not background_done(job)),
        ("results", lambda job: job.stage == "solve" and background_done(job)),
        ("results' second turn", lambda job: results_step(job) == "_results_compact"),
        ("results' last turn", lambda job: results_step(job) == "_results_finish"),
    )
    for stage, ready in moments:
        job = sim.Job(study)
        tries = 0
        while job.state == "running" and not ready(job) and tries < 20000:
            tries += 1
            if job._thread is not None and job._thread.is_alive():
                job._thread.join(0.002)
                continue
            job.poll()
        if job.state != "running" or not ready(job):
            out.append(("cancel before %s: got there" % stage, False, (job.state, job.stage)))
            job.cancel()
            job.wait(60)
            continue
        job.cancel()
        job.wait(60)
        out.append(("cancel before %s: cancelled" % stage, job.state == "cancelled", job.message))
        out.append(
            (
                "cancel before %s: temporary folder gone" % stage,
                not os.path.isdir(job.work),
                job.work,
            )
        )
        out.append(
            (
                "cancel before %s: last results and objects kept" % stage,
                sim.result_object(study) is kept
                and sim.summary(study) == first
                and _sim_objects(doc) == objects,
                (_sim_objects(doc), objects),
            )
        )


@engine_check("a failed solve keeps the last results")
def check_failed(doc, out):
    from sciforge import simulation as sim

    body, study = _cantilever(doc)
    first = sim.solve(study, timeout=600)
    kept = sim.result_object(study)
    fixed = sim.items(study, "constraint")[0]
    sim.update_item(fixed, suppressed=True)
    job = sim.Job(study)
    job.wait(120)
    out.append(
        (
            "refused: nothing holds it",
            job.state == "failed" and "Nothing holds" in job.message,
            job.message,
        )
    )
    out.append(
        ("results kept", sim.result_object(study) is kept and sim.summary(study) == first, "")
    )
    out.append(("now out of date", sim.out_of_date(study), ""))
    sim.update_item(fixed, suppressed=False)
    out.append(("back in date", not sim.out_of_date(study), ""))
    # a model held in X only can still move: CalculiX's complaint becomes a sentence
    sim.update_item(fixed, opts={"y": False, "z": False})
    job = sim.Job(study)
    job.wait(300)
    out.append(
        (
            "not held enough: a sentence",
            job.state == "failed" and "not held enough" in job.message,
            job.message,
        )
    )
    out.append(("results still kept", sim.result_object(study) is kept, ""))


@engine_check("Generate Mesh")
def check_mesh_only(doc, out):
    from sciforge import simulation as sim

    body, study = _cantilever(doc)
    summary = sim.solve(study, timeout=600)
    kept = sim.result_object(study)
    sim.set_settings(study, {"mesh": {"size_pct": 5.0}})
    info = sim.generate_mesh(study, timeout=600)
    out.append(
        ("mesh statistics", info["nodes"] > summary["mesh"]["nodes"] and info["smallest"] > 0, info)
    )
    out.append(("results kept next to the new mesh", sim.result_object(study) is kept, ""))
    out.append(
        ("the newest mesh is shown", sim.mesh_object(study).FemMesh.NodeCount == info["nodes"], "")
    )
    out.append(("mesh summary not stale", not sim.mesh_summary(study)["stale"], ""))
    sim.set_settings(study, {"mesh": {"size_pct": 6.0}})
    out.append(("mesh summary stale after a mesh setting", sim.mesh_summary(study)["stale"], ""))
    sim.solve(study, timeout=600)
    out.append(
        ("a solve replaces the Generate Mesh run", sim.run_of(study, "SimMeshRun") is None, "")
    )
    run = sim.run_of(study)
    touched = [o.Name for o in [study] + list(sim._run_members(run)) if "Touched" in o.State]
    out.append(("nothing left needing a recompute after the solve", not touched, touched))


@engine_check("save and reopen")
def check_reopen(doc, out):
    import tempfile

    import FreeCAD as App

    from sciforge import simulation as sim

    body, study = _cantilever(doc, size_pct=3.0)
    summary = sim.solve(study, timeout=600)
    folder = tempfile.mkdtemp(prefix="sciforge-bench-")
    kept_path = os.path.join(folder, "kept.FCStd")
    doc.saveAs(kept_path)
    sim.set_settings(study, {"keep_results": False})
    small_path = os.path.join(folder, "small.FCStd")
    doc.saveAs(small_path)
    sizes = (os.path.getsize(kept_path), os.path.getsize(small_path))
    out.append(
        (
            "file size: %.0f kB with results, %.0f kB without (%d nodes)"
            % (sizes[0] / 1024.0, sizes[1] / 1024.0, summary["mesh"]["nodes"]),
            sizes[1] < sizes[0] / 5,
            sizes,
        )
    )
    name = doc.Name
    App.closeDocument(name)
    again = App.openDocument(kept_path)
    st = sim.studies(again)[0]
    res = sim.results(st)
    out.append(
        ("reopened: results back", res is not None and len(res.values("von_mises")) > 100, "")
    )
    out.append(
        (
            "reopened: same summary, not out of date",
            sim.summary(st) == summary and not sim.out_of_date(st),
            "",
        )
    )
    out.append(
        ("reopened: items and picks", len(sim.items(st)) == 2 and not sim.lost_items(st), "")
    )
    App.closeDocument(again.Name)
    small = App.openDocument(small_path)
    st = sim.studies(small)[0]
    out.append(("without results: the numbers stay", sim.summary(st) == summary, ""))
    out.append(
        (
            "without results: not out of date (keeping them changes nothing)",
            not sim.out_of_date(st),
            "",
        )
    )
    out.append(
        (
            "without results: solve again to see them",
            sim.results(st) is None and sim.results_dropped(st),
            "",
        )
    )
    again = sim.solve(st, timeout=600)
    out.append(
        ("solved again after reopening", sim.results(st) is not None, again["mesh"]["nodes"])
    )
    App.closeDocument(small.Name)


@engine_check("a body in a moved component")
def check_component(doc, out):
    import FreeCAD as App

    from sciforge import simulation as sim

    body, study = _cantilever(doc, "Plain")
    plain = sim.solve(study, timeout=600)
    part = doc.addObject("App::Part", "Component")
    place = App.Placement(App.Vector(200, 50, 30), App.Rotation(App.Vector(0, 0, 1), 90))
    moved, study2 = _cantilever(doc, "Moved", placement=place, part=part)
    summary = sim.solve(study2, timeout=600)
    a, b = plain["stats"]["displacement"]["max"], summary["stats"]["displacement"]["max"]
    out.append(("same bend as unmoved", abs(a - b) <= 0.02 * a, (a, b)))
    at = summary["stats"]["displacement"]["max_at"]
    tip = place.multVec(App.Vector(100, 5, 5))
    out.append(
        (
            "the tip is where the component put it",
            abs(at[0] - tip.x) < 6 and abs(at[1] - tip.y) < 6,
            (at, tip),
        )
    )
    out.append(
        (
            "reaction 100 N",
            abs(summary["reactions"]["Fixed 2"]["total"] - 100) < 0.5,
            summary["reactions"],
        )
    )


@engine_check("two components' bodies with the same name")
def check_same_labels(doc, out):
    """Fusion numbers bodies per component: two components can each have a "Body1". The
    result summary keeps them apart (sim-ui's report)."""
    import FreeCAD as App
    import Part

    from sciforge import simulation as sim

    params = App.ParamGet("User parameter:BaseApp/Preferences/Document")
    allowed = params.GetBool("DuplicateLabels", False)
    params.SetBool("DuplicateLabels", True)  # (SciForge's own setting, theme.py)
    try:
        first = doc.addObject("App::Part", "CompA")
        second = doc.addObject("App::Part", "CompB")
        first.Label, second.Label = "Bracket", "Plate"
        a = make_body(doc, Part.makeBox(100, 10, 10), "SameA")
        b = make_body(doc, Part.makeBox(100, 10, 10, App.Vector(0, 50, 0)), "SameB")
        first.addObject(a)
        second.addObject(b)
        a.Label = "Body1"
        b.Label = "Body1"
        doc.recompute()
        study = sim.create_study(doc, study_bodies=[a, b])
        sim.add_item(
            study,
            "constraint",
            "fixed",
            [(body, one_face(body, lambda f: near(f.CenterOfMass.x, 0))) for body in (a, b)],
        )
        sim.add_item(
            study,
            "load",
            "force",
            [(body, one_face(body, lambda f: near(f.CenterOfMass.x, 100))) for body in (a, b)],
            {"direction": "vector", "vector": [0, 0, -1], "magnitude": 100.0, "per_entity": True},
        )
        summary = sim.solve(study, timeout=600)
        rows = summary.get("bodies", {})
        keys = (sim.body_key(study, a), sim.body_key(study, b))
        out.append(
            (
                "both named Body1, two rows: %s" % ", ".join(sorted(rows)),
                a.Label == b.Label == "Body1" and len(rows) == 2 and keys[0] != keys[1],
                (a.Label, b.Label, sorted(rows), keys),
            )
        )
        out.append(
            (
                "each row is its own body (bends 0.2 mm, as one cantilever)",
                all(
                    k in rows
                    and rows[k].get("name") == body.Name
                    and abs(rows[k]["displacement_max"] - 0.2) <= 0.006
                    for k, body in zip(keys, (a, b))
                ),
                rows,
            )
        )
    finally:
        params.SetBool("DuplicateLabels", allowed)


@engine_check("a body whose middle is a hole, glued to another")
def check_hollow_owners(doc, out):
    """A steel plate with a hole in its middle under a solid aluminium plate, glued: each
    piece of the model keeps its own body, so its own material (the holed plate's centre of
    mass, in the hole, is nearer the other plate: SciForge first went by it)."""
    import FreeCAD as App
    import Part

    from sciforge import simulation as sim

    holed = Part.makeBox(100, 100, 5).cut(Part.makeCylinder(10, 5, App.Vector(50, 50, 0)))
    lower = make_body(doc, holed, "Lower")
    upper = make_body(doc, Part.makeBox(100, 100, 5, App.Vector(0, 0, 5)), "Upper")
    study = sim.create_study(doc, study_bodies=[lower, upper])
    sim.set_study_material(study, upper, "aluminium")
    model, owners = sim.build_model(study)
    right = all(
        owner is (lower if solid.BoundBox.ZMax <= 5 + 1e-6 else upper)
        for solid, owner in zip(model.Solids, owners)
    )
    out.append(
        (
            "each piece of the model belongs to its own plate",
            right and len(owners) == 2,
            [(round(s.BoundBox.ZMax, 3), o.Label) for s, o in zip(model.Solids, owners)],
        )
    )
    sim.add_item(
        study,
        "constraint",
        "fixed",
        [(lower, one_face(lower, lambda f: near(f.CenterOfMass.z, 0)))],
    )
    sim.add_item(
        study,
        "load",
        "pressure",
        [(upper, one_face(upper, lambda f: near(f.CenterOfMass.z, 10)))],
        {"magnitude": 1.0},
    )
    summary = sim.solve(study, timeout=600)
    rows = summary.get("bodies", {})
    out.append(
        (
            "each plate keeps its material in the results",
            rows.get("Lower", {}).get("material", "").startswith("Steel")
            and "lumin" in rows.get("Upper", {}).get("material", ""),
            {k: v.get("material") for k, v in rows.items()},
        )
    )


@engine_check("a design saved while it solves")
def check_saved_mid_solve(doc, out):
    """Saved while CalculiX runs, the design holds that solve's half-made run (its mesh too);
    the next solve removes it, and nothing of a running job is ever removed."""
    import tempfile

    import FreeCAD as App

    from sciforge import simulation as sim

    body, study = _cantilever(doc, size_pct=3.0)
    sim.solve(study, timeout=600)
    job = sim.Job(study)
    tries = 0
    while job.state == "running" and job.stage != "solve" and tries < 20000:
        tries += 1
        if job._thread is not None and job._thread.is_alive():
            job._thread.join(0.002)
            continue
        job.poll()
    out.append(
        (
            "a running job's run is not taken for left over",
            not [o.Name for o in sim._orphans(doc)],
            [o.Name for o in sim._orphans(doc)],
        )
    )
    path = os.path.join(tempfile.mkdtemp(prefix="sciforge-bench-"), "mid.FCStd")
    doc.saveAs(path)
    job.cancel()
    job.wait(60)
    App.closeDocument(doc.Name)
    again = App.openDocument(path)
    try:
        st = sim.studies(again)[0]
        left = [o.Name for o in sim._orphans(again)]
        out.append(("reopened: the half-made run is in the file", bool(left), left))
        sim.solve(st, timeout=600)
        out.append(
            (
                "the next solve removes it and solves",
                not sim._orphans(again) and sim.results(st) is not None,
                [o.Name for o in sim._orphans(again)],
            )
        )
    finally:
        App.closeDocument(again.Name)


@engine_check("undo steps opened while it solves")
def check_steps_between_turns(doc, out):
    """Someone opens an undo step before every turn of the solve (a command running between
    the timer's ticks): the step is closed before the turn changes anything, so undoing them
    all leaves the solve's results."""
    from sciforge import simulation as sim

    body, study = _cantilever(doc)
    doc.UndoMode = 1
    job = sim.Job(study)
    turns = 0
    while job.state == "running" and turns < 20000:
        if job._thread is not None and job._thread.is_alive():
            job._thread.join(0.002)
            continue
        doc.openTransaction("Someone's step %d" % turns)
        turns += 1
        job.poll()
    if getattr(doc, "HasPendingTransaction", False):
        doc.commitTransaction()
    out.append(("solved", job.state == "done", job.message))
    for _ in range(int(doc.UndoCount)):
        doc.undo()
    out.append(
        (
            "every step undone: the results stay (%d turns)" % turns,
            sim.results(study) is not None and sim.result_object(study) is not None,
            list(doc.UndoNames),
        )
    )


@engine_check("a change while it solves")
def check_change_during(doc, out):
    """The results are of the study as the solve started: a load changed while CalculiX runs
    leaves them out of date (sim-ui's report)."""
    from sciforge import simulation as sim

    body, study = _cantilever(doc, size_pct=3.0)
    job = sim.Job(study)
    tries = 0
    while job.state == "running" and job.stage != "solve" and tries < 20000:
        tries += 1
        if job._thread is not None and job._thread.is_alive():
            job._thread.join(0.002)
            continue
        job.poll()
    load = sim.items(study, "load")[0]
    sim.update_item(load, opts={"magnitude": 200.0})
    job.wait(600)
    out.append(("solved", job.state == "done", job.message))
    out.append(("out of date: the load changed while it solved", sim.out_of_date(study), ""))
    sim.solve(study, timeout=600)
    out.append(("solved again: up to date", not sim.out_of_date(study), ""))


@engine_check("a deleted body")
def check_deleted_body(doc, out):
    import FreeCAD as App
    import Part

    from sciforge import simulation as sim

    body, study = _cantilever(doc)
    other = make_body(doc, Part.makeBox(10, 10, 10, App.Vector(0, 50, 0)), "Other")
    sim.add_item(
        study,
        "load",
        "pressure",
        [(other, one_face(other, lambda f: near(f.CenterOfMass.z, 10)))],
        {"magnitude": 1},
    )
    study.SimBodies = [body]
    checks = sim.precheck(study)
    out.append(
        (
            "a load on a body the study leaves out: refused, naming both",
            any("Pressure 1 is on Other" in t and "leaves out" in t for _l, t in checks),
            checks,
        )
    )
    study.SimBodies = [body, other]
    doc.removeObject(other.Name)
    doc.removeObject("OtherShape")
    doc.recompute()
    checks = sim.precheck(study)
    lost = [t for level, t in checks if level == "error" and "lost what it was on" in t]
    out.append(
        (
            "the pre-check names the load that lost its face",
            len(lost) == 1 and "Pressure" in lost[0],
            checks,
        )
    )
    job = sim.Job(study)
    job.wait(120)
    out.append(
        (
            "the solve refuses with that sentence",
            job.state == "failed" and "lost" in job.message,
            job.message,
        )
    )


@engine_check("a solve is no undo step")
def check_undo(doc, out):
    import FreeCAD as App

    from sciforge import simulation as sim

    doc.UndoMode = 1
    doc.openTransaction("Make beam")
    body, study = _cantilever(doc)
    doc.commitTransaction()
    before = list(doc.UndoNames)
    doc.openTransaction("Left open")  # (a dialog's undo step, not closed yet)
    sim.solve(study, timeout=600)
    after = list(doc.UndoNames)
    out.append(("the undo list did not grow with the solve", after == before, (before, after)))
    out.append(
        ("no undo step left open", not App.getActiveTransaction(), App.getActiveTransaction())
    )
    name = study.Name
    doc.undo()
    out.append(("undo takes the setup back", doc.getObject(name) is None, list(doc.UndoNames)))
    doc.redo()
    study = doc.getObject(name)
    out.append(
        (
            "redo brings it back with its results",
            study is not None and sim.results(study) is not None and not sim.out_of_date(study),
            list(doc.RedoNames),
        )
    )


@engine_check("Netgen when Gmsh fails")
def check_netgen(doc, out):
    from sciforge import simulation as sim

    body, study = _cantilever(doc)
    real = sim._binary

    def broken(name):
        if name == "gmsh":
            return "/bin/false" if os.name != "nt" else real(name)
        return real(name)

    sim._binary = broken
    try:
        job = sim.Job(study)
        job.wait(600)
    finally:
        sim._binary = real
    if os.name == "nt":
        out.append(("(skipped on Windows)", True, ""))
        return
    out.append(
        (
            "solved with Netgen",
            job.state == "done" and job.summary["mesh"].get("mesher") == "netgen",
            job.message,
        )
    )
    out.append(("a note says so", any("Netgen" in n for n in (job.notes or [])), job.notes))
    tip = (job.summary or {}).get("stats", {}).get("displacement", {}).get("max")
    out.append(
        ("Netgen's mesh bends the same (3 %)", tip is not None and abs(tip - 0.2) < 0.006, tip)
    )


@engine_check("adaptive mesh refinement")
def check_adaptive(doc, out):
    """The plate with a hole of the accuracy cases, without a local mesh control, at the
    default mesh: adaptive refinement makes the elements where the stress changes the most
    smaller, solve after solve, until the peak stress settles; it ends nearer Peterson's Kt
    than the first solve."""
    import FreeCAD as App
    import Part

    from sciforge import simulation as sim

    W, L, t, d, s = 100.0, 200.0, 5.0, 20.0, 10.0
    plate = Part.makeBox(L, W, t).cut(Part.makeCylinder(d / 2, t, App.Vector(L / 2, W / 2, 0)))
    body = make_body(doc, plate)
    study = sim.create_study(doc)
    sim.set_settings(
        study,
        {
            "remove_rigid": True,
            "adaptive": {
                "level": "custom",
                "passes": 4,
                "tolerance": 2.0,
                "portion": 10.0,
                "result": "principal_1",
            },
        },
    )
    ends = faces(body, lambda f: near(f.CenterOfMass.x, 0) or near(f.CenterOfMass.x, L))
    sim.add_item(study, "load", "pressure", [(body, e) for e in ends], {"magnitude": -s})
    ratio = d / W
    kt = 3.0 - 3.14 * ratio + 3.667 * ratio**2 - 1.527 * ratio**3
    expected = kt * s * W / (W - d)
    summary = sim.solve(study, timeout=1200)
    passes = (summary.get("adaptive") or {}).get("passes") or []
    out.append(("several solves", len(passes) >= 2, passes))
    out.append(
        (
            "each solve on a finer mesh",
            all(b["nodes"] > a["nodes"] for a, b in zip(passes, passes[1:])),
            [p["nodes"] for p in passes],
        )
    )
    first = abs(passes[0]["value"] - expected) / expected if passes else 1.0
    last = abs(summary["stats"]["principal_1"]["max"] - expected) / expected
    out.append(
        (
            "the peak stress ends nearer Kt: first %.1f %% off, last %.1f %% (within 5 %%)"
            % (first * 100, last * 100),
            last < first and last <= 0.05,
            [p["value"] for p in passes],
        )
    )
    out.append(("a note says so", any("Adaptive" in n for n in summary["notes"]), summary["notes"]))


@engine_check("contacts and loose bodies")
def check_contacts(doc, out):
    import FreeCAD as App
    import Part

    from sciforge import simulation as sim

    a = make_body(doc, Part.makeBox(50, 10, 10), "A")
    b = make_body(doc, Part.makeBox(50, 10, 10, App.Vector(50.05, 0, 0)), "B")
    make_body(doc, Part.makeBox(50, 10, 10, App.Vector(100.6, 0, 0)), "C")
    make_body(doc, Part.makeBox(10, 10, 10, App.Vector(40, 5, 0)), "D")  # overlaps A
    study = sim.create_study(doc)
    sim.add_item(
        study, "constraint", "fixed", [(a, one_face(a, lambda f: near(f.CenterOfMass.x, 0)))]
    )
    sim.add_item(
        study,
        "load",
        "force",
        [(b, one_face(b, lambda f: near(f.CenterOfMass.z, 10)))],
        {"magnitude": 10.0},
    )
    pairs = sorted((p.Label, q.Label) for p, q, _k in sim.contacts(study))
    out.append(
        (
            "0.05 mm apart is glued, 0.55 mm is not",
            ("A", "B") in pairs and not any("C" in p for p in pairs),
            pairs,
        )
    )
    checks = sim.precheck(study)
    text = " ".join(t for _l, t in checks)
    out.append(("C would fly away: an error naming it", "C is not held" in text, checks))
    out.append(
        (
            "A and D overlap: a warning",
            any(l == "warning" and "A and D overlap" in t for l, t in checks),
            checks,
        )
    )
    # the contacts are remembered per geometry (the pre-check runs after every command):
    # moving a body or changing its shape is seen at once
    b.Placement = App.Placement(App.Vector(1, 0, 0), App.Rotation())
    doc.recompute()
    moved = sorted((p.Label, q.Label) for p, q, _k in sim.contacts(study))
    b.Placement = App.Placement()
    doc.recompute()
    back = sorted((p.Label, q.Label) for p, q, _k in sim.contacts(study))
    out.append(
        (
            "B moved 1 mm away: no longer glued; moved back: glued again",
            ("A", "B") not in moved and ("A", "B") in back and back == pairs,
            (moved, back),
        )
    )
    b.BaseFeature.Shape = Part.makeBox(49, 10, 10, App.Vector(51, 0, 0))
    doc.recompute()
    shorter = sorted((p.Label, q.Label) for p, q, _k in sim.contacts(study))
    out.append(("B made shorter, 1 mm off A: not glued", ("A", "B") not in shorter, shorter))


# -- running ----------------------------------------------------------------------------------
def _close(doc):
    import FreeCAD as App

    try:
        App.closeDocument(doc.Name)
    except Exception:
        pass


def run_case(entry, level):
    """Rows for one case at one mesh level ("default" / "fine")."""
    import FreeCAD as App

    from sciforge import simulation as sim

    doc = App.newDocument("Bench_%s_%s" % (entry["name"], level))
    rows = []
    try:
        built = entry["build"](doc)
        study, extra = built
        if isinstance(extra, dict):
            checks = extra["checks"]
            also = extra.get("settings_also", [])
            reference = extra.get("reference")
        else:
            checks, also, reference = extra, [], None
        if level == "fine":
            for st in [study] + also:
                sim.set_settings(st, {"mesh": dict(entry["fine"])})
            if entry.get("local"):
                for item in sim.items(study, "mesh"):
                    data = sim.item_data(item)["options"]
                    sim.update_item(item, opts={"size": float(data["size"]) / 2.0})
        start = time.time()
        summary = sim.solve(study, timeout=900)
        seconds = time.time() - start
        ref_summary = None
        for name, expected, got, tol in checks:
            try:
                if isinstance(expected, str) and expected.startswith("full:"):
                    if ref_summary is None:
                        ref_summary = sim.solve(reference, timeout=900)
                    expected = ref_summary["stats"][expected[5:]]["max"]
                value = got(study, summary)
                if tol == 0.0:
                    ok = value == expected
                    error = 0.0 if ok else 100.0
                elif expected == 0:
                    error = abs(value)
                    ok = error <= tol
                else:
                    error = abs(value - expected) / abs(expected) * 100.0
                    ok = error <= tol
                rows.append(
                    {
                        "case": entry["name"],
                        "title": entry["title"],
                        "mesh": level,
                        "check": name,
                        "expected": expected,
                        "got": value,
                        "error_pct": round(error, 3),
                        "tolerance_pct": tol,
                        "nodes": summary["mesh"]["nodes"],
                        "elements": summary["mesh"]["elements"],
                        "seconds": round(seconds, 2),
                        "status": "pass" if ok else "fail",
                    }
                )
            except Exception as exc:
                rows.append(_error_row(entry, level, name, exc))
    except Exception as exc:
        rows.append(_error_row(entry, level, "solve", exc))
    finally:
        _close(doc)
    return rows


def _error_row(entry, level, name, exc):
    return {
        "case": entry["name"],
        "title": entry["title"],
        "mesh": level,
        "check": name,
        "expected": None,
        "got": None,
        "error_pct": None,
        "tolerance_pct": None,
        "nodes": None,
        "elements": None,
        "seconds": None,
        "status": "fail",
        "problem": "%s\n%s" % (exc, traceback.format_exc()),
    }


def markdown(report):
    lines = [
        "# Static Stress accuracy benchmarks",
        "",
        "FreeCAD %s, %s, CalculiX on %s thread(s). %d checks: %s"
        % (
            report["freecad"],
            report["platform"],
            OMP,
            len(report["rows"]),
            "PASS" if report["passed"] else "FAIL",
        ),
        "",
        "| Case | Mesh | Check | Hand calculation | SciForge | Error % | Tolerance % | Nodes | "
        "Solve (s) | Result |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in report["rows"]:
        lines.append(
            "| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |"
            % (
                r["case"],
                r["mesh"],
                r["check"],
                _num(r["expected"]),
                _num(r["got"]),
                _num(r["error_pct"]),
                _num(r["tolerance_pct"]),
                r["nodes"] if r["nodes"] is not None else "",
                _num(r["seconds"]),
                r["status"].upper(),
            )
        )
    if report.get("engine"):
        lines += ["", "## Engine checks", "", "| Check | | Result |", "|---|---|---|"]
        for r in report["engine"]:
            lines.append("| %s | %s | %s |" % (r["case"], r["check"], r["status"].upper()))
    return "\n".join(lines) + "\n"


def _num(value):
    if value is None:
        return ""
    if isinstance(value, (int,)) and not isinstance(value, bool):
        return str(value)
    try:
        return "%.4g" % value
    except TypeError:
        return str(value)


def main():
    import FreeCAD as App

    os.environ["OMP_NUM_THREADS"] = OMP
    out_dir = os.environ.get("SCIFORGE_HEADLESS_OUT") or App.getUserAppDataDir()
    os.makedirs(out_dir, exist_ok=True)
    wanted = os.environ.get("SCIFORGE_SIM_FILTER", "")
    report = {
        "freecad": ".".join(App.Version()[:3]),
        "platform": platform.platform(),
        "rows": [],
    }
    for entry in CASES:
        if wanted and wanted not in entry["name"]:
            continue
        for level in ("default", "fine"):
            rows = run_case(entry, level)
            report["rows"] += rows
            for r in rows:
                App.Console.PrintMessage(
                    "[SciForge] sim %s %s/%s %s: expected %s got %s (%s %%, tolerance %s %%) %s\n"
                    % (
                        r["status"].upper(),
                        r["case"],
                        r["mesh"],
                        r["check"],
                        _num(r["expected"]),
                        _num(r["got"]),
                        _num(r["error_pct"]),
                        _num(r["tolerance_pct"]),
                        (r.get("problem") or "")[:600],
                    )
                )
    report["engine"] = []
    for name, fn in ENGINE_CHECKS:
        if wanted and wanted not in name:
            continue
        doc = App.newDocument("Engine")
        doc_name = doc.Name
        found = []
        start = time.time()
        try:
            fn(doc, found)
        except Exception as exc:
            found.append(("raised", False, "%s\n%s" % (exc, traceback.format_exc())))
        finally:
            if doc_name in App.listDocuments():
                App.closeDocument(doc_name)
        for check, ok, detail in found:
            row = {
                "case": name,
                "check": check,
                "status": "pass" if ok else "fail",
                "detail": str(detail)[:600],
                "seconds": round(time.time() - start, 2),
            }
            report["engine"].append(row)
            App.Console.PrintMessage(
                "[SciForge] sim %s engine/%s: %s %s\n"
                % (row["status"].upper(), name, check, "" if ok else row["detail"])
            )
    report["passed"] = (
        bool(report["rows"] or report["engine"])
        and all(r["status"] == "pass" for r in report["rows"])
        and all(r["status"] == "pass" for r in report["engine"])
    )
    with open(os.path.join(out_dir, "sim-benchmarks.json"), "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    with open(os.path.join(out_dir, "sim-benchmarks.md"), "w", encoding="utf-8") as handle:
        handle.write(markdown(report))
    App.Console.PrintMessage(
        "[SciForge] sim summary: %d checks, %d failed\n"
        % (
            len(report["rows"]) + len(report["engine"]),
            len([r for r in report["rows"] + report["engine"] if r["status"] != "pass"]),
        )
    )
    return report
