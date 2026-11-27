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


def test_long_names_never_overflow_the_page_band():
    from io import BytesIO

    from reportlab.pdfgen.canvas import Canvas

    from app.exports.pdf.player_plan_pdf import _fit
    c = Canvas(BytesIO())
    assert _fit(c, "Short title", "Helvetica-Bold", 15, 9, 300) == ("Short title", 15)           # fits: unchanged
    text, size = _fit(c, "Test results summary  ·  " + "A very long squad name " * 12, "Helvetica-Bold", 15, 9, 400)
    assert size == 9 and text.endswith("...") and c.stringWidth(text, "Helvetica-Bold", size) <= 400


def test_today_is_sri_lanka_date():
    from datetime import datetime, timedelta, timezone

    from app.core.clock import today_lk
    from app.workload.workload_service import today_lk as wl_today
    assert today_lk() == datetime.now(timezone(timedelta(hours=5, minutes=30))).date() and wl_today is today_lk


def test_copied_sit_and_reach_is_marked_and_cleared_when_measured(client, world):
    from app.core.db import SessionLocal
    from app.core.models import TestResult
    sid = make_season(client, world)
    url = f"/players/{world['ann']}/tests/{sid}/baseline"
    body = {"level": "super_provincial", "test_date": "2027-02-01", "results": {"sit_reach": ["-6"], "broad_jump": ["180"]}}
    assert client.put(url, headers=H(world, "sc_a"), json=body).status_code == 200
    with SessionLocal() as db:                                  # the coach could not measure her: a comparison player's result
        r = db.query(TestResult).filter(TestResult.test_key == "sit_reach").one()
        r.setup = "Copied from Bob Silva (not measured)"
        db.commit()
    res = f"/squads/{world['squad_a']}/seasons/{sid}/test-results?window=baseline"
    ann = next(p for p in client.get(res, headers=H(world, "coach_a")).json()["players"] if p["player_id"] == world["ann"])
    assert ann["sit_reach"] == -6.0 and ann["sit_reach_copied"] == "Copied from Bob Silva (not measured)"
    pdf = client.get(f"/squads/{world['squad_a']}/seasons/{sid}/test-summary.pdf?window=baseline", headers=H(world, "coach_a"))
    assert pdf.status_code == 200
    body["results"]["sit_reach"] = ["2"]                        # measured at last: the copy note goes
    assert client.put(url, headers=H(world, "sc_a"), json=body).status_code == 200
    ann = next(p for p in client.get(res, headers=H(world, "coach_a")).json()["players"] if p["player_id"] == world["ann"])
    assert ann["sit_reach"] == 2.0 and ann["sit_reach_copied"] is None


def test_summary_word_document(client, world):
    from io import BytesIO

    from docx import Document
    sid = make_season(client, world)
    url = f"/squads/{world['squad_a']}/seasons/{sid}/test-summary.docx?window=baseline"
    empty = client.get(url, headers=H(world, "coach_a"))
    assert empty.status_code == 200 and empty.content.startswith(b"PK")                       # a .docx is a zip
    for pid, sr, bj in ((world["ann"], "-8", "180"), (world["bob"], "12", "215")):
        assert client.put(f"/players/{pid}/tests/{sid}/baseline", headers=H(world, "sc_a"),
                          json={"level": "super_provincial", "test_date": "2027-02-01",
                                "results": {"sit_reach": [sr], "broad_jump": [bj], "sprint_20m": ["3.6"]}}).status_code == 200
    r = client.get(url, headers=H(world, "coach_a"))
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/vnd.openxmlformats-officedocument.wordprocessingml")
    assert r.headers["content-disposition"].endswith('baseline.docx"')
    doc = Document(BytesIO(r.content))
    text = "\n".join(p.text for p in doc.paragraphs)
    for heading in ("Physical Test Results Summary", "Key findings", "Results by test", "Flexibility", "Player overview", "Full results",
                    "Squad priorities", "Next steps", "Method and notes"):
        assert heading in text, heading
    assert len(doc.sections) == 3 and doc.sections[1].page_width > doc.sections[1].page_height          # landscape middle section
    assert client.get(url, headers=H(world, "coach_b")).status_code in (403, 404)
    assert client.get(url).status_code == 401
