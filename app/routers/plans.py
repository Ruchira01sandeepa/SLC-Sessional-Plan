"""Seasonal plan: generate, save progress, edit status / review, download as Excel."""
import re
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import audit, current_user
from ..models import (CalendarEvent, DevArea, EventType, GoalStatus, PlanItem, PlanLevel, Player, PlayerRole, Scenario, Season,
                      SkillTemplate, SquadStaff, TemplateKind, User, UserRole)
from ..permissions import authorize_squad
from ..annual_grid import YEAR_WEEKS, build_grid
from ..annual_grid_excel import build_grid_workbook
from ..seasonal_workbook import build_seasonal_workbook
from ..plan_excel import build_workbook
from ..season_phases import suggest_phases
from ..seasonal_plan import CATEGORY_VIEWS, PHASE_ORDER, ROLE_ORDER, build_plan, category_grid, category_view
from ..exercises import bowling_types

router = APIRouter(tags=["seasonal plan"])
LK = timezone(timedelta(hours=5, minutes=30))            # Sri Lanka has no daylight saving


def _utc_naive(d: date, end_of_day: bool) -> datetime:
    local = datetime(d.year, d.month, d.day, tzinfo=LK) + (timedelta(days=1) if end_of_day else timedelta())
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def _local_date(dt: datetime) -> date:
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(LK).date()


def _parse_roles(raw: str | None, present: set[str]) -> list[str]:
    if raw:
        wanted = [x.strip() for x in raw.split(",") if x.strip()]
        bad = [x for x in wanted if x not in ROLE_ORDER]
        if bad or not wanted:
            raise HTTPException(422, f"roles must be a comma list of: {', '.join(ROLE_ORDER)}")
        return wanted
    return [r for r in ROLE_ORDER if r in present] or list(ROLE_ORDER)       # empty squad: plan for every role


def _key(phase, area, applies_to) -> str:
    return f"{phase}|{area}|{applies_to or 'all'}"


def _phases_for(season: Season) -> tuple[list[dict], str]:
    """The season's own phases if it has them, otherwise the suggested split."""
    defined = sorted(season.phases, key=lambda p: p.start_date)
    if defined:
        return [{"phase_type": p.phase_type.value, "start_date": p.start_date, "end_date": p.end_date, "focus": p.focus} for p in defined], "defined"
    try:
        return suggest_phases(season.start_date, season.end_date), "suggested"
    except ValueError as e:
        raise HTTPException(422, str(e))


def _roles_and_bowling(db: Session, squad_id: int, roles_param: str | None) -> tuple[list[str], set[str]]:
    """Player roles to plan for (the squad's own, or those asked for) and the bowling types of its all-rounders."""
    players = db.execute(select(Player.role, Player.style).where(Player.squad_id == squad_id, Player.is_active)).all()
    roles = _parse_roles(roles_param, {r.value for r, _ in players})
    bowling: set[str] = set()
    for r, style in players:
        bowling |= bowling_types(r.value, style) or set()
    return roles, bowling


