"""The squad test results summary as an editable Word document (.docx): the same content as the PDF
(exports/test_summary_content.py), laid out with Word tables so coaches can edit, add notes and reuse it.

Ranked charts are drawn with shaded table cells (a bar per player), so they stay sharp and editable in Word."""
from __future__ import annotations

from datetime import date
from io import BytesIO

from docx import Document
from docx.enum.section import WD_ORIENT, WD_SECTION
from docx.enum.table import WD_ROW_HEIGHT_RULE, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from app.core.paths import BRAND_DIR
from app.exports.test_summary_content import (AGE_BAR, AGE_FILL, AGE_TXT, BAND_BAR, BAND_FILL, COPIED_BAR, f1, mean, short, show, sr,
                                              sr_colour, summary_content)

NAVY, GOLD, INK, MUTE, LINE, PALE, ZEBRA = "0D2B6E", "E3B23C", "0F1E2E", "55657A", "C9D5E3", "EEF3F9", "F6F8FB"
LOGO = BRAND_DIR / "logo.png"
BAR_SLOTS = 30                                           # bar resolution: one bar is up to 30 table cells long


# ───────────── low-level helpers ─────────────
def _rgb(hexs: str) -> RGBColor:
    return RGBColor.from_string(hexs.lstrip("#").upper())


def _shade(cell, hexs: str) -> None:
    tcPr = cell._tc.get_or_add_tcPr()
    for old in tcPr.findall(qn("w:shd")):
        tcPr.remove(old)
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hexs.lstrip("#").upper())
    tcPr.append(shd)


def _cell_margins(table, top=40, bottom=40, left=70, right=70) -> None:
    tblPr = table._tbl.tblPr
    mar = OxmlElement("w:tblCellMar")
    for side, v in (("top", top), ("bottom", bottom), ("left", left), ("right", right)):
        e = OxmlElement(f"w:{side}")
        e.set(qn("w:w"), str(v))
        e.set(qn("w:type"), "dxa")
        mar.append(e)
    tblPr.append(mar)


