"""Players' own seasonal plans in the supplied workbook's structure, and every player in one Excel."""
import io
from datetime import date

import openpyxl

from app.planning.annual_grid import build_grid
from app.planning.player_season_plan import personal_grid
from app.exports.excel.seasonal_workbook import SHEETS, build_seasonal_workbook
H = lambda w, who: w["h"][who]

PHASES = [{"phase_type": "pre_season", "start_date": date(2027, 1, 1), "end_date": date(2027, 5, 31)},
          {"phase_type": "pre_competition", "start_date": date(2027, 6, 1), "end_date": date(2027, 6, 30)},
          {"phase_type": "in_season", "start_date": date(2027, 7, 1), "end_date": date(2027, 8, 31)},
          {"phase_type": "transition", "start_date": date(2027, 9, 1), "end_date": date(2027, 9, 30)}]


def grid():
    return build_grid(squad_name="X", season={"name": "2027", "start_date": date(2027, 1, 1), "end_date": date(2027, 9, 30)},
                      phases=PHASES, events=[], generated_on=date(2026, 11, 19), age_group="U15")


def row(g, sec, label):
    return next(r for s in g["sections"] if s["name"] == sec for r in s["rows"] if r["label"] == label)["marks"]


AREAS = [{"area": "speed", "label": "Speed", "percentile": 22.0}, {"area": "endurance", "label": "Endurance", "percentile": 88.0},
         {"area": "core", "label": "Core", "percentile": 60.0}]


def test_weak_areas_get_more_work_strong_areas_keep_the_full_squad_work():
    g = grid()
    pg = personal_grid(g, name="Kasun Perera", role="Fast bowler", areas=AREAS)
    k, light = g["kinds"], g["recovery_weeks"]
    squad_speed, own_speed = row(g, "Physical", "Speed"), row(pg, "Physical", "Speed")
    phases = {k[w] for w in range(g["weeks"]) if squad_speed[w]}
    assert all(own_speed[w] for w in range(g["weeks"]) if k[w] in phases and not light[w])            # weak: every week of its phases
    assert not any(own_speed[w] for w in range(g["weeks"]) if k[w] not in phases)                     # never outside the phase rules
    assert row(pg, "Physical", "Endurance") == row(g, "Physical", "Endurance")                         # strong: never cut, keeps improving
    assert row(pg, "Physical", "Coordination") == row(g, "Physical", "Coordination")                   # middle: as the squad
    assert pg["title"] == "ANNUAL PLAN FOR KASUN PERERA (Fast bowler) - FOCUS: SPEED"
    assert pg["performance"][:3] == ["SPD 22", "CORE 60", "END 88"]                                    # own ranks, weakest first
    assert pg["player"]["extra_endurance_reps"] == 0 and row(g, "Physical", "Speed") == squad_speed     # the squad grid is untouched


def test_untested_player_follows_the_squad_plan():
    g = grid()
    pg = personal_grid(g, name="New Boy", role="Batter", areas=[])
    assert all(row(pg, s["name"], r["label"]) == r["marks"] for s in g["sections"] for r in s["rows"])
    assert "NONE BELOW THE 50TH PERCENTILE" in pg["title"]


def test_player_workbook_has_the_four_sheets_and_extra_reps_for_weak_endurance():
    g = grid()
    weak_endurance = [{"area": "endurance", "label": "Endurance", "percentile": 20.0}]
    wb = openpyxl.load_workbook(io.BytesIO(build_seasonal_workbook(personal_grid(g, name="A", role="Batter", areas=weak_endurance))))
    squad = openpyxl.load_workbook(io.BytesIO(build_seasonal_workbook(g)))
    assert wb.sheetnames[:5] == SHEETS and wb["Annual plan"]["A2"].value.startswith("ANNUAL PLAN FOR A (Batter)")
    assert "SESSION PLANS - A -" in wb["Session plan"]["A1"].value and "TOPIC" in [c.value for c in wb["Jan W2 2027"]["A"]]  # the player's own
    own = [c.value for c in wb["Load distribution"][15][1:] if isinstance(c.value, int)]
    base = [c.value for c in squad["Load distribution"][15][1:] if isinstance(c.value, int)]
    assert own and [a - b for a, b in zip(own, base)] == [1] * len(base)                                 # +1 rep of 120 m


# ───────────── API ─────────────
def make_season(client, w, **kw):
    body = {"name": "2027", "start_date": "2027-01-01", "end_date": "2027-09-30", "phases": []}
    body.update(kw)
    return client.post(f"/squads/{w['squad_a']}/seasons", json=body, headers=H(w, "admin")).json()["id"]


