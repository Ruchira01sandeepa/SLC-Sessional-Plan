"""A player's seasonal plan as a PDF: the Annual plan and the Week plans."""
import re

from app.player_plan_pdf import build_player_plan_pdf
from app.player_season_plan import personal_grid
from app.weekly_sessions import build_weeks
from tests.test_player_season_plan import H, grid, make_season


def _pages(data: bytes) -> int:
    return len(re.findall(rb"/Type /Page[^s]", data))


def test_pdf_parts_from_the_same_plan():
    g = personal_grid(grid(), name="Ann Perera", role="Spin bowler",
                      areas=[{"area": "speed", "label": "Speed", "percentile": 20.0}, {"area": "core", "label": "Core", "percentile": 90.0}])
    weeks = build_weeks(g, roles=["spin_bowler"])
    annual = build_player_plan_pdf(g, None, "annual")
    assert annual.startswith(b"%PDF") and _pages(annual) == 1                          # the whole sheet on one A3 page, like Excel
    rep = {"age_group": "U15", "progress": None, "windows": [{"window": "baseline", "window_label": "Baseline", "level_label": "Super Provincial",
           "test_date": None, "height_cm": 160, "weight_kg": 45, "bmi": 17.6, "band": 3, "band_label": "Competent", "overall": 55,
           "benchmark": {"total": 13, "max": 34, "band_label": "Red"}, "focus": ["Speed"], "sit_reach": None, "skinfold_sum": None, "copied": [],
           "skinfolds": [{"label": "Triceps", "final": 6.4}],
           "tests": [{"key": "sprint_20m", "label": "20 m sprint", "unit": "s", "trials": ["3.66", "3.52", None], "best": "3.52",
                      "expected": "3.45", "age": "developing", "age_label": "Developing", "percentile": 35.0}]}]}
    with_tests = build_player_plan_pdf(g, None, "annual", rep)
    assert _pages(with_tests) == 2                                                     # Annual plan, then the test results
    week_pdf = build_player_plan_pdf(g, weeks, "weeks")
    real = sum(1 for w in weeks["weeks"] if any(d["kind"] != "outside" for d in w["days"]))
    assert _pages(week_pdf) >= real                                                    # every week starts on its own page
    both = build_player_plan_pdf(g, weeks, "all")
    assert _pages(both) == _pages(annual) + _pages(week_pdf)


def test_pdf_download_and_access(client, world):
    sid = make_season(client, world)
    url = f"/squads/{world['squad_a']}/seasons/{sid}/player-plans/{world['ann']}.pdf"
    r = client.get(url + "?part=annual", headers=H(world, "coach_a"))
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf" and r.content.startswith(b"%PDF")
    assert 'filename="Annual-plan-' in r.headers["content-disposition"] and _pages(r.content) == 2   # sheet + test results (none yet)
    w = client.get(url + "?part=weeks", headers=H(world, "sc_a"))
    assert w.status_code == 200 and 'filename="Week-plans-' in w.headers["content-disposition"]
    assert client.get(url + "?part=bogus", headers=H(world, "coach_a")).status_code == 422
    assert client.get(url).status_code == 401
    assert client.get(url, headers=H(world, "coach_b")).status_code in (403, 404)
    assert client.get(url, headers=H(world, "physio_a")).status_code == 403                # plans follow the test results' access


def test_sit_and_reach_drives_a_flexibility_focus():
    from app.player_season_plan import classify, flexibility_area
    assert flexibility_area(None) is None
    assert flexibility_area(-5.1)["status"] == "weak" and flexibility_area(2.5)["status"] == "ok" and flexibility_area(12.7)["status"] == "strong"
    areas = [{"area": "speed", "label": "Speed", "percentile": 80.0}, flexibility_area(-15.2)]
    weak, strong = classify(areas)
    assert [a["area"] for a in weak] == ["flexibility"] and [a["area"] for a in strong] == ["speed"]
    g = personal_grid(grid(), name="Ann Perera", role="Spin bowler", areas=areas)
    assert "FLEXIBILITY" in g["title"] and any(x == "FLEX -15cm" for x in g["performance"] if x)
    flex_row = next(r for s in g["sections"] if s["name"] == "Physical" for r in s["rows"] if r["label"] == "Flexibility")
    squad_row = next(r for s in grid()["sections"] if s["name"] == "Physical" for r in s["rows"] if r["label"] == "Flexibility")
    assert sum(flex_row["marks"]) >= sum(squad_row["marks"])                             # never less flexibility than the squad
    days = [d for w in build_weeks(g, roles=["spin_bowler"])["weeks"] for d in w["days"] if d["kind"] in ("trainer", "school")]
    assert days and all(any(r["desc"] == "FLEXIBILITY - FOCUS" for r in d["rows"]) for d in days)
    plain = personal_grid(grid(), name="Bob", role="Batter", areas=[flexibility_area(3.0)])
    days = [d for w in build_weeks(plain, roles=["batter"])["weeks"] for d in w["days"] if d["kind"] in ("trainer", "school")]
    assert not any(r["desc"] == "FLEXIBILITY - FOCUS" for d in days for r in d["rows"])   # reaches the toes: squad work only


