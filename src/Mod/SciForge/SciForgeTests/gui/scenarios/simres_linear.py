# SPDX-License-Identifier: LGPL-2.1-or-later
"""Results of a study meshed with straight (linear, 4-node) elements, strains and English units
(builder sim-results), on a steel cantilever 100 x 10 x 10 mm with 100 N down at the tip.

A  The study's mesh order is Linear: the results draw from 4-node elements (no face split, each
   mesh edge a straight line).
B  Legend > Strain > Normal XX: the beam's top is stretched near the held end (the most positive
   strain on the top face), its bottom squeezed (the most negative on the bottom face).
C  Strain > 1st Principal: on the top face away from the support it equals the stretch along the
   beam (one-way stress there), within 5 %.
D  Stress in psi and ksi: the legend's values are the MPa values converted (1 MPa = 145.04 psi).
E  The design in inches (the browser's Units row > Inch): the displacement shown at once in
   inches, the design's units (Fusion's Simulation follows them); stress stays in ksi, the unit
   chosen in the legend; Results Details' per-body table in ksi and inches too.
"""

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtWidgets

from SciForgeTests.gui import harness as h
from SciForgeTests.gui import simres_steps as s

state = {}


def setup():
    from sciforge import simulation

    Gui.activateWorkbench("SciForgeWorkbench")
    doc = App.newDocument("SimResLinear")
    body = s.beam(doc)
    study = s.cantilever_study(doc, body, 100.0)
    simulation.set_settings(study, {"mesh": {"order": "linear", "size_pct": 4.0}})
    s.solve(study)
    h.fit()


def enter():
    s.workspace("Simulation")


def results():
    s.close_new_study_dialog()
    s.click_tab("sim_results")


def a_check():
    sess = s.session()
    h.check("results shown", sess is not None)
    if sess is None:
        return
    h.check("4-node elements", sess.data.tets.shape[1] == 4, sess.data.tets.shape)
    surf = sess.data.surface
    h.check(
        "faces not split (one triangle per element face)",
        len(surf["triangles"]) == len(surf["faces"]),
    )
    h.check("mesh edges are straight (two nodes each)", surf["lines"].shape[1] == 2)
    h.check(
        "the surface is closed (every edge on two faces)",
        len(surf["lines"]) * 2 == 3 * len(surf["faces"]),
    )


def b_strain():
    s.choose_result("Strain", "Normal XX")


def _extreme(values, test):
    sess = s.session()
    pts = sess.data.points
    best = None
    for n in sess.display.nodes.tolist():
        if test(*pts[n]):
            if best is None or values[n] > values[best]:
                best = n
    return best


def b_check():
    sess = s.session()
    h.check("Strain: Normal XX shown", sess.result == "exx", sess.result)
    exx = sess.data.values("exx")
    top = [
        exx[n]
        for n in sess.display.nodes.tolist()
        if sess.data.points[n][2] > 10 - 1e-6 and sess.data.points[n][0] < 20
    ]
    bottom = [
        exx[n]
        for n in sess.display.nodes.tolist()
        if sess.data.points[n][2] < 1e-6 and sess.data.points[n][0] < 20
    ]
    h.check("the top is stretched near the held end", min(top) > 0, (min(top), max(top)))
    h.check("the bottom is squeezed near the held end", max(bottom) < 0, (min(bottom), max(bottom)))
    h.check(
        "no unit for strain",
        sess.legend_info["unit"] == "" and not s.legend_widget("SciForgeSimResultUnit").isVisible(),
    )
    hooke = 100.0 * 100.0 * 5.0 / (10.0 * 10.0**3 / 12.0) / 200000.0  # M c / I / E
    # straight 4-node elements bend too stiffly (why Fusion's default is parabolic): the order of
    # magnitude only
    h.check(
        "about the beam theory's stretch (M c / I E)",
        0.4 * hooke < max(top) < 1.3 * hooke,
        (max(top), hooke),
    )
    state["exx_top"] = max(top)
    # a top node away from the support, where the stress is one-way (beam bending)
    state["node"] = _extreme(exx, lambda x, y, z: z > 10 - 1e-6 and 25 < x < 45)


