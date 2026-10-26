# SPDX-License-Identifier: LGPL-2.1-or-later
"""RESULT TOOLS > Report with real clicks (builder sim-results), on a solved steel cantilever.

A  Report: the dialog offers a title, an author, pictures and a file; Save writes one HTML page
   with the study's setup (settings, the material with its strengths, the constraint and the
   load), the mesh, every result's min and max (the solve's numbers), the per-body table, the
   safety factor sentence, the limits of the study, the reaction force at the constraint, a
   picture of the loads and constraints and one of each of three results; the result shown
   before is shown again after.
B  Without pictures: no picture in the page.
C  No file name: the dialog says so and stays open; Preview opens the report in the web browser
   from the temporary folder (the dialog stays open); Cancel writes nothing.
D  Nothing of it lands in the undo history.
E  A second study (300 N) solved: the Report dialog lists both, this one ticked; ticking the
   other, a summary, the project, who approved it, the revision, a logo and a cover picture
   give one page with the cover (logo, picture, summary, properties) and a part per study, each
   with its own numbers and pictures.
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
        ("the reaction force table", "<h3>Reaction force</h3>"),
    ):
        h.check("report has %s" % name, needle in text, needle)
    from sciforge import simulation_results as results_data

    found = results_data.reactions(s.study()) or {}
    totals = [sum(c * c for c in v) ** 0.5 for v in found.values()]
    h.check(
        "the fixed end takes the 100 N",
        len(totals) == 1
        and abs(totals[0] - 100.0) < 0.5
        and "<td>%s</td>" % core.fmt(totals[0]) in text,
        totals,
    )
    h.check("four pictures", text.count("<img ") == 4, text.count("<img "))
    h.check("pictures in the page", text.count("data:image/png;base64,") == 4)
    h.check("the loads and constraints first", "Loads and constraints" in text)
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


def c_preview():
    from sciforge import simulation_results_panels as panels

    dialog = s.dialog("SciForgeSimReport")
    opened = state.setdefault("opened", [])
    state["open_in_browser"] = panels.open_in_browser
    panels.open_in_browser = opened.append  # (no web browser under the test: noted instead)
    s.click_widget(dialog.findChild(QtWidgets.QPushButton, "SciForgeSimReportPreview"))


c_preview.wait_ms = 1500


def c_preview_check():
    from sciforge import simulation_results_panels as panels

    panels.open_in_browser = state.pop("open_in_browser")
    dialog = s.dialog("SciForgeSimReport")
    opened = state.get("opened") or []
    h.check("Preview keeps the dialog open", dialog is not None)
    h.check("Preview opened a page in the web browser", len(opened) == 1, opened)
    if opened:
        h.check("a page in the temporary folder", os.path.isfile(opened[0]), opened[0])
        h.check("not where the report goes", os.path.abspath(opened[0]) != os.path.abspath(PATH3))
        with open(opened[0], encoding="utf-8") as handle:
            h.check("the study's numbers in it", s.study().Label in handle.read())
    if dialog is not None:
        h.check("it says so", "preview" in dialog.message.text().lower(), dialog.message.text())


def c_cancel():
    dialog = s.dialog("SciForgeSimReport")
    s.click_widget(dialog.findChild(QtWidgets.QPushButton, "SciForgeSimReportCancel"))


def c_cancel_check():
    h.check("Cancel closed it", s.dialog("SciForgeSimReport") is None)
    h.check("Cancel wrote nothing", not os.path.isfile(PATH3))
    h.check("nothing in the undo history", s.undo_count() == state["undo"], s.undo_count())


PATH4 = os.path.join(s.OUT, "simres_report_two.html")
LOGO = os.path.join(s.OUT, "simres_report_logo.png")


def e_second():
    """(setup) a second study of the same beam, 300 N, solved; a logo picture."""
    from PySide import QtGui

    for p in (PATH4, LOGO):
        if os.path.isfile(p):
            os.remove(p)
    first = s.study()
    state["first"] = first.Name
    second = s.cantilever_study(s.doc(), s.body(), 300.0, label="Heavy Load")
    s.solve(second)
    state["second"] = second.Name
    image = QtGui.QImage(120, 40, QtGui.QImage.Format_RGB32)
    image.fill(QtGui.QColor("#3fa9f5"))
    image.save(LOGO)
    from sciforge import simulation_ui

    simulation_ui.set_active_study(first)  # (the results shown stay the first study's)
    state["undo2"] = s.undo_count()


def e_report():
    s.big("Report")


def e_fill():
    from PySide import QtCore
    from PySide6 import QtTest

    dialog = s.dialog("SciForgeSimReport")
    h.check("Report dialog open", dialog is not None)
    if dialog is None:
        return
    listing = dialog.findChild(QtWidgets.QListWidget, "SciForgeSimReportStudies")
    names = [listing.item(i).text() for i in range(listing.count())]
    h.check("both studies listed", len(names) == 2 and "Heavy Load" in names, names)
    ticked = [
        listing.item(i).text()
        for i in range(listing.count())
        if listing.item(i).checkState() == QtCore.Qt.Checked
    ]
    h.check("the study shown ticked", ticked == [s.doc().getObject(state["first"]).Label], ticked)
    # tick the other one: a click on its tick box
    for i in range(listing.count()):
        item = listing.item(i)
        if item.text() == "Heavy Load":
            rect = listing.visualItemRect(item)
            QtTest.QTest.mouseClick(
                listing.viewport(),
                QtCore.Qt.LeftButton,
                QtCore.Qt.NoModifier,
                QtCore.QPoint(rect.left() + 10, rect.center().y()),
            )
    summary = dialog.findChild(QtWidgets.QPlainTextEdit, "SciForgeSimReportSummary")
    summary.setFocus()
    QtTest.QTest.keyClicks(summary, "Two loads on the bracket arm.")
    for name, text in (
        ("SciForgeSimReportProject", "Bracket B-12"),
        ("SciForgeSimReportApprover", "M. Rossi"),
        ("SciForgeSimReportRevision", "C"),
        ("SciForgeSimReportLogo", LOGO),
        ("SciForgeSimReportCoverPicture", LOGO),
        ("SciForgeSimReportPath", PATH4),
    ):
        ui.type_into(dialog.findChild(QtWidgets.QLineEdit, name), text)


def e_save():
    dialog = s.dialog("SciForgeSimReport")
    s.click_widget(dialog.findChild(QtWidgets.QPushButton, "SciForgeSimReportSave"))


e_save.wait_ms = 2500


def e_check():
    from sciforge import simulation

    core = s.results_core()
    h.check("the two-study report written", os.path.isfile(PATH4), PATH4)
    if not os.path.isfile(PATH4):
        return
    with open(PATH4, encoding="utf-8") as handle:
        text = handle.read()
    first = s.doc().getObject(state["first"])
    second = s.doc().getObject(state["second"])
    for name, needle in (
        ("the summary", "Two loads on the bracket arm."),
        ("the project", "Bracket B-12"),
        ("who approved it", "M. Rossi"),
        ("the revision", "<td>C</td>"),
        ("the logo", 'class="logo" src="data:image/png;base64,'),
        ("the cover picture", 'class="cover" src="data:image/png;base64,'),
        ("both studies on the cover", "Studies: %s, Heavy Load" % first.Label),
        ("a part for the first study", '<h1 class="study">%s</h1>' % first.Label),
        ("a part for the second", '<h1 class="study">Heavy Load</h1>'),
    ):
        h.check("report has %s" % name, needle in text, needle)
    for study in (first, second):
        low = simulation.summary(study)["stats"]["safety"]["min"]
        h.check("%s's own lowest safety factor" % study.Label, core.fmt(low) in text, low)
    h.check(
        "pictures of both (4 each), the logo and the cover picture",
        text.count("<img ") == 10,
        text.count("<img "),
    )
    h.check("the first study's results still shown", s.session().study is first)
    h.check("nothing in the undo history", s.undo_count() == state["undo2"], s.undo_count())


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
        c_preview,
        c_preview_check,
        c_cancel,
        c_cancel_check,
        e_second,
        e_report,
        e_fill,
        e_save,
        e_check,
    ],
)
