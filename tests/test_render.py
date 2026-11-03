import json
import re
import unittest
from datetime import date, datetime, timedelta

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
from weekly_report.render import (
    NEW_INSTALLS,
    Better,
    Figure,
    Headline,
    Missing,
    figure,
    render,
    summary,
)

REPORT_WEEK = Period(date(2026, 10, 26), date(2026, 11, 1))
BUCKET_WEEK = Period(date(2026, 10, 19), date(2026, 10, 25))
GENERATED = datetime(2026, 11, 2, 8, 0)


def weekly_trend(value):
    return tuple(
        Point(date(2026, 8, 3) + timedelta(weeks=week), 40 + week) for week in range(11)
    ) + (Point(date(2026, 10, 19), value),)


def growth(value=69, previous=52, coverage=None):
    coverage = coverage or Coverage(BUCKET_WEEK)
    series = tuple(Point(day, 10) for day in coverage.covered.days())
    return Growth(
        coverage=coverage,
        installs=Metric(
            value=value, previous=previous, series=series, trend=weekly_trend(value)
        ),
    )


def report(*apps, period=REPORT_WEEK):
    return Report(period=period, apps=apps, generated=GENERATED)


def chart_configs(html: str) -> list:
    match = re.search(r"const CHARTS = (.*?);\n", html)
    return json.loads(match.group(1))


def chart(html: str, label: str) -> dict:
    [canvas_id] = re.findall(
        rf'<canvas id="([\w-]+)" role="img" aria-label="{label}"', html
    )
    return dict(chart_configs(html))[canvas_id]


def values(config: dict) -> list:
    return config["data"]["datasets"][0]["data"]


def part(html: str, start: str, end: str = "</section>") -> str:
    begin = html.index(start)
    return html[begin : html.index(end, begin)]


def apps(html: str) -> list[str]:
    return html.split('<section class="app"')[1:]


def cards(html: str) -> list[str]:
    return re.split(r'<div class="kpi[ "]', html)[1:]


def installs(better):
    return Headline("Installs", "growth", lambda section: section.installs, better)


class FigureTest(unittest.TestCase):
    def test_a_rise_in_a_number_that_should_rise_is_better(self):
        shown = figure(installs(Better.UP), growth(value=69, previous=52))
        self.assertEqual(
            (shown.value, shown.change, shown.direction, shown.verdict),
            ("69", "+17 (+32.7%)", "up", "better"),
        )

    def test_a_rise_in_a_number_that_should_fall_is_worse(self):
        shown = figure(installs(Better.DOWN), growth(value=69, previous=52))
        self.assertEqual((shown.direction, shown.verdict), ("up", "worse"))

    def test_a_fall_in_a_number_that_should_fall_is_better(self):
        shown = figure(installs(Better.DOWN), growth(value=40, previous=50))
        self.assertEqual(
            (shown.change, shown.direction, shown.verdict),
            ("−10 (−20.0%)", "down", "better"),
        )

    def test_a_fall_in_a_number_that_should_rise_is_worse(self):
        shown = figure(installs(Better.UP), growth(value=40, previous=50))
        self.assertEqual((shown.direction, shown.verdict), ("down", "worse"))

    def test_a_change_in_a_number_with_no_better_side_is_neutral(self):
        shown = figure(installs(Better.NEITHER), growth(value=69, previous=52))
        self.assertEqual((shown.direction, shown.verdict), ("up", "neutral"))

    def test_no_change_is_flat_and_neutral(self):
        shown = figure(installs(Better.UP), growth(value=52, previous=52))
        self.assertEqual(
            (shown.change, shown.direction, shown.verdict),
            ("no change", "flat", "neutral"),
        )

    def test_a_rise_from_zero_has_no_percent(self):
        shown = figure(installs(Better.UP), growth(value=4, previous=0))
        self.assertEqual(shown.change, "+4")

    def test_carries_the_previous_value_the_range_and_the_trend(self):
        trend = (Point(date(2026, 8, 3), 40), Point(date(2026, 8, 10), 52))
        section = Growth(
            Coverage(BUCKET_WEEK, date(2026, 10, 22)),
            Metric(value=69, previous=52, trend=trend),
        )
        shown = figure(NEW_INSTALLS, section)
        self.assertIsInstance(shown, Figure)
        self.assertEqual(shown.label, "New installs")
        self.assertEqual(shown.was, "52 the 4 days before")
        self.assertEqual(shown.range, "19 Oct to 25 Oct 2026, data to 22 Oct")
        self.assertEqual(shown.trend, trend)

    def test_a_failed_section_is_missing_and_names_its_source(self):
        shown = figure(NEW_INSTALLS, Failure("Play report bucket", "403 Forbidden"))
        self.assertEqual(
            shown, Missing("New installs", "", "Play report bucket failed", failed=True)
        )

    def test_an_unreachable_section_is_missing_with_its_range(self):
        shown = figure(NEW_INSTALLS, Unavailable("Play report bucket", BUCKET_WEEK))
        self.assertEqual(
            shown,
            Missing(
                "New installs",
                "19 Oct to 25 Oct 2026",
                "not available for this range",
                failed=False,
            ),
        )


