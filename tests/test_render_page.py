import re
import unittest
from datetime import date

from render_fixtures import (
    BUCKET_WEEK,
    app,
    apps,
    feedback,
    growth,
    installs,
    part,
    render,
    report,
    suggestion,
    summary,
    user_report,
)

from weekly_report import render as renderer
from weekly_report.headlines import (
    NEW_INSTALLS,
    Better,
)
from weekly_report.model import (
    Failure,
    Unavailable,
)
from weekly_report.periods import Coverage, Period


class TopTest(unittest.TestCase):
    def test_shows_the_report_range_and_when_it_was_made(self):
        html = render(report(app("first", growth())))
        top = part(html, '<header class="top"', "</header>")
        self.assertIn("26 Oct to 1 Nov 2026", top)
        self.assertIn("generated Mon 2 Nov 2026, 08:00", top)

    def test_the_key_says_what_every_change_is_against(self):
        week = render(report(app("first", growth())))
        ten_days = render(
            report(
                app("first", growth()),
                period=Period(date(2026, 10, 1), date(2026, 10, 10)),
            )
        )
        self.assertIn("Every change is against the week before", week)
        self.assertIn("Every change is against the 10 days before", ten_days)


class PageTest(unittest.TestCase):
    def test_every_app_gets_its_own_part_with_its_name(self):
        html = render(report(app("first", growth()), app("second", growth())))
        first, second = apps(html)
        self.assertIn(">first<", first)
        self.assertIn(">second<", second)

    def test_inlines_chart_js_with_animation_off(self):
        html = render(report(app("first", growth())))
        self.assertIn("Chart.js v4.4.1", html)
        self.assertIn("Released under the MIT License", html)
        self.assertLess(
            html.index("Chart.defaults.animation = false"), html.index("new Chart(")
        )
        self.assertNotIn("<script src=", html)

    def test_prints_on_a4_with_each_app_on_a_new_page(self):
        html = render(report(app("first", growth())))
        self.assertIn("@page { size: A4;", html)
        self.assertIn(".app + .app { break-before: page;", html)

    def test_grid_columns_shrink_and_cards_do_not_split(self):
        html = render(report(app("first", growth())))
        self.assertIn("repeat(4, minmax(0, 1fr))", html)
        self.assertIn("minmax(0, 1fr) minmax(0, 1fr)", html)
        self.assertNotRegex(html, r"repeat\(\d, 1fr\)")
        self.assertRegex(html, r"\.kpi \{[^}]*break-inside: avoid")
        self.assertRegex(html, r"\.card \{[^}]*break-inside: avoid")

    def test_forces_chart_canvas_size_only_when_printing(self):
        html = render(report(app("first", growth())))
        forced = [
            match.start() for match in re.finditer(r"width: 100% !important", html)
        ]
        self.assertEqual(len(forced), 1)
        self.assertLess(html.index("@media print"), forced[0])


class PdfRedactionTest(unittest.TestCase):
    EMAIL = "someone@example.com"
    APP_ID = "made-up-installation-id"

    def html(self):
        reports = [
            user_report(
                "It crashed",
                android_version="14",
                email=self.EMAIL,
                app_id=self.APP_ID,
            ),
            suggestion("Nice"),
        ]
        return renderer.render(
            report(app("first", feedback_section=feedback(reports=reports)))
        )

    @staticmethod
    def printed(html):
        return re.sub(r'<p class="private">.*?</p>', "", html, flags=re.DOTALL)

    def test_the_local_html_shows_the_email_and_the_app_id(self):
        html = self.html()
        self.assertIn(self.EMAIL, html)
        self.assertIn(self.APP_ID, html)

    def test_only_private_elements_hold_them(self):
        remainder = self.printed(self.html())
        self.assertNotIn(self.EMAIL, remainder)
        self.assertNotIn(self.APP_ID, remainder)

    def test_private_elements_are_hidden_when_printing_and_only_then(self):
        html = self.html()
        rule = ".private { display: none; }"
        self.assertIn(rule, html[html.index("@media print") :])
        self.assertNotIn(rule, html[: html.index("@media print")])

    def test_the_message_stays_in_the_pdf(self):
        self.assertIn("It crashed", self.printed(self.html()))

    def test_the_email_and_app_id_are_not_in_a_chart_or_an_attribute(self):
        html = self.html()
        for hidden in (self.EMAIL, self.APP_ID):
            self.assertEqual(html.count(hidden), 1)


