"""Periodized S&C season plan (Zatsiorsky ch. 5 + youth guidelines ch. 10)."""
import io
from datetime import date

import openpyxl

from app.planning import sc_periodization as scp
from app.reference.exercise_kinds import PHASE_KINDS
from app.planning.season_phases import suggest_phases
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


# ───────────── second reading: ch. 4 methods, ch. 8 power / endurance / injury prevention, ch. 5 details ─────────────
def test_endurance_is_targeted_last():
    assert scp.order_targets(SA)[-1] == "endurance"                        # strength first, endurance afterward (ch. 8)


def test_complex_kept_for_two_mesocycles_and_methods_named():
    p = full()
    acc = [m for m in p["mesocycles"] if m["type"] == "accumulation"]
    assert acc[0]["new_complex"] and not acc[1]["new_complex"]             # changed every 2 mesocycles (ch. 8)
    shared = {e["name"] for e in acc[0]["complex"]} & {e["name"] for e in acc[1]["complex"]}
    assert len(shared) >= 5
    by = {m["type"]: m for m in p["mesocycles"]}
    assert "Dynamic effort" in by["transmutation"]["methods"] and "Repeated effort" in by["accumulation"]["methods"]
    assert any("Maximal-effort method" in r and "not used" in r for r in p["rules"])


def test_every_exercise_twice_a_week_and_injury_groups_present():
    p = full()
    for m in p["mesocycles"]:
        if m["type"] in ("accumulation", "transmutation"):
            week = " | ".join(d["session"] for d in m["microcycle"])
            for e in m["complex"]:
                assert week.count(e["name"]) >= 2, (m["label"], e["name"])
        if m["type"] != "transition":
            kinds = {e["kind"] for e in m["complex"]}
            assert "trunk_stability" in kinds or "rotation_power" in kinds, m["label"]


def test_tournament_is_one_microcycle():
    p = scp.build_macrocycle(season={"name": "T", "start_date": date(2026, 11, 26), "end_date": date(2026, 12, 5)},
                             phases=[{"phase_type": "in_season", "start_date": date(2026, 11, 26), "end_date": date(2026, 12, 5)}],
                             squad_areas=SA, role_groups=RG, today=date(2026, 11, 15))
    assert {w["microcycle"] for w in p["weeks"]} == {"Tournament microcycle (10 days)"}


def test_player_plans_and_download_all(client, world, db):
    import zipfile
    ids = add_players(db, world)
    sid = make_season(client, world)
    upload(client, world, fill(get_template(client, world, sid).content, {pid: good_row(i) for i, pid in enumerate(ids)}), sid, confirm=True)
    base = f"/squads/{world['squad_a']}/seasons/{sid}"
    r = client.get(f"{base}/sc-season-plan/players/{ids[0]}.xlsx", headers=H(world, "sc_a"))
    assert r.status_code == 200 and "Test-Player-0" in r.headers["content-disposition"]
    ws = openpyxl.load_workbook(io.BytesIO(r.content))["Macrocycle"]
    assert "Test Player 0" in ws["A1"].value and "own" in ws["A2"].value
    assert client.get(f"{base}/sc-season-plan/players/{world['cara']}.xlsx", headers=H(world, "admin")).status_code == 404   # other squad
    z = client.get(f"{base}/sc-season-plans.zip", headers=H(world, "coach_a"))
    assert z.status_code == 200 and z.headers["content-type"] == "application/zip"
    names = zipfile.ZipFile(io.BytesIO(z.content)).namelist()
    active = client.get(f"/players?squad_id={world['squad_a']}", headers=H(world, "admin")).json()
    assert names[0].startswith("00-Squad") and len(names) == 1 + len(active)
    assert client.get(f"{base}/sc-season-plans.zip", headers=H(world, "coach_b")).status_code in (403, 404)
