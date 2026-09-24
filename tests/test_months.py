import unittest

from outils.months import WEEKS_SHOWN, month_weeks, shift_month, weekday_labels

MONDAY, SUNDAY = 0, 6


class MonthsTest(unittest.TestCase):
    def test_shift_month_crosses_years_both_ways(self):
        self.assertEqual(shift_month(2026, 9, 1), (2026, 10))
        self.assertEqual(shift_month(2026, 12, 1), (2027, 1))
        self.assertEqual(shift_month(2026, 1, -1), (2025, 12))
        self.assertEqual(shift_month(2026, 9, -21), (2024, 12))

    def test_weeks_start_on_the_chosen_day_and_every_month_has_six_rows(self):
        # September 2026 starts on a Tuesday
        monday_weeks = month_weeks(2026, 9, MONDAY)
        self.assertEqual(monday_weeks[0], [0, 1, 2, 3, 4, 5, 6])
        self.assertEqual(month_weeks(2026, 9, SUNDAY)[0], [0, 0, 1, 2, 3, 4, 5])
        # February 2021 fits in four Monday weeks; it still gets six rows, the last ones empty
        february = month_weeks(2021, 2, MONDAY)
        self.assertEqual(len(monday_weeks), WEEKS_SHOWN)
        self.assertEqual(len(february), WEEKS_SHOWN)
        self.assertEqual(february[4:], [[0] * 7, [0] * 7])

    def test_weekday_labels_follow_the_first_day(self):
        self.assertEqual(weekday_labels(MONDAY), ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"])
        self.assertEqual(weekday_labels(SUNDAY)[:2], ["Su", "Mo"])


if __name__ == "__main__":
    unittest.main()
