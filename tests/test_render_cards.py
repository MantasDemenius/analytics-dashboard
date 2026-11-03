import re
import unittest
from datetime import date

from render_fixtures import (
    BUCKET_WEEK,
    LISTING_WEEK,
    NO_ADMOB,
    NO_REVIEWS,
    app,
    apps,
    cards,
    chart,
    chart_configs,
    growth,
    installs,
    listing,
    part,
    render,
    report,
    values,
)

from weekly_report import render as renderer
from weekly_report.headlines import (
    LISTING_CONVERSION,
    NEW_INSTALLS,
    Better,
)
from weekly_report.model import (
    Failure,
    Unavailable,
)
from weekly_report.periods import Coverage


class GlanceTest(unittest.TestCase):
    columns = (NEW_INSTALLS, installs(Better.DOWN))

    def glance(self, *apps) -> str:
        return part(
            render(report(*apps), glance=self.columns), '<section class="glance"'
        )

    def test_has_a_column_per_headline_and_a_row_per_app(self):
        glance = self.glance(app("first", growth()), app("second", growth()))
        self.assertEqual(
            re.findall(r"<th>(.*?)</th>", glance), ["App", "New installs", "Installs"]
        )
        body = part(glance, "<tbody>", "</tbody>")
        self.assertEqual(body.count("<tr>"), 2)
        self.assertEqual(body.count("<td"), 6)
        self.assertLess(body.index(">first<"), body.index(">second<"))

    def test_shows_each_value_with_its_change_coloured_by_better_or_worse(self):
        glance = self.glance(app("first", growth(value=69, previous=52)))
        row = part(glance, "<tbody>", "</tbody>")
        self.assertIn(">69<", row)
        self.assertIn(
            '<span class="d better"><span class="arr">▲</span>+17 (+32.7%)', row
        )
        self.assertIn(
            '<span class="d worse"><span class="arr">▲</span>+17 (+32.7%)', row
        )

    def test_every_cell_shows_its_own_range_in_the_page(self):
        coverage = Coverage(BUCKET_WEEK, date(2026, 10, 22))
        glance = self.glance(app("first", growth(coverage=coverage)))
        row = part(glance, "<tbody>", "</tbody>")
        self.assertEqual(
            re.findall(r'<span class="rng">(.*?)</span>', row),
            ["19 Oct to 25 Oct 2026, data to 22 Oct"] * 2,
        )
        self.assertNotIn("title=", row)

    def test_a_failed_and_an_unreachable_section_say_so_in_their_cells(self):
        glance = self.glance(
            app("first", Failure("Play report bucket", "403 Forbidden")),
            app("second", Unavailable("Play report bucket", BUCKET_WEEK)),
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
            report(app("first", growth()), app("second", growth())),
            cards=(NEW_INSTALLS, installs(Better.DOWN)),
        )
        for each in apps(html):
            labels = re.findall(
                r'<span class="l">(.*?)</span>', part(each, '<div class="kpis">')
            )
            self.assertEqual(labels, ["New installs", "Installs"])

    def test_a_card_shows_its_value_change_and_previous_value(self):
        [card] = cards(render(report(app("first", growth(value=69, previous=52)))))
        self.assertIn(">69<", card)
        self.assertIn(
            '<span class="d better"><span class="arr">▲</span>+17 (+32.7%)', card
        )
        self.assertIn("52 the week before", card)

    def test_a_fall_that_is_better_and_no_change(self):
        fall = cards(
            render(
                report(app("first", growth(value=40, previous=50))),
                cards=(installs(Better.DOWN),),
            )
        )[0]
        flat = cards(render(report(app("first", growth(value=50, previous=50)))))[0]
        self.assertIn(
            '<span class="d better"><span class="arr">▼</span>−10 (−20.0%)', fall
        )
        self.assertIn(
            '<span class="d neutral"><span class="arr">■</span>no change', flat
        )

    def test_a_card_shows_its_range_in_the_page_and_not_only_on_hover(self):
        [card] = cards(render(report(app("first", growth()))))
        self.assertIn('<span class="rng">19 Oct to 25 Oct 2026</span>', card)
        self.assertNotIn("title=", card)

    def test_a_card_over_an_older_week_shows_that_week(self):
        html = render(
            report(app("first", listing_section=listing())),
            cards=(NEW_INSTALLS, LISTING_CONVERSION),
        )
        installs, conversion = cards(html)
        self.assertIn('<span class="rng">19 Oct to 25 Oct 2026</span>', installs)
        self.assertIn('<span class="rng">12 Oct to 18 Oct 2026</span>', conversion)

    def test_a_card_with_data_ending_inside_its_range_says_where(self):
        coverage = Coverage(BUCKET_WEEK, date(2026, 10, 22))
        [card] = cards(render(report(app("first", growth(coverage=coverage)))))
        self.assertIn(
            '<span class="rng">19 Oct to 25 Oct 2026, data to 22 Oct</span>', card
        )

    def test_a_card_draws_its_12_period_sparkline(self):
        html = render(report(app("first", growth(value=69))))
        [card] = cards(html)
        sparkline = chart(html, "New installs, 12 weeks")
        self.assertIn("New installs, 12 weeks", card)
        self.assertEqual(
            values(sparkline), [40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 69]
        )
        self.assertIn("3 Aug", card)
        self.assertIn("19 Oct", card)

    def test_a_card_of_a_failed_section_says_so_without_a_sparkline(self):
        html = render(
            report(
                app(
                    "first",
                    Failure("Play report bucket", "boom"),
                    reviews_section=NO_REVIEWS,
                    admob_section=NO_ADMOB,
                )
            )
        )
        [card] = cards(html)
        self.assertIn('class="kpi missing failed"', html)
        self.assertIn("Play report bucket failed", card)
        self.assertNotIn("<canvas", card)
        self.assertEqual(chart_configs(html), [])

    def test_a_card_of_an_unreachable_section_says_so(self):
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
        [card] = cards(html)
        self.assertIn('class="kpi missing"', html)
        self.assertIn("not available for this range", card)
        self.assertNotIn("<canvas", card)