def test_all_players_in_one_excel(client, world):
    sid = make_season(client, world)
    r = client.get(f"/squads/{world['squad_a']}/seasons/{sid}/player-plans.xlsx", headers=H(world, "coach_a"))
    assert r.status_code == 200 and "Seasonal-plans-all-players" in r.headers["content-disposition"]
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    cut = wb.sheetnames.index("Component distribution")
    pairs = wb.sheetnames[:cut]
    assert wb.sheetnames[cut:cut + 3] == SHEETS[2:] and len(pairs) >= 4 and len(set(wb.sheetnames)) == len(wb.sheetnames)
    players, loads = pairs[0::2], pairs[1::2]                                                         # each player: plan, then own load
    titles = [wb[n]["A2"].value for n in players]
    assert all(t.startswith("ANNUAL PLAN FOR ") for t in titles) and len(set(titles)) == len(titles)   # one sheet per player
    assert wb[players[0]]["B9"].hyperlink is not None                                               # each plan's weeks open their sessions
    for p, ld in zip(players, loads):
        assert " Load " in f" {ld} " and wb[ld]["B10"].value == f"='{p}'!B10"                        # linked to that player's plan
        assert wb[ld]["A25"].value.endswith("other qualities (per week)")


def test_one_player_plan_and_access(client, world):
    sid = make_season(client, world)
    url = f"/squads/{world['squad_a']}/seasons/{sid}/player-plans/{world['ann']}.xlsx"
    r = client.get(url, headers=H(world, "coach_a"))
    assert r.status_code == 200 and openpyxl.load_workbook(io.BytesIO(r.content)).sheetnames[:5] == SHEETS
    assert client.get(url).status_code == 401
    assert client.get(url, headers=H(world, "coach_b")).status_code in (403, 404)
    other = f"/squads/{world['squad_a']}/seasons/{sid}/player-plans/{world['cara']}.xlsx"
    assert client.get(other, headers=H(world, "coach_a")).status_code in (200, 404)


def test_tournament_gets_the_same_four_sheets(client, world):
    sid = make_season(client, world, name="cup", start_date="2028-01-01", end_date="2028-01-10")
    for path in ("seasonal-workbook.xlsx", "player-plans.xlsx"):
        r = client.get(f"/squads/{world['squad_a']}/seasons/{sid}/{path}", headers=H(world, "admin"))
        names = openpyxl.load_workbook(io.BytesIO(r.content)).sheetnames
        assert r.status_code == 200 and "Session plan" in names and "Charts" in names and any("Load" in n for n in names), path


def test_tournament_rows_are_filled_and_personal():
    season = {"name": "cup", "start_date": date(2026, 11, 26), "end_date": date(2026, 12, 5)}
    ph = [{"phase_type": "in_season", "start_date": date(2026, 11, 26), "end_date": date(2026, 12, 5)}]
    g = build_grid(squad_name="X", season=season, phases=ph, events=[], generated_on=date(2026, 11, 19), age_group="U15")
    d = g["daily"]
    assert d["short"] and all(h is not None for h in d["hours"]) and d["hours_planned"]          # planned hours, no calendar times
    assert d["medical_days"][0] and d["medical_days"][-1]                                         # medical check first and last day
    between = [i for i, k in enumerate(d["day_kind_keys"]) if k == "between"]
    assert between and all(row(d, "Physical", "Strength")[i] for i in between)                    # short retaining strength
    assert all(row(d, "Technical", "Basic")[i] and row(d, "Tactical", "Basic")[i] for i in between)
    weak = personal_grid(g, name="A", role="Batter", areas=[{"area": "speed", "label": "Speed", "percentile": 10.0}])["daily"]
    ok = personal_grid(g, name="B", role="Batter", areas=[{"area": "speed", "label": "Speed", "percentile": 60.0}])["daily"]
    assert all(row(weak, "Physical", "Speed")[i] for i in between) and not any(row(ok, "Physical", "Speed")[i] for i in between)
    matchday = [i for i, k in enumerate(d["day_kind_keys"]) if k == "match"]
    assert not any(row(weak, "Physical", "Speed")[i] for i in matchday)                           # never extra work on a match day
    from app.planning.load_distribution import STRIDES, build_interval_loads
    ld = build_interval_loads(d)
    assert all(ld["speed_100m"][i] == STRIDES for i in between) and not any(ld["total"])         # strides, no interval conditioning
