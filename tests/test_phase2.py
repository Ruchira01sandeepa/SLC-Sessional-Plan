"""Phase 2: screening, seasons & calendar, fitness entry and progress."""
import pytest

H = lambda w, who: w["h"][who]


@pytest.fixture
def season(client, world):
    w = world
    body = {"name": "2026/27", "start_date": "2026-09-01", "end_date": "2027-06-30", "phases": [
        {"phase_type": "pre_season", "start_date": "2026-09-01", "end_date": "2026-11-30"},
        {"phase_type": "in_season", "start_date": "2026-12-01", "end_date": "2027-04-30"}]}
    r = client.post(f"/squads/{w['squad_a']}/seasons", json=body, headers=H(w, "coach_a"))
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ───────────── screening ─────────────
SCREEN = {"screening_date": "2026-09-05", "years_playing_band": "less_than_5", "start_age": 8,
          "format_played_pct": {"3day": 20, "oneday": 50, "t20": 30}, "favourite_shot": "Cover drive",
          "yoyo_last_time": "15.2", "needs": [{"category": "Speed", "item": "Acceleration", "level": "LOW"},
                                              {"category": "Energy systems", "item": "ATP-PC", "level": "HIGH"}]}


def test_screening_roundtrip_and_replace_needs(client, world):
    w = world
    r = client.post(f"/players/{w['ann']}/screenings", json=SCREEN, headers=H(w, "coach_a"))
    assert r.status_code == 201 and len(r.json()["needs"]) == 2
    sid = r.json()["id"]
    r = client.patch(f"/screenings/{sid}", json={"favourite_shot": "Sweep", "needs": [{"category": "Speed", "item": "Maximum", "level": "MOD"}]}, headers=H(w, "coach_a"))
    assert r.json()["favourite_shot"] == "Sweep" and [n["item"] for n in r.json()["needs"]] == ["Maximum"]
    assert r.json()["yoyo_last_time"] == "15.2"                           # untouched field kept
    assert len(client.get(f"/players/{w['ann']}/screenings", headers=H(w, "ann_login")).json()) == 1   # player reads own


@pytest.mark.parametrize("bad", [
    {"needs": [{"category": "Speed", "item": "ATP-PC", "level": "LOW"}]},                      # item not in that category
    {"needs": [{"category": "Speed", "item": "Acceleration", "level": "EXTREME"}]},
    {"needs": [{"category": "Speed", "item": "Acceleration", "level": "LOW"}] * 2},            # duplicate
    {"format_played_pct": {"t20": 80, "oneday": 40}},                                           # > 100 %
    {"start_age": 30},
])
def test_screening_validation(client, world, bad):
    r = client.post(f"/players/{world['ann']}/screenings", json={**SCREEN, **bad}, headers=H(world, "coach_a"))
    assert r.status_code == 422


def test_screening_access(client, world):
    w = world
    assert client.post(f"/players/{w['cara']}/screenings", json=SCREEN, headers=H(w, "coach_a")).status_code == 404
    assert client.post(f"/players/{w['ann']}/screenings", json=SCREEN, headers=H(w, "ann_login")).status_code == 403
    assert client.post(f"/players/{w['ann']}/screenings", json=SCREEN, headers=H(w, "physio_a")).status_code == 403
    sid = client.post(f"/players/{w['ann']}/screenings", json=SCREEN, headers=H(w, "coach_a")).json()["id"]
    assert client.patch(f"/screenings/{sid}", json={"favourite_shot": "x"}, headers=H(w, "coach_b")).status_code == 404
    assert client.get(f"/players/{w['ann']}/screenings", headers=H(w, "bob_login")).status_code == 404


def test_screening_response_has_no_medical_data(client, world):
    w = world
    client.put(f"/players/{w['ann']}/medical", json={"current_health": "Stress reaction"}, headers=H(w, "physio_a"))
    client.post(f"/players/{w['ann']}/screenings", json=SCREEN, headers=H(w, "coach_a"))
    assert "Stress" not in client.get(f"/players/{w['ann']}/screenings", headers=H(w, "coach_a")).text


