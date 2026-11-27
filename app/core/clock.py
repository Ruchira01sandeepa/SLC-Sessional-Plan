"""Sri Lanka's date and time. The server runs on UTC, so date.today() there is still YESTERDAY in Sri Lanka from
00:00 to 05:30 local time: every "today" in the app (ages, date-of-birth checks, plans, workload) uses today_lk()."""
from datetime import date, datetime, timedelta, timezone

LK = timezone(timedelta(hours=5, minutes=30))            # Sri Lanka: fixed offset, no daylight saving


def today_lk() -> date:
    return datetime.now(LK).date()