class TopTest(unittest.TestCase):
    def test_shows_the_report_range_and_when_it_was_made(self):
        html = render(report(AppReport("first", growth())))
        top = part(html, '<header class="top"', "</header>")
        self.assertIn("26 Oct to 1 Nov 2026", top)
        self.assertIn("generated Mon 2 Nov 2026, 08:00", top)

    def test_the_key_says_what_every_change_is_against(self):
        week = render(report(AppReport("first", growth())))
        ten_days = render(
            report(
                AppReport("first", growth()),
                period=Period(date(2026, 10, 1), date(2026, 10, 10)),
            )
        )
        self.assertIn("Every change is against the week before", week)
        self.assertIn("Every change is against the 10 days before", ten_days)


class GlanceTest(unittest.TestCase):
    columns = (NEW_INSTALLS, installs(Better.DOWN))

    def glance(self, *apps) -> str:
        return part(
            render(report(*apps), glance=self.columns), '<section class="glance"'
        )

    def test_has_a_column_per_headline_and_a_row_per_app(self):
        glance = self.glance(
            AppReport("first", growth()), AppReport("second", growth())
        )
        self.assertEqual(
            re.findall(r"<th>(.*?)</th>", glance), ["App", "New installs", "Installs"]
        )
        body = part(glance, "<tbody>", "</tbody>")
        self.assertEqual(body.count("<tr>"), 2)
        self.assertEqual(body.count("<td"), 6)
        self.assertLess(body.index(">first<"), body.index(">second<"))

    def test_shows_each_value_with_its_change_coloured_by_better_or_worse(self):
        glance = self.glance(AppReport("first", growth(value=69, previous=52)))
        row = part(glance, "<tbody>", "</tbody>")
        self.assertIn(">69<", row)
        self.assertIn(
            '<span class="d better"><span class="arr">▲</span>+17 (+32.7%)', row
        )
        self.assertIn(
            '<span class="d worse"><span class="arr">▲</span>+17 (+32.7%)', row
        )

    def test_a_failed_and_an_unreachable_section_say_so_in_their_cells(self):
        glance = self.glance(
            AppReport("first", Failure("Play report bucket", "403 Forbidden")),
            AppReport("second", Unavailable("Play report bucket", BUCKET_WEEK)),
        )
        self.assertEqual(glance.count("Play report bucket failed"), 2)
        self.assertEqual(glance.count("not available for this range"), 2)
        self.assertNotIn("403 Forbidden", glance)

    def test_no_apps_leaves_an_empty_table(self):
        glance = self.glance()
        self.assertEqual(part(glance, "<tbody>", "</tbody>").count("<tr>"), 0)


