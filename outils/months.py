"""The month grids the calendar draws, laid out like cal: weeks as rows, days of the week as columns."""

import calendar

# The names week_start takes in config.yaml, in calendar's order (Monday is 0)
WEEKDAY_NAMES = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
# Every month gets this many rows, as cal does, so months side by side line up and keep their height
WEEKS_SHOWN = 6


def shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    """The month delta months away, across years as needed."""
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def month_weeks(year: int, month: int, first_weekday: int) -> list[list[int]]:
    """The month's days, one list of 7 per week and 0 for a day outside it, always WEEKS_SHOWN weeks."""
    weeks = calendar.Calendar(first_weekday).monthdayscalendar(year, month)
    return weeks + [[0] * 7 for _ in range(WEEKS_SHOWN - len(weeks))]


def weekday_labels(first_weekday: int) -> list[str]:
    """Two-letter day names starting on first_weekday, as cal heads its columns."""
    return [calendar.day_abbr[(first_weekday + offset) % 7][:2] for offset in range(7)]
