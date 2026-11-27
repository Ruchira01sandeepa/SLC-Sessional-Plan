"""The Fitness page's overall test results summary as a PDF: a professional squad document for coaches and S&C staff.

Executive summary (key numbers, key findings, squad against the age-group reference, bands), one ranked chart per test,
flexibility (sit and reach) and body composition, a player overview, the full results matrix, past tests, squad priorities
and the method. What it says comes from exports/test_summary_content.py (shared with the Word version); this module only
lays it out."""
from __future__ import annotations

from datetime import date
from io import BytesIO

from reportlab.graphics.shapes import Drawing, Line, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (CondPageBreak, Frame, KeepTogether, NextPageTemplate, PageBreak, PageTemplate, Paragraph, Spacer,
                                Table, TableStyle)

from app.exports.pdf.player_plan_pdf import GOLD, INK, LINE, MUTE, NAVY, PALE, S_BASE, S_CELL, S_CELLB, S_H2, S_SMALL, _Doc, _Section, _ascii, _esc
from app.exports.test_summary_content import (AGE_BAR, AGE_FILL, AGE_TXT, BAND_BAR, BAND_FILL, COPIED_BAR, SR_BAR, f1 as _f1, mean as _mean,
                                              short as _short, show as _show, sr as _sr, sr_colour, summary_content)

S_TITLE = ParagraphStyle("title", parent=S_BASE, fontName="Helvetica-Bold", fontSize=20, leading=24, textColor=NAVY)
S_LEAD = ParagraphStyle("lead", parent=S_BASE, fontSize=9, leading=12, textColor=MUTE)
S_BODY = ParagraphStyle("body", parent=S_BASE, fontSize=8.5, leading=11.5)
S_BUL = ParagraphStyle("bul", parent=S_BODY, leftIndent=9, bulletIndent=0, spaceAfter=2.5)
S_HEAD = ParagraphStyle("head", parent=S_CELLB, textColor=colors.white, fontSize=7, leading=8.5)
S_HEADC = ParagraphStyle("headc", parent=S_HEAD, alignment=1)
S_CELLC = ParagraphStyle("cellc", parent=S_CELL, alignment=1)
S_MINI = ParagraphStyle("mini", parent=S_CELL, fontSize=6.3, leading=7.6)
S_MINIC = ParagraphStyle("minic", parent=S_MINI, alignment=1)
S_KPI_V = ParagraphStyle("kpiv", parent=S_BASE, fontName="Helvetica-Bold", fontSize=17, leading=20, textColor=NAVY, alignment=1)
S_KPI_L = ParagraphStyle("kpil", parent=S_BASE, fontName="Helvetica-Bold", fontSize=6.8, leading=8.5, textColor=INK, alignment=1)
S_KPI_S = ParagraphStyle("kpis", parent=S_BASE, fontSize=6.3, leading=7.8, textColor=MUTE, alignment=1)
S_CHART_T = ParagraphStyle("ct", parent=S_BASE, fontName="Helvetica-Bold", fontSize=9, leading=11, textColor=NAVY)


def _t(s) -> str:
    return _ascii(_esc(s)).replace("−", "-")


def _p(text, style=S_CELL) -> Paragraph:
    return Paragraph(_t(text), style)


def _lead(lead: str, rest: str, style) -> Paragraph:
    """A finding or step: bold lead, then the rest."""
    return Paragraph(f"<b>{_t(lead)}</b>{_t(rest)}".replace("..", "."), style, bulletText="•")


def _grid(data, widths, extra=(), head_rows=1, zebra=True) -> Table:
    """A report table: navy header, light rules, zebra rows."""
    t = Table(data, colWidths=widths, repeatRows=head_rows)
    st = [("BACKGROUND", (0, 0), (-1, head_rows - 1), NAVY), ("LINEBELOW", (0, 0), (-1, -1), 0.25, LINE),
          ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 2.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
          ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3), ("LINEBELOW", (0, head_rows - 1), (-1, head_rows - 1), 1.2, GOLD)]
    if zebra:
        for i in range(head_rows, len(data)):
            if (i - head_rows) % 2:
                st.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#f6f8fb")))
    t.setStyle(TableStyle(st + list(extra)))
    return t


def _h2(text: str) -> Paragraph:
    return Paragraph(_t(text), S_H2)


