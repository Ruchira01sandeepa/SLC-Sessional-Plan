# SLC U15 Player Workload, Development & Seasonal Planning System

Phase 1: data model, authentication, role-based access, encrypted medical data.
Phase 2: player profiles & screening, seasons & calendar, fitness testing with progress reports, and a mobile-friendly web UI at `/ui/`.

## Run it - Windows (PowerShell)
Run each line separately (Windows PowerShell does not understand `&&`):
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # if blocked: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
python -m pip install -r requirements.txt
python -m scripts.make_env                 # creates .env with fresh random keys (do NOT copy .env.example)
alembic upgrade head                       # create the tables
python -m scripts.seed_templates           # load skills / rubric / scenarios from templates\*.xlsx
python -m scripts.create_admin you@example.com "Your Name"
python -m uvicorn app.main:app --reload    # then open http://localhost:8000/
```
Optional demo squad (empty database only): `python -m scripts.demo_data` (password `Demo-Pass-2026`).
Tests: `python -m pytest`.

## Run it - Linux / macOS
```bash
python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
python -m scripts.make_env
alembic upgrade head
python -m scripts.seed_templates
python -m scripts.create_admin you@example.com "Your Name"
python -m uvicorn app.main:app --reload    # API docs at http://localhost:8000/docs, app at /
python -m pytest                           # 93 tests
```
Browser smoke test (optional, needs playwright): `python -m scripts.ui_smoke <outdir>`.

## Before real use (required)
* `SLC_JWT_SECRET` and `SLC_MEDICAL_KEY` **must** be replaced; the built-in values are for development only.
  Generate the medical key with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
* **Back up `SLC_MEDICAL_KEY` separately from the database.** Lose it and every medical record is unreadable.
* Use PostgreSQL (`SLC_DATABASE_URL=postgresql+psycopg://...`) and serve over HTTPS.

## Who can see what
See `app/permissions.py`: one table, readable in a minute. Summary: players see only themselves; coaches / S&C / physio see only their assigned squads; **only physios** read medical detail; admins manage users and squads but cannot read medical detail. Every medical read, write and denied attempt is audited.

## Phase 2 notes
* Fitness results are compared only with the player's own baseline, personal targets, coach benchmarks and squad peers (percentile shown once 5+ players are tested). No adult standards are applied.
* Entry is validated against plausible U15 ranges to catch typos (e.g. a 20 m sprint of `34` instead of `3.4`) and sprint times must increase with distance.
* The UI inserts server data as text only and is served with a strict Content-Security-Policy; API responses are `no-store`.
* Administrator screens (users, squad staff) are available through the API docs at `/docs` for now.

## Update: admin-only mode and seasonal plan

- **Admin-only**: only administrators can sign in by default. To open other roles later, set `SLC_ENABLED_ROLES=coach,sc_coach,physio,player` (or `all`) in `.env` and restart.
- **Existing database?** Run `alembic upgrade head` once (new plan columns).
- **Admin tab**: users, squads, squad staff, season phases.
- **Seasonal plan tab**: pick the player groups, review the plan, Save plan (to track status and coach review), Download Excel.
- **Role-specific measures** (from the role development sheets) are entered on the fitness form and shown in progress.
- **Exercise library** comes from `data/source/exercise_library.txt`; rebuild with `python -m scripts.build_exercise_library`.
- Smoke tests: `python -m scripts.ui_smoke_admin <dir>` (admin-only server on port 8765 with demo data).

## Phase 3: workload and safety

- **Workload tab** (admin, coach, S&C, physio): squad overview, open alerts with "Mark seen". Open a player to log sessions, daily wellness, check a planned session, or set bowling limits.
- **Rules** (`app/workload_rules.py`, one file, fully tested; `GET /workload/rules` lists the numbers):
  - Fast bowlers: 5 overs a spell, 16 a match day (caution at 12, the Cricket Australia level for ages 13 to 15), 3 bowling days in 7, a non-bowling day after every bowling day. These come from the project brief and are **provisional until SLC / provincial approval**.
  - Spin bowlers, all-rounders, batters and keepers have no automatic limits until a coach sets them for that player.
  - Load = RPE x minutes. Load ratio = last 7 days / 4-week average (needs 3 weeks of logs). Flags at 1.3 and 1.5, a 30% rise on last week, no rest day, very uniform days. These are rules of thumb, not proven cut-offs for children.
  - Wellness: pain flag (stop), soreness or fatigue 8+ (warning), low sleep (note). Alerts never contain medical detail.
  - Next-week load guidance is a suggested range for the coach to confirm, adjusted by season phase.
- Players never see alerts or guidance. Existing database: run `alembic upgrade head`.
- Browser check: `python -m scripts.ui_smoke_workload <dir>`.

## Annual plan grid
Seasonal plan tab > "Download plan workbook" gives the 4-part workbook (annual plan, load distribution, component distribution, session plans). See `docs/ANNUAL_PLAN_GRID.md`.


## SLC U15 physical tests (import, categories, individual plans)
Admin or S&C download an Excel template pre-filled with the squad's players, fill the SOP test trials, and import it (Tests tab). Results are saved on each
player's profile, players are banded within their level, and each player gets an individual plan (on screen and as Excel).
See `docs/TESTING_BATTERY.md`. Run `alembic upgrade head` to add the new tables.

