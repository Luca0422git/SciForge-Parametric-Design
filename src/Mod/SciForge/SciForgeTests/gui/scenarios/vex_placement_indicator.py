# SPDX-License-Identifier: LGPL-2.1-or-later
"""The placement indicator made only when it is shown (core patch #18,
docs/sciforge/core-patches.md): FreeCAD 1.1 made one for every part's view when it was
attached, about 8 s of opening a 300-part VEX robot (docs/sciforge/parity/vex-assembly.md).

On a SciForge program with the patch (0.1.0-beta.3.1 or later): a new body's view holds no
indicator; FreeCAD's Show Placement switch makes it and shows it, and hides it again. On
FreeCAD itself (the tests' usual program) or an older SciForge program, only the switch is
checked: it shows and hides the indicator as before.
"""

import FreeCAD as App
import FreeCADGui as Gui
from pivy import coin

from SciForgeTests.gui import harness as h

PATCHED_FROM = "0.1.0-beta.3.1"
s = {}


def patched():
    """Whether this program has core patch #18 (its compiled version says so)."""
    from sciforge import version_core

    built = App.ConfigGet("SciForgeVersion") or ""
    if not version_core.canonical(built):
        return False
    return built == PATCHED_FROM or version_core.newer(built, PATCHED_FROM)


OWN_DEPTH = 5  # the view's root > its annotation > the switch > a 3D annotation > the indicator


def kits(vobj):
    """The view's own placement indicators (not its steps' or origin's, which FreeCAD draws
    inside the body's scene too), and whether one is switched on."""
    kind = coin.SoType.fromName("SoFCPlacementIndicatorKit")
    if kind == coin.SoType.badType():
        return None, None
    search = coin.SoSearchAction()
    search.setType(kind)
    search.setInterest(coin.SoSearchAction.ALL)
    search.setSearchingAll(True)
    search.apply(vobj.RootNode)
    paths = search.getPaths()
    own = [paths[i] for i in range(paths.getLength()) if paths[i].getLength() == OWN_DEPTH]
    shown = False
    for path in own:
        for j in range(path.getLength()):
            node = path.getNode(j)
            if isinstance(node, coin.SoSwitch) and node.whichChild.getValue() == coin.SO_SWITCH_ALL:
                shown = True
    return len(own), shown


def setup():
    Gui.activateWorkbench("SciForgeWorkbench")
    document = App.newDocument("Indicator")
    s["doc"] = document.Name
    body = document.addObject("PartDesign::Body", "Body")
    box = document.addObject("PartDesign::AdditiveBox", "Box")
    body.addObject(box)
    document.recompute()
    s["body"] = body.Name
    h.fit()
    h.check(
        "the program",
        True,
        {"SciForgeVersion": App.ConfigGet("SciForgeVersion"), "patched": patched()},
    )


def body_view():
    return App.getDocument(s["doc"]).getObject(s["body"]).ViewObject


def p1_none_yet():
    count, shown = kits(body_view())
    h.check("the indicator's type is known", count is not None)
    if patched():
        h.check("a new body's view holds no placement indicator", count == 0, count)
    else:
        h.check("(FreeCAD or an older program: one per view, hidden)", not shown, (count, shown))
    body_view().ShowPlacement = True
    Gui.updateGui()


def p2_shown():
    count, shown = kits(body_view())
    h.check("Show Placement shows one indicator", count == 1 and shown, (count, shown))
    body_view().ShowPlacement = False
    Gui.updateGui()


def p3_hidden():
    count, shown = kits(body_view())
    h.check("hidden again (kept for the next time)", count == 1 and not shown, (count, shown))


def cleanup():
    for name in list(App.listDocuments()):
        Gui.getDocument(name).Modified = False
        App.closeDocument(name)


h.run("vex_placement_indicator", [setup, p1_none_yet, p2_shown, p3_hidden, cleanup], paced_by="state")