# ───────────── seasons / calendar ─────────────
def test_season_validation(client, world):
    w, url = world, f"/squads/{world['squad_a']}/seasons"
    base = {"name": "S", "start_date": "2026-09-01", "end_date": "2027-06-30"}
    assert client.post(url, json={**base, "end_date": "2026-08-01"}, headers=H(w, "coach_a")).status_code == 422
    out = {"phase_type": "pre_season", "start_date": "2026-08-01", "end_date": "2026-09-30"}
    assert client.post(url, json={**base, "phases": [out]}, headers=H(w, "coach_a")).status_code == 422
    a = {"phase_type": "pre_season", "start_date": "2026-09-01", "end_date": "2026-10-31"}
    b = {"phase_type": "in_season", "start_date": "2026-10-31", "end_date": "2027-01-31"}
    assert client.post(url, json={**base, "phases": [a, b]}, headers=H(w, "coach_a")).status_code == 422   # overlap


def test_overlapping_seasons_rejected_and_scoping(client, world, season):
    w = world
    r = client.post(f"/squads/{w['squad_a']}/seasons", json={"name": "Dup", "start_date": "2027-01-01", "end_date": "2027-03-01"}, headers=H(w, "coach_a"))
    assert r.status_code == 409
    assert client.post(f"/squads/{w['squad_a']}/seasons", json={"name": "X", "start_date": "2030-01-01", "end_date": "2030-03-01"}, headers=H(w, "coach_b")).status_code == 404
    assert client.get(f"/squads/{w['squad_a']}/seasons", headers=H(w, "ann_login")).status_code == 200      # player reads
    assert client.get(f"/squads/{w['squad_b']}/seasons", headers=H(w, "ann_login")).status_code == 404       # other squad
    assert client.post(f"/squads/{w['squad_a']}/seasons", json={"name": "Y", "start_date": "2031-01-01", "end_date": "2031-03-01"}, headers=H(w, "ann_login")).status_code == 403


def test_events_crud_filter_and_access(client, world):
    w, url = world, f"/squads/{world['squad_a']}/events"
    m = {"event_type": "match", "title": "vs Central", "start_at": "2026-10-24T09:00:00+05:30", "end_at": "2026-10-24T17:00:00+05:30", "intensity_planned": 8}
    t = {"event_type": "training", "title": "Nets", "start_at": "2026-10-22T15:00:00+05:30"}
    mid = client.post(url, json=m, headers=H(w, "coach_a")).json()["id"]
    client.post(url, json=t, headers=H(w, "sc_a"))
    assert [e["title"] for e in client.get(url, headers=H(w, "ann_login")).json()] == ["Nets", "vs Central"]       # sorted, player can read
    assert [e["title"] for e in client.get(url + "?event_type=match", headers=H(w, "coach_a")).json()] == ["vs Central"]
    assert [e["title"] for e in client.get(url + "?from=2026-10-23T00:00:00%2B05:30", headers=H(w, "coach_a")).json()] == ["vs Central"]
    assert client.get(url, headers=H(w, "coach_b")).status_code == 404
    assert client.post(url, json=t, headers=H(w, "ann_login")).status_code == 403
    assert client.post(url, json=t, headers=H(w, "physio_a")).status_code == 403
    assert client.patch(f"/events/{mid}", json={"title": "x"}, headers=H(w, "coach_b")).status_code == 404
    assert client.patch(f"/events/{mid}", json={"title": "vs Kandy"}, headers=H(w, "coach_a")).json()["title"] == "vs Kandy"
    assert client.patch(f"/events/{mid}", json={"end_at": "2026-10-24T01:00:00+05:30"}, headers=H(w, "coach_a")).status_code == 422
    assert client.delete(f"/events/{mid}", headers=H(w, "coach_b")).status_code == 404
    assert client.delete(f"/events/{mid}", headers=H(w, "coach_a")).status_code == 204


def test_event_validation(client, world):
    url = f"/squads/{world['squad_a']}/events"
    base = {"event_type": "match", "title": "x", "start_at": "2026-10-24T09:00:00Z"}
    for bad in ({"end_at": "2026-10-24T08:00:00Z"}, {"intensity_planned": 11}, {"title": ""}, {"event_type": "party"}):
        assert client.post(url, json={**base, **bad}, headers=H(world, "coach_a")).status_code == 422


