import unittest
from datetime import date

from render_fixtures import (
    BUCKET_WEEK,
    REVIEWS_WEEK,
    VITALS_WEEK,
    admob,
    app,
    crashlytics,
    growth,
    installs,
    listing,
    part,
    report,
    reviews,
    summary,
    vitals,
    weekly_trend,
)

from weekly_report import render as renderer
from weekly_report.headlines import (
    AD_EARNINGS,
    ANR_RATE,
    CRASH_FREE_USERS,
    LISTING_CONVERSION,
    NEW_INSTALLS,
    PLAY_CRASH_RATE,
    STORE_RATING,
    Better,
    Figure,
    Missing,
    figure,
)
from weekly_report.model import (
    Failure,
    Growth,
    Metric,
    Point,
    Reviews,
    Unavailable,
    Vitals,
)
from weekly_report.periods import Coverage


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
        metric = Metric(value=69, previous=52, trend=trend)
        section = Growth(
            Coverage(BUCKET_WEEK, date(2026, 10, 22)), metric, metric, metric
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


class RoundedChangeTest(unittest.TestCase):
    def assert_flat(self, shown):
        self.assertEqual(
            (shown.change, shown.direction, shown.verdict),
            ("no change", "flat", "neutral"),
        )

    def test_a_rate_change_that_rounds_to_nothing_is_no_change(self):
        self.assert_flat(
            figure(PLAY_CRASH_RATE, vitals(crash=0.352, crash_before=0.35))
        )
        self.assert_flat(
            figure(PLAY_CRASH_RATE, vitals(crash=0.348, crash_before=0.35))
        )

    def test_a_rate_change_that_rounds_to_a_hundredth_is_a_change(self):
        shown = figure(PLAY_CRASH_RATE, vitals(crash=0.356, crash_before=0.35))
        self.assertEqual(
            (shown.change, shown.direction, shown.verdict), ("+0.01 pts", "up", "worse")
        )

    def test_a_listing_conversion_change_under_a_tenth_of_a_point_is_no_change(self):
        self.assert_flat(figure(LISTING_CONVERSION, listing(10.04, 10.0)))

    def test_a_store_rating_change_under_a_hundredth_of_a_star_is_no_change(self):
        self.assert_flat(figure(STORE_RATING, reviews(store=3.674, previous=3.67)))

    def test_a_crash_free_change_under_a_hundredth_of_a_point_is_no_change(self):
        self.assert_flat(
            figure(CRASH_FREE_USERS, crashlytics(free=96.004, before=96.0))
        )

    def test_an_ad_earnings_change_under_a_hundredth_is_no_change(self):
        self.assert_flat(
            figure(AD_EARNINGS, admob(earnings=10.004, earnings_before=10.0))
        )

    def test_a_count_change_is_decided_on_whole_numbers(self):
        self.assert_flat(figure(NEW_INSTALLS, growth(value=52, previous=52)))

    def test_the_email_says_no_change_without_a_verdict(self):
        page = report(
            app("first", vitals_section=vitals(crash=0.352, crash_before=0.35))
        )
        line = [x for x in summary(page, (PLAY_CRASH_RATE,)) if "Play crash" in x]
        self.assertEqual(
            line, ["  Play crash rate, 19 Oct to 25 Oct 2026: 0.35%, no change"]
        )


class UncomparableLevelTest(unittest.TestCase):
    def new_vitals(self):
        return Vitals(
            Coverage(VITALS_WEEK),
            crash_rate=Metric(0.42, 0.0, trend=weekly_trend(0.42), comparable=False),
            anr_rate=Metric(0.21, 0.0, trend=weekly_trend(0.21), comparable=False),
        )

    def test_a_rate_with_no_data_before_is_not_a_change_from_zero(self):
        shown = figure(PLAY_CRASH_RATE, self.new_vitals())
        self.assertEqual(
            (shown.value, shown.change, shown.direction, shown.verdict),
            ("0.42%", "nothing to compare", "flat", "neutral"),
        )
        self.assertEqual(shown.was, "none the week before")

    def test_an_anr_rate_with_no_data_before_is_not_compared_either(self):
        shown = figure(ANR_RATE, self.new_vitals())
        self.assertEqual(shown.change, "nothing to compare")

    def test_the_card_and_the_gauge_show_no_tick_for_the_week_before(self):
        html = renderer.render(report(app("first", vitals_section=self.new_vitals())))
        gauge = part(html, 'id="app-0-vitals"', 'id="app-0-crashlytics"')
        self.assertIn("nothing to compare", gauge)
        self.assertNotIn('class="tick"', gauge)

    def test_a_genuine_zero_rate_before_is_still_a_change(self):
        shown = figure(PLAY_CRASH_RATE, vitals(crash=0.42, crash_before=0.0))
        self.assertEqual((shown.change, shown.verdict), ("+0.42 pts", "worse"))

    def test_the_store_rating_with_no_rating_before_is_not_compared(self):
        section = Reviews(
            Coverage(REVIEWS_WEEK),
            store_rating=Metric(3.67, 0.0, comparable=False),
            new_ratings=Metric(1, 0),
            new_average=Metric(4.0, 0.0),
            breakdown={5: 0, 4: 1, 3: 0, 2: 0, 1: 0},
            reviews=(),
        )
        shown = figure(STORE_RATING, section)
        self.assertEqual(shown.change, "no ratings to compare")
        self.assertEqual(shown.was, "none the week before")
