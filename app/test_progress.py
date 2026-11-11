"""Progress between SOP test windows (baseline -> mid-season -> end of season). Pure module (no database, no Excel).

A player is compared with THEIR OWN earlier results, test by test, in the right direction (a faster time or more reps is better).
Bands are relative to the same-level group in each window, so a player can improve a lot and still stay in the same band. The
output says so rather than hiding it. Only tests present in both windows are compared; nothing is estimated.
"""
from __future__ import annotations

from .test_battery import BY_KEY, WINDOW_LABEL, WINDOWS, display

SAME_PCT = 0.5          # a change under 0.5% of the earlier value counts as "no clear change" (test-to-test noise)


def _change(test, first: float, last: float) -> dict:
    delta = last - first
    pct = (delta / first * 100) if first else 0.0
    better = delta < 0 if not test.higher_is_better else delta > 0
    if abs(pct) < SAME_PCT:
        state = "same"
    else:
        state = "improved" if better else "declined"
    unit = "s" if test.kind == "mmss" or test.unit == "s" else test.unit
    mag = f"{abs(delta):.0f}" if test.kind in ("mmss", "count") else f"{abs(delta):.2f}"
    if state == "same":
        text = "No clear change"
    elif test.unit in ("mm.ss", "s") and not test.higher_is_better:
        text = f"{mag} {unit} {'faster' if state == 'improved' else 'slower'}"
    else:
        text = f"{'+' if delta > 0 else '-'}{mag} {unit}"
    return {"state": state, "delta": round(delta, 2), "percent": round(pct, 1), "text": text}


def progress(windows: list[dict]) -> dict:
    """windows: [{window, level, finals: {test_key: value}, cat: categorisation result or None}] for ONE player.
    Returns the table of tests with values per window, the change from first to latest, band movement and focus-area changes."""
    order = {w: i for i, w in enumerate(WINDOWS)}
    ws = sorted(windows, key=lambda x: order[x["window"]])
    keys = [k for k in BY_KEY if any(k in w["finals"] for w in ws)]
    tests = []
    for k in keys:
        t = BY_KEY[k]
        have = [w for w in ws if w["finals"].get(k) is not None]
        row = {"key": k, "label": t.label, "unit": t.unit, "area": t.area,
               "values": {w["window"]: display(t, w["finals"].get(k)) for w in ws}, "change": None}
        if len(have) >= 2:
            row["change"] = {**_change(t, have[0]["finals"][k], have[-1]["finals"][k]),
                             "from_window": have[0]["window"], "to_window": have[-1]["window"]}
        tests.append(row)

    cols = [{"window": w["window"], "label": WINDOW_LABEL[w["window"]], "level": w["level"],
             "band": w["cat"]["band"] if w["cat"] else None, "band_label": w["cat"]["band_label"] if w["cat"] else None,
             "overall": w["cat"]["overall"] if w["cat"] else None,
             "focus_areas": [f["label"] for f in w["cat"]["focus_areas"]] if w["cat"] else []} for w in ws]
    banded = [c for c in cols if c["band"] is not None]
    movement = None
    if len(banded) >= 2:
        a, b = banded[0], banded[-1]
        d = b["band"] - a["band"]
        movement = {"from_window": a["window"], "to_window": b["window"], "from_band": a["band"], "to_band": b["band"], "delta": d,
                    "overall_delta": round(b["overall"] - a["overall"], 1),
                    "text": f"Band {a['band']} to Band {b['band']}" + (f" (up {d})" if d > 0 else f" (down {-d})" if d < 0 else " (no change)")}
    first_f, last_f = (banded[0]["focus_areas"], banded[-1]["focus_areas"]) if len(banded) >= 2 else ([], [])
    improved = sum(1 for t in tests if t["change"] and t["change"]["state"] == "improved")
    compared = sum(1 for t in tests if t["change"])
    notes = ["Each test is compared with the player's own earlier result. Bands compare the player with the same-level group in each window, so a player "
             "can improve and still stay in the same band."]
    if len({c["level"] for c in cols}) > 1:
        notes.append("The player was tested at a different level in some windows. Bronco and 2 km are different tests and are not compared.")
    if len(cols) < 2:
        notes.append("Progress needs results from at least two test windows.")
    return {"windows": cols, "tests": tests, "band_movement": movement, "tests_compared": compared, "tests_improved": improved,
            "focus_resolved": [f for f in first_f if f not in last_f], "focus_new": [f for f in last_f if f not in first_f],
            "focus_still": [f for f in last_f if f in first_f], "notes": notes}