def test_event_times_are_stored_in_utc(client, world):
    url = f"/squads/{world['squad_a']}/events"
    r = client.post(url, json={"event_type": "training", "title": "t", "start_at": "2026-10-24T09:00:00+05:30"}, headers=H(world, "coach_a"))
    assert r.json()["start_at"].startswith("2026-10-24T03:30:00")


# ───────────── fitness ─────────────
def put(client, w, who, pid, season, phase, body):
    return client.put(f"/players/{pid}/fitness/{season}/{phase}", json=body, headers=H(w, who))


BASE = {"test_date": "2026-09-05", "bodyweight_kg": 45.2, "height_cm": 158, "cmj_cm": 30.0, "squat_jump_cm": 28.0,
        "sprint_5m_s": 1.10, "sprint_10m_s": 1.90, "sprint_20m_s": 3.40, "yoyo_level": "15.3", "yoyo_distance_m": 1040,
        "prone_plank_s": 90, "side_plank_front_s": 45, "side_plank_back_s": 44, "calf_raises_front_leg": 25, "calf_raises_back_leg": 27}


def test_fitness_entry_and_upsert(client, world, season):
    w = world
    r = put(client, w, "sc_a", w["ann"], season, "baseline", BASE)
    assert r.status_code == 200 and r.json()["cmj_cm"] == 30.0
    r = put(client, w, "sc_a", w["ann"], season, "baseline", {"cmj_cm": 31.0})              # partial update keeps the rest
    assert r.json()["cmj_cm"] == 31.0 and r.json()["sprint_20m_s"] == 3.40
    r = put(client, w, "sc_a", w["ann"], season, "baseline", {"cmj_cm": None})              # explicit clear
    assert r.json()["cmj_cm"] is None and r.json()["sprint_20m_s"] == 3.40
    assert len(client.get(f"/players/{w['ann']}/fitness", headers=H(w, "ann_login")).json()) == 1


@pytest.mark.parametrize("bad", [
    {"sprint_20m_s": 34.0},                                   # decimal-point typo
    {"cmj_cm": -3},
    {"sprint_5m_s": 2.0, "sprint_10m_s": 1.5},                # not increasing with distance
    {"yoyo_level": "fifteen"},
    {"height_cm": 15.8},
])
def test_fitness_rejects_implausible_values(client, world, season, bad):
    assert put(client, world, "sc_a", world["ann"], season, "baseline", {**BASE, **bad}).status_code == 422


def test_fitness_requirements(client, world, season):
    w = world
    assert put(client, w, "sc_a", w["ann"], season, "baseline", {"test_date": "2026-09-05"}).status_code == 422      # nothing entered
    assert put(client, w, "sc_a", w["ann"], season, "baseline", {"cmj_cm": 30}).status_code == 422                  # no date on new test
    assert put(client, w, "sc_a", w["ann"], season, "baseline", {**BASE, "test_date": "2025-01-01"}).status_code == 422  # outside season
    assert put(client, w, "sc_a", w["ann"], 9999, "baseline", BASE).status_code == 404
    assert put(client, w, "sc_a", w["ann"], season, "pre_game", BASE).status_code == 422


def test_fitness_season_must_belong_to_the_players_squad(client, world, season):
    w = world
    r = client.post(f"/squads/{w['squad_b']}/seasons", json={"name": "B", "start_date": "2026-09-01", "end_date": "2027-06-30"}, headers=H(w, "coach_b"))
    assert put(client, w, "sc_a", w["ann"], r.json()["id"], "baseline", BASE).status_code == 404


def test_fitness_access(client, world, season):
    w = world
    assert put(client, w, "ann_login", w["ann"], season, "baseline", BASE).status_code == 403      # players cannot enter
    assert put(client, w, "physio_a", w["ann"], season, "baseline", BASE).status_code == 403
    assert put(client, w, "coach_b", w["ann"], season, "baseline", BASE).status_code == 404
    assert put(client, w, "coach_a", w["bob"], season, "baseline", BASE).status_code == 200        # coaches may
    assert client.get(f"/players/{w['bob']}/fitness", headers=H(w, "ann_login")).status_code == 404   # teammate's results hidden


