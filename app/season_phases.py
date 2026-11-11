"""Default split of a season into the four phases. A suggestion only: the admin can change every date."""
from datetime import date, timedelta

PHASE_FOCUS = {
    "pre_season": "Build the physical base and technical foundations; baseline testing; low volume and intensity.",
    "pre_competition": "Raise specificity and intensity step by step; variations, scenarios and match-simulation.",
    "in_season": "Compete, maintain and recover; apply the workload rules; mid-season testing and review.",
    "transition": "Active rest and recovery; end-of-season testing and review; reset goals.",
}


def suggest_phases(start: date, end: date) -> list[dict]:
    total = (end - start).days + 1
    if total < 28:
        raise ValueError("A season shorter than 4 weeks cannot be split into four phases")
    w = total / 7
    b1 = max(1, round(w * 0.25))
    b2 = max(b1 + 1, round(w * 0.40))
    b3 = max(b2 + 1, round(w * 0.85))
    if b3 * 7 > total - 7:                       # keep at least one week for the last phase
        b3 = (total - 7) // 7
    cuts = [start, start + timedelta(days=7 * b1), start + timedelta(days=7 * b2), start + timedelta(days=7 * b3)]
    ends = [cuts[1] - timedelta(days=1), cuts[2] - timedelta(days=1), cuts[3] - timedelta(days=1), end]
    names = ["pre_season", "pre_competition", "in_season", "transition"]
    return [{"phase_type": n, "start_date": s, "end_date": e, "focus": PHASE_FOCUS[n]} for n, s, e in zip(names, cuts, ends)]