def _borders(table, color: str = LINE, inside_v: bool = False, size: int = 4) -> None:
    tblPr = table._tbl.tblPr
    b = OxmlElement("w:tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        e = OxmlElement(f"w:{side}")
        none = side in ("left", "right") or (side == "insideV" and not inside_v)
        e.set(qn("w:val"), "nil" if none else "single")
        if not none:
            e.set(qn("w:sz"), str(size))
            e.set(qn("w:color"), color)
        b.append(e)
    tblPr.append(b)


def _no_borders(table) -> None:
    tblPr = table._tbl.tblPr
    b = OxmlElement("w:tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        e = OxmlElement(f"w:{side}")
        e.set(qn("w:val"), "nil")
        b.append(e)
    tblPr.append(b)


def _fixed(table, widths_cm: list[float]) -> None:
    """Fixed layout with these column widths (Word and LibreOffice both honour it)."""
    table.autofit = False
    tblPr = table._tbl.tblPr
    lay = OxmlElement("w:tblLayout")
    lay.set(qn("w:type"), "fixed")
    tblPr.append(lay)
    grid = table._tbl.tblGrid
    for i, gc in enumerate(grid.findall(qn("w:gridCol"))):
        gc.set(qn("w:w"), str(int(widths_cm[i] * 567)))
    for row in table.rows:
        for i, cell in enumerate(row.cells):
            cell.width = Cm(widths_cm[i])


def _repeat_header(row) -> None:
    trPr = row._tr.get_or_add_trPr()
    e = OxmlElement("w:tblHeader")
    e.set(qn("w:val"), "true")
    trPr.append(e)


def _text(cell, text, *, bold=False, size=8.0, color=INK, align=None, italic=False) -> None:
    cell.text = ""
    p = cell.paragraphs[0]
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.space_before = Pt(0)
    if align == "c":
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    elif align == "r":
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = p.add_run("" if text is None else str(text))
    run.bold, run.italic = bold, italic
    run.font.size = Pt(size)
    run.font.color.rgb = _rgb(color)


def _para(doc_or_cell, text="", *, size=9.0, bold=False, color=INK, italic=False, after=4, align=None):
    p = doc_or_cell.add_paragraph()
    p.paragraph_format.space_after = Pt(after)
    p.paragraph_format.space_before = Pt(0)
    if align == "c":
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if text:
        r = p.add_run(text)
        r.bold, r.italic = bold, italic
        r.font.size = Pt(size)
        r.font.color.rgb = _rgb(color)
    return p


def _heading(doc, text: str, lead: str | None = None) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.keep_with_next = True
    r = p.add_run(text)
    r.bold = True
    r.font.size = Pt(13)
    r.font.color.rgb = _rgb(NAVY)
    pPr = p._p.get_or_add_pPr()                                # gold rule under the heading
    bdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    for k, v in (("val", "single"), ("sz", "8"), ("space", "2"), ("color", GOLD)):
        bottom.set(qn(f"w:{k}"), v)
    bdr.append(bottom)
    pPr.append(bdr)
    if lead:
        q = _para(doc, lead, size=8.5, color=MUTE, after=5)
        q.paragraph_format.keep_with_next = True


def _bullet(doc, lead: str, rest: str) -> None:
    p = doc.add_paragraph(style="List Bullet")
    p.paragraph_format.space_after = Pt(2.5)
    r = p.add_run(lead)
    r.bold = True
    r.font.size = Pt(9)
    r2 = p.add_run(rest.replace("..", "."))
    r2.font.size = Pt(9)


def _grid(doc, head: list[str], rows: list[list], widths_cm: list[float], *, center_from: int = 1, size: float = 8.0,
          fills: dict | None = None, bold_first: bool = True, zebra: bool = True, left: tuple = ()):
    """A report table: navy header (repeats on every page), light rules, zebra rows; fills = {(row, col): hex}."""
    t = doc.add_table(rows=1 + len(rows), cols=len(head))
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    _fixed(t, widths_cm)
    _borders(t)
    _cell_margins(t)
    _repeat_header(t.rows[0])
    for j, h in enumerate(head):
        cell = t.rows[0].cells[j]
        _shade(cell, NAVY)
        _text(cell, h, bold=True, size=size - 0.5, color="FFFFFF", align="c" if j >= center_from and j not in left else None)
    for i, row in enumerate(rows, 1):
        for j, v in enumerate(row):
            cell = t.rows[i].cells[j]
            _text(cell, v, bold=bold_first and j == 0, size=size, align="c" if j >= center_from and j not in left else None)
            fill = (fills or {}).get((i, j))
            if fill:
                _shade(cell, fill)
            elif zebra and i % 2 == 0:
                _shade(cell, ZEBRA)
    return t


def _bars(doc, rows: list[tuple[str, float, str, str]], width_cm: float, *, base: float = 0.0, caption: str | None = None,
          name_cm: float = 3.2, value_cm: float = 1.8) -> None:
    """A ranked bar chart made of table cells: (label, value, shown text, colour) per row."""
    if caption:
        _para(doc, caption, size=7.5, color=MUTE, after=2).paragraph_format.keep_with_next = True     # title, caption and bars together
    top = max(v for _, v, _, _ in rows)
    span = (top - base) or 1
    slot = (width_cm - name_cm - value_cm) / BAR_SLOTS
    t = doc.add_table(rows=len(rows), cols=BAR_SLOTS + 2)
    _fixed(t, [name_cm] + [slot] * BAR_SLOTS + [value_cm])
    _no_borders(t)
    _cell_margins(t, top=0, bottom=0, left=40, right=40)
    spacing = OxmlElement("w:tblCellSpacing")                # a thin white gap between the bars
    spacing.set(qn("w:w"), "14")
    spacing.set(qn("w:type"), "dxa")
    t._tbl.tblPr.append(spacing)
    for i, (label, v, txt, col) in enumerate(rows):
        t.rows[i].height = Cm(0.36)
        t.rows[i].height_rule = WD_ROW_HEIGHT_RULE.EXACTLY
        cells = t.rows[i].cells
        _text(cells[0], label, size=7, align="r")
        k = max(1, min(BAR_SLOTS, round(max(0.0, v - base) / span * BAR_SLOTS)))
        bar = cells[1].merge(cells[k]) if k > 1 else cells[1]
        _shade(bar, col)
        _text(bar, "", size=5)
        if k < BAR_SLOTS:
            rest = cells[k + 1].merge(cells[BAR_SLOTS]) if k + 1 < BAR_SLOTS else cells[k + 1]
            _text(rest, "", size=5)
        _text(cells[BAR_SLOTS + 1], txt, bold=True, size=7)
        if i < len(rows) - 1:                                     # keep the whole chart on one page
            cells[0].paragraphs[0].paragraph_format.keep_with_next = True
    _para(doc, "", after=3)


def _legend(doc, items: list[tuple[str, str]]) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(4)
    for label, col in items:
        r = p.add_run("■ ")
        r.font.size = Pt(10)
        r.font.color.rgb = _rgb(col)
        r2 = p.add_run(label + "     ")
        r2.font.size = Pt(7.5)
        r2.font.color.rgb = _rgb(INK)


def _page_field(paragraph) -> None:
    run = paragraph.add_run()
    for kind, text in (("begin", None), (None, "PAGE"), ("end", None)):
        if kind:
            e = OxmlElement("w:fldChar")
            e.set(qn("w:fldCharType"), kind)
        else:
            e = OxmlElement("w:instrText")
            e.set(qn("xml:space"), "preserve")
            e.text = text
        run._r.append(e)
    run.font.size = Pt(7.5)


def _header_footer(section, who: str, sub: str, width_cm: float) -> None:
    """Navy band with the logo in the page header; squad, season and the page number in the footer."""
    section.header_distance = Cm(0.6)
    section.footer_distance = Cm(0.6)
    hdr = section.header
    hdr.is_linked_to_previous = False
    for p in hdr.paragraphs:
        p.text = ""
    t = hdr.add_table(rows=1, cols=2, width=Cm(width_cm))
    _fixed(t, [2.0, width_cm - 2.0])
    _no_borders(t)
    for cell in t.rows[0].cells:
        _shade(cell, NAVY)
    if LOGO.is_file():
        lp = t.rows[0].cells[0].paragraphs[0]
        lp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        lp.add_run().add_picture(str(LOGO), height=Cm(1.5))
    c = t.rows[0].cells[1]
    _text(c, "SRI LANKA CRICKET  ·  STRENGTH AND CONDITIONING", bold=True, size=7.5, color=GOLD)
    p = c.add_paragraph()
    r = p.add_run(f"Test results summary  ·  {who}")
    r.bold = True
    r.font.size = Pt(13)
    r.font.color.rgb = _rgb("FFFFFF")
    p2 = c.add_paragraph()
    r2 = p2.add_run(sub)
    r2.font.size = Pt(8)
    r2.font.color.rgb = _rgb("DBE6FB")
    ftr = section.footer
    ftr.is_linked_to_previous = False
    fp = ftr.paragraphs[0]
    fp.text = ""
    fr = fp.add_run(f"{who}  ·  {sub}  ·  Page ")
    fr.font.size = Pt(7.5)
    fr.font.color.rgb = _rgb(MUTE)
    _page_field(fp)


def _new_section(doc, landscape: bool, who: str, sub: str) -> float:
    s = doc.add_section(WD_SECTION.NEW_PAGE)
    s.orientation = WD_ORIENT.LANDSCAPE if landscape else WD_ORIENT.PORTRAIT
    w, h = (Cm(29.7), Cm(21.0)) if landscape else (Cm(21.0), Cm(29.7))
    s.page_width, s.page_height = w, h
    width = (29.7 if landscape else 21.0) - 3.6
    _header_footer(s, who, sub, width)
    return width


# ───────────── the document ─────────────
def build_test_summary_docx(d: dict, cats: dict, *, band_names=None, next_label: str | None = None, prepared: date | None = None) -> bytes:
    """d: squad_test_results(...) for one window; cats: {player_id: categorisation} for the same window."""
    c = summary_content(d, cats, band_names=band_names, next_label=next_label, prepared=prepared)
    ag, tested, used, who, sub = c["ag"], c["tested"], c["used"], d["squad"], c["sub"]
    doc = Document()
    doc.core_properties.title = c["title"]
    doc.core_properties.author = "Sri Lanka Cricket"
    st = doc.styles["Normal"]
    st.font.name = "Calibri"
    st.font.size = Pt(9)
    s0 = doc.sections[0]
    s0.page_width, s0.page_height = Cm(21.0), Cm(29.7)
    for s in (s0,):
        s.left_margin = s.right_margin = Cm(1.8)
        s.top_margin, s.bottom_margin = Cm(3.4), Cm(1.6)
    W = 21.0 - 3.6
    _header_footer(s0, who, sub, W)

    # ── title ──
    _para(doc, "Physical Test Results Summary", size=22, bold=True, color=NAVY, after=2)
    _para(doc, c["meta"], size=9, color=MUTE, after=8)
    if not tested:
        _para(doc, c["empty"], size=9.5)
        buf = BytesIO()
        doc.save(buf)
        return buf.getvalue()
    vs, srs, sr_avg, sf_avg = c["vs"], c["srs"], c["sr_avg"], c["sf_avg"]

    # ── key numbers ──
    kt = doc.add_table(rows=1, cols=len(c["tiles"]))
    _fixed(kt, [W / len(c["tiles"])] * len(c["tiles"]))
    _no_borders(kt)
    _cell_margins(kt, top=90, bottom=90)
    for cell, (label, value, subtext) in zip(kt.rows[0].cells, c["tiles"]):
        _shade(cell, PALE)
        _text(cell, value, bold=True, size=17, color=NAVY, align="c")
        _para(cell, label, size=7.5, bold=True, after=0, align="c")
        _para(cell, subtext, size=7, color=MUTE, after=0, align="c")
    _para(doc, "", after=4)

    # ── key findings ──
    _heading(doc, "Key findings")
    for lead, rest in c["findings"]:
        _bullet(doc, lead, rest)

    # ── squad against the reference ──
    _heading(doc, f"Squad against the {ag} reference", f"Share of tested players at or above the {ag} expected value, test by test.")
    rows, fills = [], {}
    for i, v in enumerate(vs, 1):
        t, ref, best = v["t"], v["t"]["reference"], v["best"]
        rows.append([t["label"], t["unit"], show(t["key"], v["avg"]), ref["expected_display"] if ref else "-", ref["strong_display"] if ref else "-",
                     f"{best['results'][t['key']]}  {short(best['name'])}" if best else "-",
                     "-" if v["pct"] is None else f"{v['pct']}%  ({len(v['ok'])}/{len(v['have'])})"])
        if v["pct"] is not None:
            fills[(i, 6)] = AGE_FILL["strong"] if v["pct"] >= 60 else AGE_FILL["developing"] if v["pct"] >= 40 else AGE_FILL["below"]
    _grid(doc, ["Test", "Unit", "Squad avg", f"{ag} expected", "Strong", "Best (player)", "At or above expected"], rows,
          [3.2, 1.6, 1.8, 2.0, 1.6, 4.0, 3.2], fills=fills)

    # ── bands ──
    counts, band_names = c["band_counts"], c["band_names"]
    if any(counts):
        _heading(doc, "Squad bands", "Each player's band from the full test set, inside their own level group (Band 5 = best). "
                                     "Bands compare players with each other, not with the age-group reference.")
        _grid(doc, [f"Band {i + 1} · {band_names[i]}" for i in range(5)], [[str(n) for n in counts]], [W / 5] * 5, center_from=0,
              size=9, fills={(1, i): BAND_FILL[i] for i in range(5)}, bold_first=False)

    # ── results by test ──
    doc.add_page_break()
    _heading(doc, "Results by test", f"Players ranked from best to weakest. Bar colour = result against the {ag} reference. "
                                     "Bars start near the lowest value so differences show.")
    _legend(doc, [(AGE_TXT[k], AGE_BAR[k]) for k in AGE_TXT])
    for v in vs:
        t, k, rs = v["t"], v["t"]["key"], v["ranked"]
        if not rs:
            continue
        allv = [r["values"][k] for r in rs] + [v["avg"]] + ([t["reference"]["expected"]] if t["reference"] else [])
        base = max(0.0, min(allv) * 0.85)
        p = _para(doc, t["label"], size=10.5, bold=True, color=NAVY, after=0)
        p.paragraph_format.keep_with_next = True
        cap = (f"{t['unit']} · {'higher' if t['higher_is_better'] else 'lower'} is better · squad average {show(k, v['avg'])}"
               + (f" · {ag} expected {t['reference']['expected_display']}" if t["reference"] else "")
               + ("" if v["pct"] is None else f" · {v['pct']}% at or above expected"))
        _bars(doc, [(short(r["name"]), r["values"][k], r["results"][k], AGE_BAR.get(r["age"].get(k), "#7fa7d9")) for r in rs], W * 0.8,
              base=base, caption=cap)

    # ── flexibility and body composition ──
    doc.add_page_break()
    _heading(doc, "Flexibility · sit and reach", "cm from the toes: + past them, - short of them. Recorded, not ranked: a player short of "
                                                 "the toes gets a daily 10-minute flexibility block in their plan.")
    if srs:
        _legend(doc, [("10 cm or more past the toes", "#3c8d40"), ("Reaches the toes", "#2f6db5"), ("Short of the toes", "#e0a526"),
                      ("* Copied, not measured", COPIED_BAR)])
        rs = sorted(srs, key=lambda r: -r["sit_reach"])
        base = float(int(min(0.0, *[r["sit_reach"] for r in rs])) - 3)
        _bars(doc, [(short(r["name"]) + (" *" if r.get("sit_reach_copied") else ""), r["sit_reach"], f"{sr(r['sit_reach'])} cm", sr_colour(r))
                    for r in rs], W * 0.8, base=base, caption=f"Squad average {sr(sr_avg)} cm · the toes are at 0")
        _grid(doc, ["Squad flexibility", "Players"],
              [["10 cm or more past the toes", str(len(c["sr_strong"]))],
               ["Reach the toes (0 to 10 cm)", str(len(srs) - len(c["sr_strong"]) - len(c["sr_short"]))],
               ["Short of the toes (focus)", str(len(c["sr_short"]))], ["Squad average", f"{sr(sr_avg)} cm"]], [6.0, 2.4])
        if c["sr_short"]:
            _para(doc, "Flexibility focus: " + ", ".join(f"{short(r['name'])} ({sr(r['sit_reach'])})"
                                                         for r in sorted(c["sr_short"], key=lambda r: r["sit_reach"])), size=8.5, after=2)
        if c["sr_copied"]:
            _para(doc, "* Copied, not measured (the comparison player's result, chosen by the coach): "
                  + ", ".join(short(n) for n in c["sr_copied"]).rstrip(".") + ".", size=8.5, color="A85D00", after=2)
        if c["sr_missing"]:
            _para(doc, "Not tested: " + ", ".join(short(n) for n in c["sr_missing"]) + ".", size=8.5, after=2)
    else:
        _para(doc, "No sit-and-reach results in this window yet.")

    _heading(doc, "Body composition", "Height, weight and the sum of 8 ISAK skinfolds (mm, lower = leaner). For growing players track each "
                                      "player's own trend rather than comparing players; BMI is a rough guide only.")
    stat_rows = []
    for label, key, unit in (("Height", "height_cm", "cm"), ("Weight", "weight_kg", "kg"), ("BMI", "bmi", ""), ("Sum of 8 skinfolds", "skinfold_sum", "mm")):
        xs = [r[key] for r in tested if r.get(key) is not None]
        stat_rows.append([label, str(len(xs))] + [f"{f1(v)} {unit}".strip() if xs else "-"
                                                  for v in ((mean(xs), min(xs), max(xs), max(xs) - min(xs)) if xs else (None,) * 4)])
    _grid(doc, ["Measure", "Players", "Average", "Lowest", "Highest", "Range"], stat_rows, [4.2, 2.0, 2.8, 2.8, 2.8, 2.8])
    if c["skinfolds"]:
        p = _para(doc, "Sum of 8 skinfolds by player", size=10.5, bold=True, color=NAVY, after=0)
        p.paragraph_format.space_before = Pt(8)
        p.paragraph_format.keep_with_next = True
        _bars(doc, [(short(r["name"]) + (" *" if r["copied"] else ""), r["skinfold_sum"], f1(r["skinfold_sum"]),
                     COPIED_BAR if r["copied"] else "#5b7fb8") for r in c["skinfolds"]], W * 0.8,
              caption=f"mm · lower = leaner · squad average {f1(sf_avg)} mm")
        if any(r["copied"] for r in c["skinfolds"]):
            _para(doc, "* Grey bars: one or more sites copied from a comparison player, not measured. Measure these players at the next test.",
                  size=8, color="A85D00")

    # ── player overview, full results and past tests (landscape) ──
    WL = _new_section(doc, True, who, sub)
    _heading(doc, "Player overview", f"Every player's standing: SLC benchmark points and band (within the level group), how many results are "
                                     f"at or above the {ag} expected value, flexibility and the plan's focus areas. Sorted by points.")
    rows, fills = [], {}
    for i, o in enumerate(c["overview"], 1):
        rows.append([o["rank"], o["name"], o["role"], o["level"], o["points"], o["band_text"], o["good"], o["weak"], o["sit_reach"], o["focus"]])
        if o["band"]:
            fills[(i, 5)] = BAND_FILL[o["band"] - 1]
        if o["sit_reach_fill"]:
            fills[(i, 8)] = o["sit_reach_fill"]
    t = _grid(doc, ["#", "Player", "Role", "Level", "Points", "Band", "Strong / on track", "Developing / below", "Sit and reach", "Focus areas"],
              rows, [0.9, 4.6, 2.6, 2.6, 1.6, 2.6, 1.9, 1.9, 2.1, 5.3], fills=fills, bold_first=False, size=7.5, left=(1, 9))
    for row in t.rows[1:]:
        for run in row.cells[1].paragraphs[0].runs:
            run.bold = True

    doc.add_page_break()
    _heading(doc, "Full results", f"Best of 3 trials; times in mm.ss. Cell colour = result against the {ag} reference. A + or - after a value: "
                                  "better or worse than the player's previous test. * = not measured: copied from the comparison player.")
    head = ["Player", "Ht cm", "Wt kg"] + [f"{t['label']} ({t['unit']})" for t in used] + ["S&R cm", "SF sum mm"]
    rows, fills = [], {}
    for i, r in enumerate(c["matrix"], 1):
        row = [r["name"], f1(r["height_cm"]), f1(r["weight_kg"])]
        for j, t in enumerate(used):
            k = t["key"]
            ch = (r.get("change") or {}).get("tests", {}).get(k)
            arrow = "" if not ch or ch.get("state") == "same" else " +" if ch.get("state") == "improved" else " -"
            row.append((r["results"].get(k) or "-") + arrow)
            if r["age"].get(k):
                fills[(i, 3 + j)] = AGE_FILL[r["age"][k]]
        row += [sr(r["sit_reach"]) + (" *" if r.get("sit_reach_copied") else ""), f1(r["skinfold_sum"]) + (" *" if r["copied"] else "")]
        rows.append(row)
    n = len(rows)
    rows.append(["Squad average", f1(mean([r["height_cm"] for r in tested])), f1(mean([r["weight_kg"] for r in tested]))]
                + [show(v["t"]["key"], v["avg"]) for v in vs] + [sr(sr_avg), f1(sf_avg)])
    rows.append([f"{ag} expected", "", ""] + [t["reference"]["expected_display"] if t["reference"] else "-" for t in used] + ["0.0", ""])
    for i in (n + 1, n + 2):
        for j in range(len(head)):
            fills[(i, j)] = PALE
    rest = (WL - 4.4 - 1.4 * 2 - 1.6 * 2) / max(len(used), 1)
    _grid(doc, head, rows, [4.4, 1.4, 1.4] + [rest] * len(used) + [1.6, 1.6], fills=fills, size=7, zebra=False)
    _legend(doc, [(AGE_TXT[k], AGE_BAR[k]) for k in AGE_TXT])

    if c["history"]:
        _heading(doc, "Past tests", "Squad averages of every test window on record, oldest first. The current window is highlighted.")
        head = ["Test window", "Date", "Tested"] + [t["label"] for t in used] + ["Ht cm", "Wt kg", "SF sum", "S&R cm"]
        rows, fills = [], {}
        for i, x in enumerate(c["history"], 1):
            rows.append([f"{x['window_label']} · {x['season']}", x["date"] or "-", str(x["tested"])]
                        + [(x["means"].get(t["key"]) or {}).get("display") or "-" for t in used]
                        + [f1(x["height_cm"]), f1(x["weight_kg"]), f1(x["skinfold_sum"]), sr(x["sit_reach"])])
            if x["current"]:
                for j in range(len(head)):
                    fills[(i, j)] = "FFF6DC"
        rest = (WL - 5.0 - 2.0 - 1.4 - 1.4 * 4) / max(len(used), 1)
        _grid(doc, head, rows, [5.0, 2.0, 1.4] + [rest] * len(used) + [1.4] * 4, fills=fills, size=7, zebra=False)

    # ── priorities and next steps (portrait) ──
    _new_section(doc, False, who, sub)
    _heading(doc, "Squad priorities", f"Tests where fewer than half of the tested players reach the {ag} expected value, weakest first, with "
                                      "the training emphasis for the squad plan and the players who need it most.")
    if c["priorities"]:
        _grid(doc, ["Priority", "At or above expected", "Training emphasis", "Players below or developing"],
              [[f"{i}. {x['label']}", x["share"], x["work"], x["players"]] for i, x in enumerate(c["priorities"], 1)],
              [3.2, 2.6, 6.0, 5.6], center_from=1, size=7.5, left=(2, 3))
    else:
        _para(doc, f"No squad-wide gap: at least half of the tested players reach the {ag} expected value in every test. "
                   "Keep the current plan and work on each player's own focus areas.")
    if c["flex_note"]:
        _para(doc, c["flex_note"], size=9, after=4).paragraph_format.space_before = Pt(4)
    if c["attention"]:
        _heading(doc, "Players to watch", f"Two or more results below the {ag} reference: give these players extra support and check growth, "
                                          "illness or injury before adding load.")
        _grid(doc, ["Player", "Below the reference in", "Plan focus"], [[x["name"], x["below"], x["focus"]] for x in c["attention"]],
              [4.6, 7.4, 5.4], center_from=9, size=7.5)
    _heading(doc, "Next steps")
    for lead, rest in c["steps"]:
        _bullet(doc, lead, rest)
    _heading(doc, "Method and notes")
    for note in c["notes"]:
        p = doc.add_paragraph(style="List Bullet")
        p.paragraph_format.space_after = Pt(2)
        r = p.add_run(note)
        r.font.size = Pt(8.5)
    _para(doc, "Coach's notes:", size=9, bold=True, color=NAVY, after=2).paragraph_format.space_before = Pt(10)
    for _ in range(4):
        _para(doc, "_" * 95, size=9, color=LINE, after=6)
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()
