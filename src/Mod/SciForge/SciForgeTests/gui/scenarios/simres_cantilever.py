# SPDX-License-Identifier: LGPL-2.1-or-later
"""The RESULTS tab's main path with real clicks (builder sim-results): a steel cantilever
100 x 10 x 10 mm, fixed at one end with 300 N down at the other (about 180 MPa at the held
end: a lowest safety factor near 1.2), solved on this computer.

A  Workspace > Simulation: the SETUP tab is selected, the RESULTS tab is offered (the study has
   results), nothing is drawn yet and the beam shows.
B  A click on the RESULTS tab: the safety factor shows first (Fusion), red-ish at the held end
   and blue at the free end, the legend's max / min are the solve's, the beam itself is hidden
   on the view only (its Visibility, the undo history and the modified mark do not change),
   the min / max tags sit at the solve's places (drawn on the bent shape).
C  Legend > Stress (Von Mises, then 1st Principal) and Displacement: the colours change, the
   legend's values are the solve's; the unit drop-down (in) converts them. Legend Min/Max (not
   for the safety factor): the colours run from 0 to 100 MPa, values above take the top colour,
   the legend says so; Reset from RESULT TOOLS.
D  The legend's Results Details button: the lowest safety factor against the targets in a
   sentence, one row per body with its material; Close.
E  Finish Results: back to SETUP, the beam shows again, nothing of the results is left on the
   view. RESULTS again shows the same result; Workspace > Design takes it all away.
"""

from PySide import QtWidgets

from SciForgeTests.gui import harness as h
from SciForgeTests.gui import simres_steps as s
from SciForgeTests.gui import widget_input as w

state = {}


def a_enter():
    state["undo"] = s.undo_count()
    state["modified"] = s.modified()
    state["visibility"] = s.body().ViewObject.Visibility
    s.workspace("Simulation")


def a_check():
    s.close_new_study_dialog()
    h.check("SETUP tab selected", s.current_tab() == "sim_setup", s.current_tab())
    h.check("RESULTS tab offered (the study has results)", s.tab_visible("sim_results"))
    h.check("no results drawn on SETUP", s.session() is None and not s.result_root_in_view())
    h.check("the beam shows", s.design_switches() != -1)


def b_results():
    s.click_tab("sim_results")


def b_check():
    sess = s.session()
    h.check("results shown on the RESULTS tab", sess is not None)
    if sess is None:
        return
    h.check("RESULTS tab selected", s.current_tab() == "sim_results", s.current_tab())
    h.check("Safety Factor first", sess.result == "safety", sess.result)
    sf = s.stats("safety")
    info = sess.legend_info
    h.check(
        "legend min is the solve's lowest safety factor",
        abs(info["min"] - sf["min"]) < 1e-9,
        (info["min"], sf["min"]),
    )
    h.check("legend max is the solve's highest", abs(info["max"] - sf["max"]) < 1e-9)
    h.check(
        "legend labels",
        s.legend_text("SciForgeSimLegendMin") == "Min: %s" % s.results_core().fmt(sf["min"]),
        s.legend_text("SciForgeSimLegendMin"),
    )
    # the held end's top and bottom edges carry the highest bending stress
    held = s.mean(s.colours_where(lambda x, y, z: x < 1e-6 and (z < 1e-6 or z > 10 - 1e-6)))
    free = s.mean(s.colours_where(lambda x, y, z: x > 100 - 1e-6))
    h.check("held end red-ish (low safety factor)", held[0] > 0.7 and held[2] < 0.2, held)
    h.check("free end blue (high safety factor)", free[2] > 0.8 and free[0] < 0.2, free)
    h.check("the beam is hidden on the view", s.design_switches() == -1)
    h.check("its Visibility is untouched", s.body().ViewObject.Visibility == state["visibility"])
    h.check("the result is drawn", s.result_root_in_view())
    h.check("nothing in the undo history", s.undo_count() == state["undo"], s.undo_count())
    h.check("the design is not marked changed", s.modified() == state["modified"])
    tags = {t["kind"]: t for t in s.tags()}
    h.check("min and max tags", "min" in tags and "max" in tags, list(tags))
    if "min" in tags:
        place = [round(c, 4) for c in sess.data.points[tags["min"]["node"]]]
        h.check("min tag at the solve's place", place == sf["min_at"], (place, sf["min_at"]))
        drawn = sess.display.node_place(tags["min"]["node"])
        h.check(
            "the tag follows the bent shape",
            max(abs(a - b) for a, b in zip(tags["min"]["point"], drawn)) < 1e-6,
        )
    h.check("Adjusted deformation", sess.deformation == "adjusted" and sess.display.factor > 1.0)
    verdict = s.legend_text("SciForgeSimLegendVerdict")
    h.check(
        "the legend says how the lowest safety factor does",
        verdict.startswith("Lowest %s" % s.results_core().fmt(sf["min"])) and "target" in verdict,
        verdict,
    )