class NumberCardTest(unittest.TestCase):
    def test_each_app_gets_a_card_per_headline_in_order(self):
        html = render(
            report(AppReport("first", growth()), AppReport("second", growth())),
            cards=(NEW_INSTALLS, installs(Better.DOWN)),
        )
        for app in apps(html):
            labels = re.findall(
                r'<span class="l">(.*?)</span>', part(app, '<div class="kpis">')
            )
            self.assertEqual(labels, ["New installs", "Installs"])

    def test_a_card_shows_its_value_change_and_previous_value(self):
        [card] = cards(
            render(report(AppReport("first", growth(value=69, previous=52))))
        )
        self.assertIn(">69<", card)
        self.assertIn(
            '<span class="d better"><span class="arr">▲</span>+17 (+32.7%)', card
        )
        self.assertIn("52 the week before", card)

    def test_a_fall_that_is_better_and_no_change(self):
        fall = cards(
            render(
                report(AppReport("first", growth(value=40, previous=50))),
                cards=(installs(Better.DOWN),),
            )
        )[0]
        flat = cards(render(report(AppReport("first", growth(value=50, previous=50)))))[
            0
        ]
        self.assertIn(
            '<span class="d better"><span class="arr">▼</span>−10 (−20.0%)', fall
        )
        self.assertIn(
            '<span class="d neutral"><span class="arr">■</span>no change', flat
        )

    def test_a_card_draws_its_12_period_sparkline(self):
        html = render(report(AppReport("first", growth(value=69))))
        [card] = cards(html)
        sparkline = chart(html, "New installs, 12 weeks")
        self.assertIn("New installs, 12 weeks", card)
        self.assertEqual(
            values(sparkline), [40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 69]
        )
        self.assertIn("3 Aug", card)
        self.assertIn("19 Oct", card)

    def test_a_card_of_a_failed_section_says_so_without_a_sparkline(self):
        html = render(report(AppReport("first", Failure("Play report bucket", "boom"))))
        [card] = cards(html)
        self.assertIn('class="kpi missing failed"', html)
        self.assertIn("Play report bucket failed", card)
        self.assertNotIn("<canvas", card)
        self.assertEqual(chart_configs(html), [])

    def test_a_card_of_an_unreachable_section_says_so(self):
        html = render(
            report(AppReport("first", Unavailable("Play report bucket", BUCKET_WEEK)))
        )
        [card] = cards(html)
        self.assertIn('class="kpi missing"', html)
        self.assertIn("not available for this range", card)
        self.assertNotIn("<canvas", card)


