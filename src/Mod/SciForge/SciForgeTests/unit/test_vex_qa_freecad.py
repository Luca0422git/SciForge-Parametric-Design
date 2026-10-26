# SPDX-License-Identifier: LGPL-2.1-or-later
"""Beta 3 VEX QA checks in real FreeCAD without a window: runs
SciForgeTests/headless/vex_qa_check.py (Duplicate With Joints and Rigid Groups, the parts
list of occurrences whose original was deleted, occurrence names, the same STEP file again,
hole centres on parts with real VEX files' traits) and expects every check to pass. Skipped
when FreeCAD is not found (run_tests.sh gives its command in SCIFORGE_FC_CMD)."""

import os
import re
import shlex
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE = os.path.dirname(os.path.dirname(HERE))


def _command():
    cmd = os.environ.get("SCIFORGE_FC_CMD", "").strip()
    return shlex.split(cmd) if cmd else None


@unittest.skipUnless(_command(), "FreeCAD not given (SCIFORGE_FC_CMD)")
class VexQaChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        code = (
            "import sys; sys.path.insert(0, %r); "
            "from SciForgeTests.headless import vex_qa_check as c; c.main()" % MODULE
        )
        run = subprocess.run(_command() + ["-c", code], capture_output=True, text=True, timeout=900)
        cls.output = (run.stdout + run.stderr).replace("\r", "\n")

    def test_every_check_ran(self):
        path = os.path.join(MODULE, "SciForgeTests", "headless", "vex_qa_check.py")
        with open(path, encoding="utf-8") as handle:
            wanted = len(re.findall(r"^def check_", handle.read(), re.M))
        done = re.search(r"vexqa done (\d+)", self.output)
        self.assertIsNotNone(done, self.output[-3000:])
        self.assertEqual(int(done.group(1)), wanted, self.output[-3000:])

    def test_every_check_passes(self):
        failed = re.findall(r"vexqa FAIL (.*)", self.output)
        self.assertEqual(failed, [])


if __name__ == "__main__":
    unittest.main()