def _rule(width: float) -> Drawing:
    d = Drawing(width, 3)
    d.add(Rect(0, 1, 28 * mm, 1.4, fillColor=GOLD, strokeColor=None))
    d.add(Line(28 * mm, 1.7, width, 1.7, strokeColor=LINE, strokeWidth=0.4))
    return d


def _section(title: str, width: float, lead: str | None = None) -> list:
    out = [_h2(title), _rule(width), Spacer(0, 1.5 * mm)]
    if lead:
        out += [_p(lead, S_LEAD), Spacer(0, 2 * mm)]
    return out


# ───────────── charts ─────────────
def _hbars(rows: list[tuple[str, float, str, str]], width: float, *, base: float = 0.0, refs=(), label_w: float = 27 * mm,
           row_h: float = 4.3 * mm) -> Drawing:
    """Horizontal ranked bars: rows of (label, value, shown text, colour); refs of (value, label) drawn as dashed lines."""
    top_pad = 7.5 * mm if refs else 1.5 * mm
    h = len(rows) * row_h + top_pad + 1 * mm
    d = Drawing(width, h)
    bar_w = width - label_w - 15 * mm
    vals = [v for _, v, _, _ in rows] + [v for v, _ in refs]
    top = max(vals) if vals else 1
    span = (top - base) or 1

    def x(v):
        return label_w + max(0.0, (v - base) / span) * bar_w

    for i, (lab, v, txt, col) in enumerate(rows):
        y = h - top_pad - (i + 1) * row_h
        if i % 2 == 0:
            d.add(Rect(0, y, width, row_h, fillColor=colors.HexColor("#f6f8fb"), strokeColor=None))
        d.add(String(label_w - 1.5 * mm, y + row_h * 0.3, _ascii(lab), fontName="Helvetica", fontSize=6.6, fillColor=INK, textAnchor="end"))
        d.add(Rect(label_w, y + row_h * 0.18, max(0.6, x(v) - label_w), row_h * 0.64, fillColor=colors.HexColor(col), strokeColor=None))
    d.add(Line(label_w, h - top_pad, label_w, h - top_pad - len(rows) * row_h, strokeColor=MUTE, strokeWidth=0.5))
    placed: list[float] = []
    for v, lab in refs:
        xv = x(v)
        d.add(Line(xv, h - top_pad + 0.5 * mm, xv, h - top_pad - len(rows) * row_h, strokeColor=NAVY, strokeWidth=0.7, strokeDashArray=[2, 1.5]))
        if lab:
            lift = 2.8 * mm if any(abs(xv - p) < 22 * mm for p in placed) else 0       # stagger labels that would overlap
            placed.append(xv)
            d.add(String(xv, h - top_pad + 1.3 * mm + lift, _ascii(lab),
                         fontName="Helvetica-Bold", fontSize=6, fillColor=NAVY, textAnchor="middle"))
    for i, (_, v, txt, _) in enumerate(rows):            # value labels last, on a white backing, so reference lines never cross them
        y = h - top_pad - (i + 1) * row_h
        tw = len(txt) * 6.4 * 0.56
        d.add(Rect(x(v) + 0.8 * mm, y + row_h * 0.18, tw + 0.8 * mm, row_h * 0.64, fillColor=colors.white, strokeColor=None))
        d.add(String(x(v) + 1.2 * mm, y + row_h * 0.3, _ascii(txt), fontName="Helvetica-Bold", fontSize=6.4, fillColor=INK))
    return d


def _meter(frac: float, width: float = 26 * mm, height: float = 3.2 * mm) -> Drawing:
    frac = max(0.0, min(1.0, frac))
    col = "#3c8d40" if frac >= 0.6 else "#e0a526" if frac >= 0.4 else "#c94a4a"
    d = Drawing(width, height)
    d.add(Rect(0, 0, width, height, fillColor=colors.HexColor("#e7edf5"), strokeColor=None))
    d.add(Rect(0, 0, width * frac, height, fillColor=colors.HexColor(col), strokeColor=None))
    d.add(Line(width * 0.5, -0.6, width * 0.5, height + 0.6, strokeColor=MUTE, strokeWidth=0.4))
    return d