class GrowthSectionTest(unittest.TestCase):
    def test_shows_its_own_range(self):
        html = render(report(AppReport("first", growth())))
        self.assertIn("19 Oct to 25 Oct 2026", part(html, 'id="app-0-growth"'))

    def test_draws_the_daily_installs_chart(self):
        html = render(report(AppReport("first", growth())))
        daily = chart(html, "Daily new installs")
        self.assertEqual(daily["type"], "bar")
        self.assertEqual(values(daily), [10] * 7)
        self.assertEqual(daily["data"]["labels"][0], "Mon 19 Oct")

    def test_draws_the_12_period_trend(self):
        html = render(report(AppReport("first", growth(value=69))))
        trend = chart(html, "New installs over the last 12 weeks")
        self.assertEqual(trend["type"], "line")
        self.assertEqual(values(trend)[-1], 69)
        self.assertEqual(trend["data"]["labels"][0], "3 Aug")
        self.assertIn("Last 12 weeks", html)

    def test_a_partly_covered_section_says_where_its_data_ends(self):
        coverage = Coverage(BUCKET_WEEK, date(2026, 10, 22))
        html = render(report(AppReport("first", growth(coverage=coverage))))
        self.assertIn("19 Oct to 25 Oct 2026, data to 22 Oct", html)
        self.assertIn("52 the 4 days before", html)
        self.assertEqual(len(values(chart(html, "Daily new installs"))), 4)

    def test_a_range_that_is_not_a_week_names_its_length(self):
        coverage = Coverage(Period(date(2026, 10, 1), date(2026, 10, 10)))
        html = render(report(AppReport("first", growth(coverage=coverage))))
        self.assertIn("52 the 10 days before", html)
        self.assertIn("Last 12 periods of 10 days", html)

    def test_a_single_day_range(self):
        coverage = Coverage(Period(date(2026, 10, 1), date(2026, 10, 1)))
        html = render(report(AppReport("first", growth(coverage=coverage))))
        self.assertIn("52 the day before", html)
        self.assertIn("Last 12 days", html)

    def test_an_unreachable_range_says_so_and_is_no_problem(self):
        html = render(
            report(AppReport("first", Unavailable("Play report bucket", BUCKET_WEEK)))
        )
        section = part(html, 'id="app-0-growth"')
        self.assertIn("not available for this range", section)
        self.assertIn("19 Oct to 25 Oct 2026", section)
        self.assertNotIn('class="problems"', html)
        self.assertEqual(chart_configs(html), [])

    def test_a_failed_section_shows_its_error_in_a_full_width_card(self):
        failure = Failure(source="Play report bucket", error="403 Forbidden")
        html = render(report(AppReport("first", failure)))
        section = part(html, 'id="app-0-growth"')
        self.assertIn('class="card wide"', section)
        self.assertIn("Play report bucket: 403 Forbidden", section)

    def test_a_fall_shows_a_minus(self):
        html = render(report(AppReport("first", growth(value=40, previous=50))))
        self.assertIn("−10", html)
        self.assertIn("−20.0%", html)

    def test_a_rise_from_zero_has_no_percent(self):
        html = render(report(AppReport("first", growth(value=4, previous=0))))
        self.assertIn("+4", html)
        self.assertNotIn("%</", html)


class PageTest(unittest.TestCase):
    def test_every_app_gets_its_own_part_with_its_name(self):
        html = render(
            report(AppReport("first", growth()), AppReport("second", growth()))
        )
        first, second = apps(html)
        self.assertIn(">first<", first)
        self.assertIn(">second<", second)

    def test_inlines_chart_js_with_animation_off(self):
        html = render(report(AppReport("first", growth())))
        self.assertIn("Chart.js v4.4.1", html)
        self.assertIn("Released under the MIT License", html)
        self.assertLess(
            html.index("Chart.defaults.animation = false"), html.index("new Chart(")
        )
        self.assertNotIn("<script src=", html)

    def test_prints_on_a4_with_each_app_on_a_new_page(self):
        html = render(report(AppReport("first", growth())))
        self.assertIn("@page { size: A4;", html)
        self.assertIn(".app + .app { break-before: page;", html)

    def test_grid_columns_shrink_and_cards_do_not_split(self):
        html = render(report(AppReport("first", growth())))
        self.assertIn("repeat(4, minmax(0, 1fr))", html)
        self.assertIn("minmax(0, 1fr) minmax(0, 1fr)", html)
        self.assertNotRegex(html, r"repeat\(\d, 1fr\)")
        self.assertRegex(html, r"\.kpi \{[^}]*break-inside: avoid")
        self.assertRegex(html, r"\.card \{[^}]*break-inside: avoid")

    def test_forces_chart_canvas_size_only_when_printing(self):
        html = render(report(AppReport("first", growth())))
        forced = [
            match.start() for match in re.finditer(r"width: 100% !important", html)
        ]
        self.assertEqual(len(forced), 1)
        self.assertLess(html.index("@media print"), forced[0])


