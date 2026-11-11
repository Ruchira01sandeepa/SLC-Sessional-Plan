# Data model: workbook sheet -> database table

All five role workbooks (Spin, Fast, Batter, Batting-WK, All-Rounder) share the same 8-sheet layout.
`Fitness Report` is identical in all five. `Initial Screening`, `PDP` and `Scenario` differ only in a few
role labels. The `Development`, `Adaptability` and `Progress Status` sheets differ in which skill rows they list.
So there is **one schema for every role**. The role-specific rows are *data* (`skill_templates`), loaded from
the workbooks themselves by `python -m scripts.seed_templates`.

| Workbook sheet | Tables |
|---|---|
| Initial Screening - PLAYER PROFILE | `players` |
| Initial Screening - NEEDS ANALYSIS (LOW/MOD/HIGH grid) | `needs_analysis_items` (per `screenings` row) |
| Initial Screening - RESEARCH OF PLAY, goals, last year review | `screenings` |
| Initial Screening - PHYSICAL & INJURY STATUS | `player_medical` (**encrypted**, physio only) + `players.availability` (coach-safe summary) |
| PDP - goals #1-3 and measures | `plan_items` (`is_pdp_goal = true`) |
| PDP - Individual Rating Assessment (1-5 grid) | `pdp_rubric_items` (the 50 rows) + `pdp_ratings` (one rating per item per date) |
| PDP - 12-week development focus | `plan_items` (level monthly/weekly) |
| <Role> Skill Analysis | `skill_analyses` + `micro_plan_rows` (Mon-Fri) + `media_evidence` |
| <Role> Development (15-week grid, symbols) | `skill_templates` (kind `development`) + `skill_assessments` |
| <Role> Adaptability (primary / secondary challenges) | `skill_templates` (kinds `adaptability_*`) + `skill_assessments` |
| Progress Status | `skill_templates` (kinds `progress_*`) + `skill_assessments` |
| Scenario | `scenarios` |
| Fitness Report | `fitness_tests` (baseline / mid / end per season) + `fitness_benchmarks` |

Added for features in the spec that the workbook has no sheet for:
`seasons`, `season_phases`, `calendar_events`, `plan_items` (annual/seasonal/monthly/weekly),
`workload_logs`, `wellness_logs`, `alerts`, `audit_log`, `users`, `squads`, `squad_staff`.

## Decisions worth knowing
* **Status symbols** (`?`, Naturally Good, Have to improve, Improving, Good, Complete) are the `ProgressStatus` enum.
* `skill_templates.source_cell` records the workbook cell of every skill, so the Phase-5 Excel export writes to exactly the right cell. A test checks this for every row.
* Skill names repeat inside a workbook (the batter sheet has two "Feet using Away the spine (Range Hitting)" blocks), so templates are unique by **position**, not name.
* Age is computed from `date_of_birth`, never stored.
* One fitness test per player per **season** per phase is enforced by the database.
* `pain_detail` and all of `player_medical` are Fernet-encrypted at rest. Coaches and players only ever see `players.availability`.

## Things in the workbooks that look like template mistakes (kept as-is so export matches)
* Spin Bowler Development: the block `A20:A24` ("Field-setting plan" ... "Repeatability under fatigue") has **no group label**; stored as group `Ungrouped`.
* Spelling in the source ("Octomber", "Agints Spine", "Alingment", "HIGHT") is preserved. It can be corrected in the templates later.
* `Agints Spine` in the batting-task block is probably meant to be "against spin".

## Phase 2 additions
* `fitness_tests.season_id` is now **required**: one test per player / season / phase.
* Needs-analysis grid is validated against the workbook layout (`app/screening_schema.py`).
* Event times are stored in UTC; the UI shows them in the viewer's local time.