def _stack(parts: list[tuple[str, int, str]], width: float, height: float = 7 * mm) -> Drawing:
    """One stacked bar (label, count, colour) with the counts written in the segments."""
    total = sum(n for _, n, _ in parts) or 1
    d = Drawing(width, height)
    x = 0.0
    for lab, n, col in parts:
        w = width * n / total
        if w <= 0:
            continue
        d.add(Rect(x, 0, w, height, fillColor=colors.HexColor(col), strokeColor=colors.white, strokeWidth=0.8))
        if w > 6 * mm:
            d.add(String(x + w / 2, height / 2 - 2.2, str(n), fontName="Helvetica-Bold", fontSize=7.5, fillColor=colors.white, textAnchor="middle"))
        x += w
    return d


def _legend(items: list[tuple[str, str]], width: float) -> Drawing:
    d = Drawing(width, 4 * mm)
    x = 0.0
    for lab, col in items:
        d.add(Rect(x, 1.2, 2.6 * mm, 2.6 * mm, fillColor=colors.HexColor(col), strokeColor=None))
        d.add(String(x + 3.6 * mm, 2.1, _ascii(lab), fontName="Helvetica", fontSize=6.5, fillColor=INK))
        x += 3.6 * mm + len(lab) * 1.25 * mm + 4 * mm
    return d


# ───────────── document ─────────────
class _SummaryDoc(_Doc):
    def __init__(self, buf, **kw):
        super().__init__(buf, **kw)
        port, land = A4, landscape(A4)
        self.pageTemplates = []
        self.addPageTemplates([
            PageTemplate("port", [Frame(12 * mm, 14 * mm, port[0] - 24 * mm, port[1] - 44 * mm, id="p", leftPadding=0, rightPadding=0)],
                         onPageEnd=self._band, pagesize=port),
            PageTemplate("land", [Frame(12 * mm, 14 * mm, land[0] - 24 * mm, land[1] - 44 * mm, id="l", leftPadding=0, rightPadding=0)],
                         onPageEnd=self._band, pagesize=land)])


