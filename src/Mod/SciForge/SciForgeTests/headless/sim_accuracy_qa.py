# SPDX-License-Identifier: LGPL-2.1-or-later
"""Independent accuracy checks of SciForge's Static Stress engine (beta 3 QA, sim-engine-qa):
hand-calculated cases written by the QA agent, not by the engine's builder (its own cases are
sim_benchmarks.py). Every case runs through the engine's public API (sciforge/simulation.py)
at the study's default mesh and at a finer one; a few run through the AI tools
(sciforge/ai/actions/simulate_actions.py) the way an AI app calls them. Real FreeCAD without a
window:

    freecadcmd -c "from SciForgeTests.headless import sim_accuracy_qa; sim_accuracy_qa.main()"

tools/sciforge/run_tests.sh runs it with --only sim (and base), after sim_benchmarks. It writes
sim-accuracy-qa.json / .md to SCIFORGE_HEADLESS_OUT; SCIFORGE_SIM_FILTER runs only the cases and
checks whose name contains that text.

Every hand calculation names its formula and its source next to it. Steel is FreeCAD's
Steel-Generic (E 200 GPa, nu 0.3, 7900 kg/m3, yield 207 / ultimate 345 MPa filled in by
SciForge); every formula reads E, nu and the density from the study material, so the solve and
the formula use the same numbers. Units: mm, N, MPa, N mm, kg/m3 (tonnes per mm3 inside
CalculiX: 1 kg/m3 = 1e-12 t/mm3; g = 9806.65 mm/s2).

Besides accuracy, the "engine checks" look for results that are wrong without a word: a load on
the wrong faces after an edit, materials swapped between glued bodies, gravity's direction and
size, the units of pressure (MPa) and moment (N mm), picks on a body in a moved and turned
component, results out of date after a change, results kept in / dropped from the file,
warnings for a thin wall at the default mesh, and reactions that add up to the applied loads.
"""

import json
import math
import os
import platform
import time
import traceback

from . import sim_benchmarks as sb

OMP = "1"  # one CalculiX thread: the timings compare between runs

# Timoshenko shear coefficients (Cowper 1966, "The shear coefficient in Timoshenko's beam
# theory", J. Appl. Mech. 33: 335-340): rectangle 10(1+nu)/(12+11nu), solid circle
# 6(1+nu)/(7+6nu)


def kappa_rect(nu):
    return 10.0 * (1.0 + nu) / (12.0 + 11.0 * nu)


def kappa_circle(nu):
    return 6.0 * (1.0 + nu) / (7.0 + 6.0 * nu)


# -- building ---------------------------------------------------------------------------------
def boxes(*specs):
    """One solid of boxes fused without refining, so the faces of each box stay apart where
    they meet in one plane (a beam whose top face is split at its middle has an edge across
    it there: a line load, and mesh nodes on it). specs: (x0, y0, z0, dx, dy, dz)."""
    import FreeCAD as App
    import Part

    shapes = [Part.makeBox(dx, dy, dz, App.Vector(x0, y0, z0)) for x0, y0, z0, dx, dy, dz in specs]
    out = shapes[0]
    for s in shapes[1:]:
        out = out.fuse(s)
    solids = out.Solids
    if len(solids) != 1:
        raise AssertionError("expected one solid, got %d" % len(solids))
    return solids[0]


def edges(body, pred):
    return ["Edge%d" % i for i, e in enumerate(body.Shape.Edges, 1) if pred(e)]


def one_edge(body, pred):
    found = edges(body, pred)
    if len(found) != 1:
        raise AssertionError("expected one edge, found %d" % len(found))
    return found[0]


def line_at(body, **where):
    """The straight edge whose middle is at the given coordinates (x=..., y=..., z=...)."""

    def pred(e):
        c = e.CenterOfMass
        return all(sb.near(getattr(c, k), v, 1e-6) for k, v in where.items())

    return one_edge(body, pred)


def node_mean(study, key, pred):
    return sb.mean(v for p, v in sb.node_values(study, key) if pred(p))


def disp_mean(study, axis, pred):
    index = "xyz".index(axis)
    return sb.mean(d[index] for p, d in sb.node_vectors(study) if pred(p))


def reaction(summary, label, axis="total"):
    return summary["reactions"][label][axis]


def steel(study, body):
    return sb.material(study, body)


# -- the cases --------------------------------------------------------------------------------
# A case: build(doc) -> (study, checks) or (study, {"checks": [...], "also": [studies whose mesh
# goes finer too]}); a check: (name, expected (a number, or a function of nothing evaluated after
# the solve: a reference study's numbers), got(study, summary), tolerance %).
CASES = []


def case(name, title, fine, thin=False):
    """thin: a thin-walled part; at the default mesh a number outside its tolerance is honest
    when the solve said the walls are thinner than the elements (simulation_core.
    thin_wall_note): the row passes as "warned"."""

    def register(fn):
        CASES.append({"name": name, "title": title, "build": fn, "fine": fine, "thin": thin})
        return fn

    return register


THIN_WORDS = "comes out too stiff"  # (simulation_core.thin_wall_note's sentence)


# simply supported beam: line supports under both ends (a pin line and a roller line), span
# 200 mm, b 10 x h 20 mm; the top and side faces are split at x = 100 (the load line, and mesh
# nodes there to read the deflection)
SPAN, B, H = 200.0, 10.0, 20.0


def _supported_beam(doc, split=(100.0,), label="Beam"):
    from sciforge import simulation as sim

    cuts = [0.0] + list(split) + [SPAN]
    body = sb.make_body(
        doc, boxes(*[(a, 0, 0, b - a, B, H) for a, b in zip(cuts, cuts[1:])]), label
    )
    study = sim.create_study(doc, study_bodies=[body])
    # the left bottom edge holds X, Y and Z (a pin line), the right one only Z (a roller line)
    sim.add_item(study, "constraint", "fixed", [(body, line_at(body, x=0.0, z=0.0))])
    sim.add_item(
        study,
        "constraint",
        "fixed",
        [(body, line_at(body, x=SPAN, z=0.0))],
        {"x": False, "y": False, "z": True},
    )
    return body, study


def _beam_props(study, body):
    props = steel(study, body)
    E, nu = props["youngs_mpa"], props["poisson"]
    G = E / (2 * (1 + nu))
    inertia = B * H**3 / 12.0
    return E, G, inertia, kappa_rect(nu) * G * B * H  # E, G, I, kappa G A


def _mid_dz(x):
    """Mean vertical movement of the nodes on the split edges at x, around mid height (away
    from the line load at the top and the bending's own squeeze)."""

    def read(study, summary):
        return -disp_mean(study, "z", lambda p: sb.near(p[0], x, 1e-6) and 5.0 <= p[2] <= 15.0)

    return read


def _bottom_bending(moment_at, ranges):
    """sigma_xx on the bottom face over M(x) c / I (beam theory: 1) between the x ranges."""

    def read(study, summary):
        c, inertia = H / 2.0, B * H**3 / 12.0
        ratios = [
            v / (moment_at(p[0]) * c / inertia)
            for p, v in sb.node_values(study, "sxx")
            if sb.near(p[2], 0.0, 1e-6) and any(a <= p[0] <= b for a, b in ranges)
        ]
        return sb.mean(ratios)

    return read


@case(
    "ss_beam_centre",
    "Simply supported beam 200 x 10 x 20 mm (pin and roller lines under its ends), 1 kN on a "
    "line across the top at mid span (a force on an edge)",
    {"size_pct": 3.0},
)
def ss_beam_centre(doc):
    from sciforge import simulation as sim

    body, study = _supported_beam(doc)
    P = 1000.0
    sim.add_item(
        study,
        "load",
        "force",
        [(body, line_at(body, x=100.0, z=H, y=B / 2))],
        {"direction": "vector", "vector": [0, 0, -1], "magnitude": P},
    )
    E, G, inertia, kGA = _beam_props(study, body)
    # mid-span deflection, centre point load: P L^3 / (48 E I) (Gere & Goodno, Mechanics of
    # Materials, Appendix H, simple beam case 4) plus the shear deflection P L / (4 kappa G A)
    # (Timoshenko beam; Timoshenko & Gere, Mechanics of Materials, section 9.11)
    deflection = P * SPAN**3 / (48 * E * inertia) + P * SPAN / (4 * kGA)
    checks = [
        ("mid-span deflection (mm) = P L^3 / 48EI + P L / 4kGA", deflection, _mid_dz(100.0), 3.0),
        (
            "bottom bending stress / (M c / I), x 30-70 and 130-170 mm (M = P x / 2)",
            1.0,
            _bottom_bending(lambda x: P * min(x, SPAN - x) / 2.0, [(30, 70), (130, 170)]),
            3.0,
        ),
        ("pin line carries half (N, z)", P / 2, lambda s, m: reaction(m, "Fixed 1", "z"), 0.5),
        ("roller line carries half (N, z)", P / 2, lambda s, m: reaction(m, "Fixed 2", "z"), 0.5),
    ]
    return study, checks


@case(
    "ss_beam_pressure",
    "Simply supported beam 200 x 10 x 20 mm under 0.5 MPa on its top (5 N/mm)",
    {"size_pct": 3.0},
)
def ss_beam_pressure(doc):
    from sciforge import simulation as sim

    body, study = _supported_beam(doc)
    q = 0.5
    tops = sb.faces(body, lambda f: sb.near(f.CenterOfMass.z, H, 1e-6))
    sim.add_item(study, "load", "pressure", [(body, f) for f in tops], {"magnitude": q})
    E, G, inertia, kGA = _beam_props(study, body)
    w = q * B
    # 5 w L^4 / (384 E I) (Gere & Goodno, Appendix H, simple beam case 1) plus the shear
    # deflection w L^2 / (8 kappa G A) (Timoshenko & Gere 9.11)
    deflection = 5 * w * SPAN**4 / (384 * E * inertia) + w * SPAN**2 / (8 * kGA)
    checks = [
        ("mid-span deflection (mm) = 5wL^4/384EI + wL^2/8kGA", deflection, _mid_dz(100.0), 3.0),
        (
            "bottom bending stress / (M c / I), x 30-70 and 130-170 mm (M = w x (L - x) / 2)",
            1.0,
            _bottom_bending(lambda x: w * x * (SPAN - x) / 2.0, [(30, 70), (130, 170)]),
            3.0,
        ),
        (
            "the supports carry the load (N) = q b L",
            w * SPAN,
            lambda s, m: reaction(m, "Fixed 1", "z") + reaction(m, "Fixed 2", "z"),
            0.5,
        ),
    ]
    return study, checks


@case(
    "symmetry_beam",
    "Half of the centre-loaded beam on a Frictionless symmetry plane at mid span against the "
    "full beam (the line load on the plane's top edge, halved)",
    {"size_pct": 3.0},
)
def symmetry_beam(doc):
    from sciforge import simulation as sim

    full_body, full = _supported_beam(doc, label="Full")
    P = 1000.0
    sim.add_item(
        full,
        "load",
        "force",
        [(full_body, line_at(full_body, x=100.0, z=H, y=B / 2))],
        {"direction": "vector", "vector": [0, 0, -1], "magnitude": P},
    )
    import FreeCAD as App

    half_shape = boxes((0, 0, 0, SPAN / 2, B, H))
    half_shape.translate(App.Vector(0, 40, 0))
    half_body = sb.make_body(doc, half_shape, "Half")
    half = sim.create_study(doc, study_bodies=[half_body])
    # (the symmetry plane holds X at mid span; the end line only Y and Z: the full beam's
    # bottom fibre stretches from its pin line to its roller line, held along X nowhere else)
    sim.add_item(
        half,
        "constraint",
        "fixed",
        [(half_body, line_at(half_body, x=0.0, z=0.0))],
        {"x": False, "y": True, "z": True},
    )
    sim.add_item(
        half,
        "constraint",
        "frictionless",
        [(half_body, sb.one_face(half_body, lambda f: sb.near(f.CenterOfMass.x, SPAN / 2)))],
    )
    sim.add_item(
        half,
        "load",
        "force",
        [(half_body, line_at(half_body, x=SPAN / 2, z=H))],
        {"direction": "vector", "vector": [0, 0, -1], "magnitude": P / 2},
    )
    holder = {}

    def full_value(fn):
        def value():
            if "summary" not in holder:
                holder["summary"] = sim.solve(full, timeout=900)
            return fn(full, holder["summary"])

        return value

    mid = _mid_dz(100.0)
    bending = _bottom_bending(lambda x: P * min(x, SPAN - x) / 2.0, [(30, 70)])

    def half_bending(study, summary):
        return bending(study, summary)

    checks = [
        (
            "half model's mid-span deflection = the full model's (mm)",
            full_value(mid),
            lambda s, m: -disp_mean(
                s, "z", lambda p: sb.near(p[0], SPAN / 2, 1e-6) and 5.0 <= p[2] <= 15.0
            ),
            1.0,
        ),
        (
            "half model's bending stress ratio = the full model's (x 30-70 mm)",
            full_value(bending),
            half_bending,
            1.0,
        ),
        (
            "half model's support carries half the load (N) = full model's pin line",
            full_value(lambda s, m: reaction(m, "Fixed 1", "z")),
            lambda s, m: reaction(m, "Fixed 3", "z"),
            0.5,
        ),
    ]
    return half, {"checks": checks, "also": [full]}


