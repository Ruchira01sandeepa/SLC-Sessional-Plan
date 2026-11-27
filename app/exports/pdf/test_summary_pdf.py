"""The Fitness page's overall test results summary as a PDF: a professional squad document for coaches and S&C staff.

Executive summary (key numbers, key findings, squad against the age-group reference, bands), one ranked chart per test,
flexibility (sit and reach) and body composition, a player overview, the full results matrix, past tests, squad priorities
and the method. Built from the same data as the Fitness page (squad_test_results + the window's categorisation); nothing is
recalculated except averages and counts."""
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

from app.exports.pdf.player_plan_pdf import AGE_FILL, GOLD, INK, LINE, MUTE, NAVY, PALE, S_BASE, S_CELL, S_CELLB, S_H2, S_SMALL, _Doc, _Section, _ascii, _esc
from app.assessment.test_battery import AREA_LABEL, BY_KEY, display
from app.core.clock import today_lk

AGE_BAR = {"strong": "#3c8d40", "on_track": "#2f6db5", "developing": "#e0a526", "below": "#c94a4a"}
AGE_TXT = {"strong": "Strong for age", "on_track": "On track", "developing": "Developing", "below": "Below reference"}
BAND_BAR = ["#c94a4a", "#e0a526", "#7fa7d9", "#2f6db5", "#3c8d40"]
BAND_FILL = ["#f8dcdc", "#fff0cc", "#e8f0fa", "#dcebfa", "#cfe9cc"]
SR_BAR = {"strong": "#3c8d40", "ok": "#2f6db5", "short": "#e0a526"}
AREA_WORK = {
    "endurance": "aerobic intervals twice a week (e.g. 4-6 x 3 min hard, 2 min easy) plus one longer steady run",
    "power": "jumps, bounds and medicine-ball throws 2-3 times a week: low volume, full recovery, best quality",
    "upper_strength": "push-up and inverted-row progressions three times a week (tempo, then volume, then load)",
    "speed": "short sprints of 10-20 m with full recovery twice a week, plus acceleration technique",
    "agility": "change-of-direction and reaction drills twice a week, with deceleration technique first",
    "core": "plank, side-plank and anti-rotation circuits 3-4 times a week, adding time before difficulty",
}

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


def _mean(vals):
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


def _f1(v) -> str:
    return "-" if v is None else f"{v:.1f}"


def _sr(v) -> str:
    return "-" if v is None else f"{v:+.1f}"


def _show(key: str, v) -> str:
    t = BY_KEY[key]
    return "-" if v is None else display(t, round(v) if t.kind != "decimal" else v)


def _short(name: str) -> str:
    p = name.split()
    return f"{p[0]} {p[-1][0]}." if len(p) > 1 else name