class DefaultCardsTest(unittest.TestCase):
    def cards(self, *apps):
        return cards(renderer.render(report(*apps)))

    def labels(self, html):
        return re.findall(r'<span class="l">(.*?)</span>', html)

    def test_are_installs_uninstalls_net_growth_listing_conversion_rating_and_both_crash_measures(
        self,
    ):
        html = renderer.render(report(app("first")))
        self.assertEqual(
            self.labels(part(html, '<div class="kpis">')),
            [
                "New installs",
                "Uninstalls",
                "Net growth",
                "Listing conversion",
                "Store rating",
                "Crash free users",
                "Play crash rate",
                "Ad earnings",
            ],
        )

    def test_a_rise_in_uninstalls_is_worse(self):
        uninstalls = self.cards(app("first", growth(uninstalls=(30, 25))))[1]
        self.assertIn(
            '<span class="d worse"><span class="arr">▲</span>+5 (+20.0%)', uninstalls
        )

    def test_net_growth_shows_its_sign(self):
        net = self.cards(app("first", growth(value=69, uninstalls=(20, 25))))[2]
        self.assertIn(">+49<", net)
        self.assertIn("+27 the week before", net)

    def test_a_negative_net_growth_is_a_minus_and_a_rise_from_it_is_better(self):
        net = self.cards(
            app("first", growth(value=10, previous=2, uninstalls=(25, 20)))
        )[2]
        self.assertIn(">−15<", net)
        self.assertIn(
            '<span class="d better"><span class="arr">▲</span>+3 (+16.7%)', net
        )

    def test_net_growth_draws_its_own_sparkline(self):
        html = renderer.render(report(app("first", growth(value=69))))
        self.assertEqual(values(chart(html, "Net growth, 12 weeks"))[-1], 49)

    def test_listing_conversion_is_a_percent_changing_in_points(self):
        conversion = self.cards(app("first", listing_section=listing(12.5, 10.0)))[3]
        self.assertIn(">12.5%<", conversion)
        self.assertIn(
            '<span class="d better"><span class="arr">▲</span>+2.5 pts', conversion
        )
        self.assertIn("10.0% the week before", conversion)

    def test_a_fall_in_listing_conversion_is_worse_and_no_change_is_flat(self):
        fall = self.cards(app("first", listing_section=listing(8.0, 10.0)))[3]
        flat = self.cards(app("first", listing_section=listing(10.0, 10.0)))[3]
        self.assertIn('<span class="d worse"><span class="arr">▼</span>−2.0 pts', fall)
        self.assertIn('<span class="arr">■</span>no change', flat)

    def test_listing_conversion_shows_the_listing_files_own_range(self):
        conversion = self.cards(app("first"))[3]
        self.assertIn("12 Oct to 18 Oct 2026", conversion)
        self.assertIn("19 Oct to 25 Oct 2026", self.cards(app("first"))[0])

    def test_a_failed_listing_fails_only_its_card_and_is_one_problem(self):
        failure = Failure("Play report bucket", "403 Forbidden")
        html = renderer.render(report(app("first", listing_section=failure)))
        shown = cards(html)
        self.assertIn('class="kpi missing failed"', html)
        self.assertEqual(html.count('class="kpi missing failed"'), 1)
        self.assertIn("Play report bucket failed", shown[3])
        self.assertIn("69", shown[0])
        self.assertEqual(part(html, '<section class="problems"').count("<li>"), 1)

    def test_an_unreachable_listing_range_says_so_and_is_no_problem(self):
        unavailable = Unavailable("Play report bucket", LISTING_WEEK)
        html = renderer.render(report(app("first", listing_section=unavailable)))
        self.assertIn("not available for this range", cards(html)[3])
        self.assertNotIn('class="problems"', html)

    def test_a_partly_covered_listing_says_where_its_data_ends(self):
        coverage = Coverage(LISTING_WEEK, date(2026, 10, 15))
        conversion = self.cards(
            app("first", listing_section=listing(coverage=coverage))
        )[3]
        self.assertIn("12 Oct to 18 Oct 2026, data to 15 Oct", conversion)