@case(
    "cantilever_edge_vertex",
    "Cantilever 100 x 10 x 10 mm loaded on an edge (100 N), on two corners (shared, then per "
    "corner)",
    {"size_pct": 3.0},
)
def cantilever_edge_vertex(doc):
    import FreeCAD as App
    import Part

    from sciforge import simulation as sim

    L, b = 100.0, 10.0
    studies = []
    for k, label in enumerate(("Edge", "Corners", "PerCorner")):
        shape = Part.makeBox(L, b, b)
        shape.translate(App.Vector(0, 30.0 * k, 0))
        body = sb.make_body(doc, shape, label)
        st = sim.create_study(doc, study_bodies=[body])
        sim.add_item(
            st,
            "constraint",
            "fixed",
            [(body, sb.one_face(body, lambda f: sb.near(f.CenterOfMass.x, 0)))],
        )
        y0 = 30.0 * k
        if label == "Edge":
            refs = [(body, line_at(body, x=L, z=b))]
            opts = {}
        else:
            refs = [
                (body, sb.vertex_at(body, (L, y0, b))),
                (body, sb.vertex_at(body, (L, y0 + b, b))),
            ]
            opts = {"per_entity": label == "PerCorner"}
        opts.update({"direction": "vector", "vector": [0, 0, -1], "magnitude": 100.0})
        sim.add_item(st, "load", "force", refs, opts)
        studies.append(st)
    props = steel(studies[0], sim.study_bodies(studies[0])[0])
    E, nu = props["youngs_mpa"], props["poisson"]
    inertia = b**4 / 12.0
    kGA = kappa_rect(nu) * E / (2 * (1 + nu)) * b * b
    # tip deflection of a cantilever with an end load: F L^3 / (3 E I) (Gere & Goodno,
    # Appendix H, cantilever case 4) plus the shear deflection F L / (kappa G A)
    tip = 100.0 * L**3 / (3 * E * inertia) + 100.0 * L / kGA
    solved = {}

    def summary_of(st):
        if st.Name not in solved:
            solved[st.Name] = sim.solve(st, timeout=900)
        return solved[st.Name]

    def tip_dz(st):
        def read(s, m):
            if st is not s:
                summary_of(st)
            # the tip face's lower half: away from where the edge or corners are pushed
            return -disp_mean(st, "z", lambda p: sb.near(p[0], L, 1e-6) and p[2] <= 5.0)

        return read

    edge, corners, per = studies
    checks = [
        ("edge load: tip deflection (mm) = FL^3/3EI + FL/kGA", tip, tip_dz(edge), 3.0),
        (
            "edge load: the fixed end holds 100 N",
            100.0,
            lambda s, m: reaction(m, "Fixed 1", "total"),
            0.5,
        ),
        (
            "two corners sharing 100 N: tip deflection (mm)",
            tip,
            tip_dz(corners),
            3.0,
        ),
        (
            "two corners sharing 100 N: the fixed end holds 100 N",
            100.0,
            lambda s, m: summary_of(corners)["reactions"]["Fixed 2"]["total"],
            0.5,
        ),
        (
            "100 N per corner (Force Per Entity): the fixed end holds 200 N",
            200.0,
            lambda s, m: summary_of(per)["reactions"]["Fixed 3"]["total"],
            0.5,
        ),
        (
            "100 N per corner: tip deflection twice the shared one (mm)",
            2 * tip,
            tip_dz(per),
            3.0,
        ),
    ]
    return edge, {"checks": checks, "also": [corners, per]}


@case(
    "stepped_bar",
    "Stepped bar pulled by 5 kN: steel 20 x 20 x 100 mm glued to aluminium 10 x 10 x 100 mm",
    {"size_pct": 3.0},
)
def stepped_bar(doc):
    import FreeCAD as App
    import Part

    from sciforge import simulation as sim

    F, L1, L2 = 5000.0, 100.0, 100.0
    a1, a2 = 20.0, 10.0
    big = sb.make_body(doc, Part.makeBox(L1, a1, a1), "SteelPart")
    small = sb.make_body(
        doc, Part.makeBox(L2, a2, a2, App.Vector(L1, (a1 - a2) / 2, (a1 - a2) / 2)), "AluPart"
    )
    study = sim.create_study(doc)
    sim.set_study_material(study, small, "aluminium")
    sim.add_item(
        study,
        "constraint",
        "frictionless",
        [(big, sb.one_face(big, lambda f: sb.near(f.CenterOfMass.x, 0)))],
    )
    sim.add_item(study, "constraint", "fixed", [(big, sb.vertex_at(big, (0, 0, 0)))], {"x": False})
    sim.add_item(
        study,
        "constraint",
        "fixed",
        [(big, sb.vertex_at(big, (0, a1, 0)))],
        {"x": False, "y": False},
    )
    sim.add_item(
        study,
        "load",
        "force",
        [(small, sb.one_face(small, lambda f: sb.near(f.CenterOfMass.x, L1 + L2)))],
        {"direction": "vector", "vector": [1, 0, 0], "magnitude": F},
    )
    e1 = sb.material(study, big)["youngs_mpa"]
    e2 = sb.material(study, small)["youngs_mpa"]
    A1, A2 = a1 * a1, a2 * a2
    # two bars in series: delta = F L1 / (E1 A1) + F L2 / (E2 A2) (Gere & Goodno, section 2.3,
    # bars with intermediate axial loads / prismatic segments); stress F / A in each
    stretch = F * L1 / (e1 * A1) + F * L2 / (e2 * A2)
    swapped = F * L1 / (e2 * A1) + F * L2 / (e1 * A2)

    def end_dx(study, summary):
        return disp_mean(study, "x", lambda p: sb.near(p[0], L1 + L2, 1e-6))

    def material_of(name):
        def read(study, summary):
            key = sim.body_key(study, big if name == "big" else small)
            return summary["bodies"][key]["material"]

        return read

    checks = [
        ("the end moves (mm) = F L1/E1A1 + F L2/E2A2", stretch, end_dx, 2.0),
        (
            "steel bar stress (MPa) = F / A1, x 30-70 mm",
            F / A1,
            lambda s, m: node_mean(s, "sxx", lambda p: 30 <= p[0] <= 70),
            2.0,
        ),
        (
            "aluminium bar stress (MPa) = F / A2, x 130-170 mm",
            F / A2,
            lambda s, m: node_mean(s, "sxx", lambda p: 130 <= p[0] <= 170),
            2.0,
        ),
        (
            "materials not swapped: end movement far from the swapped value %.4g mm" % swapped,
            1.0,
            lambda s, m: 1.0 if abs(end_dx(s, m) - swapped) > 0.3 * swapped else 0.0,
            0.0,
        ),
        (
            "per-body rows name each body's material (steel part)",
            sim.study_material(study, big)[0],
            material_of("big"),
            0.0,
        ),
        (
            "per-body rows name each body's material (aluminium part)",
            sim.study_material(study, small)[0],
            material_of("small"),
            0.0,
        ),
        (
            "the hold takes the pull (N)",
            F,
            lambda s, m: reaction(m, "Frictionless 1", "x") * -1,
            0.5,
        ),
    ]
    return study, checks


@case(
    "clamped_plate",
    "Circular plate, radius 50 mm, 2.5 mm thick, clamped at its rim, 0.1 MPa on top",
    {"size_mm": 2.5},
    thin=True,
)
def clamped_plate(doc):
    import Part

    from sciforge import simulation as sim

    a, t, q = 50.0, 2.5, 0.1
    body = sb.make_body(doc, Part.makeCylinder(a, t), "Plate")
    study = sim.create_study(doc)
    rim = sb.one_face(body, lambda f: f.Surface.TypeId == "Part::GeomCylinder")
    sim.add_item(study, "constraint", "fixed", [(body, rim)])
    top = sb.one_face(body, lambda f: sb.near(f.CenterOfMass.z, t))
    sim.add_item(study, "load", "pressure", [(body, top)], {"magnitude": q})
    props = sb.material(study, body)
    E, nu = props["youngs_mpa"], props["poisson"]
    G = E / (2 * (1 + nu))
    D = E * t**3 / (12 * (1 - nu**2))
    # centre deflection: q a^4 / (64 D) (Roark's Formulas for Stress and Strain, 7th ed.,
    # Table 11.2 case 10b, clamped edge, uniform load) plus the transverse shear deflection
    # q a^2 / (4 kappa G t) of a Mindlin plate (Wang, Reddy & Lee, Shear Deformable Beams and
    # Plates, 2000, chapter 5: clamped circular plate under uniform load), kappa = 5/6
    w0 = q * a**4 / (64 * D) + q * a**2 / (4 * (5.0 / 6.0) * G * t)

    def sigma_xx(x, y):
        # bending stress on the bottom face: sigma_r = 3q/(8t^2) ((1+nu) a^2 - (3+nu) r^2),
        # sigma_t = 3q/(8t^2) ((1+nu) a^2 - (1+3nu) r^2) (Roark Table 11.2 case 10b; Timoshenko
        # & Woinowsky-Krieger, Theory of Plates and Shells, section 15); sigma_xx from both
        r2 = x * x + y * y
        k = 3 * q / (8 * t**2)
        sr = k * ((1 + nu) * a**2 - (3 + nu) * r2)
        st = k * ((1 + nu) * a**2 - (1 + 3 * nu) * r2)
        c2 = x * x / r2 if r2 > 1e-12 else 1.0
        return sr * c2 + st * (1 - c2)

    def bottom_ratio(study, summary):
        return sb.mean(
            v / sigma_xx(p[0], p[1])
            for p, v in sb.node_values(study, "sxx")
            if sb.near(p[2], 0.0, 1e-6) and math.hypot(p[0], p[1]) <= 0.4 * a
        )

    checks = [
        (
            "centre deflection (mm) = q a^4 / 64D + q a^2 / 4 kappa G t",
            w0,
            lambda s, m: m["stats"]["displacement"]["max"],
            5.0,
        ),
        ("bottom bending stress / plate theory, r < 0.4 a", 1.0, bottom_ratio, 5.0),
        (
            "the rim holds the load (N) = q pi a^2",
            q * math.pi * a**2,
            lambda s, m: reaction(m, "Fixed 1", "z"),
            0.5,
        ),
    ]
    return study, checks


@case(
    "tube_torsion",
    "Tube 30 / 24 mm across, 150 mm long, held at one end, twisted by 50 N m (a Moment, N mm)",
    {"size_mm": 1.5},
    thin=True,
)
def tube_torsion(doc):
    import Part

    from sciforge import simulation as sim

    ro, ri, L, T = 15.0, 12.0, 150.0, 50000.0
    body = sb.make_body(doc, Part.makeCylinder(ro, L).cut(Part.makeCylinder(ri, L)), "Tube")
    study = sim.create_study(doc)
    sim.add_item(
        study,
        "constraint",
        "fixed",
        [(body, sb.one_face(body, lambda f: sb.near(f.CenterOfMass.z, 0)))],
    )
    sim.add_item(
        study,
        "load",
        "moment",
        [(body, sb.one_face(body, lambda f: sb.near(f.CenterOfMass.z, L)))],
        {"direction": "vector", "vector": [0, 0, 1], "magnitude": T},
    )
    props = sb.material(study, body)
    G = sb.shear_modulus(props)
    J = math.pi * (ro**4 - ri**4) / 2.0
    # circular tube in torsion: tau = T r / J, J = pi (ro^4 - ri^4) / 2, angle T L / (G J)
    # (Gere & Goodno, Mechanics of Materials, section 3.4, circular tubes); von Mises of pure
    # shear = sqrt(3) tau
    tau = T * ro / J
    turn = T * L / (G * J)

    def surface_vm(study, summary):
        return node_mean(
            study,
            "von_mises",
            lambda p: sb.near(math.hypot(p[0], p[1]), ro, 1e-3) and 50 <= p[2] <= 100,
        )

    def end_turn(study, summary):
        # how far the outer rim of the free end moved, along the tangent (the rim turns
        # T L r_o / (G J))
        vals = []
        for p, d in sb.node_vectors(study):
            r = math.hypot(p[0], p[1])
            if sb.near(p[2], L, 1e-6) and sb.near(r, ro, 1e-3):
                vals.append((-p[1] * d[0] + p[0] * d[1]) / r)
        return sb.mean(vals)

    checks = [
        (
            "von Mises on the outer surface (MPa) = sqrt(3) T r / J",
            math.sqrt(3) * tau,
            surface_vm,
            3.0,
        ),
        ("the free end's rim turns (mm) = T L r / (G J)", turn * ro, end_turn, 3.0),
        (
            "the held end takes no force (N): a moment only",
            0.0,
            lambda s, m: reaction(m, "Fixed 1", "total"),
            0.5,
        ),
    ]
    return study, checks


@case(
    "gravity_bracket",
    "Steel L bracket held at its wall face with an aluminium block glued on it, gravity alone",
    {"size_pct": 4.0},
)
def gravity_bracket(doc):
    from sciforge import simulation as sim

    # wall plate 6 x 40 x 60 at x 0..6, arm 60 x 40 x 6 along x on its foot
    bracket = sb.make_body(doc, boxes((0, 0, 0, 6, 40, 60), (6, 0, 0, 54, 40, 6)), "Bracket")
    import Part
    import FreeCAD as App

    block = sb.make_body(doc, Part.makeBox(20, 20, 10, App.Vector(30, 10, 6)), "Block")
    study = sim.create_study(doc)
    sim.set_study_material(study, block, "aluminium")
    sim.set_settings(study, {"gravity": {"on": True, "direction": [0, 0, -1]}})
    sim.add_item(
        study,
        "constraint",
        "fixed",
        [(bracket, sb.one_face(bracket, lambda f: sb.near(f.CenterOfMass.x, 0)))],
    )
    g = 9806.65  # mm/s2, standard gravity (BIPM, the SI brochure)
    rho_s = sb.material(study, bracket)["density"] * 1e-12  # kg/m3 -> t/mm3
    rho_a = sb.material(study, block)["density"] * 1e-12
    # the weight: W = g (rho_1 V_1 + rho_2 V_2) in t mm/s2 = N (Newton's second law)
    weight = g * (rho_s * bracket.Shape.Volume + rho_a * block.Shape.Volume)
    checks = [
        (
            "the wall holds the weight (N, z) = g sum(rho V)",
            weight,
            lambda s, m: reaction(m, "Fixed 1", "z"),
            0.2,
        ),
        (
            "nothing sideways (N)",
            0.0,
            lambda s, m: abs(reaction(m, "Fixed 1", "x")) + abs(reaction(m, "Fixed 1", "y")),
            0.2,
        ),
        (
            "the arm's tip goes down, not up (sign of its z movement)",
            -1.0,
            lambda s, m: math.copysign(1.0, disp_mean(s, "z", lambda p: sb.near(p[0], 60.0, 1e-6))),
            0.0,
        ),
    ]
    return study, checks


