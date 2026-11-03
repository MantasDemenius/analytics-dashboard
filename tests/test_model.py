import unittest
from datetime import date, timedelta

from weekly_report.model import (
    AppReport,
    Failure,
    Growth,
    Listing,
    Metric,
    Point,
    Report,
    Unavailable,
)
from weekly_report.periods import Coverage, Period

WEEK = Period(date(2026, 10, 19), date(2026, 10, 25))


class MetricTest(unittest.TestCase):
    def test_a_rise(self):
        metric = Metric(value=12, previous=8)
        self.assertEqual(metric.change, 4)
        self.assertEqual(metric.percent_change, 50.0)

    def test_a_fall(self):
        metric = Metric(value=6, previous=8)
        self.assertEqual(metric.change, -2)
        self.assertEqual(metric.percent_change, -25.0)

    def test_no_change(self):
        metric = Metric(value=5, previous=5)
        self.assertEqual(metric.change, 0)
        self.assertEqual(metric.percent_change, 0.0)

    def test_from_zero_has_no_percent(self):
        metric = Metric(value=3, previous=0)
        self.assertEqual(metric.change, 3)
        self.assertIsNone(metric.percent_change)

    def test_a_rise_from_a_negative_value_is_a_positive_percent(self):
        metric = Metric(value=-2, previous=-8)
        self.assertEqual(metric.change, 6)
        self.assertEqual(metric.percent_change, 75.0)

    def test_a_fall_below_a_negative_value_is_a_negative_percent(self):
        metric = Metric(value=-12, previous=-8)
        self.assertEqual(metric.percent_change, -50.0)

    def test_series_defaults_to_empty(self):
        self.assertEqual(Metric(value=1, previous=1).series, ())


def per_day(first: date, values: list[float]) -> dict[date, float]:
    return {first + timedelta(days=offset): v for offset, v in enumerate(values)}


