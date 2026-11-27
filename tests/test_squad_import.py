"""Squad sheet import: the SLC National Talent Pathway squad list -> a new squad with its players."""
import datetime as dt
from io import BytesIO

import openpyxl
import pytest
from sqlalchemy import select

from app.core.models import Player, Squad, UserRole
from app.importers.squad_import import parse_workbook

from .conftest import login, make_user

TODAY = dt.date(2026, 11, 14)
D = dt.datetime

# (ranking, name, captaincy, dob, school, district, province, bat, bowl) or a group heading string
SHEET = [
    "Batting group",
    (1, "Sethuja Mandinu", "VIC CAPTAIN", D(2011, 11, 18), "St Thomas College Mathara", "Matara", "Southern", "LH", None),
    (2, "Movindu Tunal", None, D(2012, 7, 23), "Dharmashoka College", "Galle 3", "Southern", "RH", "RAOS"),
    (3, "Udula Kumudaka", None, "1/10/2012", "Richmond College", "Galle 2", "Southern", "RH", "RALS"),
    "Wicket Keeper group",
    (7, "Sasindu Losith", None, D(2012, 2, 27), "Sri Sumangala College", "Galle 2", "Southern", "RH", "WK"),
    "Spin group",
    (9, "Vindila Chanul Walpalage", None, D(2012, 1, 16), "St. Thomas College,Matara", "Matara", "Southern", "LH", "LAO"),
    "Pace group",
    (12, "Deneth Dinuka", None, D(2011, 11, 24), "Devapathiraja College", "Galle 2", "Southern", "RH", "RAF"),
    (13, "Maheesha Dissanayake", None, D(2011, 12, 24), "Mahinda Rajapakse,Matara", "Matara", "Southern", "RH", "LAF"),
    "Spin All Rounder",
    (15, "Anuga palliayaguru", None, D(2011, 10, 4), "Mahinda College", "Galle 1", "Southern", "LH", "RALS"),
    "Pace All Rounder",
    (16, "Diyath Sanjitha", "CAPTAIN", D(2011, 12, 5), "Devapathiraja College", "Galle 2", "Southern", "RH", "RAF"),
    None,
    "Stand By",
    (17, "Dasun Nethsara", None, D(2011, 12, 15), "PresidentColl:Embilipitiya", "Rathnapura", "Uva", "RHB", None),
    (18, "Jithum Atthanayake", None, D(2011, 11, 29), "Central College Badulla", "Badulla", "Uva", "RH", "LAF"),
    (19, "Shenuka Hesandu", None, D(2012, 8, 27), "Central College Badulla", "Badulla", "Uva", "LH", "RAOS"),
    (20, "Nisal Dineth", None, D(2011, 11, 3), "National School Mahiyanganaya", "Badulla", "Uva", "RH", "LAO"),
]


def workbook(rows=SHEET, *, footer=True) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Squad"
    ws.append([None, "SLC National Talent Pathway"])
    ws.append([None, "U15  Galle Super Provincial Touranment 16 players Squad 2026"])
    ws.append([None, None, None, None, "Age @"])
    ws.append(["Ranking", "Player Name", None, "DOB", D(2026, 9, 1), "School", "District", "Province", "Bat", "Bowl"])
    for r in rows:
        if r is None:
            ws.append([])
        elif isinstance(r, str):
            ws.append([None, r])
        else:
            rank, name, cap, dob, school, district, prov, bat, bowl = r
            ws.append([rank, name, cap, dob, None, school, district, prov, bat, bowl])
    if footer:
        ws.append([])
        ws.append(["Priyantha Udayarathna", None, "Rohitha Perera", None, None, "KH Nandasena", None, None, "Jayathu Neelaweera"])
        ws.append(["National Jonior Selector", None, "National Selectors Coordineter"])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def by_name(parsed):
    return {r["full_name"]: r for r in parsed["rows"]}


def test_reads_the_slc_squad_sheet():
    p = parse_workbook(workbook(), today=TODAY)
    assert p["errors"] == [] and p["warnings"] == []
    assert len(p["rows"]) == 13
    assert p["suggested"] == {"name": "U15 Galle Super Provincial Touranment 16 players Squad 2026", "province": "Southern", "age_group": "U15"}
    r = by_name(p)
    assert r["Sethuja Mandinu"]["role"] == "batter" and r["Sethuja Mandinu"]["captaincy"] == "vice_captain"
    assert r["Sethuja Mandinu"]["batting_hand"] == "Left" and r["Sethuja Mandinu"]["bowling_arm"] is None
    assert r["Diyath Sanjitha"]["role"] == "all_rounder" and r["Diyath Sanjitha"]["captaincy"] == "captain"
    assert "fast" in r["Diyath Sanjitha"]["style"]
    assert r["Anuga palliayaguru"]["role"] == "all_rounder" and "spin" in r["Anuga palliayaguru"]["style"]
    assert r["Sasindu Losith"]["role"] == "bat_wicketkeeper" and r["Sasindu Losith"]["bowling_arm"] is None
    assert r["Vindila Chanul Walpalage"]["role"] == "spin_bowler" and r["Vindila Chanul Walpalage"]["bowling_arm"] == "Left"
    assert r["Maheesha Dissanayake"]["style"] == "left-arm fast"
    assert r["Deneth Dinuka"]["squad_no"] == 12 and r["Deneth Dinuka"]["district"] == "Galle 2"
    assert r["Udula Kumudaka"]["date_of_birth"] == "2012-01-10"            # text date, month/day like the sheet