@case(
    "gravity_sideways",
    "The same bracket with gravity along -Y: the wall holds the weight along +Y",
    {"size_pct": 4.0},
)
def gravity_sideways(doc):
    from sciforge import simulation as sim

    bracket = sb.make_body(doc, boxes((0, 0, 0, 6, 40, 60), (6, 0, 0, 54, 40, 6)), "Bracket")
    study = sim.create_study(doc)
    sim.set_settings(study, {"gravity": {"on": True, "direction": [0, -1, 0]}})
    sim.add_item(
        study,
        "constraint",
        "fixed",
        [(bracket, sb.one_face(bracket, lambda f: sb.near(f.CenterOfMass.x, 0)))],
    )
    rho = sb.material(study, bracket)["density"] * 1e-12
    weight = 9806.65 * rho * bracket.Shape.Volume
    from sciforge import material as materials

    kg = materials.mass(bracket)  # (what Inspect shows: a body on FreeCAD's Default is Steel)
    checks = [
        (
            "the weight = Inspect's mass %.6g kg x 9.80665 m/s2 (N)" % kg,
            kg * 9.80665,
            lambda s, m: reaction(m, "Fixed 1", "y"),
            0.2,
        ),
        (
            "the wall holds the weight along +Y (N)",
            weight,
            lambda s, m: reaction(m, "Fixed 1", "y"),
            0.2,
        ),
        (
            "nothing along Z (N)",
            0.0,
            lambda s, m: abs(reaction(m, "Fixed 1", "z")),
            0.2,
        ),
    ]
    return study, checks


@case(
    "shaft_bearing",
    "Shaft 20 mm across, 120 mm long, held at one end, 500 N bearing load on its last 20 mm",
    {"size_pct": 3.0},
)
def shaft_bearing(doc):
    import FreeCAD as App
    import Part

    from sciforge import simulation as sim

    r, L, c, P = 10.0, 120.0, 100.0, 500.0
    x = App.Vector(1, 0, 0)
    shape = Part.makeCylinder(r, c, App.Vector(0, 0, 0), x).fuse(
        Part.makeCylinder(r, L - c, App.Vector(c, 0, 0), x)
    )
    body = sb.make_body(doc, shape.Solids[0], "Shaft")
    study = sim.create_study(doc)
    sim.add_item(
        study,
        "constraint",
        "fixed",
        [(body, sb.one_face(body, lambda f: sb.near(f.CenterOfMass.x, 0)))],
    )
    journal = sb.one_face(
        body,
        lambda f: f.Surface.TypeId == "Part::GeomCylinder" and f.CenterOfMass.x > c,
    )
    sim.add_item(
        study, "load", "bearing", [(body, journal)], {"vector": [0, 0, -1], "magnitude": P}
    )
    props = sb.material(study, body)
    E, nu = props["youngs_mpa"], props["poisson"]
    G = E / (2 * (1 + nu))
    inertia, area = math.pi * r**4 / 4.0, math.pi * r * r
    w = P / (L - c)
    # the bearing load is even along the journal: the tip deflection of a cantilever under a
    # load w on [c, L], integrating P a^2 (3L - a) / (6 E I) for a point load at a (Roark,
    # 7th ed., Table 8.1 case 1a): w / (6EI) (3L^4/4 - L c^3 + c^4/4); shear w (L^2 - c^2) /
    # (2 kappa G A) (Cowper's kappa for a circle)
    bend = w / (6 * E * inertia) * (0.75 * L**4 - L * c**3 + c**4 / 4.0)
    shear = w * (L * L - c * c) / (2 * kappa_circle(nu) * G * area)

    def end_dz(study, summary):
        return -disp_mean(study, "z", lambda p: sb.near(p[0], L, 1e-6))

    checks = [
        ("free end deflection (mm), distributed load on the journal", bend + shear, end_dz, 3.0),
        ("the held end takes the load (N, z)", P, lambda s, m: reaction(m, "Fixed 1", "z"), 0.5),
        (
            "nothing sideways (N)",
            0.0,
            lambda s, m: abs(reaction(m, "Fixed 1", "x")) + abs(reaction(m, "Fixed 1", "y")),
            0.5,
        ),
    ]
    return study, checks


@case(
    "pinned_link",
    "Link 100 x 20 x 5 mm with two 8 mm holes 80 mm apart: one on a Pin (tangential held "
    "too), a 2 kN bearing load pulling the other along the link",
    {"size_pct": 3.0},
)
def pinned_link(doc):
    import FreeCAD as App
    import Part

    from sciforge import simulation as sim

    L, w, t, r, F = 100.0, 20.0, 5.0, 4.0, 2000.0
    shape = Part.makeBox(L, w, t)
    for x in (10.0, 90.0):
        shape = shape.cut(Part.makeCylinder(r, t, App.Vector(x, w / 2, 0)))
    body = sb.make_body(doc, shape, "Link")
    study = sim.create_study(doc)

    def hole(x):
        return sb.one_face(
            body,
            lambda f: f.Surface.TypeId == "Part::GeomCylinder" and sb.near(f.Surface.Center.x, x),
        )

    sim.add_item(
        study,
        "constraint",
        "pin",
        [(body, hole(10.0))],
        {"radial": True, "axial": True, "tangential": True},
    )
    sim.add_item(
        study, "load", "bearing", [(body, hole(90.0))], {"vector": [1, 0, 0], "magnitude": F}
    )
    E = sb.material(study, body)["youngs_mpa"]
    # the link between its holes is a bar in tension: sigma = F / (w t) in the middle
    # (Gere & Goodno 2.2), and the part between the holes' edges (x 14..86) stretches
    # F L' / (E w t); the pin takes the whole pull (statics)

    def middle_stress(study, summary):
        return node_mean(study, "sxx", lambda p: 40.0 <= p[0] <= 60.0)

    def stretch(study, summary):
        def mean_dx(x):
            return disp_mean(
                study, "x", lambda p: sb.near(p[0], x, 0.6) and abs(p[1] - w / 2) > r + 1
            )

        return mean_dx(70.0) - mean_dx(30.0)

    checks = [
        ("stress in the middle (MPa) = F / (w t)", F / (w * t), middle_stress, 2.0),
        ("x 30..70 mm stretches (mm) = F 40 / (E w t)", F * 40.0 / (E * w * t), stretch, 3.0),
        ("the pin takes the pull (N, -x)", -F, lambda s, m: reaction(m, "Pin 1", "x"), 0.5),
        (
            "nothing across (N)",
            0.0,
            lambda s, m: abs(reaction(m, "Pin 1", "y")) + abs(reaction(m, "Pin 1", "z")),
            0.5,
        ),
    ]
    return study, checks


def _cantilever_study(doc, scale=1.0, label="Body", force=100.0, extra=None):
    """A steel cantilever L x a x a (100 x 10 x 10 mm times scale) fixed at x = 0, a force on
    its end face along -Z."""
    import Part

    from sciforge import simulation as sim

    L, a = 100.0 * scale, 10.0 * scale
    body = sb.make_body(doc, Part.makeBox(L, a, a), label)
    study = sim.create_study(doc, study_bodies=[body])
    sim.add_item(
        study,
        "constraint",
        "fixed",
        [(body, sb.one_face(body, lambda f: sb.near(f.CenterOfMass.x, 0, 1e-9 * max(L, 1))))],
    )
    opts = {"direction": "vector", "vector": [0, 0, -1], "magnitude": force}
    opts.update(extra or {})
    sim.add_item(
        study,
        "load",
        "force",
        [(body, sb.one_face(body, lambda f: sb.near(f.CenterOfMass.x, L, 1e-9 * max(L, 1))))],
        opts,
    )
    return body, study


@case(
    "inch_cantilever",
    "Cantilever 1 x 1 x 12 in, 100 lbf at its end (an inch-sized part; numbers in mm, N, MPa)",
    {"size_pct": 3.0},
)
def inch_cantilever(doc):
    import Part

    from sciforge import simulation as sim

    inch, lbf = 25.4, 4.4482216152605  # mm, N (exact definitions: NIST SP 811 appendix B)
    L, a, F = 12 * inch, 1 * inch, 100 * lbf
    body = sb.make_body(doc, Part.makeBox(L, a, a), "InchBar")
    study = sim.create_study(doc)
    sim.add_item(
        study,
        "constraint",
        "fixed",
        [(body, sb.one_face(body, lambda f: sb.near(f.CenterOfMass.x, 0)))],
    )
    sim.add_item(
        study,
        "load",
        "force",
        [(body, sb.one_face(body, lambda f: sb.near(f.CenterOfMass.x, L)))],
        {"direction": "vector", "vector": [0, 0, -1], "magnitude": F},
    )
    props = sb.material(study, body)
    E_psi = props["youngs_mpa"] / 0.006894757293168  # MPa -> psi (NIST SP 811)
    inertia_in = 1.0 / 12.0
    # worked in inches and pounds, as a US student would: F L^3 / 3EI in inches, M c / I in
    # psi; then converted to mm and MPa
    tip_in = 100.0 * 12.0**3 / (3 * E_psi * inertia_in)
    root_psi_at_6in = 100.0 * 6.0 * 0.5 / inertia_in  # at the middle (6 in from the end)

    def top_ratio(study, summary):
        # sigma_xx on the top face over the beam formula M(x) c / I at its x (20-80 % of L)
        c, inertia = a / 2.0, a**4 / 12.0
        return sb.mean(
            v / (F * (L - p[0]) * c / inertia)
            for p, v in sb.node_values(study, "sxx")
            if sb.near(p[2], a, 1e-6) and 0.2 * L <= p[0] <= 0.8 * L
        )

    checks = [
        (
            "tip deflection (mm) = 25.4 x F L^3 / 3EI [in]",
            tip_in * inch,
            lambda s, m: m["stats"]["displacement"]["max"],
            3.0,
        ),
        (
            "top stress / (0.00689 x M c / I [psi]), 20-80 %% of the length (%.4g MPa at mid)"
            % (root_psi_at_6in * 0.006894757293168),
            1.0,
            top_ratio,
            3.0,
        ),
        ("reaction (N) = 100 lbf", F, lambda s, m: reaction(m, "Fixed 1", "total"), 0.5),
    ]
    return study, checks


@case(
    "scale_1000mm",
    "The 100 mm cantilever made 10 times bigger (1000 x 100 x 100 mm, 10 kN): the same stress, "
    "10 times the deflection",
    {"size_pct": 3.0},
)
def scale_big(doc):
    return _scaled(doc, 10.0)


@case(
    "scale_1mm",
    "The 100 mm cantilever made 100 times smaller (1 x 0.1 x 0.1 mm, 0.01 N): the same stress, "
    "a hundredth of the deflection",
    {"size_pct": 3.0},
)
def scale_small(doc):
    return _scaled(doc, 0.01)


def _scaled(doc, s):
    body, study = _cantilever_study(doc, scale=s, force=100.0 * s * s)
    props = steel(study, body)
    E = props["youngs_mpa"]
    L, a, F = 100.0 * s, 10.0 * s, 100.0 * s * s
    inertia = a**4 / 12.0
    # F L^3 / 3EI scales with s (F ~ s^2, L^3 / I ~ s^-1); stress M c / I does not change
    tip = F * L**3 / (3 * E * inertia)

    def bending(study, summary):
        ratios = [
            v / (F * (L - p[0]) * (a / 2) / inertia)
            for p, v in sb.node_values(study, "sxx")
            if sb.near(p[2], a, 1e-9 * L) and 0.2 * L <= p[0] <= 0.8 * L
        ]
        return sb.mean(ratios)

    checks = [
        (
            "tip deflection (mm) = F L^3 / 3EI",
            tip,
            lambda st, m: m["stats"]["displacement"]["max"],
            3.0,
        ),
        ("bending stress / (M c / I), top face 20-80 %", 1.0, bending, 3.0),
        ("reaction (N)", F, lambda st, m: reaction(m, "Fixed 1", "total"), 0.5),
    ]
    return study, checks


@case(
    "safety_basis",
    "Bar 20 x 20 x 100 mm, 100 MPa in tension and in compression: safety factor on yield "
    "(207 MPa / von Mises) and on ultimate (345 MPa / largest principal stress)",
    {"size_pct": 5.0},
)
def safety_basis(doc):
    import FreeCAD as App
    import Part

    from sciforge import simulation as sim

    made = []
    for k, (label, push) in enumerate((("Pulled", -100.0), ("Pushed", 100.0))):
        for basis in ("yield", "ultimate"):
            shape = Part.makeBox(20, 20, 100)
            x0 = 40.0 * len(made)
            shape.translate(App.Vector(x0, 0, 0))
            body = sb.make_body(doc, shape, "%s%s" % (label, basis.capitalize()))
            st = sim.create_study(doc, study_bodies=[body])
            sim.set_settings(st, {"safety_basis": basis})
            sim.add_item(
                st,
                "constraint",
                "frictionless",
                [(body, sb.one_face(body, lambda f: sb.near(f.CenterOfMass.z, 0)))],
            )
            sim.add_item(
                st, "constraint", "fixed", [(body, sb.vertex_at(body, (x0, 0, 0)))], {"z": False}
            )
            sim.add_item(
                st,
                "constraint",
                "fixed",
                [(body, sb.vertex_at(body, (x0 + 20, 0, 0)))],
                {"x": False, "z": False},
            )
            sim.add_item(
                st,
                "load",
                "pressure",
                [(body, sb.one_face(body, lambda f: sb.near(f.CenterOfMass.z, 100)))],
                {"magnitude": push},
            )
            made.append((label, basis, st, body))
    solved = {}

    def safety_min(st):
        def read(s, m):
            if st is s:
                return m["stats"]["safety"]["min"]
            if st.Name not in solved:
                solved[st.Name] = sim.solve(st, timeout=900)
            return solved[st.Name]["stats"]["safety"]["min"]

        return read

    props = steel(made[0][2], made[0][3])
    yield_, ultimate = props["yield_mpa"], props["ultimate_mpa"]
    checks = []
    for label, basis, st, _body in made:
        strength = yield_ if basis == "yield" else ultimate
        # yield basis: yield / von Mises (Fusion, research 5.4); ultimate basis: ultimate /
        # the largest principal stress; in compression the largest is the compressive one
        # (maximum normal stress theory, Rankine; Shigley's Mechanical Engineering Design,
        # 10th ed., section 5.8), not the tension-only 1st principal, which is 0 there and
        # would read 15: "very strong" for a bar crushed beyond its strength
        checks.append(
            (
                "%s 100 MPa, %s basis: lowest safety factor = %s / 100"
                % (label.lower(), basis, sb._num(strength) if hasattr(sb, "_num") else strength),
                strength / 100.0,
                safety_min(st),
                1.0,
            )
        )
    return made[0][2], {"checks": checks, "also": [m[2] for m in made[1:]]}


