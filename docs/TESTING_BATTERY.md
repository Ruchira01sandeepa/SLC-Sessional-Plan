# SLC U15 physical tests: import, categories, individual plans

Source: SLC National U15 Physical Testing SOP. Results are confidential: coaches and S&C of the squad and admin only. Players do not see them.

## Flow
1. Tests tab, choose season and test window (baseline, mid-season, end of season), **Download template**. One sheet per level (Provincial, Super Provincial), one row per player, pre-filled with the system's Player ID and name.
2. Fill the date, Cleared (Yes), height, weight, and up to **3 trials** per test. Leave a blank where there is no result; nothing is ever estimated.
3. **Check file** shows a preview and every problem by sheet, row and column. **Save** stores the valid rows only. Re-importing a window replaces it.
4. Each player's profile shows results (all trials and the best), band, focus areas, readiness and the individual plan (screen + Excel).

## Tests
| Level | Tests |
| --- | --- |
| Provincial | height, weight, Bronco (mm.ss) |
| Super Provincial | height, weight, 2 km run (mm.ss), standing broad jump (cm), push-ups, inverted row (reps), 20 m sprint (s), 5-10-5 (s), plank (s) |

Times in minutes are **mm.ss** (8.25 = 8 min 25 s; seconds 00-59, so 8.75 is rejected). Best of three is final. Bronco and 2 km are never compared. Ranges in `app/test_battery.py` only catch typing errors; coaches should confirm them.

## Categories
* Players are ranked only against players of the **same level** in the same window. No outside standards.
* Test percentile (direction-aware, mid-rank) → area average → overall score → **5 equal bands**: Developing, Emerging, Competent, Advanced, Elite (names are placeholders, edit `BAND_NAMES` in `app/categorisation.py`).
* A band needs at least 5 same-level players with results. A missing test is left out of the average, and the profile says how many areas the band rests on. Provincial players have one ranked area (endurance), shown as such.
* Focus areas = every area below the middle (percentile under 50), weakest first.
* Readiness (Ready / Caution / Hold) comes from the workload alerts and availability. It never changes the band. Caution = 80% load, Hold = no new load.

## Individual plan: development in all areas
Every area of the player's level is in the plan, so the player develops across the board. Areas ranked below the middle are **priority areas** and get about **60%** of the exercise slots (12 per phase, the weakest area the most); the other areas share the remaining 40%, and every area has at least one slot. If nothing is below the middle, all areas share equally. Areas not tested yet are listed with general work.
Focus area -> exercise kinds (`AREA_KINDS` in `app/individual_plan.py`) -> exercises from the supplied list, filtered by `exercise_kinds.PHASE_KINDS`. If a phase does not allow work for an area, the plan says where it is trained. Excel: Test summary, Focus plan, Weekly load, (Progress), then the squad workbook sheets for the player's role.

## Personal sets and reps (`app/dosing.py`)
The supplied exercise list has no sets or reps, so each exercise type has a conservative U15 range (for example 8-12 reps, 2-3 sets). Each exercise in a player's plan starts at the **low end** and builds toward a **personal target**: priority areas aim for the top of the range (the weaker the area, the higher), other areas are kept near the lower-middle, untested areas stay low. In-season work is capped at the middle of the range, transition stays at the low end, and Caution stays at the low end. Nothing goes above the range. The plan says why for every exercise and gives the progression rule: add one rep (or one set once the reps reach the target) every two weeks if technique stays good and there is no pain; hold or step back if the player is sore or tired. Special cases (such as Nordic curls) stay at very low volume.

## Workload in the plan (`app/plan_load.py`)
Load is counted like the workload log: session RPE x minutes (units), a week = 7 days, load ratio = this week / average of the last 4 weeks.
1. **Start:** the player's average weekly load over the last 4 weeks of logged sessions (needs 3 weeks of history). With less, a **low starting estimate of 900 units** is used and the plan says so.
2. **Shape:** the squad's weekly percentage shapes the season: 75% of the starting load at the lowest percentage, 140% at the peak, transition weeks at 60% of that.
3. **Readiness:** Caution = 80%; Hold = nothing planned until a coach or physiotherapist clears the player.
4. **Rise cap:** at most 10% above the week before (counted from the last build week after an easy week).
5. **Match and test weeks:** no increase.
6. **Easy week:** after 3 build weeks the 4th is 75% of the average of the last three; also first if the real load rose 4 weeks in a row.
7. **Load ratio cap:** never above 1.3.
8. **Matches and bowling are inside the week's load.** The week's total is shared as: matches first (fixed by the calendar; each counts 600 units, about 120 minutes at RPE 5, and the plan assumes the player plays every squad match), then bowling (the squad load sheet's overs, counted as 30 units an over; batters and keepers have none), then individual focus sessions (40 or 30 minutes, at most 40% of the week), and what is left is general squad training.
9. **Bowling limits:** overs only come from the squad sheet, which already respects the fast-bowler limits (5 overs a spell, 16 a day, 3 bowling days in 7, matches counted as bowling days). The plan can only reduce them to fit the load, never add. Spin bowlers and all-rounders have no automatic limit; the coach sets theirs.
10. **Match weeks above the limit:** if a match week alone is above the weekly limit, the plan shows it on that week and in the summary instead of hiding it, and plans no other training.
11. **No history:** the 900-unit estimate is training only; the first week's matches are added to it so the first weeks are not all flagged.
Every plan is re-checked by `plan_load.verify()`; any violation is shown on the plan. All numbers are proposals; rises of about 10% are common practice, not a proven safe limit for children.

## Progress between windows
Import the mid-season and end-of-season files the same way (pick the window in the Tests tab). Then:
* A player's profile shows each test across baseline, mid-season and end, the change from the first result to the latest (direction-aware: a faster time or more reps is an improvement; under 0.5% counts as "no clear change"), the band movement, and which focus areas are resolved or new.
* The Tests tab shows one line per player: band movement, tests improved, focus areas resolved or new.
* The player's Excel plan gets a **Progress** sheet once there are two windows. Choosing a later window rebuilds the focus areas and plan from that window's results.
* Only tests present in both windows are compared; nothing is estimated. Bands are relative to the same-level group in each window, so a player can improve and stay in the same band; the screens say so. Bronco and 2 km are never compared.
Endpoints: `GET /players/{id}/test-progress`, `GET /squads/{id}/seasons/{sid}/test-progress`. Code: `app/test_progress.py`.

## Files
`app/test_battery.py`, `app/test_import.py`, `app/test_template_excel.py`, `app/categorisation.py`, `app/individual_plan.py`, `app/dosing.py`, `app/plan_load.py`, `app/individual_plan_excel.py`, `app/test_progress.py`, `app/routers/testing.py`, migration `2458cef34f8b`, `tests/test_testing.py`, `scripts/ui_smoke_testing.py`.

## Still to be fixed by SLC (SOP leaves these open)
Push-up depth, cadence and limit; inverted-row bar height and limit; plank maximum time. The template records the set-up as text.
