import json
import re
import unittest
from datetime import date, datetime

from weekly_report.model import (
    AppReport,
    Failure,
    Growth,
    Metric,
    Point,
    Report,
    Unavailable,
)
from weekly_report.periods import Coverage, Period
from weekly_report.render import render, summary

REPORT_WEEK = Period(date(2026, 10, 26), date(2026, 11, 1))
BUCKET_WEEK = Period(date(2026, 10, 19), date(2026, 10, 25))
GENERATED = datetime(2026, 11, 2, 8, 0)


def growth(value=69, previous=52, coverage=None):
    coverage = coverage or Coverage(BUCKET_WEEK)
    series = tuple(Point(day, 10) for day in coverage.covered.days())
    return Growth(
        coverage=coverage,
        installs=Metric(value=value, previous=previous, series=series),
    )


def report(*apps):
    return Report(period=REPORT_WEEK, apps=apps, generated=GENERATED)


def chart_configs(html: str) -> list:
    match = re.search(r"const CHARTS = (.*?);\n", html)
    return json.loads(match.group(1))


class RenderTest(unittest.TestCase):
    def test_shows_the_report_and_section_periods(self):
        html = render(report(AppReport("first", growth())))
        self.assertIn("26 Oct to 1 Nov 2026", html)
        self.assertIn("19 Oct to 25 Oct 2026", html)

    def test_shows_new_installs_with_their_change(self):
        html = render(report(AppReport("first", growth(value=69, previous=52))))
        self.assertIn(">69<", html)
        self.assertIn("+17", html)
        self.assertIn("+32.7%", html)
        self.assertIn("52 the week before", html)

    def test_a_partly_covered_section_says_where_its_data_ends(self):
        coverage = Coverage(BUCKET_WEEK, date(2026, 10, 22))
        html = render(report(AppReport("first", growth(coverage=coverage))))
        self.assertIn("19 Oct to 25 Oct 2026, data to 22 Oct", html)
        self.assertIn("52 the 4 days before", html)
        [(_, config)] = chart_configs(html)
        self.assertEqual(len(config["data"]["datasets"][0]["data"]), 4)

    def test_a_range_that_is_not_a_week_names_its_length(self):
        coverage = Coverage(Period(date(2026, 10, 1), date(2026, 10, 10)))
        html = render(report(AppReport("first", growth(coverage=coverage))))
        self.assertIn("52 the 10 days before", html)

    def test_a_single_day_range(self):
        coverage = Coverage(Period(date(2026, 10, 1), date(2026, 10, 1)))
        html = render(report(AppReport("first", growth(coverage=coverage))))
        self.assertIn("52 the day before", html)

    def test_an_unreachable_range_says_so_in_its_section_and_is_no_problem(self):
        html = render(
            report(AppReport("first", Unavailable("Play report bucket", BUCKET_WEEK)))
        )
        self.assertIn("not available for this range", html)
        self.assertIn("19 Oct to 25 Oct 2026", html)
        self.assertNotIn('class="problems"', html)
        self.assertEqual(chart_configs(html), [])

    def test_a_fall_shows_a_minus(self):
        html = render(report(AppReport("first", growth(value=40, previous=50))))
        self.assertIn("−10", html)
        self.assertIn("−20.0%", html)

    def test_a_rise_from_zero_has_no_percent(self):
        html = render(report(AppReport("first", growth(value=4, previous=0))))
        self.assertIn("+4", html)
        self.assertNotIn("%</", html)

    def test_draws_the_daily_installs_chart(self):
        html = render(report(AppReport("first", growth())))
        [(canvas_id, config)] = chart_configs(html)
        self.assertIn(f'id="{canvas_id}"', html)
        self.assertEqual(config["data"]["datasets"][0]["data"], [10] * 7)
        self.assertEqual(config["data"]["labels"][0], "Mon 19 Oct")

    def test_inlines_chart_js_with_animation_off(self):
        html = render(report(AppReport("first", growth())))
        self.assertIn("Chart.js v4.4.1", html)
        self.assertIn("Released under the MIT License", html)
        self.assertLess(
            html.index("Chart.defaults.animation = false"), html.index("new Chart(")
        )
        self.assertNotIn("<script src=", html)

    def test_prints_on_a4(self):
        html = render(report(AppReport("first", growth())))
        self.assertIn("size: A4", html)

    def test_no_failures_means_no_problems_box(self):
        html = render(report(AppReport("first", growth())))
        self.assertNotIn('class="problems"', html)

    def test_a_failed_source_shows_in_the_problems_box_and_its_section(self):
        failure = Failure(source="Play report bucket", error="403 Forbidden")
        html = render(report(AppReport("first", failure)))
        problems = html[html.index('class="problems"') :]
        self.assertIn("first", problems[: problems.index("</section>")])
        self.assertIn("Play report bucket", problems[: problems.index("</section>")])
        self.assertEqual(html.count("403 Forbidden"), 2)
        self.assertEqual(chart_configs(html), [])

    def test_error_text_is_escaped(self):
        failure = Failure(source="Play report bucket", error="<b>bad</b>")
        html = render(report(AppReport("first", failure)))
        self.assertNotIn("<b>bad</b>", html)
        self.assertIn("&lt;b&gt;bad&lt;/b&gt;", html)

    def test_every_app_gets_a_section(self):
        html = render(
            report(AppReport("first", growth()), AppReport("second", growth()))
        )
        self.assertIn(">first<", html)
        self.assertIn(">second<", html)
        self.assertEqual(len(chart_configs(html)), 2)


class SummaryTest(unittest.TestCase):
    def test_lists_the_period_and_each_apps_new_installs(self):
        self.assertEqual(
            summary(report(AppReport("first", growth(value=69, previous=52)))),
            [
                "Weekly app report, 26 Oct to 1 Nov 2026",
                "",
                "first",
                "  New installs, 19 Oct to 25 Oct 2026: 69 (+17, +32.7%)",
            ],
        )

    def test_a_rise_from_zero_shows_no_percent(self):
        lines = summary(report(AppReport("first", growth(value=4, previous=0))))
        self.assertEqual(lines[-1], "  New installs, 19 Oct to 25 Oct 2026: 4 (+4)")

    def test_a_partly_covered_section_says_where_its_data_ends(self):
        coverage = Coverage(BUCKET_WEEK, date(2026, 10, 22))
        lines = summary(report(AppReport("first", growth(coverage=coverage))))
        self.assertEqual(
            lines[-1],
            "  New installs, 19 Oct to 25 Oct 2026, data to 22 Oct: 69 (+17, +32.7%)",
        )

    def test_an_unreachable_range_says_so(self):
        lines = summary(
            report(AppReport("first", Unavailable("Play report bucket", BUCKET_WEEK)))
        )
        self.assertEqual(
            lines[-1], "  Play report bucket: not available for this range"
        )
        self.assertNotIn("Problems:", lines)

    def test_failures_show_in_their_section_and_as_problems(self):
        failure = Failure(source="Play report bucket", error="403 Forbidden")
        self.assertEqual(
            summary(report(AppReport("first", failure))),
            [
                "Weekly app report, 26 Oct to 1 Nov 2026",
                "",
                "Problems:",
                "  first, Play report bucket: 403 Forbidden",
                "",
                "first",
                "  Play report bucket failed, see Problems",
            ],
        )


if __name__ == "__main__":
    unittest.main()