class ProblemsTest(unittest.TestCase):
    def test_no_failures_means_no_problems_box(self):
        html = render(report(app("first", growth())))
        self.assertNotIn('class="problems"', html)

    def test_a_failed_source_shows_in_the_problems_box_and_its_section(self):
        failure = Failure(source="Play report bucket", error="403 Forbidden")
        html = render(report(app("first", failure)))
        problems = part(html, '<section class="problems"')
        self.assertIn("<b>first</b>, Play report bucket: 403 Forbidden", problems)
        self.assertEqual(html.count("403 Forbidden"), 2)

    def test_the_problems_box_comes_before_the_at_a_glance_table(self):
        failure = Failure(source="Play report bucket", error="403 Forbidden")
        html = render(report(app("first", failure)))
        self.assertLess(
            html.index('<section class="problems"'),
            html.index('<section class="glance"'),
        )

    def test_lists_every_failure_of_every_app(self):
        html = render(
            report(
                app("first", Failure("Play report bucket", "403 Forbidden")),
                app("second", Failure("Play report bucket", "timed out")),
            )
        )
        problems = part(html, '<section class="problems"')
        self.assertEqual(problems.count("<li>"), 2)
        self.assertIn("<b>second</b>, Play report bucket: timed out", problems)

    def test_error_text_is_escaped(self):
        failure = Failure(source="Play report bucket", error="<b>bad</b>")
        html = render(report(app("first", failure)))
        self.assertNotIn("<b>bad</b>", html)
        self.assertIn("&lt;b&gt;bad&lt;/b&gt;", html)


class SummaryTest(unittest.TestCase):
    def test_lists_the_period_and_each_apps_at_a_glance_numbers(self):
        self.assertEqual(
            summary(report(app("first", growth(value=69, previous=52)))),
            [
                "Weekly app report, 26 Oct to 1 Nov 2026",
                "",
                "first",
                "  New installs, 19 Oct to 25 Oct 2026: 69, +17 (+32.7%), better",
            ],
        )

    def test_says_worse_and_unchanged_in_words(self):
        fall = summary(report(app("first", growth(value=40, previous=50))))
        flat = summary(report(app("first", growth(value=50, previous=50))))
        self.assertEqual(
            fall[-1], "  New installs, 19 Oct to 25 Oct 2026: 40, −10 (−20.0%), worse"
        )
        self.assertEqual(
            flat[-1], "  New installs, 19 Oct to 25 Oct 2026: 50, no change"
        )

    def test_a_rise_from_zero_shows_no_percent(self):
        lines = summary(report(app("first", growth(value=4, previous=0))))
        self.assertEqual(
            lines[-1], "  New installs, 19 Oct to 25 Oct 2026: 4, +4, better"
        )

    def test_a_partly_covered_section_says_where_its_data_ends(self):
        coverage = Coverage(BUCKET_WEEK, date(2026, 10, 22))
        lines = summary(report(app("first", growth(coverage=coverage))))
        self.assertEqual(
            lines[-1],
            "  New installs, 19 Oct to 25 Oct 2026, data to 22 Oct: "
            "69, +17 (+32.7%), better",
        )

    def test_an_unreachable_range_says_so(self):
        lines = summary(
            report(app("first", Unavailable("Play report bucket", BUCKET_WEEK)))
        )
        self.assertEqual(
            lines[-1],
            "  New installs, 19 Oct to 25 Oct 2026: not available for this range",
        )
        self.assertNotIn("Problems:", lines)

    def test_failures_show_in_their_column_and_as_problems(self):
        failure = Failure(source="Play report bucket", error="403 Forbidden")
        self.assertEqual(
            summary(report(app("first", failure))),
            [
                "Weekly app report, 26 Oct to 1 Nov 2026",
                "",
                "Problems:",
                "  first, Play report bucket: 403 Forbidden",
                "",
                "first",
                "  New installs: Play report bucket failed, see Problems",
            ],
        )

    def test_one_line_per_at_a_glance_column_and_a_gap_between_apps(self):
        columns = (NEW_INSTALLS, installs(Better.DOWN))
        lines = summary(
            report(
                app("first", growth(value=69, previous=52)),
                app("second", growth(value=40, previous=50)),
            ),
            columns,
        )
        self.assertEqual(
            lines[2:],
            [
                "first",
                "  New installs, 19 Oct to 25 Oct 2026: 69, +17 (+32.7%), better",
                "  Installs, 19 Oct to 25 Oct 2026: 69, +17 (+32.7%), worse",
                "",
                "second",
                "  New installs, 19 Oct to 25 Oct 2026: 40, −10 (−20.0%), worse",
                "  Installs, 19 Oct to 25 Oct 2026: 40, −10 (−20.0%), better",
            ],
        )

    def test_no_apps_lists_only_the_period(self):
        self.assertEqual(
            summary(report()), ["Weekly app report, 26 Oct to 1 Nov 2026", ""]
        )


if __name__ == "__main__":
    unittest.main()
