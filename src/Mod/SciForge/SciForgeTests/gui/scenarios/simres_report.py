# SPDX-License-Identifier: LGPL-2.1-or-later
"""RESULT TOOLS > Report with real clicks (builder sim-results), on a solved steel cantilever.

A  Report: the dialog offers a title, an author, pictures and a file; Save writes one HTML page
   with the study's setup (settings, the material with its strengths, the constraint and the
   load), the mesh, every result's min and max (the solve's numbers), the per-body table, the
   safety factor sentence, the limits of the study and a picture of each of three results;
   the result shown before is shown again after.
B  Without pictures: no picture in the page.
C  No file name: the dialog says so and stays open; Cancel writes nothing.
D  Nothing of it lands in the undo history.
"""

import os

from PySide import QtWidgets

from SciForgeTests.gui import dialog_input as ui
from SciForgeTests.gui import harness as h
from SciForgeTests.gui import simres_steps as s

state = {}
PATH = os.path.join(s.OUT, "simres_report.html")
PATH2 = os.path.join(s.OUT, "simres_report_plain.html")
PATH3 = os.path.join(s.OUT, "simres_report_cancelled.html")


def start():
    for p in (PATH, PATH2, PATH3):
        if os.path.isfile(p):
            os.remove(p)
    state["undo"] = s.undo_count()
    s.workspace("Simulation")


def results():
    s.close_new_study_dialog()
    s.click_tab("sim_results")


def results_check():
    h.check("results shown", s.session() is not None)
    s.choose_result("Displacement")


def a_report():
    s.big("Report")


def a_fill():
    dialog = s.dialog("SciForgeSimReport")
    h.check("Report dialog open", dialog is not None)
    if dialog is None:
        return
    h.check(
        "title proposed from the study",
        dialog.title_field.text() == "%s report" % s.study().Label,
        dialog.title_field.text(),
    )
    h.check("pictures ticked", dialog.pictures.isChecked())
    ui.type_into(dialog.findChild(QtWidgets.QLineEdit, "SciForgeSimReportAuthor"), "Luca")
    ui.type_into(dialog.findChild(QtWidgets.QLineEdit, "SciForgeSimReportPath"), PATH)


def a_save():
    dialog = s.dialog("SciForgeSimReport")
    s.click_widget(dialog.findChild(QtWidgets.QPushButton, "SciForgeSimReportSave"))


a_save.wait_ms = 2500


def a_check():
    core = s.results_core()
    h.check("dialog closed after Save", s.dialog("SciForgeSimReport") is None)
    h.check("report written", os.path.isfile(PATH), PATH)
    if not os.path.isfile(PATH):
        return
    with open(PATH, encoding="utf-8") as handle:
        text = handle.read()
    state["text"] = text
    sf = s.stats("safety")
    vm = s.stats("von_mises")
    disp = s.stats("displacement")
    for name, needle in (
        ("an HTML page", "<!DOCTYPE html>"),
        ("the study's name", s.study().Label),
        ("the author", "Luca"),
        ("the lowest safety factor", core.fmt(sf["min"])),
        ("the highest von Mises stress", core.fmt(vm["max"])),
        ("the largest displacement", core.fmt(disp["max"])),
        ("the material", "Steel"),
        ("the yield strength", "207"),
        ("the constraint", "Fixed 1"),
        ("the load", "Force 1"),
        ("the load's size", "100 N"),
        ("the mesh's nodes", str(s.summary()["mesh"]["nodes"])),
        ("the safety factor sentence", "safety factor target"),
        ("the limits", "Results are a guide"),
        ("the per-body table", "Min safety factor"),
    ):
        h.check("report has %s" % name, needle in text, needle)
    h.check("three pictures", text.count("<img ") == 3, text.count("<img "))
    h.check("pictures in the page", text.count("data:image/png;base64,") == 3)
    h.check("the result shown before is back", s.session().result == "displacement")


def b_plain():
    s.big("Report")
    dialog = s.dialog("SciForgeSimReport")
    s.click_widget(dialog.findChild(QtWidgets.QCheckBox, "SciForgeSimReportPictures"))
    ui.type_into(dialog.findChild(QtWidgets.QLineEdit, "SciForgeSimReportPath"), PATH2)
    s.click_widget(dialog.findChild(QtWidgets.QPushButton, "SciForgeSimReportSave"))


def b_check():
    h.check("plain report written", os.path.isfile(PATH2))
    if os.path.isfile(PATH2):
        with open(PATH2, encoding="utf-8") as handle:
            text = handle.read()
        h.check("no pictures", "<img " not in text)
        h.check("the numbers still there", s.results_core().fmt(s.stats("safety")["min"]) in text)


def c_empty():
    s.big("Report")
    dialog = s.dialog("SciForgeSimReport")
    path = dialog.findChild(QtWidgets.QLineEdit, "SciForgeSimReportPath")
    path.clear()
    s.click_widget(dialog.findChild(QtWidgets.QPushButton, "SciForgeSimReportSave"))


def c_empty_check():
    dialog = s.dialog("SciForgeSimReport")
    h.check("the dialog stays open", dialog is not None)
    if dialog is not None:
        h.check(
            "it says what is missing",
            "Choose where" in dialog.message.text(),
            dialog.message.text(),
        )
        ui.type_into(dialog.findChild(QtWidgets.QLineEdit, "SciForgeSimReportPath"), PATH3)


def c_cancel():
    dialog = s.dialog("SciForgeSimReport")
    s.click_widget(dialog.findChild(QtWidgets.QPushButton, "SciForgeSimReportCancel"))


def c_cancel_check():
    h.check("Cancel closed it", s.dialog("SciForgeSimReport") is None)
    h.check("Cancel wrote nothing", not os.path.isfile(PATH3))
    h.check("nothing in the undo history", s.undo_count() == state["undo"], s.undo_count())


h.run(
    "simres_report",
    [
        s.new_solved_beam("SimResReport"),
        start,
        results,
        results_check,
        a_report,
        a_fill,
        a_save,
        a_check,
        b_plain,
        b_check,
        c_empty,
        c_empty_check,
        c_cancel,
        c_cancel_check,
    ],
)
