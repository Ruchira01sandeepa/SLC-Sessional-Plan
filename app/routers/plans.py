"""Seasonal plan: generate, save progress, edit status / review, download as Excel."""
import re
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import audit, current_user
from ..models import (CalendarEvent, DevArea, GoalStatus, PlanItem, PlanLevel, Player, PlayerRole, Scenario, Season,
                      SkillTemplate, SquadStaff, TemplateKind, User, UserRole)
from ..permissions import authorize_squad
from ..annual_grid import build_grid
from ..annual_grid_excel import build_grid_workbook
from ..seasonal_workbook import build_seasonal_workbook
from ..plan_excel import build_workbook
from ..season_phases import suggest_phases
from ..seasonal_plan import PHASE_ORDER, ROLE_ORDER, build_plan
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


@router.get("/squads/{squad_id}/seasons/{season_id}/seasonal-plan")
def get_plan(squad_id: int, season_id: int, roles: str | None = Query(None), db: Session = Depends(get_db), user: User = Depends(current_user)):
    return _generate(db, user, squad_id, season_id, roles, "plan.squad.read")[0]


@router.post("/squads/{squad_id}/seasons/{season_id}/seasonal-plan/save")
def save_plan(squad_id: int, season_id: int, roles: str | None = Query(None), db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Store the plan as plan items so status and coach review can be tracked. Re-saving refreshes the text but keeps
    status and review; rows that are no longer generated are removed only if nobody has touched them."""
    plan, _ = _generate(db, user, squad_id, season_id, roles, "plan.squad.write")
    existing = {_key(i.phase_type, i.development_area.value, i.applies_to): i for i in db.scalars(select(PlanItem).where(
        PlanItem.level == PlanLevel.seasonal, PlanItem.squad_id == squad_id, PlanItem.season_id == season_id))}
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
def download_plan(squad_id: int, season_id: int, roles: str | None = Query(None), db: Session = Depends(get_db), user: User = Depends(current_user)):
    plan, season = _generate(db, user, squad_id, season_id, roles, "plan.squad.read")
    name = re.sub(r"[^A-Za-z0-9]+", "-", f"seasonal-plan-{plan['squad']}-{season.name}").strip("-") or "seasonal-plan"
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
    for e in db.scalars(select(CalendarEvent).where(
            CalendarEvent.squad_id == squad_id, CalendarEvent.start_at >= _utc_naive(season.start_date, False),
            CalendarEvent.start_at < _utc_naive(season.end_date, True)).order_by(CalendarEvent.start_at)):
        hours = None
        if e.end_at and e.end_at > e.start_at:
            hours = min((e.end_at - e.start_at).total_seconds() / 3600, 12)       # a stray end date cannot add days of hours
        events.append({"event_type": e.event_type.value, "date": _local_date(e.start_at), "hours": hours})
    try:
        g = build_grid(squad_name=squad.name, season={"name": season.name, "start_date": season.start_date, "end_date": season.end_date},
                       phases=phases, events=events, generated_on=datetime.now(LK).date(), age_group=squad.age_group)
    except ValueError as e:
        raise HTTPException(422, str(e))
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
def download_seasonal_workbook(squad_id: int, season_id: int, roles: str | None = Query(None), db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Annual plan, load distribution, component distribution and one session plan per role and phase, in one workbook."""
    g = _grid(db, user, squad_id, season_id)
    player_roles, bowling = _roles_and_bowling(db, squad_id, roles)
    name = re.sub(r"[^A-Za-z0-9]+", "-", f"seasonal-plan-workbook-{g['squad']}-{g['season']}").strip("-") or "seasonal-plan-workbook"
    audit(db, user, "seasonal_workbook.exported", "season", season_id)
    db.commit()
    return Response(build_seasonal_workbook(g, player_roles, bowling or None), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"'})
