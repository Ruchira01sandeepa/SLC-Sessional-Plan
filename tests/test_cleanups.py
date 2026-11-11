"""Review fixes: shared bowling parsing, upload header check, annual-sheet layout, batched workload evaluation."""
import copy
from datetime import date, timedelta

import openpyxl
from openpyxl import Workbook

from app.annual_grid import build_grid
from app.annual_grid_excel import R_LOADING_HEAD, R_SECTION, layout, write_annual_sheet
from app.exercises import bowling_types
from app.models import EventType, WellnessLog, WorkloadLog
from app.season_phases import suggest_phases
from app.workload_service import evaluate_player, evaluate_players, today_lk


def test_bowling_types_parsing_is_shared():
    assert bowling_types("all_rounder", "Right-arm leg SPIN") == {"spin"}
    assert bowling_types("all_rounder", "left-arm medium pace") == {"fast"}
    assert bowling_types("all_rounder", None) is None
    assert bowling_types("fast_bowler", "spin") is None                       # the role decides for everyone else


def test_malformed_content_length_is_a_clear_400(client, world):
    sid = client.post(f"/squads/{world['squad_a']}/seasons", json={"name": "2027", "start_date": "2027-01-01", "end_date": "2027-09-30", "phases": []},
                      headers=world["h"]["admin"]).json()["id"]
    r = client.post(f"/squads/{world['squad_a']}/test-import?season_id={sid}&window=baseline", content=b"x",
                    headers={**world["h"]["admin"], "Content-Type": "application/octet-stream", "Content-Length": "abc"})
    assert r.status_code == 400 and "Content-Length" in r.json()["detail"]


def _grid():
    s, e = date(2027, 1, 1), date(2027, 9, 30)
    return build_grid(squad_name="W", season={"name": "2027", "start_date": s, "end_date": e}, phases=suggest_phases(s, e), events=[], generated_on=s)


def test_annual_sheet_layout_matches_the_supplied_rows_and_never_overlaps():
    g = _grid()
    heads, loading, perf, notes = layout(g)
    assert heads == R_SECTION and loading == R_LOADING_HEAD                 # standard content: the supplied sheet's rows exactly
    big = copy.deepcopy(g)
    big["sections"][0]["rows"] += [{"label": f"Extra {i}", "marks": [False] * g["weeks"]} for i in range(3)]
    heads2, loading2, _, _ = layout(big)
    order = [s["name"] for s in big["sections"]]
    for a, b in zip(order, order[1:]):
        rows_a = next(len(s["rows"]) for s in big["sections"] if s["name"] == a)
        assert heads2[b] > heads2[a] + rows_a                                 # next header below the last row of this section
    assert loading2 > heads2["Nutrition"] + 6
    ws = Workbook().active
    write_annual_sheet(ws, big)
    assert ws.cell(row=heads2["Mental"], column=1).value == "Mental"
    assert ws.cell(row=heads2["Physical"] + 8, column=1).value == "Extra 2"


def test_batched_evaluation_matches_one_by_one(client, world, db):
    today = today_lk()
    bob = db.get(__import__("app.models", fromlist=["Player"]).Player, world["bob"])
    ann = db.get(__import__("app.models", fromlist=["Player"]).Player, world["ann"])
    for d in range(1, 30):
        db.add(WorkloadLog(player_id=bob.id, log_date=today - timedelta(days=d), session_type=EventType.training, attended=True,
                           duration_min=60 + d, rpe=5 + d % 3, overs_bowled=6.0 if d % 4 == 0 else None))
    db.add(WorkloadLog(player_id=ann.id, log_date=today - timedelta(days=2), session_type=EventType.training, attended=True, duration_min=90, rpe=8))
    db.add(WellnessLog(player_id=ann.id, log_date=today - timedelta(days=1), soreness=9, fatigue=3, sleep_hours=8, pain_flag=False))
    db.commit()
    batch = evaluate_players(db, [bob, ann], today)
    for p in (bob, ann):
        alerts, summ = evaluate_player(db, p, today)
        b_alerts, b_summ = batch[p.id]
        assert summ == b_summ
        assert sorted((a.rule_code, a.severity) for a in alerts) == sorted((a.rule_code, a.severity) for a in b_alerts)
