"""A player's seasonal plan as a PDF:
- Annual plan: the Excel "Annual plan" sheet exactly (same rows, labels, colours and * marks), all weeks on one A3 page;
- Test results: the player's own tests this season (trials, best, age reference, squad percentile, body measures, skinfolds);
- Week plans: the Monday to Friday sessions of every week.
Same data as the player's seasonal Excel (player_season_plan.personal_grid + weekly_sessions.build_weeks); nothing is recalculated."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Frame, KeepTogether, NextPageTemplate, PageBreak, PageTemplate, Paragraph, Spacer,
                                Table, TableStyle)

from .annual_grid import PHASE_LABEL
from .annual_grid_excel import DARK, MONTH_FILL, NAVY as X_NAVY, PERIOD_GREY, PHASE_FILL as X_PHASE

LOGO = Path(__file__).parent / "static" / "brand" / "logo.png"
NAVY = colors.HexColor("#0d2b6e")
BLUE = colors.HexColor("#1d3f8f")
GOLD = colors.HexColor("#e3b23c")
INK = colors.HexColor("#0f1e2e")
MUTE = colors.HexColor("#55657a")
LINE = colors.HexColor("#c9d5e3")
PALE = colors.HexColor("#eef3f9")
SHEET_LINE = colors.HexColor("#bfbfbf")
KIND_LABEL = {"trainer": "With the trainer", "school": "At school", "match": "Match", "holiday": "No practice", "recovery": "Recovery"}
KIND_FILL = {"trainer": "#dcebfa", "school": "#e3f2e1", "match": "#fde2c4", "holiday": "#eceff3", "recovery": "#efe6fb"}
AGE_FILL = {"strong": "#cfe9cc", "on_track": "#dcebfa", "developing": "#fff0cc", "below": "#f8dcdc"}

S_BASE = ParagraphStyle("base", fontName="Helvetica", fontSize=8, leading=10, textColor=INK)
S_SMALL = ParagraphStyle("small", parent=S_BASE, fontSize=6.5, leading=8)
S_MUTE = ParagraphStyle("mute", parent=S_BASE, textColor=MUTE)
S_H2 = ParagraphStyle("h2", parent=S_BASE, fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=NAVY, spaceBefore=4, spaceAfter=4)
S_CELL = ParagraphStyle("cell", parent=S_BASE, fontSize=7.5, leading=9)
S_CELLB = ParagraphStyle("cellb", parent=S_CELL, fontName="Helvetica-Bold")
S_GRID = ParagraphStyle("grid", parent=S_BASE, fontSize=5, leading=5.6, alignment=1)


def _hex(x: str) -> colors.Color:
    return colors.HexColor("#" + x.lstrip("#"))


def _esc(s) -> str:
    return (str(s if s is not None else "")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _ascii(s: str) -> str:
    """The core PDF fonts are Latin-1: keep the dot and dashes, replace anything else they cannot draw."""
    return (s or "").replace("→", "->").replace("≤", "<=").replace("≥", ">=").encode("latin-1", "replace").decode("latin-1")


def _p(text, style=S_CELL) -> Paragraph:
    return Paragraph(_ascii(_esc(text)), style)


def _f1(v) -> str:
    return "-" if v is None else f"{v:.1f}"


class _Doc(BaseDocTemplate):
    def __init__(self, buf, *, title: str, who: str, sub: str):
        super().__init__(buf, title=title, author="Sri Lanka Cricket", leftMargin=12 * mm, rightMargin=12 * mm, topMargin=30 * mm,
                         bottomMargin=14 * mm)
        self.who, self.sub, self.section = who, sub, ""
        a3, port = landscape(A3), A4
        self.addPageTemplates([
            PageTemplate("a3", [Frame(12 * mm, 12.5 * mm, a3[0] - 24 * mm, a3[1] - 40 * mm, id="f1", leftPadding=0, rightPadding=0)],
                         onPageEnd=self._band, pagesize=a3),
            PageTemplate("port", [Frame(12 * mm, 14 * mm, port[0] - 24 * mm, port[1] - 44 * mm, id="f2", leftPadding=0, rightPadding=0)],
                         onPageEnd=self._band, pagesize=port)])

    def _band(self, c, doc):
        w, h = c._pagesize
        c.saveState()
        c.setFillColor(NAVY)
        c.rect(0, h - 24 * mm, w, 24 * mm, stroke=0, fill=1)
        c.setFillColor(GOLD)
        c.rect(0, h - 25.2 * mm, w, 1.2 * mm, stroke=0, fill=1)
        x = 12 * mm
        if LOGO.is_file():
            c.drawImage(str(LOGO), x, h - 21 * mm, 18 * mm, 18 * mm, preserveAspectRatio=True, mask="auto")
            x += 22 * mm
        c.setFillColor(GOLD)
        c.setFont("Helvetica-Bold", 7.5)
        c.drawString(x, h - 8.5 * mm, "SRI LANKA CRICKET  ·  STRENGTH AND CONDITIONING")
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 15)
        c.drawString(x, h - 15 * mm, _ascii(f"{self.section}  ·  {self.who}"))
        c.setFont("Helvetica", 8.5)
        c.setFillColor(colors.HexColor("#dbe6fb"))
        c.drawString(x, h - 20.5 * mm, _ascii(self.sub))
        c.setStrokeColor(LINE)
        c.line(12 * mm, 10 * mm, w - 12 * mm, 10 * mm)
        c.setFillColor(MUTE)
        c.setFont("Helvetica", 7)
        c.drawString(12 * mm, 6 * mm, _ascii(f"{self.who}  ·  {self.sub}"))
        c.drawRightString(w - 12 * mm, 6 * mm, f"Page {doc.page}")
        c.restoreState()


class _Section(Spacer):
    """Zero-height flowable that changes the title drawn in the page band."""
    def __init__(self, name, who=None, sub=None):
        super().__init__(0, 0)
        self.name, self.who, self.sub = name, who, sub

    def draw(self):
        doc = self.canv._doctemplate
        doc.section = self.name
        if self.who:                                            # the all-players PDF: each player's pages carry their own name
            doc.who, doc.sub = self.who, self.sub


# ───────────── Annual plan: the Excel sheet, row for row ─────────────
def _annual_sheet(g: dict, width: float) -> Table:
    """annual_grid_excel.write_annual_sheet as a table: title, Periods, Phases, Mesos, Macros, Micros, Dates, Percentage, week hours,
    Competition, Test (Medical, Lab, Field), the sections with their * marks, Loading index and Performance index."""
    if g.get("daily", {}).get("short"):                          # a tournament (season under 4 weeks) is drawn day by day, as in Excel
        g = g["daily"]
    n = g["weeks"]
    first = 30 * mm
    cw = (width - first) / n
    rows: list[list] = []
    st = [("FONT", (0, 0), (-1, -1), "Helvetica", 6), ("ALIGN", (1, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
          ("GRID", (0, 1), (-1, -1), 0.25, SHEET_LINE), ("FONT", (0, 0), (0, -1), "Helvetica", 7),
          ("LEFTPADDING", (0, 0), (-1, -1), 1.2), ("RIGHTPADDING", (0, 0), (-1, -1), 1.2),
          ("TOPPADDING", (0, 0), (-1, -1), 1.1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.1)]

    def add(label, cells=None):
        rows.append([label] + (cells if cells is not None else [""] * n))
        return len(rows) - 1

    def span(r, a, b, text, fill, white=False):
        s = _ascii(str(text if text is not None else ""))
        if (b - a + 1) * cw < len(s) * 3.0:                     # too long for the span: "November 2026" -> "Nov"
            s = s[:3]
        rows[r][a + 1] = s
        if b > a:
            st.append(("SPAN", (a + 1, r), (b + 1, r)))
        if fill:
            st.append(("BACKGROUND", (a + 1, r), (b + 1, r), _hex(fill)))
        if white:
            st.append(("TEXTCOLOR", (a + 1, r), (b + 1, r), colors.white))

    def band(label, marks=None):
        r = add(label, ["*" if marks and marks[w] else "" for w in range(n)])
        st.extend([("BACKGROUND", (1, r), (-1, r), _hex(X_NAVY)), ("TEXTCOLOR", (1, r), (-1, r), colors.white), ("FONT", (1, r), (-1, r), "Helvetica-Bold", 7)])
        return r

    def blank():
        return add("")

    r = add(g["title"], [""] * n)
    st += [("SPAN", (0, r), (-1, r)), ("ALIGN", (0, r), (-1, r), "CENTER"), ("FONT", (0, r), (-1, r), "Helvetica-Bold", 9),
           ("BOTTOMPADDING", (0, r), (-1, r), 4)]
    r = add("Periods")
    for a, b, name in g["periods"]:
        span(r, a, b, name, PERIOD_GREY)
    r = add("Phases")
    for a, b, k in g["phases"]:
        span(r, a, b, PHASE_LABEL[k], X_PHASE[k], X_PHASE[k] in DARK)
    r = add("Mesos")
    for a, b, name, month in g["mesos"]:
        span(r, a, b, name, MONTH_FILL[month], MONTH_FILL[month] in DARK)
    r = add("Macros")
    for a, b, num in g["macros"]:
        span(r, a, b, num, None)
    r = add("Micros")
    if g.get("micros"):
        for a, b, num in g["micros"]:
            span(r, a, b, num, None)
    else:
        rows[r][1:] = [str(w + 1) for w in range(n)]
    add("Dates", [f"{g['weekdays'][w]} {g['days'][w]}" if g.get("weekdays") else str(g["days"][w]) for w in range(n)])
    add("Percentage", [f"{round(g['percentage'][w] * 100)}%" for w in range(n)])
    add(g.get("hours_label", "week hours"), [f"{g['hours'][w]:.1f}" for w in range(n)])
    band("Competition", g["match_weeks"])
    blank()
    band("Test")
    for label in ("Medical", "Lab", "Field"):
        marks = g.get("medical_days") if label == "Medical" and g.get("medical_days") else g["test_weeks"]
        add(label, ["*" if label != "Lab" and marks[w] else "" for w in range(n)])
    blank()
    for sec in g["sections"]:
        band(sec["name"])
        for row in sec["rows"]:
            add(row["label"], ["*" if on else "" for on in row["marks"]])
        blank()
    r = add("Loading index")
    st.append(("FONT", (0, r), (0, r), "Helvetica-Bold", 7))
    for name in ("Volume", "Intensity", "Load"):
        r = add(name, [g["loading"][name][w] or "" for w in range(n)])
        st.append(("FONT", (1, r), (-1, r), "Helvetica", 4.6))
    blank()
    perf = g.get("performance") or ["results" if t else None for t in g["test_weeks"]]
    r = add("Performance index", [Paragraph(_ascii(_esc(perf[w])), S_GRID) if perf[w] else "" for w in range(n)])
    st.append(("FONT", (0, r), (0, r), "Helvetica-Bold", 7))
    t = Table(rows, colWidths=[first] + [cw] * n)
    t.setStyle(TableStyle(st))
    return t


def _annual(g: dict, story: list, width: float) -> None:
    pl = g.get("player") or {}
    from .player_season_plan import area_text
    weak = ", ".join(area_text(x) for x in pl.get("weak", []))
    strong = ", ".join(area_text(x) for x in pl.get("strong", []))
    story += [_Section("Annual plan"), _annual_sheet(g, width), Spacer(0, 3 * mm)]
    if pl:
        story.append(Paragraph(_ascii(_esc(f"Extra work for: {weak or 'none below the 50th percentile (keeps the full squad work)'}"
                                           f"   ·   Strengths: {strong or '-'}")), S_MUTE))
    story.append(Paragraph("* = trained / planned that week. Competition: match weeks. Test: Medical and Field test weeks. "
                           "Performance index: this player's own test results; FLEX = sit and reach, cm past (+) or short of (-) the toes.", S_SMALL))


# ───────────── Test results ─────────────
def _tests(rep: dict, story: list, width: float) -> None:
    story.append(_Section("Test results"))
    ag = rep.get("age_group", "U15")
    if not rep.get("windows"):
        story += [Paragraph("Test results", S_H2), Paragraph("No test results for this player this season yet.", S_MUTE)]
        return
    for i, w in enumerate(rep["windows"]):
        head = f"{w['window_label']} test · {w['level_label']}" + (f" · {w['test_date']:%d %b %Y}" if w.get("test_date") else "")
        story.append(Paragraph(_ascii(_esc(head)), S_H2))
        bm = w.get("benchmark")
        kpis = [("Height", f"{_f1(w['height_cm'])} cm" if w["height_cm"] else "-"), ("Weight", f"{_f1(w['weight_kg'])} kg" if w["weight_kg"] else "-"),
                ("BMI", _f1(w["bmi"])), ("Sum of 8 skinfolds", f"{_f1(w['skinfold_sum'])} mm" if w["skinfold_sum"] is not None else "-"),
                ("Sit and reach", f"{_f1(w['sit_reach'])} cm" if w["sit_reach"] is not None else "-"),
                ("Band", f"Band {w['band']} · {w['band_label']}" if w.get("band") else "-"),
                (f"{ag} points", f"{bm['total']} / {bm['max']} · {bm['band_label']}" if bm else "-")]
        kt = Table([[_p(k, ParagraphStyle("kl", parent=S_SMALL, textColor=MUTE)) for k, _ in kpis],
                    [_p(v, ParagraphStyle("kv", parent=S_CELLB, fontSize=9, leading=11)) for _, v in kpis]], colWidths=[width / len(kpis)] * len(kpis))
        kt.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, NAVY), ("LINEAFTER", (0, 0), (-2, -1), 0.25, LINE), ("BACKGROUND", (0, 0), (-1, -1), PALE),
                                ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
        data = [[_p(x, S_CELLB) for x in ("Test", "Unit", "Trial 1", "Trial 2", "Trial 3", "Best", f"{ag} expected", f"Against {ag}")]]
        st = [("GRID", (0, 0), (-1, -1), 0.25, LINE), ("BACKGROUND", (0, 0), (-1, 0), PALE), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
              ("ALIGN", (2, 1), (-1, -1), "CENTER")]
        for t in w["tests"]:
            data.append([_p(t["label"], S_CELLB), _p(t["unit"]), *[_p(v or "-") for v in (t["trials"] + [None] * 3)[:3]], _p(t["best"], S_CELLB),
                         _p(t["expected"] or "-"), _p(t["age_label"] or "-")])
            if t["age"]:
                st.append(("BACKGROUND", (7, len(data) - 1), (7, len(data) - 1), colors.HexColor(AGE_FILL[t["age"]])))
        if w.get("sit_reach") is not None:                       # recorded, not ranked: against the toes, not an age reference
            cm = w["sit_reach"]
            tr = [f"{v:+.1f}" if v is not None else "-" for v in (w.get("sit_reach_trials") or [None] * 3)[:3]]
            data.append([_p("Sit and reach", S_CELLB), _p("cm from toes"), *[_p(v) for v in tr], _p(f"{cm:+.1f}", S_CELLB), _p("toes (0)"),
                         _p("Past the toes" if cm > 0 else "Short of the toes" if cm < 0 else "At the toes")])
            st.append(("BACKGROUND", (7, len(data) - 1), (7, len(data) - 1),
                       colors.HexColor("#cfe9cc" if cm >= 10 else "#dcebfa" if cm >= 0 else "#fff0cc")))
        tt = Table(data, colWidths=[w_ * width for w_ in (0.22, 0.11, 0.1, 0.1, 0.1, 0.1, 0.12, 0.15)], repeatRows=1)
        tt.setStyle(TableStyle(st))
        sf = w["skinfolds"]
        sft = Table([[_p(x["label"], S_SMALL) for x in sf] + [_p("Sum of 8", ParagraphStyle("sb", parent=S_SMALL, fontName="Helvetica-Bold"))],
                     [_p(_f1(x["final"])) for x in sf] + [_p(_f1(w["skinfold_sum"]), S_CELLB)]], colWidths=[width / (len(sf) + 1)] * (len(sf) + 1))
        sft.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, LINE), ("BACKGROUND", (0, 0), (-1, 0), PALE), ("ALIGN", (0, 0), (-1, -1), "CENTER")]))
        parts = [kt, Spacer(0, 3 * mm), tt, Spacer(0, 3 * mm), Paragraph("Skinfolds (mm, ISAK 8 sites)", S_CELLB), sft]
        if w.get("copied"):
            parts.append(Paragraph(_ascii(_esc("Skinfolds not measured: " + "; ".join(w["copied"]))), ParagraphStyle("warn", parent=S_SMALL, textColor=colors.HexColor("#a85d00"))))
        focus = list(w.get("focus") or []) + (["Flexibility (sit and reach short of the toes)"] if (w.get("sit_reach") or 0) < 0 else [])
        if focus:
            parts.append(Paragraph(_ascii(_esc("Focus areas from this test: " + ", ".join(focus))), S_MUTE))
        story += [KeepTogether(parts), Spacer(0, 5 * mm)]
    pr = rep.get("progress")
    if pr and pr.get("tests"):
        cols = pr["windows"]
        data = [[_p("Test", S_CELLB)] + [_p(c["label"], S_CELLB) for c in cols] + [_p("Change", S_CELLB)]]
        for t in pr["tests"]:
            ch = t.get("change")
            data.append([_p(t["label"])] + [_p(t["values"].get(c["window"]) or "-") for c in cols] + [_p(ch["text"] if ch else "-")])
        pt = Table(data, colWidths=[width * 0.3] + [width * 0.5 / len(cols)] * len(cols) + [width * 0.2])
        pt.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, LINE), ("BACKGROUND", (0, 0), (-1, 0), PALE), ("ALIGN", (1, 1), (-1, -1), "CENTER")]))
        story.append(KeepTogether([Paragraph("Progress between tests", S_H2), pt] +
                                  ([Paragraph(_ascii(_esc(pr["band_movement"]["text"])), S_MUTE)] if pr.get("band_movement") else [])))
    nx = rep.get("next")
    if nx and nx.get("targets"):
        when = f"{nx['window_label']} test" + (f" · week of {nx['date']:%d %b %Y}" if nx.get("date") else "")
        data = [[_p(x, S_CELLB) for x in ("Test", "Unit", "Now", "Target", "", "Why")]]
        st = [("GRID", (0, 0), (-1, -1), 0.25, LINE), ("BACKGROUND", (0, 0), (-1, 0), PALE), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
              ("ALIGN", (2, 1), (4, -1), "CENTER")]
        tag = {"focus": ("FOCUS", "#fff0cc"), "improve": ("IMPROVE", "#dcebfa"), "keep": ("KEEP", "#cfe9cc")}
        for t in nx["targets"]:
            label, fill = tag[t["kind"]]
            data.append([_p(t["label"], S_CELLB), _p(t["unit"]), _p(t["now"]), _p(t["target"], S_CELLB), _p(label, S_CELLB), _p(t["why"], S_SMALL)])
            st.append(("BACKGROUND", (4, len(data) - 1), (4, len(data) - 1), colors.HexColor(fill)))
        nt = Table(data, colWidths=[w_ * width for w_ in (0.2, 0.12, 0.09, 0.1, 0.1, 0.39)], repeatRows=1)
        nt.setStyle(TableStyle(st))
        story.append(KeepTogether([Paragraph(_ascii(_esc(f"Next test: {when}")), S_H2),
                                   Paragraph("Targets to reach by the next test, built from this test: about 15 rank places higher in the "
                                             "same-level group, at least the age-group expected value, never more than 8% in one window. "
                                             "Sit and reach: about 5 cm further (short of the toes: towards the toes).", S_SMALL),
                                   Spacer(0, 2 * mm), nt, Spacer(0, 4 * mm)]))
    story.append(Paragraph(f"Against {ag}: the {ag} youth reference (developing / expected / strong). Best of 3 trials; times in mm.ss.", S_SMALL))


# ───────────── Week plans ─────────────
def _day_table(d: dict, width: float) -> KeepTogether:
    kind = d["kind"]
    head = Table([[_p(f"{d['day']} {d['date']:%d %b %Y}", ParagraphStyle("dh", parent=S_CELLB, fontSize=9, textColor=colors.white)),
                   _p(KIND_LABEL.get(kind, kind.title()), ParagraphStyle("dk", parent=S_CELLB, textColor=colors.white)),
                   _p(f"about {d['minutes']} min" if d.get("minutes") else "", ParagraphStyle("dm", parent=S_CELL, textColor=colors.white, alignment=2))]],
                 colWidths=[width * 0.45, width * 0.35, width * 0.2])
    head.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), BLUE), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                              ("LINEBELOW", (0, 0), (-1, -1), 1.2, GOLD)]))
    title = d["title"].split(" - ", 1)[-1]
    parts = [head, Table([[_p(title, S_CELLB)]], colWidths=[width],
                         style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(KIND_FILL.get(kind, "#ffffff")))]))]
    rows = d.get("rows") or []
    if rows:
        data = [[_p(x, S_CELLB) for x in ("Exercise", "Time", "Reps", "Sets", "Organisation", "Rest")]]
        st = [("GRID", (0, 0), (-1, -1), 0.25, LINE), ("BACKGROUND", (0, 0), (-1, 0), PALE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
              ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5)]
        for x in rows:
            if x.get("head"):
                data.append([_p(x["desc"], S_CELLB), _p(x["time"], S_CELLB), "", "", "", ""])
                st += [("SPAN", (2, len(data) - 1), (-1, len(data) - 1)), ("BACKGROUND", (0, len(data) - 1), (-1, len(data) - 1), colors.HexColor("#f6f1df"))]
            else:
                data.append([_p(x["desc"]), _p(x["time"]), _p(x["rep"]), _p(x["set"]), _p(x["org"]), _p(x["rest"])])
        t = Table(data, colWidths=[width * 0.42, width * 0.1, width * 0.1, width * 0.08, width * 0.18, width * 0.12], repeatRows=1)
        t.setStyle(TableStyle(st))
        parts.append(t)
    return KeepTogether(parts + [Spacer(0, 3 * mm)])


def _weeks(g: dict, weeks: dict, story: list, width: float) -> None:
    story.append(_Section("Week plans"))
    s0 = g["week_starts"][0]
    first = True
    for wk in weeks["weeks"]:
        days = [d for d in wk["days"] if d["kind"] != "outside"]
        if not days:
            continue
        if not first:
            story.append(PageBreak())
        first = False
        w = max(0, min(g["weeks"] - 1, (days[0]["date"] - s0).days // 7))
        header = days[0].get("header") or []
        focus = next((x for x in header if x.startswith("Focus areas")), "")
        info = [[_p("Phase", S_CELLB), _p(PHASE_LABEL[g["kinds"][w]]), _p("Planned load", S_CELLB), _p(f"{int(round(g['percentage'][w] * 100))}% of the maximum"),
                 _p("Practice", S_CELLB), _p(", ".join(f"{sum(1 for d in days if d['kind'] == k)} {KIND_LABEL[k].lower()}" for k in KIND_LABEL
                                                       if any(d["kind"] == k for d in days)))]]
        it = Table(info, colWidths=[width * 0.08, width * 0.2, width * 0.12, width * 0.17, width * 0.1, width * 0.33])
        it.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, NAVY), ("INNERGRID", (0, 0), (-1, -1), 0.25, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                ("BACKGROUND", (0, 0), (0, 0), PALE), ("BACKGROUND", (2, 0), (2, 0), PALE), ("BACKGROUND", (4, 0), (4, 0), PALE)]))
        story += [Paragraph(_ascii(_esc(f"Week {w + 1} · {wk['label']}")), S_H2), it]
        if focus:
            story.append(Paragraph(_ascii(_esc(focus)), S_MUTE))
        story.append(Spacer(0, 3 * mm))
        story += [_day_table(d, width) for d in days]


def build_player_plan_pdf(g: dict, weeks: dict | None, part: str = "all", tests: dict | None = None) -> bytes:
    """g: the player's grid (personal_grid); weeks: weekly_sessions.build_weeks(g, ...); tests: testing.player_test_report.
    part: annual (Annual plan + Test results) | weeks (Week plans) | all."""
    pl = g.get("player") or {}
    who = pl.get("name") or g.get("squad", "Squad")
    sub = f"{pl.get('role', '')} · {g.get('squad', '')} · {g.get('season', '')}".strip(" ·")
    buf = BytesIO()
    doc = _Doc(buf, title=f"Seasonal plan - {who}", who=who, sub=sub)
    a3_w = landscape(A3)[0] - 24 * mm
    port_w = A4[0] - 24 * mm
    story: list = []
    if part in ("annual", "all"):
        _annual(g, story, a3_w)
        if tests is not None:
            story += [NextPageTemplate("port"), PageBreak()]
            _tests(tests, story, port_w)
    if part in ("weeks", "all") and weeks:
        if story:
            story += [NextPageTemplate("port"), PageBreak()]
        else:
            doc.pageTemplates.insert(0, doc.pageTemplates.pop(1))      # start in portrait
        _weeks(g, weeks, story, port_w)
    doc.build(story)
    return buf.getvalue()


def _who(g: dict) -> tuple[str, str]:
    pl = g.get("player") or {}
    return pl.get("name") or g.get("squad", "Squad"), f"{pl.get('role', '')} · {g.get('squad', '')} · {g.get('season', '')}".strip(" ·")


def build_players_annual_pdf(players: list[tuple[dict, dict | None]]) -> bytes:
    """Every player's Annual plan (the Excel sheet) followed by their test results, one player after another.
    players: [(personal grid, testing.player_test_report)]."""
    buf = BytesIO()
    who0, sub0 = _who(players[0][0]) if players else ("Squad", "")
    doc = _Doc(buf, title="Annual plans - all players", who=who0, sub=sub0)
    a3_w, port_w = landscape(A3)[0] - 24 * mm, A4[0] - 24 * mm
    story: list = []
    for i, (g, tests) in enumerate(players):
        who, sub = _who(g)
        if i:
            story += [NextPageTemplate("a3"), PageBreak()]
        story.append(_Section("Annual plan", who, sub))
        _annual(g, story, a3_w)
        if tests is not None:
            story += [NextPageTemplate("port"), PageBreak(), _Section("Test results", who, sub)]
            _tests(tests, story, port_w)
    if not story:
        story.append(Paragraph("No players.", S_BASE))
    doc.build(story)
    return buf.getvalue()