def test_stand_by_players_keep_a_role_from_their_bowling():
    r = by_name(parse_workbook(workbook(), today=TODAY))
    assert all(r[n]["standby"] for n in ("Dasun Nethsara", "Jithum Atthanayake", "Shenuka Hesandu", "Nisal Dineth"))
    assert not r["Deneth Dinuka"]["standby"]
    assert r["Dasun Nethsara"]["role"] == "batter" and r["Dasun Nethsara"]["batting_hand"] == "Right"     # RHB
    assert r["Jithum Atthanayake"]["role"] == "fast_bowler"
    assert r["Shenuka Hesandu"]["role"] == "spin_bowler" and r["Nisal Dineth"]["role"] == "spin_bowler"


def test_text_dates_use_the_age_column_when_day_and_month_are_ambiguous():
    rows = ["Batting group", (1, "A Player", None, "10/1/2012", "S", "D", "Southern", "RH", None)]
    wb = openpyxl.load_workbook(BytesIO(workbook(rows, footer=False)))
    wb.active["E6"] = 14.64                       # age on 1 Sep 2026 -> born 10 Jan 2012, so the text is day/month
    buf = BytesIO()
    wb.save(buf)
    assert parse_workbook(buf.getvalue(), today=TODAY)["rows"][0]["date_of_birth"] == "2012-01-10"


def test_bad_rows_are_reported_with_row_and_reason():
    rows = [(1, "No Group", None, D(2012, 1, 1), "S", "D", "Southern", "RH", None),
            "Pace group",
            (2, "Too Old", None, D(2005, 1, 1), "S", "D", "Southern", "RH", "RAF"),
            (3, None, None, D(2012, 1, 1), "S", "D", "Southern", "RH", "RAF"),
            (4, "Bad Date", None, "31/31/2012", "S", "D", "Southern", "RH", "RAF"),
            (5, "Good One", None, D(2012, 3, 3), "S", "D", "Southern", "XX", "ZZZ"),
            (6, "Good One", None, D(2012, 3, 4), "S", "D", "Southern", "RH", "RAOS")]
    p = parse_workbook(workbook(rows), today=TODAY)
    msgs = {(e["row"], e["column"]) for e in p["errors"]}
    assert msgs == {(5, "Group"), (7, "DOB"), (8, "Player Name"), (9, "DOB"), (11, "Player Name")}
    assert [r["full_name"] for r in p["rows"]] == ["Good One"]
    warn = {(w["row"], w["column"]) for w in p["warnings"]}
    assert {(10, "Bat"), (10, "Bowl"), (11, "Bowl")} <= warn                # unknown codes; spin code in the pace group


def test_not_a_squad_sheet():
    wb = openpyxl.Workbook()
    wb.active.append(["Hello"])
    buf = BytesIO()
    wb.save(buf)
    with pytest.raises(ValueError, match="No squad table"):
        parse_workbook(buf.getvalue(), today=TODAY)
    with pytest.raises(ValueError, match="not a readable"):
        parse_workbook(b"not a workbook", today=TODAY)


# ───────────── API ─────────────
def post(client, h, data, **q):
    qs = "&".join(f"{k}={v}" for k, v in q.items())
    return client.post(f"/admin/squads/import?{qs}", content=data, headers={**h, "Content-Type": "application/octet-stream"})


def test_preview_saves_nothing_then_confirm_creates_the_squad(db, client):
    make_user(db, "admin@slc.lk", UserRole.admin)
    h = login(client, "admin@slc.lk")
    r = post(client, h, workbook(), confirm="false")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["saved"] is False and len(j["rows"]) == 13 and j["suggested"]["province"] == "Southern"
    assert db.scalar(select(Squad)) is None

    r = post(client, h, workbook(), confirm="true", name="Galle Super Provincial U15 2026", province="Southern", filename="squad.xlsx")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["saved"] is True and j["squad"]["name"] == "Galle Super Provincial U15 2026" and j["squad"]["age_group"] == "U15"
    players = client.get(f"/players?squad_id={j['squad']['id']}", headers=h).json()
    assert len(players) == 13
    cap = next(p for p in players if p["full_name"] == "Diyath Sanjitha")
    assert cap["captaincy"] == "captain" and cap["squad_no"] == 16 and cap["school_or_club"] == "Devapathiraja College"
    assert sum(p["standby"] for p in players) == 4 and {p["gender"] for p in players} == {"male"}

    r = post(client, h, workbook(), confirm="true", name="Galle Super Provincial U15 2026", province="Southern")
    assert r.status_code == 409                                             # same squad name twice


def test_confirm_refuses_a_sheet_with_problems(db, client):
    make_user(db, "admin@slc.lk", UserRole.admin)
    h = login(client, "admin@slc.lk")
    rows = ["Pace group", (1, "Fine", None, D(2012, 1, 1), "S", "D", "Southern", "RH", "RAF"),
            (2, "Too Old", None, D(2005, 1, 1), "S", "D", "Southern", "RH", "RAF")]
    r = post(client, h, workbook(rows), confirm="true", name="X", province="Southern")
    assert r.status_code == 422 and "1 problem" in r.json()["detail"]
    assert db.scalar(select(Player)) is None


def test_only_admins_can_import(db, client):
    make_user(db, "coach@slc.lk", UserRole.coach)
    h = login(client, "coach@slc.lk")
    assert post(client, h, workbook(), confirm="false").status_code == 403
