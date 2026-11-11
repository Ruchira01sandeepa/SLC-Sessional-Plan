"""Load role skill lists, the PDP rubric and scenarios from the workbooks in /templates.

Run: python -m scripts.seed_templates     (safe to re-run; existing rows are kept)
"""
from pathlib import Path

import openpyxl
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (PdpRubricItem, PlayerRole, Scenario, SkillTemplate, TemplateKind)

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"

UNGROUPED = "Ungrouped"   # skill block whose group label is blank in the template

WORKBOOKS = {
    PlayerRole.spin_bowler: "Spin_Bowler_PDP.xlsx",
    PlayerRole.fast_bowler: "Fast_Bowler_PDP.xlsx",
    PlayerRole.batter: "Batter_PDP.xlsx",
    PlayerRole.bat_wicketkeeper: "Batting_Wicket_Keeper_PDP.xlsx",
    PlayerRole.all_rounder: "All_Rounder_PDP.xlsx",
}


def _s(v) -> str | None:
    if v is None:
        return None
    t = " ".join(str(v).split())
    return t or None


def _find_sheet(wb, *keywords):
    for ws in wb.worksheets:
        if all(k.lower() in ws.title.lower() for k in keywords):
            return ws
    raise KeyError(f"No sheet with {keywords} in {wb.sheetnames}")


def _legend_row(ws, col="A", start=1) -> int:
    """Row where the 'Symbols of sign-' legend starts; skills end above it."""
    for r in range(start, ws.max_row + 1):
        v = _s(ws[f"{col}{r}"].value)
        if v and v.lower().startswith("symbols"):
            return r
    return ws.max_row + 1


def parse_pdp_rubric(ws):
    """PDP rows 14-24: group in B, five sub-skills in D,F,H,J,L."""
    out, order = [], 0
    for r in range(14, 25):
        group = _s(ws[f"B{r}"].value)
        if not group:
            continue
        for col in "DFHJL":
            skill = _s(ws[f"{col}{r}"].value)
            if skill:
                order += 1
                out.append((group, skill, order))
    return out


def _merged_group_labels(ws, col: str) -> dict[int, str | None]:
    """row -> label of the merged block it belongs to in `col` (None if the block has no label).

    Reading merges (not 'carry the last label down') matters: a merged block with an empty
    label must NOT inherit the previous block's name."""
    labels = {}
    for m in ws.merged_cells.ranges:
        if m.min_col == m.max_col == openpyxl.utils.column_index_from_string(col):
            label = _s(ws.cell(m.min_row, m.min_col).value)
            for r in range(m.min_row, m.max_row + 1):
                labels[r] = label
    return labels


def parse_development(ws):
    """Group in col A (merged blocks), skill in col B. Plus 'Role-Specific Skill Execution' skills in col J."""
    end = _legend_row(ws)
    merged = _merged_group_labels(ws, "A")
    items, order = [], 0
    for r in range(5, end):
        b = _s(ws[f"B{r}"].value)
        if b:
            group = merged[r] if r in merged else _s(ws[f"A{r}"].value)
            order += 1
            items.append((group or UNGROUPED, b, order, f"B{r}"))
    j_group = "Role-Specific Skill Execution"
    for r in range(5, end):
        j = _s(ws[f"J{r}"].value)
        if j and j.lower() != j_group.lower():
            order += 1
            items.append((j_group, j, order, f"J{r}"))
    return items


def parse_adaptability(ws):
    """Two blocks: primary (rows 6-17) and secondary (rows 24-35). Challenge names in col A."""
    def block(first, last):
        names = []
        for r in range(first, last + 1):
            a = _s(ws[f"A{r}"].value)
            if a and not a.lower().startswith(("mood", "symbols", "no clue", "naturally", "have to", "improving", "good", "complete")):
                names.append((a, f"A{r}"))
        return names
    return block(8, 17), block(26, 35)


