"""Women's and girls' teams: their own age references, a women's points benchmark, and reports that use them."""
import pytest

from app.assessment import benchmark as bm
from app.assessment.age_norms import AGE_GROUPS, FEMALE_REFERENCE, REFERENCE, age_band, ref_label, reference
from app.assessment.test_battery import BY_KEY, SUPER
from tests.test_player_season_plan import H, make_season


def test_womens_references_are_complete_and_ordered():
    assert set(FEMALE_REFERENCE) == set(REFERENCE)
    for key, by_age in FEMALE_REFERENCE.items():
        t = BY_KEY[key]
        assert set(by_age) == set(AGE_GROUPS)
        for ag, (dev, exp, strong) in by_age.items():
            assert (dev < exp < strong) if t.higher_is_better else (dev > exp > strong), (key, ag)
            boys = REFERENCE[key][ag][1]
            assert (exp < boys) if t.higher_is_better else (exp > boys), (key, ag)     # women's expected value below the boys'
    assert ref_label("U15", "female") == "U15 girls" and ref_label("U19", "female") == "U19 women" and ref_label("U15") == "U15"
    assert age_band("broad_jump", 160, "U15", "female")["age_group"] == "U15 girls"


@pytest.mark.parametrize("ag", ["U15", "U17", "U19"])
def test_womens_benchmark_one_point_at_expected(ag):
    tbl = bm.cut_table(ag, "female")
    assert tbl and set(tbl) == set(bm.U15)
    for key, (_, mx, cuts) in tbl.items():
        assert [p for _, p in cuts] == list(range(mx, 0, -1))
        assert cuts[-1][0] == pytest.approx(reference(key, ag, "female")[1], abs=0.01)  # 1 point = the expected value
    exp = {k: reference(k, ag, "female")[1] for k in tbl}
    s = bm.score(SUPER, exp, ag, "female")
    assert s["total"] == 6 and s["max"] == bm.MAX                                       # 1 point in each of the six qualities
    assert bm.score(SUPER, exp, ag, "male") is None or ag == "U15"                       # boys: U15 only, as before


def test_womens_squad_reports(client, world):
    from app.core.db import SessionLocal
    from app.core.models import Gender, Player
    with SessionLocal() as db:                                                           # squad A becomes a girls' team
        for p in db.query(Player).filter(Player.squad_id == world["squad_a"]):
            p.gender = Gender.female
        db.commit()
    sid = make_season(client, world)
    r = client.put(f"/players/{world['ann']}/tests/{sid}/baseline", headers=H(world, "sc_a"),
                   json={"level": "super_provincial", "test_date": "2027-02-01", "results": {"pushups": ["12"], "broad_jump": ["150"]}})
    assert r.status_code == 200, r.text
    d = client.get(f"/squads/{world['squad_a']}/seasons/{sid}/test-results?window=baseline", headers=H(world, "coach_a")).json()
    assert d["gender"] == "female" and d["ref_label"].endswith(("girls", "women"))
    ann = next(x for x in d["players"] if x["player_id"] == world["ann"])
    assert ann["age"] == {"pushups": "on_track", "broad_jump": "developing"}               # girls' values, not the boys'
    push = next(t for t in d["tests"] if t["key"] == "pushups")
    assert push["reference"]["expected"] == reference("pushups", d["age_group"], "female")[1]
    pdf = client.get(f"/squads/{world['squad_a']}/seasons/{sid}/test-summary.pdf?window=baseline", headers=H(world, "coach_a"))
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    norms = client.get("/meta/age-norms?gender=female", headers=H(world, "coach_a")).json()
    assert norms["gender"] == "female" and "girls" in norms["note"]
    b = client.get("/meta/benchmark?gender=female&age_group=U19", headers=H(world, "coach_a")).json()
    assert b["label"] == "U19 women" and b["max"] == bm.MAX
    assert client.get("/meta/benchmark", headers=H(world, "coach_a")).json()["label"] == "U15"
