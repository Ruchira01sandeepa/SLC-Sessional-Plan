"""Reference data seeded from the workbooks. Read-only, any authenticated user."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..age_groups import PROFILES as AGE_PROFILES
from ..age_norms import AGE_GROUPS as AGE_NORM_GROUPS, table as norms_table
from ..db import get_db
from ..deps import current_user
from ..models import PdpRubricItem, PlayerRole, Scenario, SkillTemplate, TemplateKind
from ..role_kpis import kpis_for
from ..schemas import RubricOut, ScenarioOut, SkillTemplateOut

router = APIRouter(prefix="/meta", tags=["reference data"], dependencies=[Depends(current_user)])


@router.get("/age-norms")
def age_norms():
    """Age-group reference values for the physical tests (developing / expected / strong, plus the typo-check ranges)."""
    return {"groups": list(AGE_NORM_GROUPS), "tests": norms_table(),
            "note": "Provisional references for boys, from published youth data where it exists and estimates where it does not. "
                    "Replace with SLC's own percentiles as data builds up."}


@router.get("/age-groups")
def age_groups():
    """The supported age groups and the rules each one applies (app/age_groups.py)."""
    return [p.summary() for p in AGE_PROFILES.values()]


@router.get("/skill-templates/{role}", response_model=list[SkillTemplateOut])
def skill_templates(role: PlayerRole, kind: TemplateKind | None = None, db: Session = Depends(get_db)):
    q = select(SkillTemplate).where(SkillTemplate.player_role == role).order_by(SkillTemplate.kind, SkillTemplate.sort_order)
    if kind:
        q = q.where(SkillTemplate.kind == kind)
    return db.scalars(q).all()


@router.get("/pdp-rubric", response_model=list[RubricOut])
def pdp_rubric(db: Session = Depends(get_db)):
    return db.scalars(select(PdpRubricItem).order_by(PdpRubricItem.sort_order)).all()


@router.get("/scenarios/{role}", response_model=list[ScenarioOut])
def scenarios(role: PlayerRole, db: Session = Depends(get_db)):
    return db.scalars(select(Scenario).where(Scenario.player_role == role)).all()


@router.get("/role-kpis/{role}")
def role_kpis(role: PlayerRole):
    """The measurable role-specific fields (Development sheet: Role-Specific Skill Execution)."""
    return [{"field": m.field, "label": m.label, "unit": m.unit, "higher_is_better": m.higher_is_better, "lo": m.lo, "hi": m.hi}
            for m in kpis_for(role)]