## Sign in and access requests
- The sign-in screen has a **Request access** tab. Anyone can ask for a coach, S&C coach, physiotherapist or player account; administrator access is never self-service.
- A request creates a **pending** account that cannot sign in. Administrators see it under **Admin > Access requests**, can change the role, and approve or reject it. Every step is audited.
- The answer to a request is the same whether or not the email is already registered, and a pending or rejected account is only revealed to someone who knows its password, so the form cannot be used to find out who has an account.
- Approved users still need their role in `SLC_ENABLED_ROLES` to sign in (admin-only by default).
- Turn the form off with `SLC_SIGNUP_ENABLED=false`. New requests stop while `SLC_MAX_PENDING_SIGNUPS` (default 50) are waiting.
- Existing database: run `alembic upgrade head` (adds the approval columns; existing users stay approved).

## U15 and U17 squads
Every squad has an age group (**U15** or **U17**), chosen when an administrator creates it (Admin > New squad > Age group).
Everything that depends on age follows the squad, from one file: `app/age_groups.py`.

| | U15 | U17 |
|---|---|---|
| Date-of-birth check | 8-16 years | 12-18 years |
| Fast bowlers: overs a spell / a match day (caution) / bowling days in 7 | 5 / 16 (12) / 3 | 6 / 18 (15) / 3 |
| Planned load peak (annual plan) | 90% | 93% |
| Physical tests | SLC National U15 SOP | the U15 SOP until an U17 SOP exists |

- **The U17 numbers are placeholders, not SLC rules.** They follow published junior fast-bowling guidance for 16-17 year-olds and are shown as provisional in the app (Overview banner, workload rules, seasonal plan). Confirm them with SLC and edit `app/age_groups.py`; nothing else needs to change.
- A coach can still set stricter (or different) limits for one player; those override the age-group defaults.
- A player cannot be added to, or moved into, a squad whose age range they do not fit.
- Existing squads are U15 (the column already existed), so no migration is needed. Add U19 later by adding one entry to `PROFILES`.

## Personal plans: every player gets their own plan
Player page > Physical tests > **Show individual plan** (and **Download plan (Excel)**, which now opens with a one-page *Player plan* sheet).
The plan is built from the player's own profile (`app/player_profile.py`, `app/individual_plan.py`):

| Input | Where it comes from | What it changes |
|---|---|---|
| Test ranks per area and per test, trend since the last window | Tests tab import | Priorities (below rank 50), strengths (70+); the **weakest single test** picks the movement (weak inverted row -> pulling, weak push-ups -> pushing, weak 5-10-5 -> change of direction) |
| PDP ratings 1-5 | Player page > **Development ratings (PDP)** (new) | Low cricket-skill ratings -> goals and drills from the supplied list; low habit ratings -> daily habit goals; physical ratings fill untested areas |
| Needs analysis LOW/MOD/HIGH | Screening | How much each quality matters for *this* player (weights the priorities); role default without it |
| Growth | Maturity status on the profile, or height at two tests 3+ months apart | Growth spurt (about 7+ cm a year): fewer jumps and sprints, low doses for them, lower season peak; fast bowlers in or after the spurt bowl one over fewer per bowling day |
| Training age | Screening starting age | New players: simpler exercises, smaller targets |
| Readiness, logged load, the player's own bowling limits | Workload | Weekly load (rise cap, easy weeks, ratio cap) and bowling |

Each plan has: strengths (with how they help in the player's role), priorities, **measurable goals** (test targets taken from the player's own test group, no more than 8% change per window), exercises with a *why*, cricket-skill drills, a typical week per phase, the weekly load chart and upcoming review dates.
The plan lists which inputs are missing so staff know what would make it more personal.
Evidence used: NSCA long-term athletic development position statement (Lloyd et al. 2016); reviews of training around peak height velocity; Cricket Australia junior pace-bowling guidelines. All numbers are proposals for the coach.

## Editing a plan, saving versions and tracking progress
- **Plan in use:** the newest saved version for the season (or a freshly generated plan until one is saved). *Regenerate from latest data* builds a fresh plan with the newest tests, ratings and logs; save it to make it the plan in use.
- **Edit plan:** swap an exercise for one of that area's alternatives (only work the phase allows), add or remove exercises, change reps and sets, adjust goal targets and dates, add a coach note. Every change previews at once; **Save as new version** keeps it (versions 1, 2, 3... with who and when; the Excel export is the version in use).
- **Log a focus session:** tick what was done, sets and reps (pre-filled with the current dose), technique good, pain. Minutes and RPE also add it to the workload.
- **Automatic progression** (`app/plan_progress.py`), per exercise in 14-day blocks: 2+ sessions with good technique, the reps done and no pain add one rep (one set once the reps are at the target); pain steps back at once and refers to the physiotherapist; anything else holds, with the reason. Readiness Caution or Hold stops progression.
- **Role skills** card (player page): the Development / Adaptability / Progress grids from the workbooks. *Have to improve* becomes goals and matched drills in the plan; *Good*, *Naturally good*, *Complete* are listed as strengths.
- **Batting and keeping drills** were added (`app/data/extra_drills.json`, marked "added"): the supplied list has none. Edit that file to change them.
- Existing database: run `alembic upgrade head` (two new tables: plan versions and exercise logs).

## Age references for the tests (U15 / U17 / U19)
Each test result is also labelled against the player's age group: *Below reference*, *Developing*, *On track* or *Strong for age*
(player page, "For age" column; full table on the Tests tab and in `docs/AGE_REFERENCES.md`). Each age group has its own typo-check range
for imports. When fewer than 5 players of a level are tested, the individual plan places areas against these references instead of
leaving the player without a plan, and test goals aim at the age group's expected value (never more than 8% in one window).
Values are provisional (boys only; published youth data where it exists, estimates where it does not) and live in `app/age_norms.py`.
Squads can now be U15, U17 or U19 (U19 bowling limits are placeholders like U17).