def build_test_summary_pdf(d: dict, cats: dict, *, band_names=None, next_label: str | None = None, prepared: date | None = None) -> bytes:
    """d: squad_test_results(...) for one window; cats: {player_id: categorisation} for the same window."""
    c = summary_content(d, cats, band_names=band_names, next_label=next_label, prepared=prepared)
    ag, tested, used = c["ag"], c["tested"], c["used"]
    buf = BytesIO()
    doc = _SummaryDoc(buf, title=c["title"], who=d["squad"], sub=c["sub"])
    W = doc.pageTemplates[0].frames[0]._width
    WL = doc.pageTemplates[1].frames[0]._width
    story: list = [_Section("Test results summary")]

    # ── title ──
    story += [Paragraph("Physical Test Results Summary", S_TITLE), Spacer(0, 1 * mm), _p(c["meta"], S_LEAD), Spacer(0, 4 * mm)]
    if not tested:
        story += [_p(c["empty"], S_BODY)]
        doc.build(story)
        return buf.getvalue()
    vs, srs, sr_avg, sf_avg = c["vs"], c["srs"], c["sr_avg"], c["sf_avg"]

    # ── key numbers ──
    tw = W / len(c["tiles"])
    kt = Table([[[_p(v, S_KPI_V), _p(lab, S_KPI_L), _p(s, S_KPI_S)] for lab, v, s in c["tiles"]]], colWidths=[tw] * len(c["tiles"]))
    kt.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), PALE), ("LINEABOVE", (0, 0), (-1, 0), 2, GOLD),
                            ("LINEAFTER", (0, 0), (-2, -1), 0.8, colors.white), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                            ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    story += [kt, Spacer(0, 5 * mm)]

    # ── key findings ──
    story += _section("Key findings", W)
    story += [_lead(lead, rest, S_BUL) for lead, rest in c["findings"]]
    story.append(Spacer(0, 4 * mm))

    # ── squad against the age-group reference ──
    story += _section(f"Squad against the {ag} reference", W,
                      f"Share of tested players at or above the {ag} expected value, test by test (the line marks 50%).")
    rows = [[_p(x, S_HEAD if i == 0 else S_HEADC) for i, x in enumerate(
        ("Test", "Unit", "Squad avg", f"{ag} expected", "Strong", "Best (player)", "At or above expected", ""))]]
    for v in vs:
        t, ref, best = v["t"], v["t"]["reference"], v["best"]
        rows.append([_p(t["label"], S_CELLB), _p(t["unit"], S_CELLC), _p(_show(t["key"], v["avg"]), S_CELLC),
                     _p(ref["expected_display"] if ref else "-", S_CELLC), _p(ref["strong_display"] if ref else "-", S_CELLC),
                     _p(f"{best['results'][t['key']]}  {_short(best['name'])}" if best else "-", S_CELL),
                     _meter((v["pct"] or 0) / 100) if v["pct"] is not None else _p("-", S_CELLC),
                     _p("-" if v["pct"] is None else f"{v['pct']}%  ({len(v['ok'])}/{len(v['have'])})", S_CELLB)])
    story += [_grid(rows, [w * W for w in (0.17, 0.08, 0.09, 0.1, 0.08, 0.2, 0.16, 0.12)]), Spacer(0, 5 * mm)]

    # ── bands ──
    counts, band_names = c["band_counts"], c["band_names"]
    if any(counts):
        story += _section("Squad bands", W, "Each player's band from the full test set, inside their own level group "
                          "(Band 5 = best). Bands compare players with each other, not with the age-group reference.")
        story += [_stack([(band_names[i], counts[i], BAND_BAR[i]) for i in range(5)], W),
                  Spacer(0, 1.5 * mm), _legend([(f"Band {i + 1} {band_names[i]} ({counts[i]})", BAND_BAR[i]) for i in range(5)], W)]

    # ── results by test ──
    story += [PageBreak(), _Section("Results by test")]
    story += _section("Results by test", W, "Players ranked from best to weakest. Bar colour = result against the "
                      f"{ag} reference; dashed lines = squad average and {ag} expected. Bars start near the lowest value so differences show.")
    story += [_legend([(AGE_TXT[k], AGE_BAR[k]) for k in AGE_TXT], W), Spacer(0, 2 * mm)]
    cw = (W - 6 * mm) / 2
    charts = []
    for v in vs:
        t, k, rs = v["t"], v["t"]["key"], v["ranked"]
        if not rs:
            continue
        allv = [r["values"][k] for r in rs] + [v["avg"]] + ([t["reference"]["expected"]] if t["reference"] else [])
        base = max(0.0, min(allv) * 0.85)
        base = float(int(base)) if t["kind"] != "decimal" or base > 5 else round(base, 1)
        refs = [(v["avg"], f"avg {_show(k, v['avg'])}")]
        if t["reference"]:
            refs.append((t["reference"]["expected"], f"{ag} {t['reference']['expected_display']}"))
        bars = [(_short(r["name"]), r["values"][k], r["results"][k], AGE_BAR.get(r["age"].get(k), "#7fa7d9")) for r in rs]
        best = rs[0]
        head = [Paragraph(_t(t["label"]), S_CHART_T),
                _p(f"{t['unit']} · {'higher' if t['higher_is_better'] else 'lower'} is better · best {best['name']} {best['results'][k]}"
                   + ("" if v["pct"] is None else f" · {v['pct']}% at or above expected"), S_SMALL), Spacer(0, 1 * mm)]
        charts.append(head + [_hbars(bars, cw, base=base, refs=refs)])
    for pr in [charts[i:i + 2] for i in range(0, len(charts), 2)]:
        if len(pr) == 1:
            pr.append("")
        ct = Table([pr], colWidths=[cw, cw], hAlign="LEFT")
        ct.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (0, -1), 6 * mm),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 4 * mm)]))
        story.append(ct)

    # ── flexibility and body composition ──
    story += [PageBreak(), _Section("Flexibility and body composition")]
    story += _section("Flexibility · sit and reach", W, "cm from the toes: + past them, - short of them. Recorded, not ranked: a player "
                      "short of the toes gets a daily 10-minute flexibility block in their plan.")
    if srs:
        rs = sorted(srs, key=lambda r: -r["sit_reach"])
        base = float(int(min(0.0, *[r["sit_reach"] for r in rs])) - 3)
        chart = _hbars([(_short(r["name"]) + (" *" if r.get("sit_reach_copied") else ""), r["sit_reach"], f"{_sr(r['sit_reach'])} cm",
                         sr_colour(r)) for r in rs], W * 0.6, base=base, refs=[(0.0, "toes"), (sr_avg, f"avg {_sr(sr_avg)}")], row_h=3.4 * mm)
        side = [Paragraph("Squad flexibility", S_CHART_T), Spacer(0, 1.5 * mm),
                _grid([[_p("Group", S_HEAD), _p("Players", S_HEADC)],
                       [_p("10 cm or more past the toes"), _p(str(len(c["sr_strong"])), S_CELLC)],
                       [_p("Reach the toes (0 to 10 cm)"), _p(str(len(srs) - len(c["sr_strong"]) - len(c["sr_short"])), S_CELLC)],
                       [_p("Short of the toes (focus)"), _p(str(len(c["sr_short"])), S_CELLC)],
                       [_p("Squad average", S_CELLB), _p(f"{_sr(sr_avg)} cm", S_CELLB)]], [W * 0.27, W * 0.09]),
                Spacer(0, 3 * mm)]
        if c["sr_short"]:
            side += [_p("Flexibility focus", S_CELLB), _p(", ".join(f"{_short(r['name'])} ({_sr(r['sit_reach'])})"
                                                                     for r in sorted(c["sr_short"], key=lambda r: r["sit_reach"])), S_SMALL), Spacer(0, 2 * mm)]
        if c["sr_copied"]:
            side += [_p("* Copied, not measured", S_CELLB), _p("Grey bars: the comparison player's result, chosen by the coach: "
                                                              + ", ".join(_short(n) for n in c["sr_copied"]).rstrip(".") + ".", S_SMALL), Spacer(0, 2 * mm)]
        if c["sr_missing"]:
            side += [_p("Not tested", S_CELLB), _p(", ".join(_short(n) for n in c["sr_missing"]), S_SMALL)]
        ft = Table([[chart, side]], colWidths=[W * 0.62, W * 0.38])
        ft.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        story += [_legend([("10 cm or more past the toes", SR_BAR["strong"]), ("Reaches the toes", SR_BAR["ok"]),
                           ("Short of the toes", SR_BAR["short"])], W), Spacer(0, 1.5 * mm), ft, Spacer(0, 5 * mm)]
    else:
        story += [_p("No sit-and-reach results in this window yet.", S_BODY), Spacer(0, 4 * mm)]

    story += _section("Body composition", W, "Height, weight and the sum of 8 ISAK skinfolds (mm, lower = leaner). For growing players "
                      "track each player's own trend rather than comparing players; BMI is a rough guide only.")
    stat_rows = [[_p(x, S_HEAD if i == 0 else S_HEADC) for i, x in enumerate(("Measure", "Players", "Average", "Lowest", "Highest", "Range"))]]
    for lab, key, unit in (("Height", "height_cm", "cm"), ("Weight", "weight_kg", "kg"), ("BMI", "bmi", ""), ("Sum of 8 skinfolds", "skinfold_sum", "mm")):
        xs = [r[key] for r in tested if r.get(key) is not None]
        stat_rows.append([_p(lab, S_CELLB), _p(str(len(xs)), S_CELLC)] + [_p(f"{_f1(v)} {unit}".strip() if xs else "-", S_CELLC)
                         for v in ((_mean(xs), min(xs), max(xs), max(xs) - min(xs)) if xs else (None,) * 4)])
    story += [_grid(stat_rows, [W * w for w in (0.26, 0.12, 0.155, 0.155, 0.155, 0.155)]), Spacer(0, 4 * mm)]
    sf = c["skinfolds"]
    if sf:
        story.append(KeepTogether([Paragraph("Sum of 8 skinfolds by player", S_CHART_T), Spacer(0, 1 * mm),
                                   _hbars([(_short(r["name"]) + (" *" if r["copied"] else ""), r["skinfold_sum"], _f1(r["skinfold_sum"]),
                                            COPIED_BAR if r["copied"] else "#5b7fb8") for r in sf], W * 0.75,
                                          refs=[(sf_avg, f"avg {_f1(sf_avg)}")], row_h=3.1 * mm)]
                                  + ([_p("* Grey bars: one or more sites copied from a comparison player, not measured. Measure these players "
                                         "at the next test.", S_SMALL)] if any(r["copied"] for r in sf) else [])))

    # ── player overview ──
    story += [NextPageTemplate("land"), PageBreak(), _Section("Player overview")]
    story += _section("Player overview", WL, f"Every player's standing: SLC benchmark points and band (within the level group), how many results "
                      f"are at or above the {ag} expected value, flexibility and the plan's focus areas. Sorted by points.")
    ov = [[_p(x, S_HEAD if i in (1, 9) else S_HEADC) for i, x in enumerate(
        ("#", "Player", "Role", "Level", "Points", "Band", "Strong / on track", "Developing / below", "Sit and reach", "Focus areas"))]]
    ext = []
    for i, o in enumerate(c["overview"], 1):
        ov.append([_p(o["rank"], S_CELLC), _p(o["name"], S_CELLB), _p(o["role"], S_CELLC), _p(o["level"], S_CELLC), _p(o["points"], S_CELLC),
                   _p(o["band_text"], S_CELLC), _p(o["good"], S_CELLC), _p(o["weak"], S_CELLC), _p(o["sit_reach"], S_CELLC), _p(o["focus"], S_MINI)])
        if o["band"]:
            ext.append(("BACKGROUND", (5, i), (5, i), colors.HexColor(BAND_FILL[o["band"] - 1])))
        if o["sit_reach_fill"]:
            ext.append(("BACKGROUND", (8, i), (8, i), colors.HexColor(o["sit_reach_fill"])))
    story += [_grid(ov, [WL * w for w in (0.03, 0.17, 0.1, 0.08, 0.06, 0.1, 0.07, 0.08, 0.08, 0.23)], ext, zebra=False), Spacer(0, 4 * mm)]

    # ── full results matrix ──
    story += [CondPageBreak(60 * mm), _Section("Full results")] + _section("Full results", WL, f"Best of 3 trials; times in mm.ss. Cell colour = result against the {ag} "
                                                 "reference. A + or - after a value: better or worse than the player's previous test. "
                                                 "* = not measured: copied from the comparison player the coach chose.")
    hdr = [_p("Player", S_HEAD), _p("Ht cm", S_HEADC), _p("Wt kg", S_HEADC)] + \
          [_p(f"{t['label']} ({t['unit']})", S_HEADC) for t in used] + [_p("S&R cm", S_HEADC), _p("SF sum mm", S_HEADC)]
    mat, ext = [hdr], []
    for r in c["matrix"]:
        row = [_p(r["name"], S_MINI), _p(_f1(r["height_cm"]), S_MINIC), _p(_f1(r["weight_kg"]), S_MINIC)]
        for j, t in enumerate(used):
            k = t["key"]
            ch = (r.get("change") or {}).get("tests", {}).get(k)
            arrow = "" if not ch or ch.get("state") == "same" else " +" if ch.get("state") == "improved" else " -"
            row.append(_p((r["results"].get(k) or "-") + arrow, S_MINIC))
            if r["age"].get(k):
                ext.append(("BACKGROUND", (3 + j, len(mat)), (3 + j, len(mat)), colors.HexColor(AGE_FILL[r["age"][k]])))
        row += [_p(_sr(r["sit_reach"]) + (" *" if r.get("sit_reach_copied") else ""), S_MINIC),
                _p(_f1(r["skinfold_sum"]) + (" *" if r["copied"] else ""), S_MINIC)]
        mat.append(row)
    mat += [[_p("Squad average", S_CELLB), _p(_f1(_mean([r["height_cm"] for r in tested])), S_MINIC),
             _p(_f1(_mean([r["weight_kg"] for r in tested])), S_MINIC)] + [_p(_show(v["t"]["key"], v["avg"]), S_MINIC) for v in vs]
            + [_p(_sr(sr_avg), S_MINIC), _p(_f1(sf_avg), S_MINIC)],
            [_p(f"{ag} expected", S_CELLB), _p("", S_MINIC), _p("", S_MINIC)]
            + [_p(t["reference"]["expected_display"] if t["reference"] else "-", S_MINIC) for t in used] + [_p("0.0", S_MINIC), _p("", S_MINIC)]]
    ext += [("BACKGROUND", (0, len(mat) - 2), (-1, -1), PALE), ("LINEABOVE", (0, len(mat) - 2), (-1, len(mat) - 2), 1, NAVY)]
    n = len(used)
    rest = (1 - 0.16 - 0.05 * 2 - 0.06 * 2) / max(n, 1)
    story += [_grid(mat, [WL * w for w in (0.16, 0.05, 0.05, *([rest] * n), 0.06, 0.06)], ext, zebra=False), Spacer(0, 1.5 * mm),
              _legend([(AGE_TXT[k], AGE_BAR[k]) for k in AGE_TXT] + [("+ better / - worse than previous test", "#ffffff")], WL)]

    # ── past tests ──
    hist = c["history"]
    if hist:
        story += [Spacer(0, 5 * mm), CondPageBreak((22 + 6 * len(hist)) * mm)] + _section("Past tests", WL, "Squad averages of every test window on record, "
                                                                                           "oldest first. The current window is highlighted.")
        hh = [_p("Test window", S_HEAD), _p("Date", S_HEADC), _p("Tested", S_HEADC)] + [_p(t["label"], S_HEADC) for t in used] + \
             [_p("Ht cm", S_HEADC), _p("Wt kg", S_HEADC), _p("SF sum", S_HEADC), _p("S&R cm", S_HEADC)]
        hrows, ext = [hh], []
        for x in hist:
            hrows.append([_p(f"{x['window_label']} · {x['season']}", S_MINI), _p(x["date"] or "-", S_MINIC), _p(str(x["tested"]), S_MINIC)]
                         + [_p((x["means"].get(t["key"]) or {}).get("display") or "-", S_MINIC) for t in used]
                         + [_p(_f1(x["height_cm"]), S_MINIC), _p(_f1(x["weight_kg"]), S_MINIC), _p(_f1(x["skinfold_sum"]), S_MINIC),
                            _p(_sr(x["sit_reach"]), S_MINIC)])
            if x["current"]:
                ext.append(("BACKGROUND", (0, len(hrows) - 1), (-1, len(hrows) - 1), colors.HexColor("#fff6dc")))
        rest = (1 - 0.18 - 0.07 - 0.05 - 0.05 * 4) / max(n, 1)
        story.append(_grid(hrows, [WL * w for w in (0.18, 0.07, 0.05, *([rest] * n), 0.05, 0.05, 0.05, 0.05)], ext, zebra=False))

    # ── priorities and next steps ──
    story += [NextPageTemplate("port"), PageBreak(), _Section("Priorities and next steps")]
    story += _section("Squad priorities", W, f"Tests where fewer than half of the tested players reach the {ag} expected value, weakest first, "
                      "with the training emphasis for the squad plan and the players who need it most.")
    if c["priorities"]:
        pr = [[_p(x, S_HEAD) for x in ("Priority", "At or above expected", "Training emphasis", "Players below or developing")]]
        for i, x in enumerate(c["priorities"], 1):
            pr.append([_p(f"{i}. {x['label']}", S_CELLB), _p(x["share"], S_CELLC), _p(x["work"], S_MINI), _p(x["players"], S_MINI)])
        story.append(_grid(pr, [W * w for w in (0.18, 0.14, 0.36, 0.32)]))
    else:
        story.append(_p(f"No squad-wide gap: at least half of the tested players reach the {ag} expected value in every test. "
                        "Keep the current plan and work on each player's own focus areas.", S_BODY))
    if c["flex_note"]:
        story += [Spacer(0, 2 * mm), _p(c["flex_note"], S_BODY)]
    story.append(Spacer(0, 5 * mm))

    if c["attention"]:
        story += _section("Players to watch", W, f"Two or more results below the {ag} reference: give these players extra support and check "
                          "growth, illness or injury before adding load.")
        at = [[_p("Player", S_HEAD), _p("Below the reference in", S_HEAD), _p("Plan focus", S_HEAD)]]
        for x in c["attention"]:
            at.append([_p(x["name"], S_CELLB), _p(x["below"], S_MINI), _p(x["focus"], S_MINI)])
        story += [_grid(at, [W * w for w in (0.26, 0.44, 0.30)]), Spacer(0, 5 * mm)]

    story += _section("Next steps", W)
    story += [_lead(lead, rest, S_BUL) for lead, rest in c["steps"]]
    story.append(Spacer(0, 5 * mm))
    story += _section("Method and notes", W)
    story += [Paragraph(_t(s), S_BUL, bulletText="•") for s in c["notes"]]
    doc.build(story)
    return buf.getvalue()
