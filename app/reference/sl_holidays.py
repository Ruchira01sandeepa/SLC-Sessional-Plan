"""Sri Lankan public holidays (no practice on these days). Pure module.

2027: Gazette Extraordinary No. 2493/05 of 16 June 2026 (Holidays Act No. 29 of 1971, public and bank holidays for 2027), as
reproduced by tamilguru.lk / wincore.lk / Wikipedia (Medin Poya 22 March, Vesak 19 May - earlier calendars that show 21 March /
20 May predate the gazette). Eid and Milad-un-Nabi dates are subject to the moon sighting and may move by a day.
2026: the holidays from November 2026 (the gazetted 2026 list).
Other years: only the fixed-date holidays are known here - add the year's gazetted list below, or add a "rest" event in the
Calendar for any other day without practice (it is treated the same way).
"""
from __future__ import annotations

from datetime import date

HOLIDAYS: dict[date, str] = {
    # 2026 (from November)
    date(2026, 11, 8): "Deepavali Festival Day",
    date(2026, 11, 24): "Il Full Moon Poya Day",
    date(2026, 12, 23): "Unduvap Full Moon Poya Day",
    date(2026, 12, 25): "Christmas Day",
    # 2027 (gazette 2493/05)
    date(2027, 1, 15): "Tamil Thai Pongal Day",
    date(2027, 1, 22): "Duruthu Full Moon Poya Day",
    date(2027, 2, 4): "National Day",
    date(2027, 2, 20): "Navam Full Moon Poya Day",
    date(2027, 3, 6): "Mahasivarathri Day",
    date(2027, 3, 10): "Id-Ul-Fitr (Ramazan Festival Day)",
    date(2027, 3, 22): "Medin Full Moon Poya Day",
    date(2027, 3, 26): "Good Friday",
    date(2027, 4, 13): "Day prior to Sinhala and Tamil New Year Day",
    date(2027, 4, 14): "Sinhala and Tamil New Year Day",
    date(2027, 4, 20): "Bak Full Moon Poya Day",
    date(2027, 5, 1): "May Day",
    date(2027, 5, 17): "Id-Ul-Alha (Hadji Festival Day)",
    date(2027, 5, 19): "Vesak Full Moon Poya Day",
    date(2027, 5, 20): "Day following Vesak Full Moon Poya Day",
    date(2027, 6, 18): "Poson Full Moon Poya Day",
    date(2027, 7, 18): "Esala Full Moon Poya Day",
    date(2027, 8, 15): "Milad-Un-Nabi (Holy Prophet's Birthday)",
    date(2027, 8, 16): "Nikini Full Moon Poya Day",
    date(2027, 9, 15): "Binara Full Moon Poya Day",
    date(2027, 10, 15): "Vap Full Moon Poya Day",
    date(2027, 10, 28): "Deepavali Festival Day",
    date(2027, 11, 13): "Il Full Moon Poya Day",
    date(2027, 12, 13): "Unduvap Full Moon Poya Day",
    date(2027, 12, 25): "Christmas Day",
}
KNOWN_YEARS = {2027}                                         # full gazetted list held
FIXED = {(2, 4): "National Day", (5, 1): "May Day", (12, 25): "Christmas Day"}


def holiday(d: date) -> str | None:
    """The public holiday on d, or None. For a year without its gazetted list, only the fixed-date holidays are known."""
    if d in HOLIDAYS:
        return HOLIDAYS[d]
    if d.year not in KNOWN_YEARS and not (d.year == 2026 and d.month >= 11):
        return FIXED.get((d.month, d.day))
    return None


def years_without_list(days: list[date]) -> list[int]:
    return sorted({d.year for d in days if d.year not in KNOWN_YEARS and not (d.year == 2026 and d.month >= 11)})
