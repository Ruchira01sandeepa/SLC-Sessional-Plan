"""Reference data seeded from the workbooks. Read-only, any authenticated user."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.reference.age_groups import PROFILES as AGE_PROFILES
from app.assessment.age_norms import AGE_GROUPS as AGE_NORM_GROUPS, ref_label, table as norms_table
from app.core.db import get_db
from app.core.deps import current_user
from app.core.models import PdpRubricItem, PlayerRole, Scenario, SkillTemplate, TemplateKind
from app.reference.role_kpis import kpis_for
from app.core.schemas import RubricOut, ScenarioOut, SkillTemplateOut

router = APIRouter(prefix="/meta", tags=["reference data"], dependencies=[Depends(current_user)])


@router.get("/age-norms")
def age_norms(gender: str = Query("male", pattern="^(male|female)$")):
    """Age-group reference values for the physical tests (developing / expected / strong, plus the typo-check ranges).
    gender=female: the provisional girls' / women's values."""
    who = "girls and women" if gender == "female" else "boys"
    return {"groups": list(AGE_NORM_GROUPS), "tests": norms_table(gender), "gender": gender,
            "labels": {ag: ref_label(ag, gender) for ag in AGE_NORM_GROUPS},
            "note": f"Provisional references for {who}, from published youth data where it exists and estimates where it does not. "
                    "Replace with SLC's own percentiles as data builds up."}


@router.get("/benchmark")
def benchmark_table(age_group: str = "U15", gender: str = Query("male", pattern="^(male|female)$")):
    """The SLC points benchmark (app/assessment/benchmark.py): cut-offs per test, maximum points and colour bands. The U15 boys' one, or with
    gender=female the women's one for the age group (U15 girls, U17 girls, U19 women)."""
    from app.assessment.benchmark import table
    return {**table(age_group, gender), "gender": gender, "label": ref_label(age_group, gender) if gender == "female" else "U15"}


@router.get("/age-groups")
def age_groups():
    """The supported age groups and the rules each one applies (app/reference/age_groups.py)."""
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
