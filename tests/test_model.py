import unittest
from datetime import date

from weekly_report.model import AppReport, Failure, Growth, Metric, Report
from weekly_report.periods import Period

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

    def test_series_defaults_to_empty(self):
        self.assertEqual(Metric(value=1, previous=1).series, ())


class ReportProblemsTest(unittest.TestCase):
    def growth(self):
        return Growth(period=WEEK, installs=Metric(value=1, previous=1))

    def test_no_failures_means_no_problems(self):
        report = Report(period=WEEK, apps=(AppReport("first", self.growth()),))
        self.assertEqual(report.problems, [])

    def test_every_failing_section_is_a_problem_named_by_app(self):
        failure = Failure(source="Play report bucket", error="403 Forbidden")
        report = Report(
            period=WEEK,
            apps=(AppReport("first", self.growth()), AppReport("second", failure)),
        )
        self.assertEqual(report.problems, [("second", failure)])

    def test_no_apps_means_no_problems(self):
        self.assertEqual(Report(period=WEEK, apps=()).problems, [])


if __name__ == "__main__":
    unittest.main()
