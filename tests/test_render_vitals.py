import unittest
from datetime import date

from render_fixtures import (
    VITALS_WEEK,
    app,
    cards,
    chart,
    part,
    report,
    values,
    vitals,
)

from weekly_report import render as renderer
from weekly_report.model import (
    Failure,
    Unavailable,
)
from weekly_report.periods import Coverage


class CrashRateCardTest(unittest.TestCase):
    def card(self, section):
        return cards(renderer.render(report(app("first", vitals_section=section))))[6]

    def test_shows_the_28_day_user_perceived_rate_as_of_the_last_day_with_its_change(
        self,
    ):
        card = self.card(vitals(crash=0.42, crash_before=0.35))
        self.assertIn(">Play crash rate<", card)
        self.assertIn("User-perceived, 28 days, as of 25 Oct", card)
        self.assertIn(">0.42%<", card)
        self.assertIn("0.35% the week before", card)
        self.assertIn("19 Oct to 25 Oct 2026", card)

    def test_a_rise_is_worse_and_shows_two_decimals_of_points(self):
        card = self.card(vitals(crash=0.42, crash_before=0.35))
        self.assertIn('<span class="d worse"><span class="arr">▲</span>+0.07 pts', card)

    def test_a_fall_is_better_and_no_change_is_flat(self):
        fall = self.card(vitals(crash=0.30, crash_before=0.35))
        flat = self.card(vitals(crash=0.35, crash_before=0.35))
        self.assertIn(
            '<span class="d better"><span class="arr">▼</span>−0.05 pts', fall
        )
        self.assertIn('<span class="arr">■</span>no change', flat)

    def test_the_date_is_the_last_day_with_data(self):
        coverage = Coverage(VITALS_WEEK, date(2026, 10, 23))
        card = self.card(vitals(coverage=coverage))
        self.assertIn("as of 23 Oct", card)
        self.assertIn("data to 23 Oct", card)

    def test_draws_its_12_week_sparkline(self):
        html = renderer.render(report(app("first", vitals_section=vitals(0.42))))
        self.assertEqual(values(chart(html, "Play crash rate, 12 weeks"))[-1], 0.42)

    def test_a_failed_vitals_source_fails_the_card(self):
        card = self.card(Failure("Play vitals", "403 Forbidden"))
        self.assertIn("Play vitals failed", card)

    def test_an_unreachable_range_says_so(self):
        card = self.card(Unavailable("Play vitals", VITALS_WEEK))
        self.assertIn("not available for this range", card)

    def test_the_email_line_says_the_rate_and_its_change(self):
        lines = renderer.summary(report(app("first")))
        self.assertEqual(
            lines[-3],
            "  Play crash rate, 19 Oct to 25 Oct 2026: 0.42%, +0.07 pts, worse",
        )


class VitalsSectionTest(unittest.TestCase):
    def section(self, **kwargs):
        html = renderer.render(report(app("first", vitals_section=vitals(**kwargs))))
        return part(html, 'id="app-0-vitals"', 'id="app-0-crashlytics"')

    def gauges(self, section):
        return section.split('<div class="vital">')[1:]

    def test_shows_its_own_range_and_the_28_day_label(self):
        section = self.section()
        self.assertIn("19 Oct to 25 Oct 2026", section)
        self.assertIn("28 days", section)

    def test_has_a_gauge_for_the_crash_rate_and_one_for_the_anr_rate(self):
        gauges = self.gauges(self.section())
        self.assertEqual(len(gauges), 2)
        self.assertIn("Crash rate", gauges[0])
        self.assertIn("ANR rate", gauges[1])

    def test_each_gauge_shows_value_change_and_last_periods_value(self):
        crash, anr = self.gauges(
            self.section(crash=0.42, crash_before=0.35, anr=0.21, anr_before=0.24)
        )
        self.assertIn(">0.42%<", crash)
        self.assertIn(
            '<span class="d worse"><span class="arr">▲</span>+0.07 pts', crash
        )
        self.assertIn("0.35% the week before", crash)
        self.assertIn(">0.21%<", anr)
        self.assertIn('<span class="d better"><span class="arr">▼</span>−0.03 pts', anr)

    def test_the_threshold_is_play_s_bad_behaviour_line_for_each(self):
        crash, anr = self.gauges(self.section())
        self.assertIn("1.09%", crash)
        self.assertIn("0.47%", anr)
        self.assertIn("bad behaviour", crash)

    def test_the_bar_the_tick_and_the_threshold_share_one_scale(self):
        crash, _ = self.gauges(self.section(crash=0.42, crash_before=0.35))
        self.assertIn('class="fill" style="width: 25.7%"', crash)
        self.assertIn('class="tick" style="left: 21.4%"', crash)
        self.assertIn('class="limit" style="left: 66.7%"', crash)

    def test_a_value_past_the_threshold_widens_the_scale_so_the_bar_fits(self):
        crash, _ = self.gauges(self.section(crash=3.0, crash_before=1.0))
        self.assertIn('class="fill over" style="width: 90.9%"', crash)
        self.assertIn('class="limit" style="left: 33.0%"', crash)

    def test_below_the_threshold_is_within_and_not_marked_over(self):
        crash, _ = self.gauges(self.section(crash=1.08))
        self.assertNotIn("fill over", crash)
        self.assertIn("Below the bad behaviour threshold", crash)

    def test_at_the_threshold_is_over_because_play_counts_at_least(self):
        crash, _ = self.gauges(self.section(crash=1.09))
        self.assertIn('class="fill over"', crash)
        self.assertIn("Above the bad behaviour threshold", crash)

    def test_each_rate_is_judged_against_its_own_threshold(self):
        crash, anr = self.gauges(self.section(crash=0.6, anr=0.6))
        self.assertNotIn("fill over", crash)
        self.assertIn('class="fill over"', anr)

    def test_a_partly_covered_section_says_where_its_data_ends(self):
        coverage = Coverage(VITALS_WEEK, date(2026, 10, 23))
        self.assertIn("data to 23 Oct", self.section(coverage=coverage))

    def test_a_failed_source_shows_its_error_in_a_full_width_card(self):
        failure = Failure("Play vitals", "403 Forbidden")
        html = renderer.render(report(app("first", vitals_section=failure)))
        section = part(html, 'id="app-0-vitals"')
        self.assertIn('class="card wide"', section)
        self.assertIn("Play vitals: 403 Forbidden", section)

    def test_an_unreachable_range_says_so_and_is_no_problem(self):
        unavailable = Unavailable("Play vitals", VITALS_WEEK)
        html = renderer.render(report(app("first", vitals_section=unavailable)))
        self.assertIn("not available for this range", part(html, 'id="app-0-vitals"'))
        self.assertNotIn('class="problems"', html)