@case(
    "shared_vs_per_entity",
    "Simply supported beam, 1 kN on two top faces of 60 and 140 mm: shared by area, then per "
    "face (Force Per Entity)",
    {"size_pct": 3.0},
)
def shared_vs_per_entity(doc):
    from sciforge import simulation as sim

    body, shared = _supported_beam(doc, split=(60.0,), label="Shared")
    tops = sb.faces(body, lambda f: sb.near(f.CenterOfMass.z, H, 1e-6))
    sim.add_item(
        shared,
        "load",
        "force",
        [(body, f) for f in tops],
        {"direction": "vector", "vector": [0, 0, -1], "magnitude": 1000.0},
    )
    import FreeCAD as App

    shape = boxes((0, 0, 0, 60, B, H), (60, 0, 0, 140, B, H))
    shape.translate(App.Vector(0, 40, 0))
    body2 = sb.make_body(doc, shape, "PerFace")
    per = sim.create_study(doc, study_bodies=[body2])
    sim.add_item(per, "constraint", "fixed", [(body2, line_at(body2, x=0.0, z=0.0))])
    sim.add_item(
        per,
        "constraint",
        "fixed",
        [(body2, line_at(body2, x=SPAN, z=0.0))],
        {"x": False, "y": False, "z": True},
    )
    tops2 = sb.faces(body2, lambda f: sb.near(f.CenterOfMass.z, H, 1e-6))
    sim.add_item(
        per,
        "load",
        "force",
        [(body2, f) for f in tops2],
        {"direction": "vector", "vector": [0, 0, -1], "magnitude": 1000.0, "per_entity": True},
    )
    E, G, inertia, kGA = _beam_props(shared, body)
    w = 1000.0 / SPAN
    x = 60.0
    # shared by area = an even load w = 5 N/mm: deflection at x of a simple beam under an even
    # load, w x (L^3 - 2 L x^2 + x^3) / 24EI (Gere & Goodno, Appendix H, simple beam case 1)
    # plus shear w x (L - x) / (2 kappa G A)
    at60 = w * x * (SPAN**3 - 2 * SPAN * x * x + x**3) / (24 * E * inertia) + w * x * (
        SPAN - x
    ) / (2 * kGA)
    holder = {}

    def per_summary():
        if "m" not in holder:
            holder["m"] = sim.solve(per, timeout=900)
        return holder["m"]

    checks = [
        # statics: shared by area, the left support takes 300 x 170/200 + 700 x 70/200 =
        # 500 N; an equal split (500 N a face) would give 600 N
        ("shared: the pin line takes 500 N", 500.0, lambda s, m: reaction(m, "Fixed 1", "z"), 0.5),
        ("shared: deflection at x = 60 mm = an even load's (mm)", at60, _mid_dz(60.0), 3.0),
        # per face: 1000 N at x = 30 and 1000 N at x = 130: left 1000 x 170/200 + 1000 x
        # 70/200 = 1200 N, right 800 N, total 2000 N
        (
            "per face: the pin line takes 1200 N",
            1200.0,
            lambda s, m: per_summary()["reactions"]["Fixed 3"]["z"],
            0.5,
        ),
        (
            "per face: the roller line takes 800 N",
            800.0,
            lambda s, m: per_summary()["reactions"]["Fixed 4"]["z"],
            0.5,
        ),
    ]
    return shared, {"checks": checks, "also": [per]}


@case(
    "directions",
    "Which way things push: pressure into the face, a normal force into the face, Flip, a "
    "negative pressure, a moment about the face's normal (right-hand rule), gravity",
    {"size_pct": 5.0},
)
def directions(doc):
    import FreeCAD as App
    import Part

    from sciforge import simulation as sim

    made = {}

    def bar(name, k):
        shape = Part.makeBox(100, 10, 10)
        shape.translate(App.Vector(0, 30.0 * k, 0))
        body = sb.make_body(doc, shape, name)
        st = sim.create_study(doc, study_bodies=[body])
        sim.add_item(
            st,
            "constraint",
            "fixed",
            [(body, sb.one_face(body, lambda f: sb.near(f.CenterOfMass.x, 0)))],
        )
        made[name] = (st, body)
        return st, body

    def face(body, axis, value):
        return sb.one_face(body, lambda f: sb.near(getattr(f.CenterOfMass, axis), value, 1e-6))

    st, b = bar("Pressed", 0)
    sim.add_item(st, "load", "pressure", [(b, face(b, "z", 10))], {"magnitude": 0.1})
    st, b = bar("Pulled", 1)
    sim.add_item(st, "load", "pressure", [(b, face(b, "z", 10))], {"magnitude": -0.1})
    st, b = bar("PressFlip", 2)
    sim.add_item(st, "load", "pressure", [(b, face(b, "z", 10))], {"magnitude": 0.1, "flip": True})
    st, b = bar("NormalTop", 3)
    sim.add_item(
        st, "load", "force", [(b, face(b, "z", 10))], {"direction": "normal", "magnitude": 100.0}
    )
    st, b = bar("NormalEnd", 4)
    sim.add_item(
        st, "load", "force", [(b, face(b, "x", 100))], {"direction": "normal", "magnitude": 1000.0}
    )
    st, b = bar("VectorFlip", 5)
    sim.add_item(
        st,
        "load",
        "force",
        [(b, face(b, "x", 100))],
        {"direction": "vector", "vector": [0, 0, -1], "magnitude": 100.0, "flip": True},
    )
    st, b = bar("Twist", 6)
    sim.add_item(
        st, "load", "moment", [(b, face(b, "x", 100))], {"direction": "normal", "magnitude": 1000.0}
    )
    st, b = bar("Falling", 7)
    sim.set_settings(st, {"gravity": {"on": True, "direction": [0, 0, -1]}})
    solved = {}

    def tip(name, axis):
        """Mean movement of the end face (x = 100) along an axis."""

        def read(s, m):
            st, b = made[name]
            if st is not s and st.Name not in solved:
                solved[st.Name] = sim.solve(st, timeout=900)
            return disp_mean(st, axis, lambda p: sb.near(p[0], 100.0, 1e-6))

        return read

    def sign(fn):
        return lambda s, m: math.copysign(1.0, fn(s, m))

    def twist(s, m):
        st, b = made["Twist"]
        if st.Name not in solved:
            solved[st.Name] = sim.solve(st, timeout=900)
        # the top edge of the end face moves along -Y for a turn about +X (right-hand rule)
        return math.copysign(
            1.0,
            disp_mean(st, "y", lambda p: sb.near(p[0], 100.0, 1e-6) and sb.near(p[2], 10.0, 1e-6)),
        )

    E = steel(*made["NormalEnd"])["youngs_mpa"]
    checks = [
        ("pressure pushes into the face: the tip goes down", -1.0, sign(tip("Pressed", "z")), 0.0),
        ("a negative pressure pulls: the tip goes up", 1.0, sign(tip("Pulled", "z")), 0.0),
        ("Flip on a pressure pulls: the tip goes up", 1.0, sign(tip("PressFlip", "z")), 0.0),
        (
            "a normal force on the top face pushes into it: down",
            -1.0,
            sign(tip("NormalTop", "z")),
            0.0,
        ),
        (
            "a normal force on the end face pushes into it (mm): shortens by F L / E A",
            -1000.0 * 100.0 / (E * 100.0),
            tip("NormalEnd", "x"),
            3.0,
        ),
        ("Flip on a force along -Z: the tip goes up", 1.0, sign(tip("VectorFlip", "z")), 0.0),
        ("a moment about the end face's normal (+X) turns the top edge to -Y", -1.0, twist, 0.0),
        ("gravity along -Z: the tip goes down", -1.0, sign(tip("Falling", "z")), 0.0),
    ]
    first = made["Pressed"][0]
    return first, {"checks": checks, "also": [v[0] for k, v in made.items() if k != "Pressed"]}


@case(
    "moved_component",
    "The cantilever inside a component moved by (120, -40, 35) mm and turned 37 degrees about "
    "(1, 1, 0.3): the same numbers as unmoved",
    {"size_pct": 3.0},
)
def moved_component(doc):
    import FreeCAD as App

    from sciforge import simulation as sim

    place = App.Placement(App.Vector(120, -40, 35), App.Rotation(App.Vector(1, 1, 0.3), 37))
    part = doc.addObject("App::Part", "Bracket")
    # 100 N into the end face (along its normal: it turns with the part) and 50 N down at the
    # end, given in design axes and turned by hand the same way as the part
    moved_body, moved = _cantilever_study(
        doc, label="Moved", extra={"direction": "normal", "magnitude": 100.0}
    )
    part.addObject(moved_body)
    part.Placement = place
    doc.recompute()
    down = place.Rotation.multVec(App.Vector(0, 0, -1))
    end = sb.one_face(moved_body, lambda f: sb.near(f.CenterOfMass.x, 100))
    sim.add_item(
        moved,
        "load",
        "force",
        [(moved_body, end)],
        {"direction": "vector", "vector": [down.x, down.y, down.z], "magnitude": 50.0},
    )
    still_body, still = _cantilever_study(
        doc, label="Still", extra={"direction": "normal", "magnitude": 100.0}
    )
    still_body.Placement = App.Placement(App.Vector(0, 200, 0), App.Rotation())
    doc.recompute()
    sim.add_item(
        still,
        "load",
        "force",
        [(still_body, sb.one_face(still_body, lambda f: sb.near(f.CenterOfMass.x, 100)))],
        {"direction": "vector", "vector": [0, 0, -1], "magnitude": 50.0},
    )
    props = steel(moved, moved_body)
    inertia = 10.0**4 / 12.0
    holder = {}

    def still_summary():
        if "m" not in holder:
            holder["m"] = sim.solve(still, timeout=900)
        return holder["m"]

    def bending(study, placement):
        """sigma_xx along the part's own X on its top face (own z = 10, x 20-80 mm) over
        the formula: -F_axial / A + M(x) c / I with M = 50 N (100 - x) (axial load and bending
        added: Gere & Goodno, Mechanics of Materials, the flexure formula, section 5.5, plus
        P / A, section 1.2)."""
        rot = placement.Rotation
        e = rot.multVec(App.Vector(1, 0, 0))
        e = (e.x, e.y, e.z)
        inverse = placement.inverse()
        res = sim.results(study)
        comps = [res.values(k) for k in ("sxx", "syy", "szz", "sxy", "syz", "szx")]
        ratios = []
        for i, p in enumerate(res.points):
            if p is None:
                continue
            q = inverse.multVec(p)
            if not (sb.near(q.z, 10.0, 1e-4) and 20.0 <= q.x <= 80.0):
                continue
            xx, yy, zz, xy, yz, zx = (c[i] for c in comps)
            s = [[xx, xy, zx], [xy, yy, yz], [zx, yz, zz]]
            along = sum(e[a] * s[a][b] * e[b] for a in range(3) for b in range(3))
            ratios.append(along / (-100.0 / 100.0 + 50.0 * (100.0 - q.x) * 5.0 / inertia))
        return sb.mean(ratios)

    def reaction_back(s, m):
        # the moved study's reaction turned back into the part's own axes: the loads are 100
        # N along -X and 50 N along -Z there, so the hold pushes (+100, 0, +50)
        r = m["reactions"]["Fixed 1"]
        back = place.Rotation.inverted().multVec(App.Vector(r["x"], r["y"], r["z"]))
        return abs(back.x - 100.0) + abs(back.y) + abs(back.z - 50.0)

    del props
    checks = [
        (
            "largest displacement = unmoved (mm)",
            lambda: still_summary()["stats"]["displacement"]["max"],
            lambda s, m: m["stats"]["displacement"]["max"],
            1.0,
        ),
        (
            "unmoved: top stress along the part / (-F/A + M c / I), x 20-80 mm",
            1.0,
            lambda s, m: (still_summary(), bending(still, still_body.Placement))[1],
            3.0,
        ),
        (
            "moved and turned: top stress along the part / (-F/A + M c / I), x 20-80 mm",
            1.0,
            lambda s, m: bending(s, place),
            3.0,
        ),
        (
            "reaction = unmoved (N)",
            lambda: still_summary()["reactions"]["Fixed 2"]["total"],
            lambda s, m: reaction(m, "Fixed 1", "total"),
            0.2,
        ),
        (
            "reaction turned with the part (N off (100, 0, 50) in its axes)",
            0.0,
            reaction_back,
            0.5,
        ),
    ]
    return moved, {"checks": checks, "also": [still]}


# -- through the AI tools ---------------------------------------------------------------------
# Each returns rows (check, expected, got, tolerance %) from the AI tools' answers alone
# (study_results' numbers), as an AI app would read them.
AI_CASES = []


def ai_case(name, title):
    def register(fn):
        AI_CASES.append({"name": name, "title": title, "run": fn})
        return fn

    return register


def _ai(tool, args, host):
    from sciforge.ai import headless

    answer = headless.call(tool, args, host)
    if answer["is_error"]:
        raise AssertionError("%s failed: %s" % (tool, answer["text"][:500]))
    return answer


def _ai_json(answer):
    text = answer["text"]
    return json.loads(text[text.find("{") :])


def _ai_host():
    from sciforge.ai import headless

    return headless.HeadlessHost(allow_overwrite=False)


