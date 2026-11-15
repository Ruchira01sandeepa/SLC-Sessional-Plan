"""Periodized S&C season plan (Zatsiorsky ch. 5 + youth guidelines ch. 10)."""
import io
from datetime import date

import openpyxl

from app import sc_periodization as scp
from app.exercise_kinds import PHASE_KINDS
from app.season_phases import suggest_phases
from .test_testing import add_players, fill, get_template, good_row, make_season, upload

H = lambda w, who: w["h"][who]
SA = [{"area": a, "priority": p, "median": m} for a, p, m in
      [("power", 9, 40), ("speed", 10, 45), ("agility", 9, 47), ("endurance", 9, 44), ("core", 9, 48), ("upper_strength", 7, 52)]]
RG = ["fast", "batting", "fielding"]


def full():
    s, e = date(2027, 1, 4), date(2027, 10, 31)
    return scp.build_macrocycle(season={"name": "Full", "start_date": s, "end_date": e}, phases=suggest_phases(s, e), squad_areas=SA,
                                role_groups=RG, today=date(2026, 12, 1))


def test_mesocycle_sequence_and_lengths():
    p = full()
    types = [m["type"] for m in p["mesocycles"]]
    order = ["accumulation", "transmutation", "realization", "competition", "transition"]
    assert types == sorted(types, key=order.index)                        # the book's order, never back
    assert {"accumulation", "transmutation", "realization", "competition", "transition"} <= set(types)
    assert all(2 <= m["weeks"] <= 6 for m in p["mesocycles"])            # mesocycles of 2-6 weeks
    assert 2 <= next(m for m in p["mesocycles"] if m["type"] == "realization")["weeks"] <= 4
    assert sum(m["weeks"] for m in p["mesocycles"]) == len(p["weeks"])


def test_at_most_two_targets_and_strength_before_endurance():
    p = full()
    dev = [m for m in p["mesocycles"] if m["type"] in ("accumulation", "transmutation")]
    assert all(1 <= len(m["targets"]) <= 2 for m in p["mesocycles"] if m["type"] != "transition")
    seq = [t["label"] for m in dev for t in m["targets"]]
    assert seq.index("Leg power") < seq.index("Endurance")                 # superposition: strength-type first
    assert len({t["label"] for m in dev for t in m["targets"]}) >= 4     # targets change in sequence


def test_rule_of_60_and_load_wave():
    p = full()
    vols = [w["volume"] for w in p["weeks"]]
    assert max(vols) == 100
    for m in p["mesocycles"]:
        if m["type"] in ("accumulation", "transmutation") and m["weeks"] >= 3:
            v = [w["volume"] for w in p["weeks"] if w["mesocycle"] == m["number"]]
            assert v[-1] == round(min(v)) and abs(min(v) / max(v) - 0.6) < 0.01    # unloading week = 60% of the heaviest


def test_sessions_and_complex_follow_the_phase():
    p = full()
    by = {m["type"]: m for m in p["mesocycles"]}
    assert "3 sessions" in by["accumulation"]["frequency"] and by["competition"]["minutes"] == "25-40"
    for m in p["mesocycles"]:
        allowed = set(PHASE_KINDS[scp.EX_PHASE[m["type"]]])
        assert all(e["kind"] in allowed for e in m["complex"]), m["label"]
        assert len(m["complex"]) <= scp.METHOD[m["type"]]["exercises"] + 2
        ranks = [scp.KIND_ORDER.get(e["kind"], 9) for e in m["complex"]]
        assert ranks == sorted(ranks)                                     # power and fast work first in the session
    a1, a2 = [m for m in p["mesocycles"] if m["type"] == "accumulation"][:2]
    assert {e["name"] for e in a1["complex"]} != {e["name"] for e in a2["complex"]}  # a new complex at the next block


def test_short_tournament_with_lead_in():
    p = scp.build_macrocycle(season={"name": "T", "start_date": date(2026, 11, 26), "end_date": date(2026, 12, 5)},
                             phases=[{"phase_type": "in_season", "start_date": date(2026, 11, 26), "end_date": date(2026, 12, 5)}],
                             squad_areas=SA, role_groups=RG, today=date(2026, 11, 15), lead_in_from=date(2026, 11, 15),
                             matches=[date(2026, 11, 27), date(2026, 11, 29)])
    assert [m["type"] for m in p["mesocycles"]] == ["realization", "competition"]
    assert p["weeks"][0]["before_season"] and not p["weeks"][-1]["before_season"]
    assert all((w["end"] - w["start"]).days >= 2 for w in p["weeks"][:-1])        # no 1-day stub week
    assert next(w for w in p["weeks"] if w["matches"] == 2)["sessions"] == 1          # two matches in the week: one short session
    assert any("tournament" in n for n in p["notes"])


def test_endpoint_and_workbook(client, world, db):
    ids = add_players(db, world)
    sid = make_season(client, world)
    upload(client, world, fill(get_template(client, world, sid).content, {pid: good_row(i) for i, pid in enumerate(ids)}), sid, confirm=True)
    r = client.get(f"/squads/{world['squad_a']}/seasons/{sid}/sc-season-plan", headers=H(world, "sc_a"))
    assert r.status_code == 200, r.text
    assert r.json()["mesocycles"] and "tested players" in r.json()["based_on"]
    x = client.get(f"/squads/{world['squad_a']}/seasons/{sid}/sc-season-plan.xlsx", headers=H(world, "admin"))
    assert openpyxl.load_workbook(io.BytesIO(x.content)).sheetnames == ["Macrocycle", "Mesocycles", "Rules"]
    assert client.get(f"/squads/{world['squad_a']}/seasons/{sid}/sc-season-plan", headers=H(world, "coach_b")).status_code in (403, 404)