def _generate(db: Session, user: User, squad_id: int, season_id: int, roles_param: str | None, action: str) -> tuple[dict, Season]:
    squad = authorize_squad(db, user, squad_id, action)
    season = db.get(Season, season_id)
    if season is None or season.squad_id != squad_id:
        raise HTTPException(404, "Season not found")

    phases, source = _phases_for(season)

    events = [{"event_type": e.event_type.value, "title": e.title, "date": _local_date(e.start_at)}
              for e in db.scalars(select(CalendarEvent).where(
                  CalendarEvent.squad_id == squad_id,
                  CalendarEvent.start_at >= _utc_naive(season.start_date, False),
                  CalendarEvent.start_at < _utc_naive(season.end_date, True)).order_by(CalendarEvent.start_at))]

    staff: dict[str, list[str]] = {}
    for name, role in db.execute(select(User.full_name, User.role).join(SquadStaff, SquadStaff.user_id == User.id)
                                 .where(SquadStaff.squad_id == squad_id, User.is_active).order_by(User.full_name)):
        staff.setdefault(role.value, []).append(name)

    roles, bowling = _roles_and_bowling(db, squad_id, roles_param)

    role_enums = [PlayerRole(r) for r in roles]
    skills: dict[str, list] = {}
    for t in db.scalars(select(SkillTemplate).where(SkillTemplate.player_role.in_(role_enums), SkillTemplate.kind == TemplateKind.development)
                        .order_by(SkillTemplate.sort_order)):
        skills.setdefault(t.player_role.value, []).append((t.group_name, t.skill_name))
    scenarios: dict[str, list] = {}
    for s in db.scalars(select(Scenario).where(Scenario.player_role.in_(role_enums))):
        scenarios.setdefault(s.player_role.value, []).append((s.title, s.skill))

    plan = build_plan(squad_name=squad.name, season={"name": season.name, "start_date": season.start_date, "end_date": season.end_date},
                      phases=phases, phases_source=source, events=events, staff=staff, roles=roles, bowling_types=bowling or None,
                      skills=skills, scenarios=scenarios, generated_on=datetime.now(LK).date(),
                      age_group=squad.age_group)
    missing = [p for p in PHASE_ORDER if p not in {x["phase_type"] for x in phases}]
    if missing:
        plan["notes"].append("These phases are not defined for this season, so they have no rows: "
                             + ", ".join(m.replace("_", " ") for m in missing) + ". Add them in Admin, Seasons.")
    if db.scalar(select(Player.id).where(Player.squad_id == squad_id, Player.is_active).limit(1)) is None:
        plan["notes"].append("This squad has no players yet, so the plan covers all five player roles.")

    saved = {_key(i.phase_type, i.development_area.value, i.applies_to): i for i in db.scalars(select(PlanItem).where(
        PlanItem.level == PlanLevel.seasonal, PlanItem.squad_id == squad_id, PlanItem.season_id == season_id))}
    for row in plan["rows"]:
        it = saved.get(row["key"])
        if it:
            row["plan_item_id"], row["status"], row["coach_review"] = it.id, it.status.value, it.coach_review
    plan["saved"] = bool(saved)
    plan["squad_id"], plan["season_id"] = squad_id, season_id
    return plan, season


def _check_category(category: str) -> None:
    if category not in CATEGORY_VIEWS:
        raise HTTPException(422, f"Unknown plan category '{category}'. Available: {', '.join(CATEGORY_VIEWS)}")


def _view(plan: dict, category: str | None) -> dict:
    if not category:
        return plan
    _check_category(category)
    return category_view(plan, category)


@router.get("/squads/{squad_id}/seasons/{season_id}/seasonal-plan")
def get_plan(squad_id: int, season_id: int, roles: str | None = Query(None), category: str | None = Query(None),
             db: Session = Depends(get_db), user: User = Depends(current_user)):
    """The squad's seasonal plan; with category=physical, the same plan limited to Strength & Conditioning."""
    return _view(_generate(db, user, squad_id, season_id, roles, "plan.squad.read")[0], category)