class SummedMetricTest(unittest.TestCase):
    period = Period(date(2026, 10, 19), date(2026, 10, 21))

    def test_sums_the_period_and_the_one_before(self):
        daily = per_day(date(2026, 10, 16), [1, 2, 3, 4, 5, 6, 100])
        self.assertEqual(
            Metric.summed(daily, Coverage(self.period)).series,
            (
                Point(date(2026, 10, 19), 4),
                Point(date(2026, 10, 20), 5),
                Point(date(2026, 10, 21), 6),
            ),
        )
        metric = Metric.summed(daily, Coverage(self.period))
        self.assertEqual((metric.value, metric.previous), (15, 6))

    def test_missing_days_count_as_zero(self):
        daily = {date(2026, 10, 17): 2, date(2026, 10, 20): 5}
        metric = Metric.summed(daily, Coverage(self.period))
        self.assertEqual((metric.value, metric.previous), (5, 2))
        self.assertEqual([point.value for point in metric.series], [0, 5, 0])

    def test_no_days_at_all_is_zero_against_zero(self):
        metric = Metric.summed({}, Coverage(self.period))
        self.assertEqual((metric.value, metric.previous), (0, 0))

    def test_a_partly_covered_period_is_set_against_the_same_days_of_the_one_before(
        self,
    ):
        daily = per_day(date(2026, 10, 16), [1, 2, 3, 4, 5, 6, 100])
        metric = Metric.summed(daily, Coverage(self.period, date(2026, 10, 20)))
        self.assertEqual((metric.value, metric.previous), (9, 3))
        self.assertEqual(
            [point.day for point in metric.series],
            [date(2026, 10, 19), date(2026, 10, 20)],
        )

    def test_the_trend_holds_twelve_periods_of_the_ranges_length_oldest_first(self):
        first = self.period.trailing(12)[0].start
        daily = {first + timedelta(days=n): n // 3 + 1 for n in range(36)}
        trend = Metric.summed(daily, Coverage(self.period)).trend
        self.assertEqual(len(trend), 12)
        self.assertEqual(
            [point.value for point in trend], [3 * (n + 1) for n in range(12)]
        )
        self.assertEqual(
            [point.day for point in trend][:2], [first, first + timedelta(days=3)]
        )
        self.assertEqual(trend[-1].day, self.period.start)

    def test_a_non_week_length_gives_twelve_periods_of_that_length(self):
        period = Period(date(2026, 10, 1), date(2026, 10, 10))
        trend = Metric.summed({date(2026, 10, 5): 7}, Coverage(period)).trend
        self.assertEqual(len(trend), 12)
        self.assertEqual(trend[-1], Point(date(2026, 10, 1), 7))
        self.assertEqual(trend[0].day, date(2026, 10, 1) - timedelta(days=110))

    def test_a_partly_covered_trend_cuts_every_period_to_the_same_days(self):
        daily = per_day(date(2026, 10, 12), [1, 1, 1, 50, 50, 50, 50, 1, 1, 1, 50])
        metric = Metric.summed(daily, Coverage(self.period, date(2026, 10, 20)))
        self.assertEqual(metric.trend[-1].value, 2)


class RatioMetricTest(unittest.TestCase):
    period = Period(date(2026, 10, 19), date(2026, 10, 20))

    def metric(self, part: dict, whole: dict, data_to=None):
        coverage = Coverage(self.period, data_to)
        return Metric.ratio(
            Metric.summed(part, coverage), Metric.summed(whole, coverage)
        )

    def test_is_the_sum_of_the_parts_over_the_sum_of_the_wholes_as_a_percent(self):
        part = {date(2026, 10, 19): 1, date(2026, 10, 20): 3}
        whole = {date(2026, 10, 19): 10, date(2026, 10, 20): 30}
        self.assertEqual(self.metric(part, whole).value, 10.0)

    def test_a_busy_day_weighs_more_than_a_quiet_one(self):
        part = {date(2026, 10, 19): 1, date(2026, 10, 20): 0}
        whole = {date(2026, 10, 19): 2, date(2026, 10, 20): 18}
        self.assertEqual(self.metric(part, whole).value, 5.0)

    def test_the_previous_period_is_a_ratio_of_its_own_sums(self):
        part = {date(2026, 10, 17): 2, date(2026, 10, 18): 2}
        whole = {date(2026, 10, 17): 10, date(2026, 10, 18): 30}
        metric = self.metric(part, whole)
        self.assertEqual((metric.value, metric.previous), (0.0, 10.0))

    def test_no_whole_is_zero_not_an_error(self):
        metric = self.metric({}, {})
        self.assertEqual((metric.value, metric.previous), (0.0, 0.0))

    def test_the_trend_is_a_ratio_per_period_dated_like_the_parts(self):
        part = {date(2026, 10, 19): 1}
        whole = {date(2026, 10, 19): 4, date(2026, 10, 17): 5}
        metric = self.metric(part, whole)
        self.assertEqual(len(metric.trend), 12)
        self.assertEqual(metric.trend[-1], Point(date(2026, 10, 19), 25.0))
        self.assertEqual(metric.trend[-2].value, 0.0)
        self.assertEqual(metric.trend[0].day, self.period.trailing(12)[0].start)

    def test_a_partly_covered_range_uses_the_covered_days_of_both_sums(self):
        part = {date(2026, 10, 19): 1, date(2026, 10, 20): 50}
        whole = {date(2026, 10, 19): 5, date(2026, 10, 20): 50}
        metric = self.metric(part, whole, data_to=date(2026, 10, 19))
        self.assertEqual(metric.value, 20.0)


class LevelMetricTest(unittest.TestCase):
    period = Period(date(2026, 10, 19), date(2026, 10, 21))

    def test_takes_the_value_at_the_end_of_the_range_and_one_period_earlier(self):
        metric = Metric.level(lambda day: day.day, Coverage(self.period))
        self.assertEqual((metric.value, metric.previous), (21, 18))

    def test_the_trend_samples_the_end_of_each_period(self):
        metric = Metric.level(lambda day: day.day, Coverage(self.period))
        self.assertEqual(len(metric.trend), 12)
        self.assertEqual(metric.trend[-1], Point(date(2026, 10, 19), 21))
        self.assertEqual(metric.trend[-2], Point(date(2026, 10, 16), 18))

    def test_a_partly_covered_range_takes_the_level_at_the_last_day_with_data(self):
        metric = Metric.level(
            lambda day: day.day, Coverage(self.period, date(2026, 10, 20))
        )
        self.assertEqual((metric.value, metric.previous), (20, 17))


class ReportProblemsTest(unittest.TestCase):
    def app(self, name="first", growth=None, listing=None):
        metric = Metric(value=1, previous=1)
        return AppReport(
            name,
            growth or Growth(Coverage(WEEK), metric, metric, metric),
            listing or Listing(Coverage(WEEK), metric, metric, metric),
        )

    def test_no_failures_means_no_problems(self):
        report = Report(period=WEEK, apps=(self.app(),))
        self.assertEqual(report.problems, [])

    def test_every_failing_section_is_a_problem_named_by_app(self):
        failure = Failure(source="Play report bucket", error="403 Forbidden")
        report = Report(
            period=WEEK,
            apps=(self.app(), self.app("second", growth=failure)),
        )
        self.assertEqual(report.problems, [("second", failure)])

    def test_two_failing_sections_of_one_app_are_two_problems(self):
        failure = Failure(source="Play report bucket", error="403 Forbidden")
        report = Report(period=WEEK, apps=(self.app(growth=failure, listing=failure),))
        self.assertEqual(report.problems, [("first", failure), ("first", failure)])

    def test_a_section_the_range_does_not_reach_is_not_a_problem(self):
        unavailable = Unavailable("Play report bucket", WEEK)
        report = Report(
            period=WEEK,
            apps=(self.app(growth=unavailable, listing=unavailable),),
        )
        self.assertEqual(report.problems, [])

    def test_no_apps_means_no_problems(self):
        self.assertEqual(Report(period=WEEK, apps=()).problems, [])


if __name__ == "__main__":
    unittest.main()
