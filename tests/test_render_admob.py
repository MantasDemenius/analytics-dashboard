import re
import unittest
from datetime import date

from render_fixtures import (
    ADMOB_WEEK,
    ad_unit,
    admob,
    app,
    cards,
    chart,
    part,
    report,
    values,
)

from weekly_report import render as renderer
from weekly_report.model import (
    Failure,
    Unavailable,
)
from weekly_report.periods import Coverage


class AdEarningsCardTest(unittest.TestCase):
    def card(self, section):
        html = renderer.render(report(app("first", admob_section=section)))
        return cards(html)[-1]

    def test_is_the_last_default_card_and_the_last_glance_column(self):
        html = renderer.render(report(app("first")))
        labels = re.findall(
            r'<span class="l">(.*?)</span>', part(html, '<div class="kpis">')
        )
        self.assertEqual(labels[-1], "Ad earnings")
        glance = part(html, '<section class="glance"')
        self.assertEqual(re.findall(r"<th>(.*?)</th>", glance)[-1], "Ad earnings")

    def test_shows_the_earnings_in_the_account_currency_with_its_change(self):
        card = self.card(admob(earnings=12.34, earnings_before=10.0))
        self.assertIn(">12.34 USD<", card)
        self.assertIn(
            '<span class="d better"><span class="arr">▲</span>+2.34 (+23.4%)', card
        )
        self.assertIn("10.00 USD the week before", card)

    def test_names_whatever_currency_the_account_has(self):
        self.assertIn(">12.34 EUR<", self.card(admob(currency="EUR")))

    def test_groups_thousands(self):
        card = self.card(admob(earnings=1234.5, earnings_before=1000))
        self.assertIn(">1,234.50 USD<", card)

    def test_a_fall_is_worse_and_no_change_is_flat(self):
        fall = self.card(admob(earnings=8.5, earnings_before=10))
        flat = self.card(admob(earnings=10, earnings_before=10))
        self.assertIn(
            '<span class="d worse"><span class="arr">▼</span>−1.50 (−15.0%)', fall
        )
        self.assertIn(
            '<span class="d neutral"><span class="arr">■</span>no change', flat
        )

    def test_a_rise_from_nothing_shows_no_percent(self):
        card = self.card(admob(earnings=3.2, earnings_before=0))
        self.assertIn("▲</span>+3.20<", card)

    def test_a_change_under_a_cent_is_no_change(self):
        card = self.card(admob(earnings=10.004, earnings_before=10))
        self.assertIn("no change", card)

    def test_draws_its_12_period_sparkline(self):
        html = renderer.render(
            report(app("first", admob_section=admob(earnings=12.34)))
        )
        self.assertEqual(values(chart(html, "Ad earnings, 12 weeks"))[-1], 12.34)

    def test_a_failed_source_fails_the_card(self):
        card = self.card(Failure("AdMob", "403 Forbidden"))
        self.assertIn("AdMob failed", card)

    def test_an_unreachable_range_says_so(self):
        card = self.card(Unavailable("AdMob", ADMOB_WEEK))
        self.assertIn("not available for this range", card)

    def test_the_email_line_says_the_earnings_and_their_change(self):
        lines = renderer.summary(report(app("first")))
        self.assertEqual(
            lines[-1],
            "  Ad earnings, 26 Oct to 1 Nov 2026: 12.34 USD, +2.34 (+23.4%), better",
        )

    def test_a_partly_covered_range_says_where_the_data_ends(self):
        coverage = Coverage(ADMOB_WEEK, date(2026, 10, 30))
        page = report(app("first", admob_section=admob(coverage=coverage)))
        self.assertIn(
            "26 Oct to 1 Nov 2026, data to 30 Oct: 12.34 USD",
            renderer.summary(page)[-1],
        )