def _ai_steel(host):
    """E, nu, density, yield of the active study's first body, from set_study_material's
    answer (steel, Same as Model)."""
    import FreeCAD as App

    from sciforge import bodies

    body = bodies.solid_bodies(App.ActiveDocument)[0]
    row = _ai_json(
        _ai("set_study_material", {"body": body.Name, "material": "same_as_model"}, host)
    )
    return row


@ai_case("ai_cantilever", "AI tools: box 100 x 10 x 10 mm held at one end, 100 N at the other")
def ai_cantilever(host):
    _ai("new_design", {"name": "QACantilever"}, host)
    _ai("primitive", {"kind": "box", "plane": "XY", "length": 100, "width": 10, "height": 10}, host)
    _ai("create_study", {}, host)
    _ai(
        "add_constraint",
        {"kind": "fixed", "on": [{"face": {"normal": [-1, 0, 0], "count": 1}}]},
        host,
    )
    _ai(
        "add_load",
        {
            "kind": "force",
            "on": [{"face": {"normal": [1, 0, 0], "count": 1}}],
            "magnitude": 100,
            "vector": [0, 0, -1],
        },
        host,
    )
    mat = _ai_steel(host)
    E = mat["youngs_mpa"]
    _ai("solve_study", {}, host)
    data = _ai_json(_ai("study_results", {}, host))
    tip = 100.0 * 100.0**3 / (3 * E * 10.0**4 / 12.0)  # F L^3 / 3EI (Gere & Goodno App. H)
    low = data["safety"]["lowest"]
    vm = data["results"]["von_mises"]["max"]
    return [
        ("tip deflection (mm) = F L^3 / 3EI", tip, data["results"]["displacement"]["max"], 3.0),
        ("reaction (N)", 100.0, data["reactions"]["Fixed 1"]["total"], 0.5),
        ("lowest safety factor = yield / largest von Mises", mat["yield_mpa"] / vm, low, 0.5),
        ("units named mm, N, MPa", 1.0, 1.0 if data["units"] == "mm, N, MPa" else 0.0, 0.0),
    ]


@ai_case("ai_pressure_gravity", "AI tools: the box under 1 MPa on top, then gravity alone")
def ai_pressure_gravity(host):
    import FreeCAD as App

    from sciforge import bodies

    _ai("new_design", {"name": "QAPressure"}, host)
    _ai("primitive", {"kind": "box", "plane": "XY", "length": 100, "width": 10, "height": 10}, host)
    _ai("create_study", {"label": "Pressed"}, host)
    _ai(
        "add_constraint",
        {"kind": "fixed", "on": [{"face": {"normal": [-1, 0, 0], "count": 1}}]},
        host,
    )
    _ai(
        "add_load",
        {"kind": "pressure", "on": [{"face": {"normal": [0, 0, 1], "count": 1}}], "magnitude": 1},
        host,
    )
    mat = _ai_steel(host)
    E, nu = mat["youngs_mpa"], mat["poisson"]
    _ai("solve_study", {"study": "Pressed"}, host)
    data = _ai_json(_ai("study_results", {"study": "Pressed"}, host))
    w, L, a = 1.0 * 10.0, 100.0, 10.0
    inertia = a**4 / 12.0
    G = E / (2 * (1 + nu))
    # cantilever under an even load: w L^4 / 8EI (Gere & Goodno App. H cantilever case 1) plus
    # shear w L^2 / (2 kappa G A)
    tip = w * L**4 / (8 * E * inertia) + w * L * L / (2 * kappa_rect(nu) * G * a * a)
    rows = [
        (
            "1 MPa on top: tip deflection (mm) = wL^4/8EI + wL^2/2kGA",
            tip,
            data["results"]["displacement"]["max"],
            3.0,
        ),
        ("1 MPa on 1000 mm2: reaction (N) = 1000", 1000.0, data["reactions"]["Fixed 1"]["z"], 0.5),
    ]
    _ai("create_study", {"label": "Weight"}, host)
    _ai(
        "add_constraint",
        {"study": "Weight", "kind": "fixed", "on": [{"face": {"normal": [-1, 0, 0], "count": 1}}]},
        host,
    )
    _ai(
        "study_settings",
        {"study": "Weight", "gravity": True, "gravity_direction": [0, 0, -1]},
        host,
    )
    _ai("solve_study", {"study": "Weight"}, host)
    data = _ai_json(_ai("study_results", {"study": "Weight"}, host))
    body = bodies.solid_bodies(App.ActiveDocument)[0]
    weight = mat["density"] * 1e-12 * body.Shape.Volume * 9806.65  # rho V g (N)
    rows.append(("gravity: reaction (N) = rho V g", weight, data["reactions"]["Fixed 2"]["z"], 0.2))
    return rows


@ai_case("ai_moment_units", "AI tools: a shaft 20 mm across twisted by 10000 N mm (10 N m)")
def ai_moment_units(host):
    _ai("new_design", {"name": "QAShaft"}, host)
    _ai("primitive", {"kind": "cylinder", "plane": "XY", "diameter": 20, "height": 100}, host)
    _ai("create_study", {}, host)
    _ai(
        "add_constraint",
        {"kind": "fixed", "on": [{"face": {"normal": [0, 0, -1], "count": 1}}]},
        host,
    )
    _ai(
        "add_load",
        {"kind": "moment", "on": [{"face": {"normal": [0, 0, 1], "count": 1}}], "magnitude": 10000},
        host,
    )
    _ai("study_settings", {"mesh_size": 4}, host)
    mat = _ai_steel(host)
    G = mat["youngs_mpa"] / (2 * (1 + mat["poisson"]))
    _ai("solve_study", {}, host)
    data = _ai_json(_ai("study_results", {}, host))
    r, L, T = 10.0, 100.0, 10000.0
    J = math.pi * (2 * r) ** 4 / 32.0
    # the rim turns T L r / (G J) (Gere & Goodno 3.3); a moment taken as N m would be 1000
    # times bigger
    return [
        (
            "10000 N mm: the rim turns (mm) = T L r / GJ",
            T * L * r / (G * J),
            data["results"]["displacement"]["max"],
            3.0,
        ),
    ]


@ai_case("ai_out_of_date", "AI tools: study_results says OUT OF DATE after the part changed")
def ai_out_of_date(host):
    import FreeCAD as App

    from sciforge import bodies

    _ai("new_design", {"name": "QAOutOfDate"}, host)
    _ai("primitive", {"kind": "box", "plane": "XY", "length": 100, "width": 10, "height": 10}, host)
    _ai("create_study", {}, host)
    _ai(
        "add_constraint",
        {"kind": "fixed", "on": [{"face": {"normal": [-1, 0, 0], "count": 1}}]},
        host,
    )
    _ai(
        "add_load",
        {"kind": "pressure", "on": [{"face": {"normal": [0, 0, 1], "count": 1}}], "magnitude": 1},
        host,
    )
    _ai("solve_study", {}, host)
    before = _ai("study_results", {}, host)["text"]
    doc = App.ActiveDocument
    feature = [
        o
        for o in doc.Objects
        if hasattr(o, "Length") and o.TypeId.startswith("PartDesign::Additive")
    ]
    if not feature:
        raise AssertionError("no primitive box feature to change")
    feature[0].Length = 120
    doc.recompute()
    after = _ai("study_results", {}, host)["text"]
    body = bodies.solid_bodies(doc)[0]
    return [
        ("in date right after the solve", 0.0, 1.0 if "OUT OF DATE" in before else 0.0, 0.0),
        (
            "OUT OF DATE after the box grew to %s mm" % sb._num(body.Shape.BoundBox.XLength),
            1.0,
            1.0 if after.startswith("OUT OF DATE") else 0.0,
            0.0,
        ),
    ]


# -- engine checks: wrong without a word ----------------------------------------------------
ENGINE_CHECKS = []


def engine_check(name):
    def register(fn):
        ENGINE_CHECKS.append((name, fn))
        return fn

    return register


def _pad_beam(doc, length=100.0):
    """A PartDesign body: a 100 x 10 rectangle sketch padded 10 mm (a beam along X), with the
    length a sketch dimension; returns (body, sketch, the length constraint's index)."""
    import FreeCAD as App
    import Part
    import Sketcher

    body = doc.addObject("PartDesign::Body", "Body")
    xy = next(f for f in body.Origin.OriginFeatures if getattr(f, "Role", "") == "XY_Plane")
    sketch = body.newObject("Sketcher::SketchObject", "Sketch")
    sketch.AttachmentSupport = [(xy, "")]
    sketch.MapMode = "FlatFace"
    pts = [(0, 0), (length, 0), (length, 10), (0, 10)]
    for i in range(4):
        a, b = pts[i], pts[(i + 1) % 4]
        sketch.addGeometry(Part.LineSegment(App.Vector(a[0], a[1], 0), App.Vector(b[0], b[1], 0)))
    for i in range(4):
        sketch.addConstraint(Sketcher.Constraint("Coincident", i, 2, (i + 1) % 4, 1))
    sketch.addConstraint(Sketcher.Constraint("Horizontal", 0))
    sketch.addConstraint(Sketcher.Constraint("Horizontal", 2))
    sketch.addConstraint(Sketcher.Constraint("Vertical", 1))
    sketch.addConstraint(Sketcher.Constraint("Vertical", 3))
    sketch.addConstraint(Sketcher.Constraint("Coincident", 0, 1, -1, 1))
    index = sketch.addConstraint(Sketcher.Constraint("DistanceX", 0, 1, 0, 2, length))
    sketch.addConstraint(Sketcher.Constraint("DistanceY", 1, 1, 1, 2, 10.0))
    pad = body.newObject("PartDesign::Pad", "Pad")
    pad.Profile = sketch
    pad.Length = 10.0
    doc.recompute()
    return body, sketch, index


@engine_check("picks follow their faces through edits")
def picks_through_edits(doc, out):
    """A beam made in PartDesign, held at its start face, 100 N down on its end face; the
    design is then edited (longer, a pocket through its middle, rounded top edges) and solved
    after each edit. The force must stay on the end face: the end's deflection is F L^3 / 3EI
    for the new length, the reaction 100 N."""
    import FreeCAD as App
    import Part
    import Sketcher

    from sciforge import simulation as sim

    body, sketch, length_c = _pad_beam(doc)

    def face_at_x(x):
        return sb.one_face(
            body,
            lambda f: f.Surface.TypeId == "Part::GeomPlane"
            and sb.near(f.CenterOfMass.x, x, 1e-6)
            and sb.near(abs(f.normalAt(0, 0).x), 1.0, 1e-9),
        )

    study = sim.create_study(doc)
    sim.set_settings(study, {"mesh": {"size_pct": 4.0}})
    sim.add_item(study, "constraint", "fixed", [(body, face_at_x(0.0))])
    sim.add_item(
        study,
        "load",
        "force",
        [(body, face_at_x(100.0))],
        {"direction": "vector", "vector": [0, 0, -1], "magnitude": 100.0},
    )
    E = sb.material(study, body)["youngs_mpa"]
    inertia = 10.0**4 / 12.0

    def check(step, length, slot=False):
        m = sim.solve(study, timeout=900)
        tip = -disp_mean(study, "z", lambda p: sb.near(p[0], length, 1e-6))
        # F L^3 / 3EI (Gere & Goodno, Appendix H, cantilever case 4); where the slot leaves
        # 6 of the 10 mm width (x 60..80) the beam is 10/6 times as bendy: the tip goes down
        # (10/6 - 1) F / EI x the integral of (L - x)^2 over the slot (unit load method)
        expected = 100.0 * length**3 / (3 * E * inertia)
        if slot:
            extra = ((length - 60.0) ** 3 - (length - 80.0) ** 3) / 3.0
            expected += (10.0 / 6.0 - 1.0) * 100.0 * extra / (E * inertia)
        ok = (
            abs(tip - expected) <= 0.05 * expected
            and abs(m["reactions"]["Fixed 1"]["total"] - 100.0) < 0.5
        )
        out.append(
            (
                "%s: the end (x = %s) bends %.4g mm (beam theory %.4g; %d nodes)"
                % (step, sb._num(length), tip, expected, m["mesh"]["nodes"]),
                ok,
                "notes %s, reaction %s" % (m.get("notes"), m["reactions"]),
            )
        )

    check("as made", 100.0)
    sketch.setDatum(length_c, App.Units.Quantity("140 mm"))
    doc.recompute()
    check("made 140 mm long", 140.0)
    # a pocket through the middle: a 20 x 4 slot at x 60..80 (faces with the same normal as
    # the end face appear: the slot's walls)
    xy = next(f for f in body.Origin.OriginFeatures if getattr(f, "Role", "") == "XY_Plane")
    slot = body.newObject("Sketcher::SketchObject", "Slot")
    slot.AttachmentSupport = [(xy, "")]
    slot.MapMode = "FlatFace"
    pts = [(60, 3), (80, 3), (80, 7), (60, 7)]
    for i in range(4):
        a, b = pts[i], pts[(i + 1) % 4]
        slot.addGeometry(Part.LineSegment(App.Vector(a[0], a[1], 0), App.Vector(b[0], b[1], 0)))
    for i in range(4):
        slot.addConstraint(Sketcher.Constraint("Coincident", i, 2, (i + 1) % 4, 1))
    pocket = body.newObject("PartDesign::Pocket", "Pocket")
    pocket.Profile = slot
    pocket.Type = "ThroughAll"
    pocket.Midplane = True
    doc.recompute()
    if abs(body.Shape.Volume - (140 * 10 - 20 * 4) * 10) > 1e-3:
        raise AssertionError("the slot was not cut: volume %s" % body.Shape.Volume)
    check("with a slot through its middle", 140.0, slot=True)
    sketch.setDatum(length_c, App.Units.Quantity("120 mm"))
    doc.recompute()
    check("then 120 mm long again", 120.0, slot=True)
    # the end face's top edge rounded (r 2 mm): the end face gets smaller, a round face
    # appears next to it; the force stays on the (flat) end face
    tip = body.Tip
    names = [
        "Edge%d" % i
        for i, e in enumerate(tip.Shape.Edges, 1)
        if sb.near(e.CenterOfMass.x, 120.0, 1e-6) and sb.near(e.CenterOfMass.z, 10.0, 1e-6)
    ]
    fillet = body.newObject("PartDesign::Fillet", "Fillet")
    fillet.Base = (tip, names)
    fillet.Radius = 2.0
    doc.recompute()
    if len(names) != 1 or not fillet.Shape.isValid() or fillet.Shape.isNull():
        raise AssertionError("the fillet was not made: %s" % names)
    check("with the end's top edge rounded", 120.0, slot=True)