@router.post("/squads/{squad_id}/seasons/{season_id}/seasonal-plan/save")
def save_plan(squad_id: int, season_id: int, roles: str | None = Query(None), category: str | None = Query(None),
              db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Store the plan as plan items so status and coach review can be tracked. Re-saving refreshes the text but keeps
    status and review; rows that are no longer generated are removed only if nobody has touched them."""
    plan, _ = _generate(db, user, squad_id, season_id, roles, "plan.squad.write")
    plan = _view(plan, category)
    areas = set(plan["category"]["areas"]) if plan.get("category") else None          # a category save never touches other rows
    existing = {_key(i.phase_type, i.development_area.value, i.applies_to): i for i in db.scalars(select(PlanItem).where(
        PlanItem.level == PlanLevel.seasonal, PlanItem.squad_id == squad_id, PlanItem.season_id == season_id))
        if areas is None or i.development_area.value in areas}
    new = upd = 0
    wanted = set()
    for row in plan["rows"]:
        wanted.add(row["key"])
        it = existing.get(row["key"])
        if it is None:
            it = PlanItem(level=PlanLevel.seasonal, squad_id=squad_id, season_id=season_id, phase_type=row["phase"], applies_to=row["applies_to"],
                          development_area=DevArea(row["development_area"]), status=GoalStatus.not_started)
            db.add(it)
            new += 1
        else:
            upd += 1
        it.goal, it.start_date, it.end_date = row["goal"], row["start_date"], row["end_date"]
        it.planned_activities, it.measurement_method, it.target_outcome = row["planned_activities"], row["measurement_method"], row["target_outcome"]
        it.responsible_label = row["responsible"][:300]
    removed = 0
    for k, it in existing.items():
        if k not in wanted and it.status == GoalStatus.not_started and not it.coach_review:
            db.delete(it)
            removed += 1
    audit(db, user, "seasonal_plan.saved", "season", season_id, f"new={new} updated={upd} removed={removed}")
    db.commit()
    return {"new": new, "updated": upd, "removed": removed}


class ItemUpdate(BaseModel):
    status: GoalStatus | None = None
    coach_review: str | None = Field(default=None, max_length=2000)


@router.patch("/plan-items/{item_id}")
def update_item(item_id: int, body: ItemUpdate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    it = db.get(PlanItem, item_id)
    if it is None or it.level != PlanLevel.seasonal:
        raise HTTPException(404, "Plan item not found")
    authorize_squad(db, user, it.squad_id, "plan.squad.write")
    data = body.model_dump(exclude_unset=True)
    if data.get("status") is not None:
        it.status = data["status"]
    if "coach_review" in data:
        it.coach_review = (data["coach_review"] or "").strip() or None
    audit(db, user, "plan_item.updated", "plan_item", it.id, ",".join(data))
    db.commit()
    return {"id": it.id, "status": it.status.value, "coach_review": it.coach_review}


@router.get("/squads/{squad_id}/seasons/{season_id}/seasonal-plan.xlsx")
def download_plan(squad_id: int, season_id: int, roles: str | None = Query(None), category: str | None = Query(None),
                  db: Session = Depends(get_db), user: User = Depends(current_user)):
    plan, season = _generate(db, user, squad_id, season_id, roles, "plan.squad.read")
    plan = _view(plan, category)
    name = re.sub(r"[^A-Za-z0-9]+", "-", f"seasonal-plan-{plan['squad']}-{season.name}" + (f"-{category}" if category else "")).strip("-") or "seasonal-plan"
    audit(db, user, "seasonal_plan.exported", "season", season_id)
    db.commit()
    return Response(build_workbook(plan), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"'})


# ───────────── annual plan grid (week-by-week, laid out like the supplied annual plan sheet) ─────────────
def _grid(db: Session, user: User, squad_id: int, season_id: int) -> dict:
    squad = authorize_squad(db, user, squad_id, "plan.squad.read")
    season = db.get(Season, season_id)
    if season is None or season.squad_id != squad_id:
        raise HTTPException(404, "Season not found")
    phases, source = _phases_for(season)
    events = []
    year_end = max(season.end_date, season.start_date + timedelta(days=7 * YEAR_WEEKS - 1))   # the plan covers a whole year
    for e in db.scalars(select(CalendarEvent).where(
            CalendarEvent.squad_id == squad_id, CalendarEvent.start_at >= _utc_naive(season.start_date, False),
            CalendarEvent.start_at < _utc_naive(year_end, True)).order_by(CalendarEvent.start_at)):
        hours = None
        if e.end_at and e.end_at > e.start_at:
            hours = min((e.end_at - e.start_at).total_seconds() / 3600, 12)       # a stray end date cannot add days of hours
        events.append({"event_type": e.event_type.value, "date": _local_date(e.start_at), "hours": hours, "title": e.title})
    try:
        g = build_grid(squad_name=squad.name, season={"name": season.name, "start_date": season.start_date, "end_date": season.end_date},
                       phases=phases, events=events, generated_on=datetime.now(LK).date(), age_group=squad.age_group, year=True)
    except ValueError as e:
        raise HTTPException(422, str(e))
    # "rest" days in the Calendar: no practice, like the Sri Lankan public holidays (weekly_sessions)
    g["rest_days"] = {ev["date"]: ev.get("title") or "Rest day (Calendar)" for ev in events if ev["event_type"] == "rest"}
    if source == "suggested":
        g["notes"].append("The season has no phases set, so a SUGGESTED split is used. Set the real dates in Admin, Seasons.")
    return g


@router.get("/squads/{squad_id}/seasons/{season_id}/annual-plan")
def annual_plan(squad_id: int, season_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """The grid as JSON (for a screen or a test). Dates are ISO strings."""
    g = _grid(db, user, squad_id, season_id)
    return {**g, "week_starts": [d.isoformat() for d in g["week_starts"]], "generated_on": g["generated_on"].isoformat()}


@router.get("/squads/{squad_id}/seasons/{season_id}/annual-plan.xlsx")
def download_annual_plan(squad_id: int, season_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    g = _grid(db, user, squad_id, season_id)
    name = re.sub(r"[^A-Za-z0-9]+", "-", f"annual-plan-{g['squad']}-{g['season']}").strip("-") or "annual-plan"
    audit(db, user, "annual_plan.exported", "season", season_id)
    db.commit()
    return Response(build_grid_workbook(g), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"'})


@router.get("/squads/{squad_id}/seasons/{season_id}/seasonal-workbook.xlsx")
def download_seasonal_workbook(squad_id: int, season_id: int, roles: str | None = Query(None), category: str | None = Query(None),
                               db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Annual plan, load distribution, component distribution and one session plan per role and phase, in one workbook.
    With category=physical the annual-plan sheet keeps only the Physical rows (the session plans are S&C sessions already)."""
    g = _grid(db, user, squad_id, season_id)
    if category:
        _check_category(category)
        g = category_grid(g, category)
    player_roles, bowling = _roles_and_bowling(db, squad_id, roles)
    name = re.sub(r"[^A-Za-z0-9]+", "-", f"seasonal-plan-workbook-{g['squad']}-{g['season']}" + (f"-{category}" if category else "")).strip("-") or "seasonal-plan-workbook"
    audit(db, user, "seasonal_workbook.exported", "season", season_id)
    db.commit()
    return Response(build_seasonal_workbook(g, player_roles, bowling or None), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"'})


# ───────────── the periodized annual plan (ANNUAL PLAN BUILDER: Zatsiorsky & Kraemer + NSCA), beside the other plans ─────────────
def _periodized(db: Session, user: User, squad_id: int, season_id: int, perm: str = "plan.squad.read"):
    """(squad plan, the latest window's sessions by player id) - the squad's periodized plan and the test data behind it."""
    from ..periodized_plan import YEAR_WEEKS_DEFAULT, build
    from .testing import _finals, _windows_for
    squad = authorize_squad(db, user, squad_id, perm)
    season = db.get(Season, season_id)
    if season is None or season.squad_id != squad_id:
        raise HTTPException(404, "Season not found")
    phases, _source = _phases_for(season)
    year_end = max(season.end_date, season.start_date + timedelta(days=7 * YEAR_WEEKS_DEFAULT - 1))
    matches = [{"date": _local_date(e.start_at), "title": e.title} for e in db.scalars(select(CalendarEvent).where(
        CalendarEvent.squad_id == squad_id, CalendarEvent.event_type == EventType.match,
        CalendarEvent.start_at >= _utc_naive(season.start_date, False), CalendarEvent.start_at < _utc_naive(year_end, True)))]
    results: dict[str, list[float]] = {}
    wins = _windows_for(db, squad_id, season_id)
    sessions = wins[list(wins)[-1]][1] if wins else {}
    for sess in sessions.values():
        for k, v in _finals(sess).items():
            results.setdefault(k, []).append(v)
    players = db.scalar(select(func.count()).select_from(Player).where(Player.squad_id == squad_id, Player.is_active)) or 0
    try:
        plan = build(squad=squad.name, age_group=squad.age_group or "U15",
                     season={"name": season.name, "start_date": season.start_date, "end_date": season.end_date},
                     phases=phases, matches=matches, results=results, players=players)
    except (ValueError, AssertionError) as e:
        raise HTTPException(422, f"The periodized plan could not be built for this season: {e}")
    return plan, sessions


@router.get("/squads/{squad_id}/seasons/{season_id}/periodized-plan.xlsx")
def download_periodized_plan(squad_id: int, season_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Year -> mesocycle -> microcycle -> session plan with its Inputs, Week data, Load chart, Methods by phase, Mesocycles,
    Microcycles, Conditioning and Resistance detail, Session plans and Checks (every rule recalculated by formula)."""
    from ..periodized_excel import build_workbook
    plan, _ = _periodized(db, user, squad_id, season_id)
    audit(db, user, "periodized_plan.exported", "season", season_id)
    db.commit()
    return _xlsx(build_workbook(plan), f"Periodized-annual-plan-{plan['squad']}-{plan['season']['name']}")


@router.get("/squads/{squad_id}/seasons/{season_id}/periodized-plan/{player_id}.xlsx")
def download_player_periodized_plan(squad_id: int, season_id: int, player_id: int, db: Session = Depends(get_db),
                                    user: User = Depends(current_user)):
    """One player's periodized annual plan: the squad's plan made personal from the player's own test ranks (weak areas raised
    with extra work, strong areas keep the full squad work), with the same sheets and the same formula checks."""
    from ..periodized_excel import build_workbook
    from ..periodized_plan import personalize
    from ..session_plans import ROLE_LABEL
    from ..test_battery import BY_KEY, display
    from .testing import _finals
    authorize_squad(db, user, squad_id, "testing.read")
    pl = db.get(Player, player_id)
    if pl is None or pl.squad_id != squad_id:
        raise HTTPException(404, "Player not found in this squad")
    plan, sessions = _periodized(db, user, squad_id, season_id, "testing.read")
    own = sessions.get(pl.id)
    shown = [(BY_KEY[k].label, f"best {display(BY_KEY[k], v)} {BY_KEY[k].unit}") for k, v in (_finals(own).items() if own else []) if k in BY_KEY]
    from .testing import body_measures
    shown += [(k, v) for k, v in body_measures(db, pl.id, season_id) if v != "-"]          # sit and reach, skinfolds, height, weight
    plan = personalize(plan, name=pl.full_name, role=ROLE_LABEL.get(pl.role.value, pl.role.value),
                       areas=_latest_areas(db, squad_id, season_id).get(pl.id, []), own_results=shown)
    audit(db, user, "periodized_plan.exported", "player", pl.id)
    db.commit()
    return _xlsx(build_workbook(plan), f"Periodized-plan-{pl.full_name}-{plan['season']['name']}")


# ───────────── players' own seasonal plans, in the supplied workbook's structure ─────────────
def _latest_areas(db: Session, squad_id: int, season_id: int) -> dict[int, list[dict]]:
    """{player id: [{area, label, percentile}]} from the latest test window with results this season (empty if untested)."""
    from .testing import _windows_for
    wins = _windows_for(db, squad_id, season_id)
    if not wins:
        return {}
    from ..player_season_plan import flexibility_area
    from ..test_battery import SIT_REACH
    cats = wins[list(wins)[-1]][0]
    out = {pid: [{"area": a["area"], "label": a["label"], "percentile": a["percentile"]} for a in c["areas"]] for pid, c in cats.items()}
    for _w, (_c, sessions) in wins.items():                       # flexibility: the latest sit and reach this season (not ranked)
        for pid, s in sessions.items():
            sr = next((x.final_value for x in s.results if x.test_key == SIT_REACH.key and x.final_value is not None), None)
            fa = flexibility_area(sr)
            if fa:
                out[pid] = [a for a in out.get(pid, []) if a["area"] != "flexibility"] + [fa]
    return out


def _latest_results(db: Session, user: User, squad_id: int, season_id: int) -> dict | None:
    """Every player's results (sit and reach, skinfolds included) for the latest test window with results this season."""
    from .testing import _windows_for, squad_test_results
    wins = _windows_for(db, squad_id, season_id)
    return squad_test_results(squad_id, season_id, list(wins)[-1], db, user) if wins else None


def _with_next_date(rep: dict, pg: dict) -> dict:
    """Adds the date of the plan's next test week (the first test week after the last test and not before today)."""
    nxt = rep.get("next")
    if nxt:
        from ..workload_service import today_lk
        after = max(d for d in (nxt.get("after"), today_lk()) if d)
        week = next((ws for ws, t in zip(pg["week_starts"], pg["test_weeks"]) if t and ws > after), None)
        nxt["date"] = week
    return rep


def _personal(g: dict, p: Player, areas: dict[int, list[dict]]) -> dict:
    from ..player_season_plan import personal_grid
    from ..session_plans import ROLE_LABEL
    return personal_grid(g, name=p.full_name, role=ROLE_LABEL.get(p.role.value, p.role.value), areas=areas.get(p.id, []))


def _xlsx(data: bytes, name: str) -> Response:
    name = re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-") or "seasonal-plan"
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"'})


@router.get("/squads/{squad_id}/seasons/{season_id}/player-plans.xlsx")
def download_player_plans(squad_id: int, season_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Every active player's seasonal plan in ONE Excel: one Annual-plan sheet per player (built from their own test ranks),
    then the squad's Load distribution, Component distribution and Session plan."""
    from ..seasonal_workbook import build_players_workbook, player_sheet_name
    authorize_squad(db, user, squad_id, "testing.read")
    g = _grid(db, user, squad_id, season_id)
    areas = _latest_areas(db, squad_id, season_id)
    players = db.scalars(select(Player).where(Player.squad_id == squad_id, Player.is_active)
                         .order_by(Player.squad_no.is_(None), Player.squad_no, Player.full_name)).all()
    used = {"Load distribution", "Component distribution", "Session plan"}
    sheets = [(player_sheet_name(p.full_name, p.squad_no, used), _personal(g, p, areas)) for p in players]
    audit(db, user, "player_plans.exported", "season", season_id, f"{len(players)} players")
    db.commit()
    return _xlsx(build_players_workbook(g, sheets, _latest_results(db, user, squad_id, season_id)),
                 f"Seasonal-plans-all-players-{g['squad']}-{g['season']}")


@router.get("/squads/{squad_id}/seasons/{season_id}/player-plans/{player_id}.xlsx")
def download_player_plan(squad_id: int, season_id: int, player_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """One player's seasonal plan: Annual plan (their own) | Load distribution | Component distribution | Session plan."""
    authorize_squad(db, user, squad_id, "testing.read")
    p = db.get(Player, player_id)
    if p is None or p.squad_id != squad_id:
        raise HTTPException(404, "Player not found in this squad")
    g = _grid(db, user, squad_id, season_id)
    pg = _personal(g, p, _latest_areas(db, squad_id, season_id))
    from .testing import player_test_report
    tests = player_test_report(db, squad_id, season_id, p)
    audit(db, user, "player_plan.exported", "player", p.id)
    db.commit()
    return _xlsx(build_seasonal_workbook(pg, tests=tests), f"Seasonal-plan-{p.full_name}-{g['season']}")


@router.get("/squads/{squad_id}/seasons/{season_id}/player-plans.pdf")
def download_all_annual_pdf(squad_id: int, season_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Every active player's Annual plan (the Excel sheet, built from their own tests: ranked tests and sit and reach) followed
    by their test results, in one PDF - squad number order."""
    from ..player_plan_pdf import build_players_annual_pdf
    from .testing import player_test_report
    authorize_squad(db, user, squad_id, "testing.read")
    g = _grid(db, user, squad_id, season_id)
    areas = _latest_areas(db, squad_id, season_id)
    players = db.scalars(select(Player).where(Player.squad_id == squad_id, Player.is_active)
                         .order_by(Player.standby, Player.squad_no.is_(None), Player.squad_no, Player.full_name)).all()
    items = []
    for p in players:
        pg = _personal(g, p, areas)
        items.append((pg, _with_next_date(player_test_report(db, squad_id, season_id, p), pg)))
    data = build_players_annual_pdf(items)
    audit(db, user, "player_plans.exported", "season", season_id, f"pdf annual, {len(players)} players")
    db.commit()
    name = re.sub(r"[^A-Za-z0-9]+", "-", f"Annual-plans-all-players-{g['squad']}-{g['season']}").strip("-")
    return Response(data, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}.pdf"'})


@router.get("/squads/{squad_id}/seasons/{season_id}/player-plans/{player_id}.pdf")
def download_player_plan_pdf(squad_id: int, season_id: int, player_id: int, part: str = Query("all", pattern="^(all|annual|weeks)$"),
                             db: Session = Depends(get_db), user: User = Depends(current_user)):
    """One player's seasonal plan as a PDF: part=annual is the Annual plan (the Excel sheet exactly) and the player's test results;
    part=weeks is the Week plans (Monday to Friday sessions of every week); part=all is both. The same plan as the seasonal Excel."""
    from ..player_plan_pdf import build_player_plan_pdf
    from ..seasonal_workbook import _roles_of
    from ..weekly_sessions import build_weeks
    authorize_squad(db, user, squad_id, "testing.read")
    p = db.get(Player, player_id)
    if p is None or p.squad_id != squad_id:
        raise HTTPException(404, "Player not found in this squad")
    g = _grid(db, user, squad_id, season_id)
    pg = _personal(g, p, _latest_areas(db, squad_id, season_id))
    weeks = build_weeks(pg, roles=_roles_of(pg, None), extra_off=pg.get("rest_days")) if part in ("all", "weeks") else None
    from .testing import player_test_report
    tests = _with_next_date(player_test_report(db, squad_id, season_id, p), pg) if part in ("all", "annual") else None
    data = build_player_plan_pdf(pg, weeks, part, tests)
    audit(db, user, "player_plan.exported", "player", p.id, f"pdf {part}")
    db.commit()
    what = {"all": "Seasonal-plan", "annual": "Annual-plan", "weeks": "Week-plans"}[part]
    name = re.sub(r"[^A-Za-z0-9]+", "-", f"{what}-{p.full_name}-{g['season']}").strip("-") or what
    return Response(data, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}.pdf"'})
