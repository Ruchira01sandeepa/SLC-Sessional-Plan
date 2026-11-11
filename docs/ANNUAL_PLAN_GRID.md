# Seasonal plan workbook (laid out like the supplied U-16 rugby annual plan workbook)

Seasonal plan tab > "Download plan workbook" gives one Excel file:

| Sheet | What it shows | Module |
|---|---|---|
| Annual plan | Week-by-week grid: Periods, Phases, Mesos, Macros, Micros, Dates, Percentage, week hours, Competition, Test, Physical, Mental, Technical, Tactical, Nutrition, Loading index | `annual_grid.py`, `annual_grid_excel.py` |
| Load distribution | Same header, then sprint effort, 20 m repeat sprints, shuttle runs, easy aerobic running, total metres, and bowling (matches, training bowling days, overs per day, spells, overs per week) | `load_distribution.py` |
| Component distribution | The supplied cricket exercise list (spin, fast, fielding) grouped by type, with an x for each phase it suits | `component_distribution.py` |
| One sheet per role and phase (for example "Fast Pre-comp") | A 60-minute session in the layout of the supplied "Session plan" sheet | `session_plans.py` |

`seasonal_workbook.py` assembles the sheets. Endpoints (in `routers/plans.py`):
`GET /squads/{id}/seasons/{id}/seasonal-workbook.xlsx[?roles=fast_bowler,batter]` (all sheets),
`.../annual-plan.xlsx` (annual plan sheet only), `.../annual-plan` (JSON).

What comes from your data and what is a proposal
- From the season, phases and calendar: weeks, dates, months, phase boundaries, match weeks, test weeks, week hours.
- A PROPOSAL for the coaches to confirm: which areas are marked in which phase (`PHASE_RULES`), block lengths, planned
  percentage (25% rising to 90%, lighter week at the end of each preparation block), the loading index, every number on the
  load sheet, and every dose on the session sheets.
- Exercise-to-phase rules come from `exercise_kinds.PHASE_KINDS`; tests check that the grid, the load sheet, the component
  sheet and the session sheets all agree with it.
- Safety choices for U15: sprint runs are 20 m only and effort stops at 90%; no percentage-of-maximum loading; bowling
  overs per day stay under the match-day caution; spells never exceed 5 overs; a match counts as a bowling day (3 a week);
  no strength, power or structured bowling in transition.
- Gaps: no batting or keeping drills exist in the supplied list, so those sessions have a "Coach to add" row. Lab tests are
  not scheduled by the system, so the Lab row stays empty.