class AdMobSectionTest(unittest.TestCase):
    STACK = "Ad earnings per ad unit over the last 12 weeks"

    def html(self, **kwargs):
        return renderer.render(report(app("first", admob_section=admob(**kwargs))))

    def section(self, **kwargs):
        return part(self.html(**kwargs), 'id="app-0-admob"', "</section>\n</div>")

    def test_has_a_nav_link_and_names_its_range_and_currency(self):
        section = self.section(currency="EUR")
        self.assertIn("26 Oct to 1 Nov 2026", section)
        self.assertIn("EUR", section)
        self.assertIn('<a href="#app-0-admob">AdMob: ad earnings</a>', self.html())

    def test_shows_earnings_impressions_and_ecpm_with_their_changes(self):
        section = self.section()
        self.assertIn(">12.34 USD<", section)
        self.assertIn(">5,000<", section)
        self.assertIn("4,000 the week before", section)
        self.assertIn(">2.47 USD<", section)
        self.assertIn("2.50 USD the week before", section)

    def test_a_lower_ecpm_is_worse_and_more_impressions_are_better(self):
        section = self.section(
            impressions=5000, impressions_before=4000, ecpm=2.0, ecpm_before=2.5
        )
        self.assertIn(
            '<span class="d better"><span class="arr">▲</span>+1,000 (+25.0%)',
            section,
        )
        self.assertIn(
            '<span class="d worse"><span class="arr">▼</span>−0.50 (−20.0%)', section
        )

    def test_lists_every_ad_unit_in_order_with_its_format_and_numbers(self):
        units = [
            ad_unit(
                "Level end", ("interstitial",), (9.5, 7.0), (800, 700), (11.88, 10.0)
            ),
            ad_unit(
                "Home banner",
                ("banner", "native"),
                (2.84, 3.0),
                (4200, 4300),
                (0.68, 0.7),
            ),
        ]
        section = self.section(units=units)
        rows = part(section, "<tbody>", "</tbody>").split("<tr")[1:]
        self.assertEqual(len(rows), 2)
        self.assertIn("Level end", rows[0])
        self.assertIn("interstitial", rows[0])
        self.assertIn(">9.50<", rows[0])
        self.assertIn("+2.50 (+35.7%)", rows[0])
        self.assertIn("800", rows[0])
        self.assertIn(">11.88<", rows[0])
        self.assertIn("Home banner", rows[1])
        self.assertIn("banner", rows[1])
        self.assertIn("native", rows[1])
        self.assertIn("4,200", rows[1])

    def test_the_unit_name_is_escaped(self):
        section = self.section(units=[ad_unit("<b>Hot</b> unit")])
        self.assertNotIn("<b>Hot</b>", section)
        self.assertIn("&lt;b&gt;Hot&lt;/b&gt; unit", section)

    def test_stacks_12_periods_of_earnings_a_layer_per_unit(self):
        units = [
            ad_unit("Level end", stack=(1.0, 2.0)),
            ad_unit("Home banner", stack=(3.0, 4.0)),
        ]
        config = chart(self.html(units=units), self.STACK)
        self.assertEqual(config["type"], "bar")
        self.assertEqual(
            [dataset["label"] for dataset in config["data"]["datasets"]],
            ["Level end", "Home banner"],
        )
        self.assertEqual(len(config["data"]["labels"]), 12)
        self.assertEqual(config["data"]["datasets"][1]["data"][-2:], [3.0, 4.0])
        self.assertTrue(config["options"]["scales"]["x"]["stacked"])
        self.assertTrue(config["options"]["scales"]["y"]["stacked"])

    def test_every_unit_gets_its_own_colour(self):
        units = [ad_unit(f"Unit {number}") for number in range(6)]
        config = chart(self.html(units=units), self.STACK)
        colours = [dataset["backgroundColor"] for dataset in config["data"]["datasets"]]
        self.assertEqual(len(set(colours)), 6)

    def test_draws_the_earnings_of_every_month_oldest_first(self):
        config = chart(self.html(), "Ad earnings per month")
        self.assertEqual(config["data"]["labels"], ["Aug 2026", "Sep 2026", "Oct 2026"])
        self.assertEqual(values(config), [120.5, 130.0, 90.25])

    def test_draws_no_monthly_chart_without_months(self):
        self.assertNotIn("Ad earnings per month", self.html(monthly=()))

    def test_a_range_without_ad_traffic_says_so_and_draws_no_stack(self):
        section = self.section(units=[], earnings=0, earnings_before=0)
        self.assertIn("No ad traffic in this range.", section)
        self.assertNotIn(self.STACK, section)

    def test_a_partly_covered_section_says_where_its_data_ends(self):
        section = self.section(coverage=Coverage(ADMOB_WEEK, date(2026, 10, 30)))
        self.assertIn("26 Oct to 1 Nov 2026, data to 30 Oct", section)

    def test_a_failed_source_shows_its_error_in_a_full_width_card(self):
        failure = Failure("AdMob", "403 Forbidden")
        html = renderer.render(report(app("first", admob_section=failure)))
        section = part(html, 'id="app-0-admob"')
        self.assertIn('class="card wide"', section)
        self.assertIn("AdMob: 403 Forbidden", section)

    def test_an_unreachable_range_says_so_and_is_no_problem(self):
        unavailable = Unavailable("AdMob", ADMOB_WEEK)
        html = renderer.render(report(app("first", admob_section=unavailable)))
        self.assertIn("not available for this range", part(html, 'id="app-0-admob"'))
        self.assertNotIn('class="problems"', html)