def test_all_players_annual_pdf_and_sit_and_reach_in_the_plan(client, world):
    sid = make_season(client, world)
    r = client.put(f"/players/{world['bob']}/tests/{sid}/baseline", headers=H(world, "sc_a"),
                   json={"level": "super_provincial", "test_date": "2027-02-01", "results": {"sit_reach": ["-8"], "broad_jump": ["180"]}})
    assert r.status_code == 200, r.text
    from app.routers.plans import _latest_areas
    from app.db import SessionLocal
    with SessionLocal() as db:
        flex = next(a for a in _latest_areas(db, world["squad_a"], sid)[world["bob"]] if a["area"] == "flexibility")
    assert flex["status"] == "weak" and flex["value"] == -8.0
    url = f"/squads/{world['squad_a']}/seasons/{sid}/player-plans.pdf"
    a = client.get(url, headers=H(world, "coach_a"))
    assert a.status_code == 200 and a.content.startswith(b"%PDF") and 'filename="Annual-plans-all-players-' in a.headers["content-disposition"]
    assert _pages(a.content) >= 4                                                         # every player: annual sheet + test results
    assert client.get(url, headers=H(world, "physio_a")).status_code == 403
    assert client.get(url).status_code == 401


def test_sit_and_reach_is_in_every_plan_and_report_workbook(client, world):
    import io
    import openpyxl
    sid = make_season(client, world)
    r = client.put(f"/players/{world['bob']}/tests/{sid}/baseline", headers=H(world, "sc_a"),
                   json={"level": "super_provincial", "test_date": "2027-02-01", "results": {"sit_reach": ["-6.5", "-4.0"], "broad_jump": ["180"]}})
    assert r.status_code == 200, r.text
    base = f"/squads/{world['squad_a']}/seasons/{sid}"

    def book(url):
        x = client.get(url, headers=H(world, "coach_a"))
        assert x.status_code == 200, (url, x.text[:200])
        return openpyxl.load_workbook(io.BytesIO(x.content))

    def text(wb, sheet):
        return " ".join(str(v) for row in wb[sheet].iter_rows(values_only=True) for v in row if v is not None)

    wb = book(f"{base}/player-plans/{world['bob']}.xlsx")                       # the player's seasonal plan
    assert wb.sheetnames.index("Test results") == wb.sheetnames.index("Charts") + 1
    assert "Sit and reach" in text(wb, "Test results") and "-4" in text(wb, "Test results") and "Short of the toes" in text(wb, "Test results")
    assert "Sit and reach" in text(book(f"{base}/player-plans.xlsx"), "Test results")                # all players
    assert "Sit and reach" in text(book(f"{base}/physical-report.xlsx?window=baseline"), "Test results")   # Fitness page report
    wb = book(f"{base}/periodized-plan/{world['bob']}.xlsx")
    assert any("-4.0 cm (short of the toes)" in text(wb, s) for s in wb.sheetnames)
    wb = book(f"/players/{world['bob']}/individual-plan.xlsx?season_id={sid}&window=baseline&fresh=true")
    assert "Other measures (recorded, not ranked)" in text(wb, "Test summary") and "-4.0 cm" in text(wb, "Test summary")


def test_next_test_date_and_targets():
    from app.routers.testing import sit_reach_target
    assert sit_reach_target(-15.2)["target"] == "-10.2" and sit_reach_target(-2.5)["target"] == "+0.0"     # towards, at most to the toes
    assert sit_reach_target(4.0)["target"] == "+6.0" and sit_reach_target(12.7)["kind"] == "keep"
    assert sit_reach_target(None) is None


def test_pdf_report_carries_the_next_test(client, world):
    sid = make_season(client, world)
    for who, jump in (("bob", "180"), ("ann", "200")):
        assert client.put(f"/players/{world[who]}/tests/{sid}/baseline", headers=H(world, "sc_a"),
                          json={"level": "super_provincial", "test_date": "2027-02-01",
                                "results": {"broad_jump": [jump], "sit_reach": ["-6"]}}).status_code == 200
    from app.db import SessionLocal
    from app.models import Player
    from app.routers.testing import player_test_report
    with SessionLocal() as db:
        rep = player_test_report(db, world["squad_a"], sid, db.get(Player, world["bob"]))
    nx = rep["next"]
    assert nx["window_label"] == "Mid-season"
    jump = next(t for t in nx["targets"] if t["key"] == "broad_jump")
    assert float(jump["target"]) > 180 and float(jump["target"]) <= 180 * 1.08 + 1e-6          # never more than 8% in one window
    assert next(t for t in nx["targets"] if t["key"] == "sit_reach")["target"] == "-1.0"
    r = client.get(f"/squads/{world['squad_a']}/seasons/{sid}/player-plans/{world['bob']}.pdf?part=annual", headers=H(world, "coach_a"))
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