def c_stress():
    s.choose_result("Stress")


def c_stress_check():
    sess = s.session()
    vm = s.stats("von_mises")
    info = sess.legend_info
    h.check("Von Mises shown", sess.result == "von_mises", sess.result)
    h.check("legend max = solve's max von Mises", abs(info["max"] - vm["max"]) < 1e-9)
    h.check("legend in MPa", info["unit"] == "MPa", info["unit"])
    held = s.mean(s.colours_where(lambda x, y, z: x < 1e-6 and (z < 1e-6 or z > 10 - 1e-6)))
    tip = s.mean(s.colours_where(lambda x, y, z: x > 100 - 1e-6))
    h.check("highest stress at the held end's top and bottom (red-ish)", held[0] > 0.6, held)
    h.check("low stress at the tip (blue-ish)", tip[2] > 0.6, tip)
    state["max_text"] = s.legend_text("SciForgeSimLegendMax")
    h.check("max label in MPa", state["max_text"].endswith("MPa"), state["max_text"])


def c_principal():
    s.choose_result("Stress", "1st Principal")


def c_principal_check():
    sess = s.session()
    p1 = s.stats("principal_1")
    h.check("1st Principal shown", sess.result == "principal_1", sess.result)
    h.check("legend = solve's 1st principal", abs(sess.legend_info["max"] - p1["max"]) < 1e-9)


def c_displacement():
    s.choose_result("Displacement")


def c_displacement_check():
    sess = s.session()
    d = s.stats("displacement")
    h.check("Displacement Total shown", sess.result == "displacement", sess.result)
    h.check("legend max = solve's max displacement", abs(sess.legend_info["max"] - d["max"]) < 1e-9)
    h.check("beam theory: about 0.6 mm at the tip", 0.54 < d["max"] < 0.66, d["max"])
    tip = s.mean(s.colours_where(lambda x, y, z: x > 100 - 1e-6))
    held = s.mean(s.colours_where(lambda x, y, z: x < 1e-6))
    h.check("tip moves most (red)", tip[0] > 0.8, tip)
    h.check("held end does not move (blue)", held[2] > 0.8, held)


def c_unit():
    s.choose_unit("in")


def c_unit_check():
    sess = s.session()
    d = s.stats("displacement")
    h.check("unit in", sess.legend_info["unit"] == "in", sess.legend_info["unit"])
    h.check(
        "values converted to inches",
        abs(sess.legend_info["max"] - d["max"] / 25.4) < 1e-9,
        sess.legend_info["max"],
    )
    h.check("max label in inches", s.legend_text("SciForgeSimLegendMax").endswith(" in"))


def c_range_safety():
    s.choose_result("Safety Factor")


def c_range_safety_check():
    lg = s.legend()
    h.check("no legend range for the safety factor", not s.results_ui().RangeCommand().IsActive())
    h.check("its menu entry greyed", lg is not None and not lg.range_action.isEnabled())


def c_range_open():
    s.choose_result("Stress")
    lg = s.legend()
    button = lg.findChild(QtWidgets.QToolButton, "SciForgeSimLegendOptions")
    h.check("legend options open Legend Min/Max", w.click_menu(button, "Legend Min/Max..."))


def c_range_type():
    dialog = s.dialog("SciForgeSimRange")
    h.check("Legend Min/Max open", dialog is not None)
    if dialog is None:
        return
    for name, text in (("SciForgeSimRangeMin", "0"), ("SciForgeSimRangeMax", "100")):
        spin = dialog.findChild(QtWidgets.QDoubleSpinBox, name)
        spin.lineEdit().selectAll()
        w.type_text(spin, text)
    s.click_widget(dialog.findChild(QtWidgets.QPushButton, "SciForgeSimRangeOK"))


