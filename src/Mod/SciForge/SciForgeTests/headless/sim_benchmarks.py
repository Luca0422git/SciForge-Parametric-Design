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
    report["passed"] = bool(report["rows"]) and all(r["status"] == "pass" for r in report["rows"])
    with open(os.path.join(out_dir, "sim-benchmarks.json"), "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    with open(os.path.join(out_dir, "sim-benchmarks.md"), "w", encoding="utf-8") as handle:
        handle.write(markdown(report))
    App.Console.PrintMessage(
        "[SciForge] sim summary: %d checks, %d failed\n"
        % (len(report["rows"]), len([r for r in report["rows"] if r["status"] != "pass"]))
    )
    return report