class ProblemsTest(unittest.TestCase):
    def test_no_failures_means_no_problems_box(self):
        html = render(report(AppReport("first", growth())))
        self.assertNotIn('class="problems"', html)

    def test_a_failed_source_shows_in_the_problems_box_and_its_section(self):
        failure = Failure(source="Play report bucket", error="403 Forbidden")
        html = render(report(AppReport("first", failure)))
        problems = part(html, '<section class="problems"')
        self.assertIn("<b>first</b>, Play report bucket: 403 Forbidden", problems)
        self.assertEqual(html.count("403 Forbidden"), 2)

    def test_the_problems_box_comes_before_the_at_a_glance_table(self):
        failure = Failure(source="Play report bucket", error="403 Forbidden")
        html = render(report(AppReport("first", failure)))
        self.assertLess(
            html.index('<section class="problems"'),
            html.index('<section class="glance"'),
        )

    def test_lists_every_failure_of_every_app(self):
        html = render(
            report(
                AppReport("first", Failure("Play report bucket", "403 Forbidden")),
                AppReport("second", Failure("Play report bucket", "timed out")),
            )
        )
        problems = part(html, '<section class="problems"')
        self.assertEqual(problems.count("<li>"), 2)
        self.assertIn("<b>second</b>, Play report bucket: timed out", problems)

    def test_error_text_is_escaped(self):
        failure = Failure(source="Play report bucket", error="<b>bad</b>")
        html = render(report(AppReport("first", failure)))
        self.assertNotIn("<b>bad</b>", html)
        self.assertIn("&lt;b&gt;bad&lt;/b&gt;", html)


class SummaryTest(unittest.TestCase):
    def test_lists_the_period_and_each_apps_at_a_glance_numbers(self):
        self.assertEqual(
            summary(report(AppReport("first", growth(value=69, previous=52)))),
            [
                "Weekly app report, 26 Oct to 1 Nov 2026",
                "",
                "first",
                "  New installs, 19 Oct to 25 Oct 2026: 69, +17 (+32.7%), better",
            ],
        )

    def test_says_worse_and_unchanged_in_words(self):
        fall = summary(report(AppReport("first", growth(value=40, previous=50))))
        flat = summary(report(AppReport("first", growth(value=50, previous=50))))
        self.assertEqual(
            fall[-1], "  New installs, 19 Oct to 25 Oct 2026: 40, −10 (−20.0%), worse"
        )
        self.assertEqual(
            flat[-1], "  New installs, 19 Oct to 25 Oct 2026: 50, no change"
        )

    def test_a_rise_from_zero_shows_no_percent(self):
        lines = summary(report(AppReport("first", growth(value=4, previous=0))))
        self.assertEqual(
            lines[-1], "  New installs, 19 Oct to 25 Oct 2026: 4, +4, better"
        )

    def test_a_partly_covered_section_says_where_its_data_ends(self):
        coverage = Coverage(BUCKET_WEEK, date(2026, 10, 22))
        lines = summary(report(AppReport("first", growth(coverage=coverage))))
        self.assertEqual(
            lines[-1],
            "  New installs, 19 Oct to 25 Oct 2026, data to 22 Oct: "
            "69, +17 (+32.7%), better",
        )

    def test_an_unreachable_range_says_so(self):
        lines = summary(
            report(AppReport("first", Unavailable("Play report bucket", BUCKET_WEEK)))
        )
        self.assertEqual(
            lines[-1],
            "  New installs, 19 Oct to 25 Oct 2026: not available for this range",
        )
        self.assertNotIn("Problems:", lines)

    def test_failures_show_in_their_column_and_as_problems(self):
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
                "  New installs: Play report bucket failed, see Problems",
            ],
        )

    def test_one_line_per_at_a_glance_column_and_a_gap_between_apps(self):
        columns = (NEW_INSTALLS, installs(Better.DOWN))
        lines = summary(
            report(
                AppReport("first", growth(value=69, previous=52)),
                AppReport("second", growth(value=40, previous=50)),
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