def row(report, field):
    return next(m for m in report["metrics"] if m["field"] == field)


def test_progress_change_from_baseline_and_direction(client, world, season):
    w = world
    put(client, w, "sc_a", w["ann"], season, "baseline", BASE)
    put(client, w, "sc_a", w["ann"], season, "mid_season", {"test_date": "2026-12-05", "cmj_cm": 33.0, "sprint_20m_s": 3.30, "bodyweight_kg": 47.0})
    rep = client.get(f"/players/{w['ann']}/fitness/progress?season_id={season}", headers=H(w, "ann_login")).json()
    cmj, sp, bw = row(rep, "cmj_cm"), row(rep, "sprint_20m_s"), row(rep, "bodyweight_kg")
    assert (cmj["baseline"], cmj["current"], cmj["current_phase"], cmj["change_from_baseline"], cmj["improved"]) == (30.0, 33.0, "mid_season", 3.0, True)
    assert cmj["change_pct"] == 10.0
    assert (sp["change_from_baseline"], sp["improved"]) == (-0.1, True)                 # faster sprint = improvement
    assert bw["improved"] is None and bw["higher_is_better"] is None                     # growth is never judged
    assert row(rep, "yoyo_distance_m")["current_phase"] == "baseline"                    # falls back to latest available phase
    assert "adult" in rep["note"]


def test_squad_percentile_needs_enough_players_and_is_direction_aware(client, db, world, season):
    from app.models import Gender, Player, PlayerRole
    import datetime as dt
    w = world
    put(client, w, "sc_a", w["ann"], season, "baseline", BASE)
    ids = [w["ann"], w["bob"]]
    for i in range(4):
        p = Player(full_name=f"P{i}", squad_id=w["squad_a"], role=PlayerRole.batter, gender=Gender.male, date_of_birth=dt.date(2012, 1, 1))
        db.add(p); db.flush(); ids.append(p.id)
    db.commit()
    # 6 players: cmj 30,31,32,33,34 for 5 of them ; sprint_20 3.4,3.5,3.6,3.7,3.8
    for i, pid in enumerate(ids[1:]):
        put(client, w, "sc_a", pid, season, "baseline", {"test_date": "2026-09-06", "cmj_cm": 31 + i, "sprint_20m_s": round(3.5 + 0.1 * i, 1)})
    rep = lambda pid: client.get(f"/players/{pid}/fitness/progress?season_id={season}", headers=H(w, "coach_a")).json()
    ann_cmj, ann_sp = row(rep(w["ann"]), "cmj_cm"), row(rep(w["ann"]), "sprint_20m_s")
    assert ann_cmj["squad_n"] == 6 and ann_cmj["squad_percentile"] == round(100 * 0.5 / 6, 1)       # lowest jump -> bottom
    assert ann_sp["squad_percentile"] == round(100 * 5.5 / 6, 1)                                      # fastest sprint -> top
    best = row(rep(ids[-1]), "cmj_cm")
    assert best["squad_percentile"] > 90


def test_percentile_hidden_for_small_squads(client, world, season):
    w = world
    put(client, w, "sc_a", w["ann"], season, "baseline", BASE)
    put(client, w, "sc_a", w["bob"], season, "baseline", BASE)
    assert row(client.get(f"/players/{w['ann']}/fitness/progress?season_id={season}", headers=H(w, "coach_a")).json(), "cmj_cm")["squad_percentile"] is None


