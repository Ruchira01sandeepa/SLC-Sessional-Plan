"""Age-group profiles: everything that differs between a U15 and a U17 squad, in one place. Pure module.

A squad's `age_group` picks its profile. Every rule that depends on age (date-of-birth check, fast-bowler limits,
planned load peak, the test battery used) reads it from here, so adding U19 later is one more entry below.

Status of the numbers
  * U15: the fast-bowler limits come from the project brief (5 overs a spell, 16 a match day, 3 bowling days in 7) with
    Cricket Australia's 12 overs a match day for ages 13-15 as an early caution. PROVISIONAL until SLC approval.
  * U17: PLACEHOLDERS, NOT SLC RULES. Chosen from published junior fast-bowling guidance for 16-17 year-olds (for
    example the ECB fast-bowling directives allow about 7 overs a spell and 18 a day at this age); a stricter 6-over spell
    is used until SLC confirms. Check them against the current published directive and SLC policy before real use.
  * U17 uses the SLC National U15 test battery until an SLC U17 SOP exists; players are only ever compared with players of
    the same squad level and window, so the comparison stays fair.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AgeProfile:
    code: str
    label: str
    min_age: int                      # date-of-birth plausibility check (catches typos; allows for cut-off dates)
    max_age: int
    fast_limits: dict
    load_peak: float                  # highest planned weekly percentage in the annual plan
    test_battery: str                 # which SOP is used for the physical tests
    provisional: bool
    notes: tuple[str, ...] = field(default_factory=tuple)
    start_load: float = 900.0         # weekly load (RPE x min) assumed when a player has under 3 weeks of logs

    def summary(self) -> dict:
        return {"code": self.code, "label": self.label, "min_age": self.min_age, "max_age": self.max_age,
                "fast_limits": dict(self.fast_limits), "load_peak": self.load_peak, "test_battery": self.test_battery,
                "provisional": self.provisional, "notes": list(self.notes), "start_load": self.start_load}


PROFILES: dict[str, AgeProfile] = {
    "U15": AgeProfile(
        code="U15", label="Under 15", min_age=8, max_age=16,
        fast_limits={"max_spell_overs": 5, "max_match_day_overs": 16, "caution_match_day_overs": 12, "max_bowling_days_week": 3},
        load_peak=0.90, test_battery="SLC National U15 Physical Testing SOP", provisional=True,
        notes=("Fast-bowler limits come from the project brief and are provisional until SLC / provincial approval.",
               "Cricket Australia advises 12 overs a match day for ages 13 to 15; this is shown as an early caution.")),
    "U17": AgeProfile(
        code="U17", label="Under 17", min_age=12, max_age=18,
        fast_limits={"max_spell_overs": 6, "max_match_day_overs": 18, "caution_match_day_overs": 15, "max_bowling_days_week": 3},
        load_peak=0.93, test_battery="SLC National U15 Physical Testing SOP (used for U17 until an U17 SOP exists)", provisional=True,
        notes=("U17 limits are PLACEHOLDERS, not SLC rules: 6 overs a spell, 18 a match day (caution at 15), 3 bowling days in 7. "
               "They follow published junior fast-bowling guidance for 16-17 year-olds and must be confirmed by SLC before real use.",
               "The U15 test battery is used until an SLC U17 testing SOP is available."), start_load=1100.0),
}
DEFAULT = "U15"
CODES = tuple(PROFILES)


def profile(code: str | None) -> AgeProfile:
    """The profile for a squad's age group. Unknown or missing values fall back to U15 (the original, strictest rules)."""
    return PROFILES.get((code or DEFAULT).upper(), PROFILES[DEFAULT])


def age_on(dob, today) -> int:
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def check_dob(code: str | None, dob, today) -> None:
    p = profile(code)
    if not p.min_age <= age_on(dob, today) <= p.max_age:
        raise ValueError(f"Date of birth is outside the plausible {p.code} range ({p.min_age}-{p.max_age} years)")
