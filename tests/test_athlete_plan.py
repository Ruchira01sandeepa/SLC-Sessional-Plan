"""Athlete seasonal plan in 16 steps (Zatsiorsky & Kraemer ch. 1 and 5, youth ch. 10)."""
import io
from datetime import date, timedelta

import openpyxl

from app import athlete_season_plan as asp
from .test_testing import add_players, fill, get_template, good_row, make_season, upload

H = lambda w, who: w["h"][who]
TODAY = date(2026, 11, 16)


def plan(answers=None, prefill=None, role="fast_bowler", matches=None):
    pre = {"position": "Fast bowler", "age": 14, "sex": "male", "body_weight_kg": 52, **(prefill or {})}
    ans = {"competitions": [{"name": "Prov T20", "start": "2027-03-01", "days": 6, "importance": "secondary"},
                            {"name": "National U15", "start": "2027-04-12", "days": 10, "importance": "main"}],
           "training_days": 3, "sessions_per_day": 1, "limiting": ["power", "aerobic", "speed"], "load_increase": "normal", **(answers or {})}
    return asp.build_athlete_plan(answers=ans, prefill=pre, role=role, role_groups=["fast", "fielding"], today=TODAY, matches=matches)


def test_step0_missing_answers_become_assumptions():
    a, assume = asp.resolve_inputs({}, {"age": 14}, TODAY)
    assert a["level"] == "beginner" and a["training_days"] == 3 and a["youth"]
    assert any("Training days not given" in x for x in assume) and any("No competitions listed" in x for x in assume)
    assert len(asp.QUESTIONS) == 9


def test_backward_from_the_main_competition():
    p = plan()
    types = [m["type"] for m in p["mesocycles"]]
    assert types == sorted(types, key=["accumulation", "transmutation", "realization", "competition", "transition"].index)
    comp = next(m for m in p["mesocycles"] if m["type"] == "competition")
    real = next(m for m in p["mesocycles"] if m["type"] == "realization")
    assert comp["start"] == date(2027, 4, 12) and real["end"] == date(2027, 4, 11)          # realization sits right before the peak
    assert real["weeks"] == 4                                                                # normal load increase -> ~4 weeks
    assert all(2 <= m["weeks"] <= 6 for m in p["mesocycles"] if m["type"] in ("accumulation", "transmutation"))
    mild = plan({"load_increase": "mild"})
    assert next(m for m in mild["mesocycles"] if m["type"] == "realization")["weeks"] == 2
    tr = next(m for m in p["mesocycles"] if m["type"] == "transition")
    assert tr["start"] == date(2027, 4, 22)                                                  # transition straight after the competition


def test_targets_superposition_and_share():
    p = plan()
    dev = [m for m in p["mesocycles"] if m["type"] in ("accumulation", "transmutation")]
    assert all(len(m["targets"]) <= 2 for m in p["mesocycles"])
    seq = [t for m in dev for t in m["targets"]]
    assert seq.index("Aerobic endurance") > seq.index("Explosive strength / power")      # strength-type before aerobic
    assert all(0.68 <= m["target_share"] <= 0.82 for m in dev)                           # 70-80% of the work on the targets
    trans = next(m for m in dev if m["type"] == "transmutation")
    assert "Aerobic endurance" not in trans["targets"]                                     # transmutation = specific abilities


def test_youth_methods_and_complex_rules():
    p = plan()
    assert all("Maximal effort" not in x for m in p["mesocycles"] for x in m["methods"])   # ch. 10: no near-max lifts for U15
    acc = [m for m in p["mesocycles"] if m["type"] == "accumulation"]
    assert not acc[1]["new_complex"] and {e["name"] for e in acc[0]["complex"]} & {e["name"] for e in acc[1]["complex"]}
    for m in p["mesocycles"]:
        ranks = [asp.KIND_ORDER.get(e["kind"], 9) for e in m["complex"]]
        assert ranks == sorted(ranks)                                                       # power first, slow strength later
    adult = plan(prefill={"age": 22}, answers={"level": "qualified", "training_age_years": 4})
    assert any("Maximal effort" in x for m in adult["mesocycles"] for x in m["methods"])


def test_microcycle_each_exercise_twice_and_legs_apart():
    p = plan()
    for m in p["mesocycles"]:
        if m["type"] not in ("accumulation", "transmutation"):
            continue
        rows = [r for r in m["microcycle"] if r["items"]]
        assert sum(1 for r in rows if r["resistance"]) >= 3
        assert not any(r["heavy_legs"] and r["endurance"] for r in rows)                   # no heavy strength + endurance in one workout
        names = [i["name"] for r in rows for i in r["items"]]
        for e in m["complex"]:
            if e["kind"] not in asp.ENDURANCE:
                assert names.count(e["name"]) >= 2, (m["label"], e["name"])
        loads = [r["load"] for r in rows]
        assert min(loads) / max(loads) == 0.6                                              # rule of 60% at day level


