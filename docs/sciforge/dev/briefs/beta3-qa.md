## Beta 3 QA and journeys: rules (after the six builders)

You check one area of beta 3 that another agent built, independently: you did not build it, so
you see what its builder could not. Read `docs/sciforge/dev/briefs/beta3-common.md` (every rule
there applies), the area's brief(s) and the builder's session log and report (the orchestrator
gives you the report), the research file, the plan `docs/sciforge/plan-beta3.md`, and the area's
parity doc.

### QA agents (one per area: sim, autotimeline, vex)
1. Your branch `sf/<area>-qa` already has the builder branch(es) merged. Read the whole diff
   adversarially (`git diff beta3...HEAD`): wrong results, exceptions that can escape a command,
   timer or event handler, FreeCAD errors printed in normal flows, things left in the undo
   history or the saved file that should not be, display state not restored, a Fusion behaviour
   the research documents that was built differently without a reason in the parity doc,
   promised features missing, tests that check nothing, slow paths.
2. Use it like Luca would: real clicks in scenarios, odd orders, Esc half way, undo / redo,
   save / reopen, a second document, components, a body deleted under a feature, empty designs,
   big parts. Write new scenarios `<area>_qa*.py` for what you try.
3. Fix every bug you find, each with a test that fails on the old code (unit test, scenario or
   headless check); commit each fix on its own with a clear message. Large design problems you
   cannot fix in the time: write them down with the evidence.
4. Run every scenario of the area, its unit tests, its headless / benchmark suites, and the
   scenarios of every shared file the area touched (grep which scenarios use those modules); all
   must pass (re-run a timeout alone).
5. Session log `docs/sciforge/sessions/beta3-<area>-qa.md`; report: bugs found and fixed (with
   tests), what you could not fix, every suite's result.

### Journey agents (whole tasks across areas, like a person)
A journey builds a real thing end to end with real clicks and keys only (no shortcuts through
the code except to read results), checks numbers worked out by hand, and fixes what breaks on
the way (each fix with a test). Steps and hand-worked numbers in
`SciForgeTests/gui/journey_<name>_steps.py`; scenarios `journey_<name>*.py`.