@engine_check("materials stay with their bodies in any order")
def materials_order(doc, out):
    """Three glued blocks in a row, made in the order aluminium, steel, aluminium but listed
    in the study the other way round, pulled along X: the stretch is the sum of the three
    springs; with materials swapped it would be far off."""
    import FreeCAD as App
    import Part

    from sciforge import simulation as sim

    a = sb.make_body(doc, Part.makeBox(40, 10, 10, App.Vector(80, 0, 0)), "AluEnd")
    s = sb.make_body(doc, Part.makeBox(40, 10, 10, App.Vector(40, 0, 0)), "SteelMid")
    b = sb.make_body(doc, Part.makeBox(40, 10, 10), "AluStart")
    study = sim.create_study(doc, study_bodies=[a, s, b])
    sim.set_study_material(study, a, "aluminium")
    sim.set_study_material(study, b, "aluminium")
    sim.add_item(
        study,
        "constraint",
        "frictionless",
        [(b, sb.one_face(b, lambda f: sb.near(f.CenterOfMass.x, 0)))],
    )
    sim.add_item(study, "constraint", "fixed", [(b, sb.vertex_at(b, (0, 0, 0)))], {"x": False})
    sim.add_item(
        study, "constraint", "fixed", [(b, sb.vertex_at(b, (0, 10, 0)))], {"x": False, "y": False}
    )
    sim.add_item(
        study,
        "load",
        "force",
        [(a, sb.one_face(a, lambda f: sb.near(f.CenterOfMass.x, 120)))],
        {"direction": "vector", "vector": [1, 0, 0], "magnitude": 1000.0},
    )
    m = sim.solve(study, timeout=900)
    es = sb.material(study, s)["youngs_mpa"]
    ea = sb.material(study, a)["youngs_mpa"]
    stretch = 1000.0 * 40 / 100.0 * (2 / ea + 1 / es)  # F L / A per block (series springs)
    got = disp_mean(study, "x", lambda p: sb.near(p[0], 120.0, 1e-6))
    out.append(
        (
            "stretch %.5g mm = sum of F L / E A (%.5g)" % (got, stretch),
            abs(got - stretch) <= 0.02 * stretch,
            m["bodies"],
        )
    )
    names = {key: row["material"] for key, row in m["bodies"].items()}
    expect = {
        "AluEnd": sim.study_material(study, a)[0],
        "SteelMid": sim.study_material(study, s)[0],
        "AluStart": sim.study_material(study, b)[0],
    }
    out.append(
        ("each body's row names its own material", names == expect, "%s vs %s" % (names, expect))
    )


@engine_check("a thin wall at the default mesh is not silently wrong")
def thin_wall_default(doc, out):
    """The clamped circular plate (2.5 mm thick, 100 mm across) at the default mesh: either
    the centre deflection is within 5 % of plate theory, or the solve says its elements are
    too big for the wall (a note) or the pre-check warns."""
    import Part

    from sciforge import simulation as sim

    a, t, q = 50.0, 2.5, 0.1
    body = sb.make_body(doc, Part.makeCylinder(a, t), "Plate")
    study = sim.create_study(doc)
    rim = sb.one_face(body, lambda f: f.Surface.TypeId == "Part::GeomCylinder")
    sim.add_item(study, "constraint", "fixed", [(body, rim)])
    top = sb.one_face(body, lambda f: sb.near(f.CenterOfMass.z, t))
    sim.add_item(study, "load", "pressure", [(body, top)], {"magnitude": q})
    props = sb.material(study, body)
    E, nu = props["youngs_mpa"], props["poisson"]
    D = E * t**3 / (12 * (1 - nu**2))
    w0 = q * a**4 / (64 * D) + q * a**2 / (4 * (5.0 / 6.0) * E / (2 * (1 + nu)) * t)
    warnings = [text for level, text in sim.precheck(study) if level == "warning"]
    m = sim.solve(study, timeout=900)
    got = m["stats"]["displacement"]["max"]
    error = abs(got - w0) / w0 * 100.0
    told = bool(m.get("notes")) or bool(warnings)
    out.append(
        (
            "default mesh: centre deflection %.4g mm vs plate theory %.4g (%.1f %% off); "
            "warned: %s" % (got, w0, error, told),
            error <= 5.0 or told,
            "notes %s; pre-check %s; mesh %s" % (m.get("notes"), warnings, m["mesh"]),
        )
    )
    # and no such note for a solid part at its default mesh (a cantilever 0.3 % off)
    beam, beam_study = _cantilever_study(doc, label="Solid")
    m = sim.solve(beam_study, timeout=900)
    thin = [n for n in m.get("notes") or [] if THIN_WORDS in n]
    out.append(("a solid cantilever at the default mesh: no thin-wall note", not thin, thin))


@engine_check("reactions add up to the loads")
def reactions_balance(doc, out):
    """A bracket held at two faces with a force, a pressure next to a held face, a moment and
    gravity at once: the reactions of all constraints add up to minus the applied loads
    (statics: sum F = 0), to 0.2 %."""
    import FreeCAD as App

    from sciforge import simulation as sim

    body = sb.make_body(doc, boxes((0, 0, 0, 6, 40, 60), (6, 0, 0, 54, 40, 6)), "Bracket")
    study = sim.create_study(doc)
    sim.set_settings(study, {"gravity": {"on": True, "direction": [0, 0, -1]}})
    sim.add_item(
        study,
        "constraint",
        "fixed",
        [(body, sb.one_face(body, lambda f: sb.near(f.CenterOfMass.x, 0)))],
    )
    # 0.2 MPa on the arm's top (it meets the wall plate along an edge: shares nodes with no
    # held face) and 0.05 MPa on the wall plate's front, which touches the held back face's
    # edges? (no: the back face is x = 0, the front x = 6; their edges are apart); the arm's
    # underside (z = 0) shares the bottom edge with the held face
    arm_top = sb.one_face(body, lambda f: sb.near(f.CenterOfMass.z, 6) and f.CenterOfMass.x > 6)
    under = sb.faces(body, lambda f: sb.near(f.CenterOfMass.z, 0))
    sim.add_item(study, "load", "pressure", [(body, arm_top)], {"magnitude": 0.2})
    sim.add_item(study, "load", "pressure", [(body, f) for f in under], {"magnitude": 0.1})
    sim.add_item(
        study,
        "load",
        "force",
        [(body, sb.one_face(body, lambda f: sb.near(f.CenterOfMass.x, 60)))],
        {"direction": "vector", "vector": [0, 1, 0], "magnitude": 30.0},
    )
    m = sim.solve(study, timeout=900)
    rho = sb.material(study, body)["density"] * 1e-12
    weight = 9806.65 * rho * body.Shape.Volume
    area_top = body.Shape.getElement(arm_top).Area
    area_under = sum(body.Shape.getElement(f).Area for f in under)
    # applied: gravity -W z, 0.2 MPa down on the arm's top, 0.1 MPa up on the underside
    # (pressure pushes into the face), 30 N along +Y
    applied = App.Vector(0.0, 30.0, -weight - 0.2 * area_top + 0.1 * area_under)
    r = m["reactions"]["Fixed 1"]
    total = App.Vector(r["x"], r["y"], r["z"]) + applied
    out.append(
        (
            "reaction %s + applied %s = %s (N)"
            % (
                tuple(round(v, 4) for v in (r["x"], r["y"], r["z"])),
                tuple(round(v, 4) for v in applied),
                tuple(round(v, 5) for v in total),
            ),
            total.Length <= 0.002 * applied.Length,
            m["reactions"],
        )
    )


@engine_check("a force's picks")
def force_picks(doc, out):
    """A force on a face and a corner, or a face and an edge, shared: refused with a sentence
    (it used to give the corner the whole force on top of the face's, twice the total, and to
    leave the edge out); per pick (Force Per Entity) each gets the whole force. Per Entity on a
    face that a glued block splits in two: still once (it was given to each piece: twice)."""
    import FreeCAD as App
    import Part

    from sciforge import simulation as sim

    body, study = _cantilever_study(doc, label="Mixed")
    tip = sb.one_face(body, lambda f: sb.near(f.CenterOfMass.x, 100))
    corner = sb.vertex_at(body, (100, 0, 10))
    top_edge = line_at(body, y=0.0, z=10.0)
    vector = {"direction": "vector", "vector": [0, 0, -1], "magnitude": 100.0}
    for label, refs in (
        ("a face and a corner", [tip, corner]),
        ("a face and an edge", [tip, top_edge]),
    ):
        try:
            sim.add_item(study, "load", "force", [(body, r) for r in refs], vector)
            out.append(("shared over %s: refused" % label, False, "it was accepted"))
        except sim.SimulationError as exc:
            out.append(("shared over %s: refused" % label, "one kind" in str(exc), str(exc)))
    try:
        sim.add_item(study, "load", "force", [(body, top_edge)], {"magnitude": 100.0})
        out.append(("along the normal on an edge: refused", False, "it was accepted"))
    except sim.SimulationError as exc:
        out.append(("along the normal on an edge: refused", "no normal" in str(exc), str(exc)))
    for item in sim.items(study, "load"):
        sim.delete_item(item)
    sim.add_item(
        study, "load", "force", [(body, tip), (body, corner)], dict(vector, per_entity=True)
    )
    m = sim.solve(study, timeout=900)
    total = m["reactions"]["Fixed 1"]["total"]
    out.append(
        (
            "per entity on a face and a corner: the hold takes 2 x 100 N (%.6g)" % total,
            abs(total - 200.0) < 1e-6 * 200.0 + 1e-6,
            m["reactions"],
        )
    )
    plate = sb.make_body(doc, Part.makeBox(100, 100, 5, App.Vector(0, 100, 0)), "Plate")
    block = sb.make_body(doc, Part.makeBox(20, 20, 10, App.Vector(40, 140, 5)), "Block")
    st = sim.create_study(doc, study_bodies=[plate, block])
    sim.add_item(
        st,
        "constraint",
        "fixed",
        [(plate, sb.one_face(plate, lambda f: sb.near(f.CenterOfMass.z, 0)))],
    )
    top = sb.one_face(plate, lambda f: sb.near(f.CenterOfMass.z, 5))
    roof = sb.one_face(block, lambda f: sb.near(f.CenterOfMass.z, 15))
    sim.add_item(
        st,
        "load",
        "force",
        [(plate, top), (block, roof)],
        {"direction": "vector", "vector": [0, 0, -1], "magnitude": 1000.0, "per_entity": True},
    )
    m = sim.solve(st, timeout=900)
    total = m["reactions"]["Fixed 2"]["z"]
    out.append(
        (
            "per entity on a plate's top that a glued block splits, and the block's roof: the "
            "hold takes 2 x 1000 N (%.6g)" % total,
            abs(total - 2000.0) < 0.002 * 2000.0,
            m["reactions"],
        )
    )


@engine_check("reactions of two holds that share an edge, linear elements")
def reactions_shared_edge(doc, out):
    """The bracket held at its wall face and, by a second Fixed, at the wall's bottom face
    (they share an edge), under gravity and a sideways force, with linear elements (4-node
    tetrahedra: the loads at held nodes worked out for them too): the two reactions add up
    to minus the loads; before, a node both held counted its whole force in both."""
    import FreeCAD as App

    from sciforge import simulation as sim

    body = sb.make_body(doc, boxes((0, 0, 0, 6, 40, 60), (6, 0, 0, 54, 40, 6)), "Bracket")
    study = sim.create_study(doc)
    sim.set_settings(
        study,
        {"gravity": {"on": True, "direction": [0, 0, -1]}, "mesh": {"order": "linear"}},
    )
    wall = sb.one_face(body, lambda f: sb.near(f.CenterOfMass.x, 0))
    foot = sb.one_face(body, lambda f: sb.near(f.CenterOfMass.z, 0) and f.CenterOfMass.x < 6)
    sim.add_item(study, "constraint", "fixed", [(body, wall)], label="Wall")
    sim.add_item(study, "constraint", "fixed", [(body, foot)], label="Foot")
    sim.add_item(
        study,
        "load",
        "force",
        [(body, sb.one_face(body, lambda f: sb.near(f.CenterOfMass.x, 60)))],
        {"direction": "vector", "vector": [0, 1, 0], "magnitude": 30.0},
    )
    m = sim.solve(study, timeout=900)
    rho = sb.material(study, body)["density"] * 1e-12
    weight = 9806.65 * rho * body.Shape.Volume
    applied = App.Vector(0.0, 30.0, -weight)
    total = App.Vector(*[m["reactions"]["Wall"][a] + m["reactions"]["Foot"][a] for a in "xyz"])
    out.append(
        (
            "Wall + Foot + loads = %s N (loads %s)"
            % (tuple(round(v, 6) for v in total + applied), tuple(round(v, 4) for v in applied)),
            (total + applied).Length <= 0.002 * applied.Length,
            m["reactions"],
        )
    )