class DefaultGlanceTest(unittest.TestCase):
    def test_is_net_growth_the_store_rating_both_crash_measures_and_new_feedback(self):
        html = renderer.render(report(app("first", growth(value=69, previous=52))))
        glance = part(html, '<section class="glance"')
        self.assertEqual(
            re.findall(r"<th>(.*?)</th>", glance),
            [
                "App",
                "Net growth",
                "Store rating",
                "Crash free users",
                "Play crash rate",
                "New feedback",
                "Ad earnings",
            ],
        )
        self.assertIn(">+49<", glance)
        self.assertIn(">3.67<", glance)
        self.assertIn(">0.42%<", glance)
        self.assertIn(">97.50%<", glance)

    def test_the_email_body_lines_are_net_growth_rating_both_crash_measures_and_new_feedback(
        self,
    ):
        lines = renderer.summary(report(app("first", growth(value=69, previous=52))))
        self.assertEqual(
            lines[2:],
            [
                "first",
                "  Net growth, 19 Oct to 25 Oct 2026: +49, +22 (+81.5%), better",
                "  Store rating, 26 Oct to 1 Nov 2026: 3.67, +0.17 stars, better",
                "  Crash free users, 26 Oct to 1 Nov 2026: 97.50%, +1.50 pts, better",
                "  Play crash rate, 19 Oct to 25 Oct 2026: 0.42%, +0.07 pts, worse",
                "  New feedback, 26 Oct to 1 Nov 2026: 5, +2 (+66.7%)",
                "  Ad earnings, 26 Oct to 1 Nov 2026: 12.34 USD, +2.34 (+23.4%), better",
            ],
        )

    def test_a_listing_failure_is_a_problem_but_not_a_glance_gap(self):
        failure = Failure("Play report bucket", "403 Forbidden")
        lines = renderer.summary(report(app("first", listing_section=failure)))
        self.assertIn("  first, Play report bucket: 403 Forbidden", lines)
        self.assertEqual(lines[-6][:12], "  Net growth")
        self.assertNotIn("see Problems", "".join(lines[-6:-1]))
