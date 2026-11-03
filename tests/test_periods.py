import unittest
from datetime import date

from weekly_report.periods import Coverage, Period, week_ending_by


class WeekEndingByTest(unittest.TestCase):
    def test_on_a_sunday_that_week_is_complete(self):
        self.assertEqual(
            week_ending_by(date(2026, 11, 1)),
            Period(date(2026, 10, 26), date(2026, 11, 1)),
        )

    def test_midweek_picks_the_week_before(self):
        self.assertEqual(
            week_ending_by(date(2026, 10, 29)),
            Period(date(2026, 10, 19), date(2026, 10, 25)),
        )

    def test_on_a_monday_picks_the_week_ending_the_day_before(self):
        self.assertEqual(
            week_ending_by(date(2026, 11, 2)),
            Period(date(2026, 10, 26), date(2026, 11, 1)),
        )

    def test_on_a_saturday_picks_the_week_before(self):
        self.assertEqual(
            week_ending_by(date(2026, 10, 31)),
            Period(date(2026, 10, 19), date(2026, 10, 25)),
        )


class PeriodTest(unittest.TestCase):
    def test_previous_is_the_same_length_just_before(self):
        period = Period(date(2026, 10, 26), date(2026, 11, 1))
        self.assertEqual(
            period.previous(), Period(date(2026, 10, 19), date(2026, 10, 25))
        )

    def test_previous_of_an_uneven_range(self):
        period = Period(date(2026, 3, 1), date(2026, 3, 3))
        self.assertEqual(
            period.previous(), Period(date(2026, 2, 26), date(2026, 2, 28))
        )

    def test_days_are_inclusive(self):
        period = Period(date(2026, 10, 30), date(2026, 11, 1))
        self.assertEqual(
            period.days(),
            [date(2026, 10, 30), date(2026, 10, 31), date(2026, 11, 1)],
        )

    def test_a_single_day(self):
        period = Period(date(2026, 10, 30), date(2026, 10, 30))
        self.assertEqual(period.days(), [date(2026, 10, 30)])
        self.assertEqual(
            period.previous(), Period(date(2026, 10, 29), date(2026, 10, 29))
        )

    def test_months_within_one_month(self):
        period = Period(date(2026, 10, 5), date(2026, 10, 11))
        self.assertEqual(period.months(), [date(2026, 10, 1)])

    def test_months_of_a_week_straddling_two_months(self):
        period = Period(date(2026, 10, 26), date(2026, 11, 1))
        self.assertEqual(period.months(), [date(2026, 10, 1), date(2026, 11, 1)])

    def test_months_across_a_year_end(self):
        period = Period(date(2025, 12, 29), date(2026, 1, 4))
        self.assertEqual(period.months(), [date(2025, 12, 1), date(2026, 1, 1)])

    def test_label_within_one_year(self):
        period = Period(date(2026, 10, 26), date(2026, 11, 1))
        self.assertEqual(period.label(), "26 Oct to 1 Nov 2026")

    def test_label_across_a_year_end(self):
        period = Period(date(2025, 12, 29), date(2026, 1, 4))
        self.assertEqual(period.label(), "29 Dec 2025 to 4 Jan 2026")

    def test_end_before_start_is_refused(self):
        with self.assertRaises(ValueError):
            Period(date(2026, 11, 2), date(2026, 11, 1))

    def test_cut_keeps_the_first_days(self):
        period = Period(date(2026, 10, 26), date(2026, 11, 1))
        self.assertEqual(period.cut(3), Period(date(2026, 10, 26), date(2026, 10, 28)))

    def test_cut_to_the_full_length_changes_nothing(self):
        period = Period(date(2026, 10, 26), date(2026, 11, 1))
        self.assertEqual(period.cut(7), period)

    def test_trailing_lists_periods_of_the_same_length_oldest_first(self):
        period = Period(date(2026, 10, 12), date(2026, 10, 14))
        self.assertEqual(
            period.trailing(3),
            [
                Period(date(2026, 10, 6), date(2026, 10, 8)),
                Period(date(2026, 10, 9), date(2026, 10, 11)),
                period,
            ],
        )

    def test_trailing_one_is_the_period_itself(self):
        period = Period(date(2026, 10, 12), date(2026, 10, 14))
        self.assertEqual(period.trailing(1), [period])


class CoverageTest(unittest.TestCase):
    period = Period(date(2026, 10, 26), date(2026, 11, 1))

    def test_data_to_the_end_covers_the_whole_period(self):
        coverage = Coverage.reaching(self.period, date(2026, 11, 1))
        self.assertEqual(coverage, Coverage(self.period))
        self.assertEqual(coverage.covered, self.period)

    def test_data_past_the_end_covers_the_whole_period(self):
        self.assertEqual(
            Coverage.reaching(self.period, date(2026, 11, 20)), Coverage(self.period)
        )

    def test_data_ending_inside_the_period_covers_the_start_of_it(self):
        coverage = Coverage.reaching(self.period, date(2026, 10, 28))
        self.assertEqual(coverage, Coverage(self.period, date(2026, 10, 28)))
        self.assertEqual(
            coverage.covered, Period(date(2026, 10, 26), date(2026, 10, 28))
        )

    def test_data_on_the_first_day_covers_one_day(self):
        coverage = Coverage.reaching(self.period, date(2026, 10, 26))
        self.assertEqual(coverage.covered.length, 1)

    def test_data_ending_before_the_period_reaches_nothing(self):
        self.assertIsNone(Coverage.reaching(self.period, date(2026, 10, 25)))

    def test_no_data_reaches_nothing(self):
        self.assertIsNone(Coverage.reaching(self.period, None))

    def test_label_of_a_complete_period_is_the_period(self):
        self.assertEqual(Coverage(self.period).label(), "26 Oct to 1 Nov 2026")

    def test_label_of_a_partial_period_names_where_the_data_ends(self):
        coverage = Coverage(self.period, date(2026, 10, 28))
        self.assertEqual(coverage.label(), "26 Oct to 1 Nov 2026, data to 28 Oct")


if __name__ == "__main__":
    unittest.main()