def test_targets_and_benchmarks(client, world, season):
    w = world
    put(client, w, "sc_a", w["ann"], season, "baseline", BASE)
    assert client.put(f"/squads/{w['squad_a']}/fitness-benchmarks", json={"field_name": "cmj_cm", "target_value": 35}, headers=H(w, "coach_a")).status_code == 200
    assert client.put(f"/squads/{w['squad_a']}/fitness-benchmarks", json={"field_name": "sprint_20m_s", "target_value": 3.5}, headers=H(w, "coach_a")).status_code == 200
    assert client.put(f"/players/{w['ann']}/fitness-targets", json={"field_name": "cmj_cm", "target_value": 32}, headers=H(w, "sc_a")).status_code == 200
    r = client.put(f"/players/{w['ann']}/fitness-targets", json={"field_name": "cmj_cm", "target_value": 29}, headers=H(w, "sc_a"))      # update, no duplicate
    rep = client.get(f"/players/{w['ann']}/fitness/progress?season_id={season}", headers=H(w, "ann_login")).json()
    cmj, sp = row(rep, "cmj_cm"), row(rep, "sprint_20m_s")
    assert (cmj["individual_target"], cmj["individual_target_status"]) == (29, "met")
    assert (cmj["coach_benchmark"], cmj["coach_benchmark_status"]) == (35, "not_yet")
    assert sp["coach_benchmark_status"] == "met"                                                      # 3.40 s <= 3.5 s (lower is better)
    for bad in ({"field_name": "bodyweight_kg", "target_value": 40}, {"field_name": "nonsense", "target_value": 1},
                {"field_name": "cmj_cm", "target_value": 900}):
        assert client.put(f"/players/{w['ann']}/fitness-targets", json=bad, headers=H(w, "sc_a")).status_code in (422,)
    assert client.put(f"/players/{w['ann']}/fitness-targets", json={"field_name": "cmj_cm", "target_value": 32}, headers=H(w, "ann_login")).status_code == 403
    assert client.put(f"/squads/{w['squad_a']}/fitness-benchmarks", json={"field_name": "cmj_cm", "target_value": 35}, headers=H(w, "coach_b")).status_code == 404


def test_benchmarks_do_not_leak_between_squads_or_players(client, world, season):
    w = world
    put(client, w, "sc_a", w["ann"], season, "baseline", BASE)
    put(client, w, "sc_a", w["bob"], season, "baseline", BASE)
    client.put(f"/players/{w['ann']}/fitness-targets", json={"field_name": "cmj_cm", "target_value": 32}, headers=H(w, "sc_a"))
    bob = row(client.get(f"/players/{w['bob']}/fitness/progress?season_id={season}", headers=H(w, "coach_a")).json(), "cmj_cm")
    assert bob["individual_target"] is None


def test_squad_fitness_table(client, world, season):
    w = world
    put(client, w, "sc_a", w["ann"], season, "baseline", BASE)
    rows = client.get(f"/squads/{w['squad_a']}/fitness?season_id={season}&phase=baseline", headers=H(w, "coach_a")).json()
    assert [r["name"] for r in rows] == ["Ann", "Bob"]
    assert rows[0]["cmj_cm"] == 30.0 and rows[1]["cmj_cm"] is None            # Bob not tested yet: still listed
    assert client.get(f"/squads/{w['squad_a']}/fitness?season_id={season}&phase=baseline", headers=H(w, "ann_login")).status_code == 403
    assert client.get(f"/squads/{w['squad_a']}/fitness?season_id={season}&phase=baseline", headers=H(w, "coach_b")).status_code == 404


def test_my_squads_is_scoped(client, world):
    w = world
    names = lambda who: [s["name"] for s in client.get("/squads", headers=H(w, who)).json()]
    assert names("coach_a") == ["Western U15"] and names("coach_b") == ["Central U15"]
    assert names("ann_login") == ["Western U15"]
    assert names("admin") == ["Central U15", "Western U15"]


def test_ui_is_served_with_strict_csp_and_api_is_not_cached(client, world):
    r = client.get("/ui/")
    assert r.status_code == 200 and "script-src 'self'" in r.headers["content-security-policy"]
    assert "unsafe-inline" not in r.headers["content-security-policy"]
    assert client.get("/ui/app.js").status_code == 200
    api = client.get("/players", headers=world["h"]["coach_a"])
    assert api.headers["cache-control"] == "no-store" and api.headers["x-content-type-options"] == "nosniff"
    assert client.get("/", follow_redirects=False).headers["location"] == "/ui/"


def test_ui_source_never_uses_innerhtml_or_eval():
    """The UI inserts API data as text only. Guard against someone re-introducing HTML injection."""
    import pathlib, re
    for name in ("app.js", "charts.js"):
        src = (pathlib.Path(__file__).parent.parent / "app/static" / name).read_text(encoding="utf-8")
        assert not re.search(r"innerHTML|outerHTML|insertAdjacentHTML|document\.write|eval\(|new Function", src), name
