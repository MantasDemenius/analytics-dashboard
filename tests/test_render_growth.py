import unittest
from datetime import date

from render_fixtures import (
    BUCKET_WEEK,
    NO_ADMOB,
    NO_REVIEWS,
    app,
    chart,
    chart_configs,
    growth,
    part,
    render,
    report,
    values,
)

from weekly_report.model import (
    Failure,
    Unavailable,
)
from weekly_report.periods import Coverage, Period


class GrowthSectionTest(unittest.TestCase):
    def test_shows_its_own_range(self):
        html = render(report(app("first", growth())))
        self.assertIn("19 Oct to 25 Oct 2026", part(html, 'id="app-0-growth"'))

    def test_draws_the_daily_installs_chart(self):
        html = render(report(app("first", growth())))
        daily = chart(html, "Daily installs and uninstalls")
        self.assertEqual(daily["type"], "bar")
        self.assertEqual(values(daily), [10] * 7)
        self.assertEqual(daily["data"]["labels"][0], "Mon 19 Oct")

    def test_the_daily_chart_pairs_installs_with_uninstalls(self):
        html = render(report(app("first")))
        daily = chart(html, "Daily installs and uninstalls")
        labels = [each["label"] for each in daily["data"]["datasets"]]
        self.assertEqual(labels, ["Installs", "Uninstalls"])
        self.assertEqual(daily["data"]["datasets"][1]["data"], [3] * 7)
        self.assertTrue(daily["options"]["plugins"]["legend"]["display"])

    def test_the_trend_draws_a_line_each_for_installs_and_uninstalls(self):
        html = render(report(app("first", growth(value=69, uninstalls=(20, 25)))))
        trend = chart(html, "Installs and uninstalls over the last 12 weeks")
        lines = {each["label"]: each["data"][-1] for each in trend["data"]["datasets"]}
        self.assertEqual(lines, {"Installs": 69, "Uninstalls": 20})

    def test_draws_the_12_period_trend(self):
        html = render(report(app("first", growth(value=69))))
        trend = chart(html, "Installs and uninstalls over the last 12 weeks")
        self.assertEqual(trend["type"], "line")
        self.assertEqual(values(trend)[-1], 69)
        self.assertEqual(trend["data"]["labels"][0], "3 Aug")
        self.assertIn("Last 12 weeks", html)

    def test_a_partly_covered_section_says_where_its_data_ends(self):
        coverage = Coverage(BUCKET_WEEK, date(2026, 10, 22))
        html = render(report(app("first", growth(coverage=coverage))))
        self.assertIn("19 Oct to 25 Oct 2026, data to 22 Oct", html)
        self.assertIn("52 the 4 days before", html)
        self.assertEqual(len(values(chart(html, "Daily installs and uninstalls"))), 4)

    def test_a_range_that_is_not_a_week_names_its_length(self):
        coverage = Coverage(Period(date(2026, 10, 1), date(2026, 10, 10)))
        html = render(report(app("first", growth(coverage=coverage))))
        self.assertIn("52 the 10 days before", html)
        self.assertIn("Last 12 periods of 10 days", html)

    def test_a_single_day_range(self):
        coverage = Coverage(Period(date(2026, 10, 1), date(2026, 10, 1)))
        html = render(report(app("first", growth(coverage=coverage))))
        self.assertIn("52 the day before", html)
        self.assertIn("Last 12 days", html)

    def test_an_unreachable_range_says_so_and_is_no_problem(self):
        html = render(
            report(
                app(
                    "first",
                    Unavailable("Play report bucket", BUCKET_WEEK),
                    reviews_section=NO_REVIEWS,
                    admob_section=NO_ADMOB,
                )
            )
        )
        section = part(html, 'id="app-0-growth"')
        self.assertIn("not available for this range", section)
        self.assertIn("19 Oct to 25 Oct 2026", section)
        self.assertNotIn('class="problems"', html)
        self.assertEqual(chart_configs(html), [])

    def test_a_failed_section_shows_its_error_in_a_full_width_card(self):
        failure = Failure(source="Play report bucket", error="403 Forbidden")
        html = render(report(app("first", failure)))
        section = part(html, 'id="app-0-growth"')
        self.assertIn('class="card wide"', section)
        self.assertIn("Play report bucket: 403 Forbidden", section)

    def test_a_fall_shows_a_minus(self):
        html = render(report(app("first", growth(value=40, previous=50))))
        self.assertIn("−10", html)
        self.assertIn("−20.0%", html)

    def test_a_rise_from_zero_has_no_percent(self):
        html = render(report(app("first", growth(value=4, previous=0))))
        section = part(html, 'id="app-0-growth"', 'id="app-0-reviews"')
        self.assertIn("+4", html)
        self.assertNotIn("%</", section)
