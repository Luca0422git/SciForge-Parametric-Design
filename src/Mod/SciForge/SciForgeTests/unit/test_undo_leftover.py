# SPDX-License-Identifier: LGPL-2.1-or-later
"""When a design closes under a dialog, which undo step is closed (sciforge/undo_leftover.py):
only the step of the closing design's own dialog that the design never joined; never the step
of a dialog still open in another design, nor a command's or a script's. Runs without FreeCAD."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sciforge import undo_leftover as u  # noqa: E402

STEP = ("Hole", 4)


class Closing(unittest.TestCase):
    def test_own_dialog_waiting_closes_the_step(self):
        # Hole open in A, waiting for its face (A has changed nothing), A closed
        self.assertEqual(u.decide("A", STEP, False, False, True, "A"), u.CLOSE)

    def test_designs_that_changed_in_it_keep_their_changes(self):
        self.assertEqual(u.decide("A", STEP, False, True, True, "A"), u.CLOSE_KEEP)

    def test_a_design_that_joined_closes_it_itself(self):
        # FreeCAD commits the step into the design as it goes
        self.assertEqual(u.decide("A", STEP, True, False, True, "A"), u.LEAVE)

    def test_nothing_open(self):
        self.assertEqual(u.decide("A", None, False, False, True, "A"), u.LEAVE)

    def test_another_designs_dialog_keeps_its_step(self):
        # a design (or the throw-away document of a Fillet's compute) closed while B's dialog
        # is open: B's step
        self.assertEqual(u.decide("A", STEP, False, False, True, "B"), u.LEAVE)
        self.assertEqual(u.decide("FilletTemp", STEP, False, False, True, "B"), u.LEAVE)

    def test_no_dialog_open_is_a_command_or_script_step(self):
        self.assertEqual(u.decide("A", STEP, False, False, False, ""), u.LEAVE)

    def test_unknown_dialog_waits(self):
        self.assertEqual(u.decide("A", STEP, False, False, True, ""), u.WAIT)


class Later(unittest.TestCase):
    def test_closed_once_the_dialog_went(self):
        self.assertEqual(u.decide_later(4, STEP, False, False, "", "A"), u.CLOSE)

    def test_waits_while_a_dialog_is_open(self):
        self.assertEqual(u.decide_later(4, STEP, False, True, "", "A"), u.WAIT)
        self.assertEqual(u.decide_later(4, STEP, False, True, "A", "A"), u.WAIT)

    def test_another_designs_dialog_is_left_alone(self):
        self.assertEqual(u.decide_later(4, STEP, False, True, "B", "A"), u.LEAVE)

    def test_a_new_step_or_none_stops(self):
        self.assertEqual(u.decide_later(4, ("Fillet", 5), False, False, "", "A"), u.LEAVE)
        self.assertEqual(u.decide_later(4, None, False, False, "", "A"), u.LEAVE)

    def test_never_takes_back_a_designs_changes(self):
        self.assertEqual(u.decide_later(4, STEP, True, False, "", "A"), u.LEAVE)


if __name__ == "__main__":
    unittest.main()
