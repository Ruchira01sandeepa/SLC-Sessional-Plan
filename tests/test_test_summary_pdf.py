"""The Fitness page's overall test results summary as a PDF."""
import re

from tests.test_player_season_plan import H, make_season


def _pages(data: bytes) -> int:
    return len(re.findall(rb"/Type /Page[^s]", data))


def test_summary_pdf_with_results_and_access(client, world):
    sid = make_season(client, world)
    url = f"/squads/{world['squad_a']}/seasons/{sid}/test-summary.pdf?window=baseline"
    empty = client.get(url, headers=H(world, "coach_a"))
    assert empty.status_code == 200 and empty.content.startswith(b"%PDF") and _pages(empty.content) == 1   # nothing tested yet: one page
    for pid, sr, bj in ((world["ann"], "-8", "180"), (world["bob"], "12", "215")):
        r = client.put(f"/players/{pid}/tests/{sid}/baseline", headers=H(world, "sc_a"),
                       json={"level": "super_provincial", "test_date": "2027-02-01",
                             "results": {"sit_reach": [sr], "broad_jump": [bj], "sprint_20m": ["3.6"], "pushups": ["25"]}})
        assert r.status_code == 200, r.text
    r = client.get(url, headers=H(world, "sc_a"))
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert 'filename="test-results-summary-' in r.headers["content-disposition"] and r.headers["content-disposition"].endswith('baseline.pdf"')
    assert _pages(r.content) >= 5                  # summary, charts, flexibility and body, overview and results, priorities
    assert client.get(url).status_code == 401
    assert client.get(url, headers=H(world, "coach_b")).status_code in (403, 404)
    assert client.get(url.replace("baseline", "bogus"), headers=H(world, "coach_a")).status_code in (400, 422)