def test_taper_and_competition_microcycle():
    p = plan(matches=[date(2027, 4, 13), date(2027, 4, 17), date(2027, 4, 20)])
    t = p["tapers"][0]["rows"]
    assert len(t) == 14 and t[-1]["days_out"] == 1
    assert not any(e["kind"] == "leg_strength" for r in t if r["days_out"] < 10 for e in r["exercises"])   # heavy legs out 10-12 days before
    comp = next(m for m in p["mesocycles"] if m["type"] == "competition")
    cm = comp["competition_microcycle"]
    assert len(cm) == 10 and sum(1 for r in cm if r["match"]) == 3
    for i, r in enumerate(cm[:-1]):
        if cm[i + 1]["match"]:
            assert not r.get("heavy")                                                         # nothing heavy the day before a match
    assert sum(1 for r in cm[:7] if r.get("heavy")) >= 2


def test_short_tournament_and_self_check():
    p = asp.build_athlete_plan(answers={}, prefill={"position": "Batter", "age": 14, "sex": "male",
                                                    "competitions": [{"name": "Galle U15", "start": "2026-11-26", "days": 10, "importance": "main"}]},
                               role="batter", role_groups=["batting", "fielding"], today=TODAY,
                               matches=[date(2026, 11, 27), date(2026, 11, 29), date(2026, 12, 2)])
    assert [m["type"] for m in p["mesocycles"]] == ["realization", "competition", "transition"]
    assert p["model"]["model"] == "nonlinear"
    assert any(r["past"] for r in p["tapers"][0]["rows"]) and not p["tapers"][0]["rows"][-1]["past"]
    assert len(p["self_check"]) == 14
    assert all(c["ok"] is not False for c in p["self_check"]), [c for c in p["self_check"] if c["ok"] is False]
    assert [s["n"] for s in p["steps"]] == list(range(1, 15))


def test_two_peaks_two_macrocycles():
    p = plan({"competitions": [{"name": "A", "start": "2027-03-01", "days": 5, "importance": "main"},
                               {"name": "B", "start": "2027-07-05", "days": 5, "importance": "main"}]})
    assert len(p["macrocycles"]) == 2
    for mc in (1, 2):
        mm = [m for m in p["mesocycles"] if m["macro"] == mc]
        i = next(i for i, m in enumerate(mm) if m["type"] == "competition")
        assert mm[i - 1]["type"] == "realization"


def test_endpoints(client, world, db):
    ids = add_players(db, world)
    sid = make_season(client, world)
    upload(client, world, fill(get_template(client, world, sid).content, {pid: good_row(i) for i, pid in enumerate(ids)}), sid, confirm=True)
    base = f"/squads/{world['squad_a']}/seasons/{sid}/athlete-plans/{ids[0]}"
    s0 = client.get(f"{base}/step0", headers=H(world, "sc_a"))
    assert s0.status_code == 200, s0.text
    assert len(s0.json()["questions"]) == 9 and s0.json()["prefill"]["position"].startswith("Batter") and s0.json()["tests"]
    assert client.get(base, headers=H(world, "sc_a")).status_code == 409                    # STEP 0 first
    body = {"training_days": 3, "sessions_per_day": 1, "level": "beginner", "load_increase": "mild", "limiting": ["power", "speed"],
            "competitions": [{"name": "Final", "start": "2027-06-01", "days": 3, "importance": "main"}]}
    assert client.put(f"{base}/step0", json={**body, "limiting": ["flying"]}, headers=H(world, "sc_a")).status_code == 422
    r = client.put(f"{base}/step0", json=body, headers=H(world, "sc_a"))
    assert r.status_code == 200, r.text
    p = client.get(base, headers=H(world, "sc_a"))
    assert p.status_code == 200, p.text
    j = p.json()
    assert j["player"]["id"] == ids[0] and len(j["self_check"]) == 14 and j["steps"][0]["n"] == 1
    x = client.get(f"{base}.xlsx", headers=H(world, "admin"))
    assert x.status_code == 200
    assert openpyxl.load_workbook(io.BytesIO(x.content)).sheetnames == ["1 Inputs", "Steps 1-14", "2 Overview", "4-5 Complexes & weeks",
                                                                        "6-7 Taper & transition", "8 Monitoring & check"]
    assert client.get(f"{base}/step0", headers=H(world, "coach_b")).status_code in (403, 404)
    other = f"/squads/{world['squad_a']}/seasons/{sid}/athlete-plans/{world['cara']}/step0"
    assert client.get(other, headers=H(world, "admin")).status_code == 404