@engine_check("reactions on sliding planes")
def reactions_on_planes(doc, out):
    """A quarter of a thick ring (inner 20, outer 40, 10 mm long) on Frictionless planes (its
    two cuts and both ends), 10 MPa inside: the bore's pressure meets the planes along edges,
    where a node is held across the plane and free along it. The plane x = 0 holds the X half
    of the pressure's push, p ri h, the plane y = 0 the Y half, the ends nothing (statics: the
    resultant of a pressure on a quarter cylinder is p ri h along each cut's normal)."""
    import FreeCAD as App
    import Part

    from sciforge import simulation as sim

    ri, ro, h, p = 20.0, 40.0, 10.0, 10.0
    ring = Part.makeCylinder(ro, h, App.Vector(0, 0, 0), App.Vector(0, 0, 1), 90).cut(
        Part.makeCylinder(ri, h, App.Vector(0, 0, 0), App.Vector(0, 0, 1), 90)
    )
    body = sb.make_body(doc, ring, "Ring")
    study = sim.create_study(doc)

    def plane(pred):
        return sb.one_face(body, lambda f: f.Surface.TypeId == "Part::GeomPlane" and pred(f))

    x0 = plane(lambda f: sb.near(f.CenterOfMass.x, 0))
    y0 = plane(lambda f: sb.near(f.CenterOfMass.y, 0))
    ends = sb.faces(
        body, lambda f: f.Surface.TypeId == "Part::GeomPlane" and abs(f.normalAt(0, 0).z) > 0.99
    )
    sim.add_item(study, "constraint", "frictionless", [(body, x0)], label="Cut X")
    sim.add_item(study, "constraint", "frictionless", [(body, y0)], label="Cut Y")
    sim.add_item(study, "constraint", "frictionless", [(body, e) for e in ends], label="Ends")
    bore = sb.one_face(
        body, lambda f: f.Surface.TypeId == "Part::GeomCylinder" and sb.near(f.Surface.Radius, ri)
    )
    sim.add_item(study, "load", "pressure", [(body, bore)], {"magnitude": p})
    m = sim.solve(study, timeout=900)
    push = p * ri * h
    r = m["reactions"]
    for label, expected in (
        ("Cut X", (-push, 0.0, 0.0)),
        ("Cut Y", (0.0, -push, 0.0)),
        ("Ends", (0.0, 0.0, 0.0)),
    ):
        got = (r[label]["x"], r[label]["y"], r[label]["z"])
        off = math.sqrt(sum((a - b) ** 2 for a, b in zip(got, expected)))
        out.append(
            (
                "%s holds (%s) N (statics (%s))"
                % (
                    label,
                    ", ".join("%.5g" % v for v in got),
                    ", ".join("%.5g" % v for v in expected),
                ),
                off <= 0.002 * push,
                r,
            )
        )


@engine_check("the bodies of a study of the whole design")
def design_bodies_check(doc, out):
    """A study with no bodies chosen simulates the design's bodies, shown or hidden: turning a
    body's eye off after a solve (the RESULTS tab says to, to look inside) leaves the results
    in date and the bodies the same (they went by the eyes: hiding the only body made the
    results out of date and left the study with no body); a body a Combine used up is left
    out (it is no longer part of the design)."""
    import FreeCAD as App
    import Part

    from sciforge import combine
    from sciforge import simulation as sim

    body, study = _cantilever_study(doc, label="Beam")
    study.SimBodies = []  # (a study of the whole design)
    sim.solve(study, timeout=900)
    body.Visibility = False
    names = [b.Name for b in sim.study_bodies(study)]
    out.append(("eye off: the same bodies", names == [body.Name], names))
    out.append(("eye off: not out of date", not sim.out_of_date(study), ""))
    body.Visibility = True
    block = sb.make_body(doc, Part.makeBox(10, 10, 5, App.Vector(40, 0, 10)), "Block")
    names = [b.Name for b in sim.study_bodies(study)]
    out.append(("a new body is in the study", names == [body.Name, block.Name], names))
    block.Visibility = False
    names = [b.Name for b in sim.study_bodies(study)]
    out.append(("a new body hidden is still in it", names == [body.Name, block.Name], names))
    combine.build({"target": body, "tools": [block], "operation": "join"})
    doc.recompute()
    names = [b.Name for b in sim.study_bodies(study)]
    out.append(("a body a Combine used up is not", names == [body.Name], names))


@engine_check("nothing asks for a recompute after a solve")
def nothing_touched(doc, out):
    """FreeCAD's recompute mark ("touched") on the study, its items and its results: none after
    a solve, after a setting changed after the solve (it stayed on the study, and was saved
    with the design: it came back touched), or after a study material or an item changed."""
    from sciforge import simulation as sim

    def touched():
        return [o.Name for o in doc.Objects if "Touched" in (o.State or [])]

    body, study = _cantilever_study(doc)
    doc.recompute()
    sim.solve(study, timeout=900)
    out.append(("after the solve", not touched(), touched()))
    sim.set_settings(study, {"keep_results": False})
    sim.set_settings(study, {"keep_results": True})
    out.append(("after Keep results in the file off and on", not touched(), touched()))
    sim.set_study_material(study, body, "aluminium")
    out.append(("after a study material", not touched(), touched()))
    force = sim.items(study, "load")[0]
    sim.update_item(force, opts={"magnitude": 150.0})
    out.append(("after a load changed", not touched(), touched()))
    out.append(("those changes leave the results out of date", sim.out_of_date(study), ""))


@engine_check("along the normal of a curved face")
def normal_of_curved(doc, out):
    """A Force or a Moment along the normal of a round face: refused with a sentence (it took
    the normal at the middle of the face's parameters: a shaft's side face pushed it sideways
    in a direction that has nothing to do with the part); along a vector it is fine."""
    import FreeCAD as App
    import Part

    from sciforge import simulation as sim

    shaft = sb.make_body(
        doc, Part.makeCylinder(10, 100, App.Vector(0, 0, 0), App.Vector(1, 0, 0)), "Shaft"
    )
    study = sim.create_study(doc)
    side = sb.one_face(shaft, lambda f: f.Surface.TypeId == "Part::GeomCylinder")
    for kind in ("force", "moment"):
        try:
            sim.add_item(study, "load", kind, [(shaft, side)], {"direction": "normal"})
            out.append(("%s along a round face's normal: refused" % kind, False, "accepted"))
        except sim.SimulationError as exc:
            out.append(
                ("%s along a round face's normal: refused" % kind, "flat faces" in str(exc), exc)
            )
    item = sim.add_item(
        study, "load", "force", [(shaft, side)], {"direction": "vector", "vector": [0, 0, -1]}
    )
    out.append(("a force along a vector on it: taken", sim.is_item(item), ""))


@engine_check("out of date after a change that keeps the size")
def out_of_date_same_size(doc, out):
    """Changes that keep a body's volume, area, face count and box: a hole moved along a
    plate, a square bar turned a quarter about its own axis (the loaded face is then a side).
    The results must show out of date (the fingerprint went by those numbers only)."""
    import FreeCAD as App
    import Part

    from sciforge import simulation as sim

    def plate(x):
        return Part.makeBox(100, 40, 5).cut(Part.makeCylinder(5, 5, App.Vector(x, 20, 0)))

    body = sb.make_body(doc, plate(30.0), "Plate")
    study = sim.create_study(doc, study_bodies=[body])
    sim.add_item(
        study,
        "constraint",
        "fixed",
        [(body, sb.one_face(body, lambda f: sb.near(f.CenterOfMass.x, 0)))],
    )
    sim.add_item(
        study,
        "load",
        "force",
        [(body, sb.one_face(body, lambda f: sb.near(f.CenterOfMass.x, 100)))],
        {"direction": "vector", "vector": [0, 0, -1], "magnitude": 100.0},
    )
    sim.solve(study, timeout=900)
    out.append(("solved: in date", not sim.out_of_date(study), ""))
    body.BaseFeature.Shape = plate(60.0)
    doc.recompute()
    out.append(("the hole moved from x 30 to 60: out of date", sim.out_of_date(study), ""))
    bar_body, bar = _cantilever_study(doc, label="Bar")
    # 1 MPa on its top face: after a quarter turn that face is a side, pushed sideways
    top = sb.one_face(bar_body, lambda f: sb.near(f.CenterOfMass.z, 10))
    sim.add_item(bar, "load", "pressure", [(bar_body, top)], {"magnitude": 1.0})
    bar_body.Placement = App.Placement(App.Vector(0, 100, 0), App.Rotation())
    doc.recompute()
    sim.solve(bar, timeout=900)
    out.append(("the bar solved: in date", not sim.out_of_date(bar), ""))
    # a quarter turn about its own axis (x through the middle of its 10 x 10 section): the
    # same box, volume, area and faces, but its top face (the pressure's) is now a side
    bar_body.Placement = App.Placement(
        App.Vector(0, 100, 0), App.Rotation(App.Vector(1, 0, 0), 90), App.Vector(0, 5, 5)
    )
    doc.recompute()
    out.append(("the bar turned a quarter about its axis: out of date", sim.out_of_date(bar), ""))


@engine_check("bodies that touch only along an edge or at a corner")
def edge_contacts(doc, out):
    """Two cubes that touch only along an edge (or at a corner) are glued only there, like a
    hinge: the pre-check was green and the solve then failed with "not held enough" (or could
    give nonsense). The pre-check now warns, naming both; bodies that share a face (a block on
    a plate, a cube on a cube's face, a pin in a hole) get no such warning."""
    import FreeCAD as App
    import Part

    from sciforge import simulation as sim

    def pair(name, b_shape, a_shape=None):
        a = sb.make_body(doc, a_shape or Part.makeBox(20, 20, 20), name + "A")
        b = sb.make_body(doc, b_shape, name + "B")
        study = sim.create_study(doc, study_bodies=[a, b])
        sim.add_item(
            study,
            "constraint",
            "fixed",
            [(a, sb.one_face(a, lambda f: sb.near(f.CenterOfMass.z, 0)))],
        )
        return [t for level, t in sim.precheck(study) if level == "warning" and "touch only" in t]

    found = pair("Edge", Part.makeBox(20, 20, 20, App.Vector(20, 0, 20)))
    out.append(("touching along an edge: warned", any("along an edge" in t for t in found), found))
    found = pair("Corner", Part.makeBox(20, 20, 20, App.Vector(20, 20, 20)))
    out.append(("touching at a corner: warned", any("at a corner" in t for t in found), found))
    found = pair("Face", Part.makeBox(10, 10, 10, App.Vector(5, 5, 20)))
    out.append(("a cube on a cube's face: no such warning", not found, found))
    pin = Part.makeCylinder(4, 30, App.Vector(10, 10, -5))
    holed = Part.makeBox(20, 20, 20).cut(Part.makeCylinder(4, 20, App.Vector(10, 10, 0)))
    found = pair("Pin", pin, holed)
    out.append(("a pin in its hole: no such warning", not found, found))


@engine_check("results kept in and dropped from the file")
def kept_and_dropped(doc, out):
    """A solved study saved and reopened: the results come back with the same numbers; with
    Keep results in the file off, only the numbers come back (results None, not out of date);
    a change after reopening makes it out of date."""
    import tempfile

    import FreeCAD as App

    from sciforge import simulation as sim

    body, study = _cantilever_study(doc)
    m = sim.solve(study, timeout=900)
    folder = tempfile.mkdtemp(prefix="sciforge_simqa_")
    try:
        for keep in (True, False):
            sim.set_settings(study, {"keep_results": keep})
            path = os.path.join(folder, "kept%d.FCStd" % int(keep))
            doc.saveCopy(path)
            again = App.openDocument(path)
            try:
                st = sim.studies(again)[0]
                back = sim.summary(st)
                res = sim.results(st)
                same = (
                    abs(back["stats"]["displacement"]["max"] - m["stats"]["displacement"]["max"])
                    < 1e-12
                )
                if keep:
                    ok = res is not None and same and not sim.out_of_date(st)
                    detail = "results %s, same %s, out of date %s" % (
                        res is not None,
                        same,
                        sim.out_of_date(st),
                    )
                    name = "kept: reopened with its results and the same numbers, in date"
                else:
                    ok = (
                        res is None and same and sim.results_dropped(st) and not sim.out_of_date(st)
                    )
                    detail = "results %s, dropped %s" % (res is not None, sim.results_dropped(st))
                    name = "dropped: reopened with the numbers only, in date, says solve again"
                out.append((name, ok, detail))
                if not keep:
                    b2 = sim.study_bodies(st)[0]
                    base = b2.BaseFeature
                    import Part

                    base.Shape = Part.makeBox(110, 10, 10)
                    again.recompute()
                    out.append(
                        (
                            "reopened, then the part changed: out of date",
                            sim.out_of_date(st),
                            "signature changed",
                        )
                    )
            finally:
                App.closeDocument(again.Name)
    finally:
        import shutil

        shutil.rmtree(folder, ignore_errors=True)


# -- running ----------------------------------------------------------------------------------
def _close(doc):
    import FreeCAD as App

    try:
        App.closeDocument(doc.Name)
    except Exception:
        pass


def _row(entry, level, name, expected, got, tol, summary=None, seconds=None, problem=None):
    if problem is None:
        if tol == 0.0:
            ok = got == expected
            error = 0.0 if ok else 100.0
        elif expected == 0:
            error = abs(got)
            ok = error <= tol
        else:
            error = abs(got - expected) / abs(expected) * 100.0
            ok = error <= tol
    else:
        ok, error = False, None
    mesh = (summary or {}).get("mesh", {})
    return {
        "case": entry["name"],
        "title": entry["title"],
        "mesh": level,
        "check": name,
        "expected": expected if problem is None else None,
        "got": got if problem is None else None,
        "error_pct": None if error is None else round(error, 3),
        "tolerance_pct": tol,
        "nodes": mesh.get("nodes"),
        "elements": mesh.get("elements"),
        "seconds": seconds,
        "status": "pass" if ok else "fail",
        "problem": problem,
    }


def run_case(entry, level):
    """Rows for one case at one mesh level ("default" / "fine")."""
    import FreeCAD as App

    from sciforge import simulation as sim

    doc = App.newDocument("QA_%s_%s" % (entry["name"], level))
    rows = []
    try:
        study, extra = entry["build"](doc)
        if isinstance(extra, dict):
            checks, also = extra["checks"], extra.get("also", [])
        else:
            checks, also = extra, []
        if level == "fine":
            for st in [study] + also:
                sim.set_settings(st, {"mesh": dict(entry["fine"])})
        start = time.time()
        summary = sim.solve(study, timeout=900)
        seconds = round(time.time() - start, 2)
        for name, expected, got, tol in checks:
            try:
                if callable(expected):
                    expected = expected()
                value = got(study, summary)
                row = _row(entry, level, name, expected, value, tol, summary, seconds)
                notes = " ".join(summary.get("notes") or [])
                if (
                    row["status"] == "fail"
                    and entry.get("thin")
                    and level == "default"
                    and THIN_WORDS in notes
                ):
                    row["status"] = "pass"
                    row["warned"] = True
                    row["problem"] = "outside the tolerance, and the solve said why: " + notes
                rows.append(row)
            except Exception as exc:
                rows.append(
                    _row(
                        entry,
                        level,
                        name,
                        None,
                        None,
                        tol,
                        summary,
                        seconds,
                        "%s\n%s" % (exc, traceback.format_exc()),
                    )
                )
    except Exception as exc:
        rows.append(
            _row(
                entry,
                level,
                "solve",
                None,
                None,
                None,
                None,
                None,
                "%s\n%s" % (exc, traceback.format_exc()),
            )
        )
    finally:
        _close(doc)
    return rows