def parse_progress(ws):
    """Progress Status. Two layouts exist:
      * bowlers / keepers / all-rounders: skills in col L, tasks in col Z
      * batter: skill groups in col L (merged), skills in col M
    Both may have batting-task blocks in col AA."""
    rows = range(6, 45)
    m_vals = [_s(ws[f"M{r}"].value) for r in rows]
    skills, tasks = [], []
    if any(m_vals):                                   # batter layout
        merged = _merged_group_labels(ws, "L")
        for r in rows:
            n = _s(ws[f"M{r}"].value)
            if n:
                g = merged.get(r) or _s(ws[f"L{r}"].value) or UNGROUPED
                skills.append((g, n, f"M{r}"))
    else:
        skills = [("Core Skills", _s(ws[f"L{r}"].value), f"L{r}") for r in rows if _s(ws[f"L{r}"].value)]
        tasks = [("Core Tasks", _s(ws[f"Z{r}"].value), f"Z{r}") for r in rows if _s(ws[f"Z{r}"].value)]
    bat = [("Core Batting Task", _s(ws[f"AA{r}"].value), f"AA{r}") for r in rows
           if _s(ws[f"AA{r}"].value) and not _s(ws[f"AA{r}"].value).lower().startswith("core")]
    return skills, tasks + bat


def parse_scenarios(ws):
    out = []
    for r in range(8, ws.max_row + 1):
        title = _s(ws[f"A{r}"].value)
        if not title:
            continue
        flag = lambda c: (_s(ws[f"{c}{r}"].value) or "").upper() == "YES"
        out.append(dict(title=title, skill=_s(ws[f"B{r}"].value), practice_activity=_s(ws[f"C{r}"].value),
                        technical=flag("D"), tactical=flag("E"), mental=flag("F"), physical=flag("G")))
    return out


def seed(db: Session, template_dir: Path = TEMPLATE_DIR) -> dict:
    counts = {"rubric": 0, "skills": 0, "scenarios": 0}

    # ---- PDP rubric: identical in all workbooks, read from the first ----
    first = next(iter(WORKBOOKS.values()))
    wb = openpyxl.load_workbook(template_dir / first, data_only=True)
    existing = {(r.group_name, r.skill_name) for r in db.scalars(select(PdpRubricItem))}
    for g, s, o in parse_pdp_rubric(wb["PDP"]):
        if (g, s) not in existing:
            db.add(PdpRubricItem(group_name=g, skill_name=s, sort_order=o))
            counts["rubric"] += 1

    # ---- per-role skills & scenarios ----
    for role, fname in WORKBOOKS.items():
        wb = openpyxl.load_workbook(template_dir / fname, data_only=True)
        have = {(t.kind, t.sort_order) for t in
                db.scalars(select(SkillTemplate).where(SkillTemplate.player_role == role))}

        def add(kind, group, skill, order, cell):
            # keyed by position, not name: templates repeat names (e.g. two "Range Hitting" blocks)
            if (kind, order) not in have:
                db.add(SkillTemplate(player_role=role, kind=kind, group_name=group, skill_name=skill,
                                     sort_order=order, source_cell=cell))
                have.add((kind, order))
                counts["skills"] += 1

        dev = _find_sheet(wb, "development")
        for g, s, o, cell in parse_development(dev):
            add(TemplateKind.development, g, s, o, cell)

        ad = _find_sheet(wb, "adaptability")
        prim, sec = parse_adaptability(ad)
        for i, (n, cell) in enumerate(prim, 1):
            add(TemplateKind.adaptability_primary, "Primary skill challenge", n, i, cell)
        for i, (n, cell) in enumerate(sec, 1):
            add(TemplateKind.adaptability_secondary, "Secondary skill challenge", n, i, cell)

        sk, tk = parse_progress(wb["Progress Status"])
        for i, (g, n, cell) in enumerate(sk, 1):
            add(TemplateKind.progress_skill, g, n, i, cell)
        for i, (g, n, cell) in enumerate(tk, 1):
            add(TemplateKind.progress_task, g, n, i, cell)

        have_sc = {s.title for s in db.scalars(select(Scenario).where(Scenario.player_role == role))}
        for sc in parse_scenarios(wb["Scenario"]):
            if sc["title"] not in have_sc:
                db.add(Scenario(player_role=role, **sc))
                counts["scenarios"] += 1

    db.commit()
    return counts