def c_range_check():
    sess = s.session()
    info = sess.legend_info
    vm = s.stats("von_mises")
    h.check("the colours run from 0 to 100 MPa", info["custom"] and info["hi"] == 100.0, info)
    h.check("the top value 100", info["ticks"][0][1] == "100", info["ticks"][0])
    h.check("the result's own max still shown", abs(info["max"] - vm["max"]) < 1e-9)
    h.check("the legend says so", s.legend().range_label.isVisible(), s.legend().range_label.text())
    above = [
        t
        for n, t in sess.display.node_positions().items()
        if sess.data.values("von_mises")[n] > 100.0
    ]
    h.check("values above 100 take the top colour", above and min(above) > 0.999, above[:5])


def c_range_reset():
    s.menu("RESULT TOOLS", "Legend Min/Max")


def c_range_reset_click():
    dialog = s.dialog("SciForgeSimRange")
    h.check("Legend Min/Max from the ribbon", dialog is not None)
    if dialog is not None:
        s.click_widget(dialog.findChild(QtWidgets.QPushButton, "SciForgeSimRangeReset"))


def c_range_reset_check():
    sess = s.session()
    vm = s.stats("von_mises")
    h.check("Reset: the result's own range again", not sess.legend_info["custom"])
    h.check("up to the max von Mises", abs(sess.legend_info["hi"] - vm["max"]) < 1e-9)
    s.choose_result("Displacement")


def d_details():
    s.click_widget(s.legend_widget("SciForgeSimDetailsButton"))


def d_check():
    dialog = s.dialog("SciForgeSimDetails")
    h.check("Results Details opens from the legend", dialog is not None)
    if dialog is None:
        return
    sf = s.stats("safety")
    text = dialog.headline.text()
    h.check("the lowest safety factor in a sentence", s.results_core().fmt(sf["min"]) in text, text)
    h.check("judged against the targets 3 and 6", "3 to 6" in text or "target 3" in text, text)
    h.check("one row per body", dialog.bodies.rowCount() == 1, dialog.bodies.rowCount())
    h.check("the body's material", "Steel" in dialog.bodies.item(0, 1).text())
    h.check("every result listed", dialog.results.rowCount() >= 10, dialog.results.rowCount())
    state["details"] = dialog


def d_close():
    from PySide import QtWidgets

    dialog = state.get("details")
    close = dialog.findChild(QtWidgets.QPushButton, "SciForgeSimDetailsClose") if dialog else None
    s.click_widget(close)


def d_closed():
    h.check("Results Details closed", s.dialog("SciForgeSimDetails") is None)


def e_finish():
    s.big("Finish Results")


def e_check():
    h.check("back to SETUP", s.current_tab() == "sim_setup", s.current_tab())
    h.check("results gone", s.session() is None and not s.result_root_in_view())
    h.check("the beam shows again", s.design_switches() != -1)
    h.check("no legend left", s.legend() is None)


def e_again():
    s.click_tab("sim_results")


def e_again_check():
    sess = s.session()
    h.check("RESULTS again shows the results", sess is not None)
    h.check("the same result as before", sess is not None and sess.result == "displacement")


def e_design():
    s.workspace("Design")


def e_design_check():
    h.check("DESIGN workspace", s.current_tab() == "solid", s.current_tab())
    h.check("results gone in DESIGN", s.session() is None and not s.result_root_in_view())
    h.check("the beam shows in DESIGN", s.design_switches() != -1)
    h.check("still nothing in the undo history", s.undo_count() == state["undo"])


h.run(
    "simres_cantilever",
    [
        s.new_solved_beam("SimResCantilever", force=300.0),
        a_enter,
        a_check,
        b_results,
        b_check,
        c_stress,
        c_stress_check,
        c_principal,
        c_principal_check,
        c_displacement,
        c_displacement_check,
        c_unit,
        c_unit_check,
        c_range_safety,
        c_range_safety_check,
        c_range_open,
        c_range_type,
        c_range_check,
        c_range_reset,
        c_range_reset_click,
        c_range_reset_check,
        d_details,
        d_check,
        d_close,
        d_closed,
        e_finish,
        e_check,
        e_again,
        e_again_check,
        e_design,
        e_design_check,
    ],
)
