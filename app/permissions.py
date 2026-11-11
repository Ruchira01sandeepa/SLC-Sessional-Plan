"""The single place that says who may do what. Read this file to audit access.

Rules (from the project spec):
  player    - sees only their own plan / workload / progress. No medical detail.
  coach     - views & edits players in the squads they are assigned to.
  sc_coach  - manages fitness & physical-development data for assigned squads.
  physio    - the ONLY role that reads/writes medical & injury detail (assigned squads).
  admin     - manages users, squads, calendars, reports. Deliberately has NO access to medical
              detail (privacy by default). To change that, add UserRole.admin to the two
              'medical.*' entries below.
Coaches and S&C see only a coarse `availability` (fit / modified / unavailable).
"""
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Player, SquadStaff, User, UserRole as R

# action -> roles allowed to perform it AT ALL. Squad/ownership scope is checked separately.
ACTIONS: dict[str, set[R]] = {
    "users.manage":        {R.admin},
    "squads.manage":       {R.admin},
    "player.read":         {R.player, R.coach, R.sc_coach, R.physio, R.admin},
    "player.create":       {R.coach, R.admin},
    "player.update":       {R.coach, R.admin},
    "player.link_user":    {R.admin},
    "medical.read":        {R.physio},
    "medical.write":       {R.physio},
    "availability.write":  {R.physio},
    "fitness.read":        {R.player, R.coach, R.sc_coach, R.physio, R.admin},
    "fitness.write":       {R.sc_coach, R.coach, R.admin},
    "plan.read":           {R.player, R.coach, R.sc_coach, R.physio, R.admin},
    "plan.write":          {R.coach, R.sc_coach, R.admin},
    "calendar.read":       {R.player, R.coach, R.sc_coach, R.physio, R.admin},
    "calendar.write":      {R.coach, R.sc_coach, R.admin},
    "plan.squad.read":     {R.coach, R.sc_coach, R.physio, R.admin},     # seasonal plan: not shared with players
    "plan.squad.write":    {R.coach, R.admin},
    "workload.read":       {R.player, R.coach, R.sc_coach, R.physio, R.admin},
    "workload.write":      {R.player, R.coach, R.sc_coach, R.admin},
    "workload.limits":     {R.coach, R.sc_coach, R.admin},               # set bowling limits for one player
    "wellness.write":      {R.player, R.coach, R.sc_coach, R.physio, R.admin},
    "alerts.read":         {R.coach, R.sc_coach, R.physio, R.admin},     # players do not see alerts or guidance
    "alerts.ack":          {R.coach, R.sc_coach, R.physio, R.admin},
    # SLC U15 SOP physical tests: results are confidential and are NOT shared with players
    "testing.read":        {R.coach, R.sc_coach, R.admin},
    "testing.write":       {R.sc_coach, R.admin},                         # download the template, import results
}


def role_allows(user: User, action: str) -> bool:
    return user.role in ACTIONS[action]


def squad_ids(db: Session, user: User) -> set[int]:
    return set(db.scalars(select(SquadStaff.squad_id).where(SquadStaff.user_id == user.id)))


def in_scope(db: Session, user: User, player: Player) -> bool:
    """Is this player within the user's reach?  (admin: all; player: self; staff: assigned squads)"""
    if user.role == R.admin:
        return True
    if user.role == R.player:
        return player.user_id == user.id
    return player.squad_id in squad_ids(db, user)


def authorize_player(db: Session, user: User, player: Player | None, action: str) -> Player:
    """Raise unless `user` may perform `action` on `player`.

    Out-of-scope players return 404 (not 403) so that a user cannot probe which players exist."""
    if player is None or not in_scope(db, user, player):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Player not found")
    if not role_allows(user, action):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Your role may not perform this action")
    return player


def authorize_squad(db: Session, user: User, squad_id: int, action: str):
    """Same idea as authorize_player, for squad-level resources (calendar, seasons, benchmarks).
    Players reach only the squad they belong to. Out-of-scope squads are 404."""
    from .models import Squad
    squad = db.get(Squad, squad_id)
    ok = squad is not None and (
        user.role == R.admin
        or (user.role == R.player and db.scalar(select(Player.id).where(Player.user_id == user.id, Player.squad_id == squad_id)) is not None)
        or (user.role != R.player and squad_id in squad_ids(db, user)))
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Squad not found")
    if not role_allows(user, action):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Your role may not perform this action")
    return squad