def convergence_rows(entry, rows):
    """Does a finer mesh bring a check nearer its hand calculation? For every check off by
    more than 1 % at the default mesh, the finer mesh must be nearer."""
    out = []
    default = {r["check"]: r for r in rows if r["mesh"] == "default"}
    for r in rows:
        if r["mesh"] != "fine" or r["check"] not in default:
            continue
        d = default[r["check"]]
        if d["error_pct"] is None or r["error_pct"] is None or not r["tolerance_pct"]:
            continue
        if d["error_pct"] <= 1.0:
            continue
        ok = r["error_pct"] < d["error_pct"]
        out.append(
            {
                "case": entry["name"],
                "title": entry["title"],
                "mesh": "default -> fine",
                "check": "converges: %s" % r["check"],
                "expected": d["error_pct"],
                "got": r["error_pct"],
                "error_pct": None,
                "tolerance_pct": None,
                "nodes": r["nodes"],
                "elements": r["elements"],
                "seconds": None,
                "status": "pass" if ok else "fail",
                "problem": None if ok else "the finer mesh is not nearer the hand calculation",
            }
        )
    return out


def run_ai_case(entry):
    import FreeCAD as App

    before = set(App.listDocuments())
    rows = []
    try:
        for name, expected, got, tol in entry["run"](_ai_host()):
            rows.append(_row(entry, "AI tools", name, expected, got, tol))
    except Exception as exc:
        rows.append(
            _row(
                entry,
                "AI tools",
                "the calls",
                None,
                None,
                None,
                None,
                None,
                "%s\n%s" % (exc, traceback.format_exc()),
            )
        )
    finally:
        for name in set(App.listDocuments()) - before:
            try:
                App.closeDocument(name)
            except Exception:
                pass
    return rows


def markdown(report):
    lines = [
        "# Static Stress accuracy, QA's own hand calculations",
        "",
        "FreeCAD %s, %s, CalculiX on %s thread(s). %d checks: %s"
        % (
            report["freecad"],
            report["platform"],
            OMP,
            len(report["rows"]) + len(report["engine"]),
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
                sb._num(r["expected"]),
                sb._num(r["got"]),
                sb._num(r["error_pct"]),
                sb._num(r["tolerance_pct"]),
                r["nodes"] if r["nodes"] is not None else "",
                sb._num(r["seconds"]),
                r["status"].upper() + (" (warned)" if r.get("warned") else ""),
            )
        )
    if report.get("engine"):
        lines += ["", "## Engine checks", "", "| Check | | Result |", "|---|---|---|"]
        for r in report["engine"]:
            lines.append("| %s | %s | %s |" % (r["case"], r["check"], r["status"].upper()))
    return "\n".join(lines) + "\n"


def _print_row(App, r):
    App.Console.PrintMessage(
        "[SciForge] simqa %s %s/%s %s: expected %s got %s (%s %%, tolerance %s %%) %s\n"
        % (
            r["status"].upper() + (" (warned)" if r.get("warned") else ""),
            r["case"],
            r["mesh"],
            r["check"],
            sb._num(r["expected"]),
            sb._num(r["got"]),
            sb._num(r["error_pct"]),
            sb._num(r["tolerance_pct"]),
            (r.get("problem") or "")[:800],
        )
    )


# -- sim QA (whole workspace): the builders' open items ------------------------------------
def _plain(motions):
    """free_motions' rows with body labels (a detail must outlive the closed document)."""
    return [([b.Label for b in piece], centre, modes) for piece, centre, modes in motions]


@engine_check("free motions, public (DOF View)")
def free_motions_public(doc, out):
    """simulation.free_motions(study) (DOF View used the engine's private _held_rows and
    _pieces): a block held by nothing can move every way; held by a Frictionless face it can
    slide two ways and turn about the face's normal, the words without rounding noise; Fixed:
    nothing."""
    import Part

    from sciforge import simulation as sim

    block = sb.make_body(doc, Part.makeBox(30, 20, 10), "Block")
    study = sim.create_study(doc, study_bodies=[block])
    found = sim.free_motions(study)
    ok = len(found) == 1 and len(found[0][2]) == 6
    out.append(("held by nothing: every way", ok, str(_plain(found))))
    bottom = sb.one_face(block, lambda f: sb.near(f.CenterOfMass.z, 0.0, 1e-9))
    item = sim.add_item(study, "constraint", "frictionless", [(block, bottom)])
    found = sim.free_motions(study)
    kinds = sorted(m[0] for m in found[0][2]) if found else []
    out.append(
        (
            "frictionless bottom: two slides and a turn",
            kinds == ["slide", "slide", "turn"],
            str(_plain(found)),
        )
    )
    words = [w for _piece, ws in sim.not_held(study) for w in ws]
    out.append(
        (
            "its words: about Z through the middle, no noise",
            "turn about an axis along Z through (15, 10, 5)" in words
            and not any("e-" in w for w in words),
            words,
        )
    )
    sim.delete_item(item)
    sim.add_item(study, "constraint", "fixed", [(block, bottom)])
    left = sim.free_motions(study)
    out.append(("fixed: nothing moves", left == [], str(_plain(left))))


@engine_check("a bearing load's default direction")
def bearing_default(doc, out):
    """A Bearing Load on a hole drilled along Z with no direction given: the engine turns its
    default (-Z, along the hole: no side would take the load) across the hole (-Y), and the
    solve carries the load (reaction = 100 N); a direction along the axis is refused with a
    sentence, through add_item and update_item."""
    import FreeCAD as App
    import Part

    from sciforge import simulation as sim

    plate = Part.makeBox(60, 40, 10).cut(
        Part.makeCylinder(5, 10, App.Vector(40, 20, 0), App.Vector(0, 0, 1))
    )
    body = sb.make_body(doc, plate, "Lug")
    study = sim.create_study(doc, study_bodies=[body])
    hole = sb.one_face(body, lambda f: f.Surface.TypeId == "Part::GeomCylinder")
    end = sb.one_face(body, lambda f: sb.near(f.CenterOfMass.x, 0.0, 1e-9))
    sim.add_item(study, "constraint", "fixed", [(body, end)])
    item = sim.add_item(study, "load", "bearing", [(body, hole)], {"magnitude": 100.0})
    vector = sim.item_data(item)["options"]["vector"]
    out.append(("no direction given: across the hole (-Y)", sb.near(vector[1], -1.0, 1e-9), vector))
    try:
        sim.add_item(study, "load", "bearing", [(body, hole)], {"vector": [0, 0, -1]})
        out.append(("along the hole: refused", False, "accepted"))
    except sim.SimulationError as exc:
        out.append(("along the hole: refused", "along the hole's axis" in str(exc), exc))
    try:
        sim.update_item(item, opts={"vector": [0, 0, 1]})
        out.append(("changed to along the hole: refused", False, "accepted"))
    except sim.SimulationError as exc:
        out.append(("changed to along the hole: refused", "along the hole's axis" in str(exc), exc))
    summary = sim.solve(study, timeout=600)
    total = reaction(summary, "Fixed 1")
    out.append(("the solve carries it: reaction 100 N", sb.near(total, 100.0, 1e-3), total))


@engine_check("a body deleted while it solves")
def deleted_mid_solve(doc, out):
    """The engine itself stops a solve whose body was deleted on the way (sim-ui stopped it in
    its dialog; a script or the AI polling the Job got "Cannot access attribute 'Label' of
    deleted object"): failed with a sentence naming the body, nothing left behind."""
    from sciforge import simulation as sim

    body, study = _cantilever_study(doc, label="Beam")
    job = sim.Job(study)
    tries = 0
    while job.state == "running" and job.stage in ("model",) and tries < 20000:
        tries += 1
        job.poll()
    out.append(("got past the model stage", job.state == "running", (job.state, job.stage)))
    doc.removeObject(body.Name)
    job.wait(120)
    out.append(("stopped: failed", job.state == "failed", (job.state, job.message)))
    out.append(
        (
            "its sentence names the body",
            "Beam was deleted while it solved" in job.message,
            job.message,
        )
    )
    out.append(("no FreeCAD error text", "Cannot access" not in job.message, job.message))
    out.append(("nothing left behind", not sim._orphans(doc), [o.Name for o in sim._orphans(doc)]))
    out.append(("no temporary folder", not os.path.isdir(job.work), job.work))


@engine_check("reading a body's material changes nothing")
def material_read_untouched(doc, out):
    """A PartDesign body made of PLA (MODIFY > Physical Material's way): the study's material
    read (Study Materials, the pre-check, a solve) must not mark the body as changed. Reading a
    value of the body's own material object did: the design asked to be recomputed and stayed
    "unsaved" right after a Save (the bracket journey)."""
    from sciforge import material
    from sciforge import simulation as sim

    body = doc.addObject("PartDesign::Body", "Bracket")
    box = body.newObject("PartDesign::AdditiveBox", "Box")
    box.Length, box.Width, box.Height = 100.0, 10.0, 10.0
    doc.recompute()
    material.assign(body, [r["key"] for r in material.available() if r["label"] == "PLA"][0])
    doc.recompute()

    def touched():
        return [o.Label for o in doc.Objects if "Touched" in (o.State or [])]

    out.append(("PLA assigned, recomputed: nothing to recompute", not touched(), touched()))
    name, props = sim.model_material(body)
    out.append(
        (
            "Same as Model reads PLA's yield 35.9 MPa",
            sb.near(props["yield_mpa"], 35.9, 1e-6),
            (name, props),
        )
    )
    out.append(("reading it: nothing to recompute", not touched(), touched()))
    study = sim.create_study(doc, study_bodies=[body])
    left = sb.one_face(body, lambda f: sb.near(f.CenterOfMass.x, 0.0, 1e-9))
    right = sb.one_face(body, lambda f: sb.near(f.CenterOfMass.x, 100.0, 1e-9))
    sim.add_item(study, "constraint", "fixed", [(body, left)])
    sim.add_item(
        study, "load", "force", [(body, right)], {"direction": "vector", "vector": [0, 0, -1]}
    )
    sim.precheck(study)
    out.append(("the pre-check: nothing to recompute", not touched(), touched()))
    sim.solve(study, timeout=600)
    out.append(("a solve: nothing to recompute", not touched(), touched()))


@engine_check("a design that is only a mesh")
def mesh_only_design(doc, out):
    """A design whose only body is a mesh (an imported STL: Luca's usual start for a printed
    part): the pre-check said only "The study has no solid body to simulate."; it names the
    mesh and says MESH > Convert Mesh makes a solid body of it."""
    import Mesh

    from sciforge import simulation as sim

    part = doc.addObject("Mesh::Feature", "Bracket")
    part.Mesh = Mesh.createBox(20.0, 10.0, 5.0)
    part.Label = "Bracket"
    doc.recompute()
    study = sim.create_study(doc)
    texts = [text for level, text in sim.precheck(study) if level == "error"]
    out.append(("no solid body: red", any("no solid body" in x for x in texts), texts))
    out.append(
        (
            "the mesh named, Convert Mesh offered",
            any("Bracket is a mesh" in x and "Convert Mesh" in x for x in texts),
            texts,
        )
    )


def main():
    import FreeCAD as App

    os.environ["OMP_NUM_THREADS"] = OMP
    out_dir = os.environ.get("SCIFORGE_HEADLESS_OUT") or App.getUserAppDataDir()
    os.makedirs(out_dir, exist_ok=True)
    # (several filters may be given, separated by commas: a case or check runs when its name
    # contains one of them)
    wanted = [w for w in os.environ.get("SCIFORGE_SIM_FILTER", "").split(",") if w]

    def skip(name):
        return bool(wanted) and not any(w in name for w in wanted)

    report = {
        "freecad": ".".join(App.Version()[:3]),
        "platform": platform.platform(),
        "rows": [],
        "engine": [],
    }
    for entry in CASES:
        if skip(entry["name"]):
            continue
        rows = []
        for level in ("default", "fine"):
            rows += run_case(entry, level)
        rows += convergence_rows(entry, rows)
        for r in rows:
            _print_row(App, r)
        report["rows"] += rows
    for entry in AI_CASES:
        if skip(entry["name"]):
            continue
        rows = run_ai_case(entry)
        for r in rows:
            _print_row(App, r)
        report["rows"] += rows
    for name, fn in ENGINE_CHECKS:
        if skip(name):
            continue
        doc = App.newDocument("QAEngine")
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
                "detail": str(detail)[:800],
                "seconds": round(time.time() - start, 2),
            }
            report["engine"].append(row)
            App.Console.PrintMessage(
                "[SciForge] simqa %s engine/%s: %s %s\n"
                % (row["status"].upper(), name, check, "" if ok else row["detail"])
            )
    report["passed"] = (
        bool(report["rows"] or report["engine"])
        and all(r["status"] == "pass" for r in report["rows"])
        and all(r["status"] == "pass" for r in report["engine"])
    )
    with open(os.path.join(out_dir, "sim-accuracy-qa.json"), "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    with open(os.path.join(out_dir, "sim-accuracy-qa.md"), "w", encoding="utf-8") as handle:
        handle.write(markdown(report))
    failed = [r for r in report["rows"] + report["engine"] if r["status"] != "pass"]
    App.Console.PrintMessage(
        "[SciForge] simqa summary: %d checks, %d failed\n"
        % (len(report["rows"]) + len(report["engine"]), len(failed))
    )
    return report