def _better(key: str, a: float, b: float) -> bool:
    return a > b if BY_KEY[key].higher_is_better else a < b


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
    prepared = prepared or today_lk()
    ag = d.get("ref_label") or d["age_group"]
    band_names = list(band_names or ["Band 1", "Band 2", "Band 3", "Band 4", "Band 5"])
    tests = {t["key"]: t for t in d["tests"]}
    tested = [r for r in d["players"] if r["level"]]
    used = [t for t in d["tests"] if any(r["values"].get(t["key"]) is not None for r in tested)]
    dates = sorted({r["test_date"] for r in tested if r["test_date"]})
    levels = sorted({r["level_label"] for r in tested if r["level_label"]})
    when = ("Not tested yet" if not dates else f"Tested {date.fromisoformat(str(dates[0])):%d %b %Y}" if len(dates) == 1 else
            f"Tested {date.fromisoformat(str(dates[0])):%d %b %Y} to {date.fromisoformat(str(dates[-1])):%d %b %Y}")
    sub = f"{d['season']['name']}  ·  {d['window_label']}  ·  {when}"
    buf = BytesIO()
    doc = _SummaryDoc(buf, title=f"Test results summary - {d['squad']} - {d['season']['name']} - {d['window_label']}", who=d["squad"], sub=sub)
    W = doc.pageTemplates[0].frames[0]._width
    WL = doc.pageTemplates[1].frames[0]._width
    story: list = [_Section("Test results summary")]

    # ── title ──
    story += [Paragraph("Physical Test Results Summary", S_TITLE), Spacer(0, 1 * mm),
              _p(f"{d['squad']}  ·  {ag}  ·  {d['season']['name']}  ·  {d['window_label']}  ·  {when}"
                 + (f"  ·  {', '.join(levels)}" if levels else "") + f"  ·  Prepared {prepared:%d %b %Y}", S_LEAD), Spacer(0, 4 * mm)]
    if not tested:
        story += [_p(f"No {d['window_label'].lower()} results have been recorded for this squad yet. Import the test template on the "
                     "Tests page or enter results on the Fitness page, then download this summary again.", S_BODY)]
        doc.build(story)
        return buf.getvalue()

    # ── squad against the reference (used by the KPIs, findings and priorities) ──
    vs = []
    for t in used:
        k = t["key"]
        have = [r for r in tested if r["age"].get(k)]
        ok = [r for r in have if r["age"][k] in ("on_track", "strong")]
        vals = [r["values"][k] for r in tested if r["values"].get(k) is not None]
        best = sorted((r for r in tested if r["values"].get(k) is not None), key=lambda r: r["values"][k], reverse=t["higher_is_better"])
        vs.append({"t": t, "have": have, "ok": ok, "pct": round(100 * len(ok) / len(have)) if have else None, "avg": _mean(vals),
                   "n": len(vals), "best": best[0] if best else None,
                   "weak": [r for r in have if r["age"][k] in ("below", "developing")]})
    age_vals = [b for r in tested for b in r["age"].values() if b]
    meets = sum(1 for b in age_vals if b in ("on_track", "strong"))
    pct_all = round(100 * meets / len(age_vals)) if age_vals else None
    pts = [(r, cats[r["player_id"]]["benchmark"]) for r in tested if cats.get(r["player_id"]) and cats[r["player_id"]].get("benchmark")]
    srs = [r for r in tested if r["sit_reach"] is not None]
    sr_avg = _mean([r["sit_reach"] for r in srs])
    sr_short = [r for r in srs if r["sit_reach"] < 0]
    sf_avg = _mean([r["skinfold_sum"] for r in tested])

    # ── key numbers ──
    tiles = [
        ("Players tested", f"{len(tested)} / {len(d['players'])}", f"{len(used)} tests · best of 3 trials"),
        (f"At or above {ag} expected", "-" if pct_all is None else f"{pct_all}%", f"{meets} of {len(age_vals)} results"),
        (f"Average {ag} points", _f1(_mean([b["total"] for _, b in pts])) if pts else "-",
         f"out of {pts[0][1]['max']} · SLC benchmark" if pts else
         "no SLC benchmark for this age group" if d.get("gender") != "female" and d["age_group"] != "U15" else "Super Provincial players only"),
        ("Sit and reach", f"{_sr(sr_avg)} cm" if sr_avg is not None else "-",
         f"{len(sr_short)} of {len(srs)} short of the toes" if srs else "not tested"),
        ("Squad body size", f"{_f1(_mean([r['height_cm'] for r in tested]))} cm",
         f"{_f1(_mean([r['weight_kg'] for r in tested]))} kg · skinfolds {_f1(sf_avg)} mm"),
    ]
    tw = W / len(tiles)
    kt = Table([[[_p(v, S_KPI_V), _p(lab, S_KPI_L), _p(s, S_KPI_S)] for lab, v, s in tiles]], colWidths=[tw] * len(tiles))
    kt.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), PALE), ("LINEABOVE", (0, 0), (-1, 0), 2, GOLD),
                            ("LINEAFTER", (0, 0), (-2, -1), 0.8, colors.white), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                            ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    story += [kt, Spacer(0, 5 * mm)]

    # ── key findings ──
    ranked = [v for v in vs if v["pct"] is not None]
    findings = []
    if ranked:
        top = max(ranked, key=lambda v: v["pct"])
        low = min(ranked, key=lambda v: v["pct"])
        findings.append(f"<b>Strongest test: {top['t']['label']}</b>. {len(top['ok'])} of {len(top['have'])} players ({top['pct']}%) are at or above "
                        f"the {ag} expected value; squad average {_show(top['t']['key'], top['avg'])} {top['t']['unit']} against "
                        f"{top['t']['reference']['expected_display']} expected.")
        if low is not top:
            findings.append(f"<b>Biggest gap: {low['t']['label']}</b>. Only {len(low['ok'])} of {len(low['have'])} players ({low['pct']}%) reach "
                            f"the {ag} expected value; squad average {_show(low['t']['key'], low['avg'])} {low['t']['unit']} against "
                            f"{low['t']['reference']['expected_display']} expected.")
    if pct_all is not None:
        findings.append(f"<b>Overall</b>: {pct_all}% of all results ({meets} of {len(age_vals)}) are at or above the {ag} expected value"
                        + (" - a solid base for the season." if pct_all >= 60 else " - room to improve before the next test." if pct_all >= 40
                           else " - physical development is a clear priority."))
    if pts:
        best3 = sorted(pts, key=lambda x: -x[1]["total"])[:3]
        findings.append("<b>Top overall</b> (SLC benchmark points): " + ", ".join(f"{_esc(r['name'])} ({b['total']})" for r, b in best3) + ".")
    ch = [c.get("state") for r in tested if r.get("change") for c in r["change"]["tests"].values()]
    if ch:
        up, down = ch.count("improved"), ch.count("worse")
        findings.append(f"<b>Since the previous test</b>: {up} results improved and {down} got worse "
                        f"({sum(1 for r in tested if r.get('change'))} players with an earlier test).")
    if srs:
        findings.append(f"<b>Flexibility</b>: {len(srs) - len(sr_short)} of {len(srs)} players reach their toes in the sit and reach "
                        f"(squad average {_sr(sr_avg)} cm)" + (f"; {len(sr_short)} are short of the toes and get a daily flexibility block." if sr_short else "."))
    gaps = [r["name"] for r in d["players"] if not r["level"]]
    if gaps:
        findings.append(f"<b>Not tested in this window</b>: {', '.join(_esc(g) for g in gaps)}.")
    story += _section("Key findings", W)
    story += [Paragraph(_ascii(f), S_BUL, bulletText="•") for f in findings]
    story.append(Spacer(0, 4 * mm))

    # ── squad against the age-group reference ──
    story += _section(f"Squad against the {ag} reference", W,
                      f"Share of tested players at or above the {ag} expected value, test by test (the line marks 50%).")
    rows = [[_p(x, S_HEAD if i == 0 else S_HEADC) for i, x in enumerate(
        ("Test", "Unit", "Squad avg", f"{ag} expected", "Strong", "Best (player)", "At or above expected", ""))]]
    for v in vs:
        t, ref = v["t"], v["t"]["reference"]
        best = v["best"]
        rows.append([_p(t["label"], S_CELLB), _p(t["unit"], S_CELLC), _p(_show(t["key"], v["avg"]), S_CELLC),
                     _p(ref["expected_display"] if ref else "-", S_CELLC), _p(ref["strong_display"] if ref else "-", S_CELLC),
                     _p(f"{best['results'][t['key']]}  {_short(best['name'])}" if best else "-", S_CELL),
                     _meter((v["pct"] or 0) / 100) if v["pct"] is not None else _p("-", S_CELLC),
                     _p("-" if v["pct"] is None else f"{v['pct']}%  ({len(v['ok'])}/{len(v['have'])})", S_CELLB)])
    story += [_grid(rows, [w * W for w in (0.17, 0.08, 0.09, 0.1, 0.08, 0.2, 0.16, 0.12)]), Spacer(0, 5 * mm)]

    # ── bands ──
    counts = [sum(1 for r in tested if (cats.get(r["player_id"]) or {}).get("band") == b) for b in range(1, 6)]
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
        t, k = v["t"], v["t"]["key"]
        rs = sorted((r for r in tested if r["values"].get(k) is not None), key=lambda r: r["values"][k], reverse=t["higher_is_better"])
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
    pairs = [charts[i:i + 2] for i in range(0, len(charts), 2)]
    for pr in pairs:
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
        col = lambda v: SR_BAR["strong"] if v >= 10 else SR_BAR["ok"] if v >= 0 else SR_BAR["short"]
        chart = _hbars([(_short(r["name"]) + (" *" if r.get("sit_reach_copied") else ""), r["sit_reach"], f"{_sr(r['sit_reach'])} cm",
                         "#9aa7b8" if r.get("sit_reach_copied") else col(r["sit_reach"])) for r in rs], W * 0.6,
                       base=base, refs=[(0.0, "toes"), (sr_avg, f"avg {_sr(sr_avg)}")], row_h=3.4 * mm)
        strong = [r for r in srs if r["sit_reach"] >= 10]
        side = [Paragraph("Squad flexibility", S_CHART_T), Spacer(0, 1.5 * mm),
                _grid([[_p("Group", S_HEAD), _p("Players", S_HEADC)],
                       [_p("10 cm or more past the toes"), _p(str(len(strong)), S_CELLC)],
                       [_p("Reach the toes (0 to 10 cm)"), _p(str(len(srs) - len(strong) - len(sr_short)), S_CELLC)],
                       [_p("Short of the toes (focus)"), _p(str(len(sr_short)), S_CELLC)],
                       [_p("Squad average", S_CELLB), _p(f"{_sr(sr_avg)} cm", S_CELLB)]], [W * 0.27, W * 0.09]),
                Spacer(0, 3 * mm)]
        if sr_short:
            side += [_p("Flexibility focus", S_CELLB), _p(", ".join(f"{_short(r['name'])} ({_sr(r['sit_reach'])})"
                                                                     for r in sorted(sr_short, key=lambda r: r["sit_reach"])), S_SMALL), Spacer(0, 2 * mm)]
        cop = [r["name"] for r in srs if r.get("sit_reach_copied")]
        if cop:
            side += [_p("* Copied, not measured", S_CELLB), _p("Grey bars: the comparison player's result, chosen by the coach: "
                                                              + ", ".join(_short(n) for n in cop).rstrip(".") + ".", S_SMALL), Spacer(0, 2 * mm)]
        miss = [r["name"] for r in d["players"] if r["sit_reach"] is None]
        if miss:
            side += [_p("Not tested", S_CELLB), _p(", ".join(_short(n) for n in miss), S_SMALL)]
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
    sf = sorted((r for r in tested if r["skinfold_sum"] is not None), key=lambda r: r["skinfold_sum"])
    if sf:
        story.append(KeepTogether([Paragraph("Sum of 8 skinfolds by player", S_CHART_T), Spacer(0, 1 * mm),
                                   _hbars([(_short(r["name"]) + (" *" if r["copied"] else ""), r["skinfold_sum"], _f1(r["skinfold_sum"]),
                                            "#9aa7b8" if r["copied"] else "#5b7fb8") for r in sf], W * 0.75,
                                          refs=[(sf_avg, f"avg {_f1(sf_avg)}")], row_h=3.1 * mm)]
                                  + ([_p("* Grey bars: one or more sites copied from a comparison player, not measured. Measure these players "
                                         "at the next test.", S_SMALL)] if any(r["copied"] for r in sf) else [])))

    # ── player overview ──
    story += [NextPageTemplate("land"), PageBreak(), _Section("Player overview")]
    story += _section("Player overview", WL, f"Every player's standing: SLC benchmark points and band (within the level group), how many results "
                      f"are at or above the {ag} expected value, flexibility and the plan's focus areas. Sorted by points.")
    order = sorted(d["players"], key=lambda r: (not r["level"], -((cats.get(r["player_id"]) or {}).get("benchmark") or {}).get("total", -1), r["name"]))
    ov = [[_p(x, S_HEAD if i in (1, 9) else S_HEADC) for i, x in enumerate(
        ("#", "Player", "Role", "Level", "Points", "Band", "Strong / on track", "Developing / below", "Sit and reach", "Focus areas"))]]
    ext = []
    for i, r in enumerate(order, 1):
        c = cats.get(r["player_id"]) or {}
        bm = c.get("benchmark")
        bands = list(r["age"].values())
        good = sum(1 for b in bands if b in ("on_track", "strong"))
        weak = sum(1 for b in bands if b in ("developing", "below"))
        foc = [f["label"] for f in c.get("focus_areas", [])]
        if r["sit_reach"] is not None and r["sit_reach"] < 0:
            foc.append("Flexibility")
        ov.append([_p(str(i) if r["level"] else "-", S_CELLC), _p(r["name"] + (" (stand-by)" if r["standby"] else ""), S_CELLB),
                   _p(r["role"].replace("_", " ").title(), S_CELLC), _p(r["level_label"] or "Not tested", S_CELLC),
                   _p(f"{bm['total']} / {bm['max']}" if bm else "-", S_CELLC),
                   _p(f"{c['band']} {c['band_label']}" if c.get("band") else "-", S_CELLC),
                   _p(str(good) if r["level"] else "-", S_CELLC), _p(str(weak) if r["level"] else "-", S_CELLC),
                   _p(f"{_sr(r['sit_reach'])} cm" if r["sit_reach"] is not None else "-", S_CELLC), _p(", ".join(foc) or "-", S_MINI)])
        if c.get("band"):
            ext.append(("BACKGROUND", (5, i), (5, i), colors.HexColor(BAND_FILL[c["band"] - 1])))
        if r["sit_reach"] is not None:
            ext.append(("BACKGROUND", (8, i), (8, i), colors.HexColor(AGE_FILL["developing"] if r["sit_reach"] < 0 else
                                                                         AGE_FILL["strong"] if r["sit_reach"] >= 10 else AGE_FILL["on_track"])))
    story += [_grid(ov, [WL * w for w in (0.03, 0.17, 0.1, 0.08, 0.06, 0.1, 0.07, 0.08, 0.08, 0.23)], ext, zebra=False), Spacer(0, 4 * mm)]

    # ── full results matrix ──
    story += [CondPageBreak(60 * mm), _Section("Full results")] + _section("Full results", WL, f"Best of 3 trials; times in mm.ss. Cell colour = result against the {ag} "
                                                 "reference. A + or - after a value: better or worse than the player's previous test. "
                                                 "* = not measured: copied from the comparison player the coach chose.")
    hdr = [_p("Player", S_HEAD), _p("Ht cm", S_HEADC), _p("Wt kg", S_HEADC)] + \
          [_p(f"{t['label']} ({t['unit']})", S_HEADC) for t in used] + [_p("S&R cm", S_HEADC), _p("SF sum mm", S_HEADC)]
    mat, ext = [hdr], []
    for r in [x for x in order if x["level"]]:
        row = [_p(r["name"], S_MINI), _p(_f1(r["height_cm"]), S_MINIC), _p(_f1(r["weight_kg"]), S_MINIC)]
        for j, t in enumerate(used):
            k = t["key"]
            val = r["results"].get(k)
            c = (r.get("change") or {}).get("tests", {}).get(k)
            arrow = "" if not c or c.get("state") == "same" else " +" if c.get("state") == "improved" else " -"
            row.append(_p((val or "-") + arrow, S_MINIC))
            if r["age"].get(k):
                ext.append(("BACKGROUND", (3 + j, len(mat)), (3 + j, len(mat)), colors.HexColor(AGE_FILL[r["age"][k]])))
        row += [_p(_sr(r["sit_reach"]) + (" *" if r.get("sit_reach_copied") else ""), S_MINIC),
                _p(_f1(r["skinfold_sum"]) + (" *" if r["copied"] else ""), S_MINIC)]
        mat.append(row)
    avg_row = [_p("Squad average", S_CELLB), _p(_f1(_mean([r["height_cm"] for r in tested])), S_MINIC),
               _p(_f1(_mean([r["weight_kg"] for r in tested])), S_MINIC)] + \
              [_p(_show(v["t"]["key"], v["avg"]), S_MINIC) for v in vs] + [_p(_sr(sr_avg), S_MINIC), _p(_f1(sf_avg), S_MINIC)]
    exp_row = [_p(f"{ag} expected", S_CELLB), _p("", S_MINIC), _p("", S_MINIC)] + \
              [_p(t["reference"]["expected_display"] if t["reference"] else "-", S_MINIC) for t in used] + [_p("0.0", S_MINIC), _p("", S_MINIC)]
    mat += [avg_row, exp_row]
    ext += [("BACKGROUND", (0, len(mat) - 2), (-1, -1), PALE), ("LINEABOVE", (0, len(mat) - 2), (-1, len(mat) - 2), 1, NAVY)]
    n = len(used)
    rest = (1 - 0.16 - 0.05 * 2 - 0.06 * 2) / max(n, 1)
    story += [_grid(mat, [WL * w for w in (0.16, 0.05, 0.05, *([rest] * n), 0.06, 0.06)], ext, zebra=False), Spacer(0, 1.5 * mm),
              _legend([(AGE_TXT[k], AGE_BAR[k]) for k in AGE_TXT] + [("+ better / - worse than previous test", "#ffffff")], WL)]

    # ── past tests ──
    hist = d.get("history") or []
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
    pri = sorted((v for v in vs if v["pct"] is not None and v["pct"] < 50), key=lambda v: v["pct"])
    if pri:
        pr = [[_p(x, S_HEAD) for x in ("Priority", "At or above expected", "Training emphasis", "Players below or developing")]]
        for i, v in enumerate(pri, 1):
            t = v["t"]
            pr.append([_p(f"{i}. {t['label']}", S_CELLB), _p(f"{v['pct']}% ({len(v['ok'])}/{len(v['have'])})", S_CELLC),
                       _p(f"{AREA_LABEL.get(BY_KEY[t['key']].area, '')}: {AREA_WORK.get(BY_KEY[t['key']].area, 'targeted work in the plan')}", S_MINI),
                       _p(", ".join(_short(r["name"]) for r in sorted(v["weak"], key=lambda r: r["values"][t["key"]],
                                                                       reverse=not t["higher_is_better"])), S_MINI)])
        story.append(_grid(pr, [W * w for w in (0.18, 0.14, 0.36, 0.32)]))
    else:
        story.append(_p(f"No squad-wide gap: at least half of the tested players reach the {ag} expected value in every test. "
                        "Keep the current plan and work on each player's own focus areas.", S_BODY))
    if sr_short:
        story += [Spacer(0, 2 * mm), _p(f"Flexibility: {len(sr_short)} players are short of the toes - daily hamstring and lower-back work "
                                        "(seated hamstring reach, band hamstring stretch, cat-camel, hip flexor stretch).", S_BODY)]
    story.append(Spacer(0, 5 * mm))

    attention = []
    for r in tested:
        below = [tests[k]["label"] for k, b in r["age"].items() if b == "below" and k in tests]
        if len(below) >= 2:
            attention.append((r, below))
    if attention:
        story += _section("Players to watch", W, f"Two or more results below the {ag} reference: give these players extra support and check "
                          "growth, illness or injury before adding load.")
        at = [[_p("Player", S_HEAD), _p("Below the reference in", S_HEAD), _p("Plan focus", S_HEAD)]]
        for r, below in sorted(attention, key=lambda x: -len(x[1])):
            at.append([_p(r["name"], S_CELLB), _p(", ".join(below), S_MINI),
                       _p(", ".join(f["label"] for f in (cats.get(r["player_id"]) or {}).get("focus_areas", [])) or "-", S_MINI)])
        story += [_grid(at, [W * w for w in (0.26, 0.44, 0.30)]), Spacer(0, 5 * mm)]

    story += _section("Next steps", W)
    steps = [f"<b>Next test</b>: {next_label or 'the next test window'} - repeat the same tests in the same order, at the same time of day, "
             "on the same surface, after the same warm-up."]
    if gaps:
        steps.append(f"<b>Test the missing players</b>: {', '.join(_esc(g) for g in gaps)}.")
    miss_sr = [r["name"] for r in tested if r["sit_reach"] is None]
    if miss_sr:
        steps.append(f"<b>Sit and reach still to record</b>: {', '.join(_esc(_short(g)) for g in miss_sr)}.")
    copied = [r["name"] for r in tested if r["copied"]]
    if copied:
        steps.append(f"<b>Measure skinfolds</b> (copied, not measured this time): {', '.join(_esc(_short(g)) for g in copied)}.")
    sr_cop = [r["name"] for r in tested if r.get("sit_reach_copied")]
    if sr_cop:
        steps.append(f"<b>Measure sit and reach</b> (copied, not measured this time): {', '.join(_esc(_short(g)) for g in sr_cop)}.")
    third = [r["name"] for r in tested if r.get("third_needed")]
    if third:
        steps.append(f"<b>Third trial needed</b> (first two trials too far apart): {', '.join(_esc(_short(g)) for g in third)}.")
    steps.append("<b>Personal plans</b>: each player's annual plan and week plans (Plans page, PDF or Excel) are built from their own "
                 "results above, with their focus areas and next-test targets.")
    story += [Paragraph(_ascii(s.replace("..", ".")), S_BUL, bulletText="•") for s in steps]
    story.append(Spacer(0, 5 * mm))

    story += _section("Method and notes", W)
    notes = [f"Tests follow the SLC {ag} SOP. Each result is the best of 3 trials (fastest time for timed tests); times are written as mm.ss.",
             f"Reference values: {ag} youth norms - published where available, otherwise SLC estimates. Developing / expected / strong "
             "thresholds are per test; 'at or above expected' counts On track and Strong for age.",
             "SLC benchmark points and bands are calculated inside each level group, so a player is compared with players at the same level.",
             "Sit and reach: cm from the toes (0 = toes; + past them, - short of them). Recorded and used for the flexibility focus, not ranked.",
             "Skinfolds: ISAK 8 sites, right side, mm; two measures per site and a third when they differ by more than 5%. Only the sum "
             "of 8 is reported: no % body-fat equation is used for growing players.",
             "This summary uses the data on the Fitness page at the time of download. Correct any result there and download again."]
    if d.get("gender") == "female":
        notes.insert(2, f"Women's and girls' squads: the {ag} references and the women's benchmark points are PROVISIONAL. Few published "
                        "female values exist for these tests (broad jump, push-ups and plank are from girls' youth data; the others are "
                        "estimated from the boys' values and the usual sex difference). Replace them with SLC's own women's data.")
    story += [Paragraph(_t(s), S_BUL, bulletText="•") for s in notes]
    doc.build(story)
    return buf.getvalue()