def c_principal():
    s.choose_result("Strain", "1st Principal")


def c_check():
    sess = s.session()
    h.check("Strain: 1st Principal shown", sess.result == "strain_1", sess.result)
    e1 = float(sess.data.values("strain_1")[state["node"]])
    exx = float(sess.data.values("exx")[state["node"]])
    h.check("equals the stretch along the beam there", abs(e1 - exx) < 0.05 * abs(exx), (e1, exx))
    h.check("legend title", sess.legend_info["title"] == "Strain: 1st Principal")


def d_psi():
    s.choose_result("Stress")
    s.choose_unit("psi")


def d_check():
    sess = s.session()
    vm = s.stats("von_mises")
    h.check("psi", sess.legend_info["unit"] == "psi")
    h.check(
        "converted", abs(sess.legend_info["max"] - vm["max"] * 145.0377377) < 1e-6 * vm["max"] * 145
    )
    s.choose_unit("ksi")


def d_ksi_check():
    sess = s.session()
    vm = s.stats("von_mises")
    h.check("ksi", sess.legend_info["unit"] == "ksi")
    h.check("converted to ksi", abs(sess.legend_info["max"] - vm["max"] * 0.1450377377) < 1e-6)
    h.check("the max tag in ksi", s.tags("max")[0]["text"].endswith(" ksi"), s.tags("max"))


def e_units():
    from SciForgeTests.gui import timeline_input as ti

    s.choose_result("Displacement")
    h.check("displacement in mm first (a mm design)", s.session().legend_info["unit"] == "mm")
    ti.click_row("Units: mm")


def e_inch():
    from PySide import QtWidgets

    from sciforge import browser_ui

    from SciForgeTests.gui import dialog_input as ui

    panel = browser_ui.UnitsPanel.last
    h.check("Change Active Units opens", panel is not None and not panel._closed)
    if panel is None:
        return
    ui.choose(panel.form.findChild(QtWidgets.QComboBox, "SciForgeUnitType"), "Inch")
    h.task_button("OK")


e_inch.wait_ms = 600


def e_check():
    sess = s.session()
    disp = s.stats("displacement")
    h.check("the legend in inches now", sess.legend_info["unit"] == "in", sess.legend_info["unit"])
    h.check(
        "converted (25.4 mm to the inch)",
        abs(sess.legend_info["max"] - disp["max"] / 25.4) < 1e-12 + 1e-9 * disp["max"],
    )
    h.check("the max tag in inches", s.tags("max")[0]["text"].endswith(" in"), s.tags("max"))
    s.choose_result("Stress")


def e_stress_check():
    h.check("stress in the unit chosen before", s.session().legend_info["unit"] == "ksi")
    s.menu("RESULT TOOLS", "Results Details")


def e_details_check():
    dialog = s.dialog("SciForgeSimDetails")
    h.check("Results Details open", dialog is not None)
    if dialog is None:
        return
    table = dialog.bodies
    heads = [table.horizontalHeaderItem(c).text() for c in range(table.columnCount())]
    h.check(
        "per body in ksi and inches",
        heads[3] == "Max von Mises (ksi)" and heads[5] == "Max displacement (in)",
        heads,
    )
    core = s.results_core()
    vm, disp = s.stats("von_mises"), s.stats("displacement")
    h.check(
        "the values converted",
        table.item(0, 3).text() == core.fmt(core.convert(vm["max"], "ksi"))
        and table.item(0, 5).text() == core.fmt(core.convert(disp["max"], "in")),
        (table.item(0, 3).text(), table.item(0, 5).text()),
    )
    s.click_widget(dialog.findChild(QtWidgets.QPushButton, "SciForgeSimDetailsClose"))


h.run(
    "simres_linear",
    [
        setup,
        enter,
        results,
        a_check,
        b_strain,
        b_check,
        c_principal,
        c_check,
        d_psi,
        d_check,
        d_ksi_check,
        e_units,
        e_inch,
        e_check,
        e_stress_check,
        e_details_check,
    ],
)
