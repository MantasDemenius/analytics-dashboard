import json
import re
import unittest
from datetime import date, datetime, timedelta

from weekly_report import render as renderer
from weekly_report.model import (
    AppReport,
    Crashlytics,
    ErrorKind,
    Failure,
    Growth,
    Issue,
    IssueState,
    Label,
    Listing,
    Metric,
    Point,
    Report,
    Review,
    Reviews,
    Signal,
    Unavailable,
    Vitals,
)
from weekly_report.periods import Coverage, Period
from weekly_report.render import (
    NEW_INSTALLS,
    SECTIONS,
    Better,
    Figure,
    Headline,
    Missing,
    figure,
    signed,
)

REPORT_WEEK = Period(date(2026, 10, 26), date(2026, 11, 1))
BUCKET_WEEK = Period(date(2026, 10, 19), date(2026, 10, 25))
LISTING_WEEK = Period(date(2026, 10, 12), date(2026, 10, 18))
GENERATED = datetime(2026, 11, 2, 8, 0)


def weekly_trend(value):
    return tuple(
        Point(date(2026, 8, 3) + timedelta(weeks=week), 40 + week) for week in range(11)
    ) + (Point(date(2026, 10, 19), value),)


def growth(value=69, previous=52, coverage=None, uninstalls=(20, 25)):
    coverage = coverage or Coverage(BUCKET_WEEK)
    series = tuple(Point(day, 10) for day in coverage.covered.days())
    gone, gone_before = uninstalls
    return Growth(
        coverage=coverage,
        installs=Metric(
            value=value, previous=previous, series=series, trend=weekly_trend(value)
        ),
        uninstalls=Metric(
            value=gone,
            previous=gone_before,
            series=tuple(Point(day, 3) for day in coverage.covered.days()),
            trend=weekly_trend(gone),
        ),
        net=Metric(
            value=value - gone,
            previous=previous - gone_before,
            trend=weekly_trend(value - gone),
        ),
    )


def listing(conversion=12.5, previous=10.0, coverage=None):
    return Listing(
        coverage=coverage or Coverage(LISTING_WEEK),
        visitors=Metric(value=400, previous=380),
        acquisitions=Metric(value=50, previous=38),
        conversion=Metric(
            value=conversion, previous=previous, trend=weekly_trend(conversion)
        ),
    )


REVIEWS_WEEK = Period(date(2026, 10, 26), date(2026, 11, 1))


def review(
    text="Works well",
    stars=4,
    label=Label.NEW,
    title="",
    original_text=None,
    language=None,
    reply=None,
    at=datetime(2026, 10, 28, 12, 0),
):
    return Review(stars, title, text, original_text, language, label, at, reply)


def reviews(
    store=3.67,
    previous=3.5,
    average=4.5,
    average_before=4.0,
    count=4,
    count_before=3,
    cards=(),
    uncovered=(),
    coverage=None,
    breakdown=None,
):
    return Reviews(
        coverage=coverage or Coverage(REVIEWS_WEEK),
        store_rating=Metric(store, previous, trend=weekly_trend(store)),
        new_ratings=Metric(count, count_before, trend=weekly_trend(count)),
        new_average=Metric(average, average_before, trend=weekly_trend(average)),
        breakdown=breakdown or {5: 2, 4: 1, 3: 1, 2: 0, 1: 0},
        reviews=tuple(cards),
        uncovered=tuple(uncovered),
    )


VITALS_WEEK = Period(date(2026, 10, 19), date(2026, 10, 25))


def vitals(crash=0.42, crash_before=0.35, anr=0.21, anr_before=0.24, coverage=None):
    return Vitals(
        coverage=coverage or Coverage(VITALS_WEEK),
        crash_rate=Metric(crash, crash_before, trend=weekly_trend(crash)),
        anr_rate=Metric(anr, anr_before, trend=weekly_trend(anr)),
    )


CRASHLYTICS_WEEK = Period(date(2026, 10, 26), date(2026, 11, 1))


def issue(
    title="Widget.render",
    users=3,
    events=7,
    signals=(),
    kind=ErrorKind.FATAL,
    state=IssueState.OPEN,
    subtitle="NullPointerException",
    version="2.3.0",
    link="https://console.example/widget",
):
    return Issue(
        title, subtitle, kind, state, tuple(signals), users, events, version, link
    )


def crashlytics(free=97.5, before=96.0, issues=(), coverage=None):
    return Crashlytics(
        coverage=coverage or Coverage(CRASHLYTICS_WEEK),
        crash_free=Metric(free, before, trend=weekly_trend(free)),
        issues=tuple(issues),
    )


def app(
    name,
    growth_section=None,
    listing_section=None,
    reviews_section=None,
    vitals_section=None,
    crashlytics_section=None,
):
    return AppReport(
        name,
        growth() if growth_section is None else growth_section,
        listing() if listing_section is None else listing_section,
        reviews() if reviews_section is None else reviews_section,
        vitals() if vitals_section is None else vitals_section,
        crashlytics() if crashlytics_section is None else crashlytics_section,
    )


def render(page, cards=(NEW_INSTALLS,), glance=(NEW_INSTALLS,), sections=SECTIONS):
    return renderer.render(page, cards, glance, sections)


def summary(page, glance=(NEW_INSTALLS,)):
    return renderer.summary(page, glance)


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
    found = []
    for block in re.findall(
        r'<div class="kpis">(.*?)<div class="grid"', html, re.DOTALL
    ):
        found += re.split(r'<div class="kpi[ "]', block)[1:]
    return found


NO_REVIEWS = Unavailable("Play reviews", REVIEWS_WEEK)


def installs(better):
    return Headline("Installs", "growth", lambda section: section.installs, better)


class SignedTest(unittest.TestCase):
    def test_marks_a_rise_and_a_fall(self):
        self.assertEqual(signed(2.5, 1, " pts"), "+2.5 pts")
        self.assertEqual(signed(-2.5, 1, " pts"), "−2.5 pts")

    def test_a_change_that_rounds_to_nothing_has_no_sign(self):
        self.assertEqual(signed(0.04, 1, " pts"), "0.0 pts")
        self.assertEqual(signed(-0.04, 1, " pts"), "0.0 pts")

    def test_no_change_has_no_sign(self):
        self.assertEqual(signed(0), "0")


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
                )
            )
        )
        [card] = cards(html)
        self.assertIn('class="kpi missing"', html)
        self.assertIn("not available for this range", card)
        self.assertNotIn("<canvas", card)


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
                "Play crash rate",
                "Crash free users",
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


class StoreRatingCardTest(unittest.TestCase):
    def card(self, section):
        return cards(renderer.render(report(app("first", reviews_section=section))))[4]

    def test_shows_the_28_day_average_as_of_the_last_day_with_its_change(self):
        card = self.card(reviews(store=3.67, previous=3.5))
        self.assertIn(">Store rating<", card)
        self.assertIn("28 day average rating, as of 1 Nov", card)
        self.assertIn(">3.67<", card)
        self.assertIn(
            '<span class="d better"><span class="arr">▲</span>+0.17 stars', card
        )
        self.assertIn("3.50 the week before", card)

    def test_a_fall_is_worse_and_no_change_is_flat(self):
        fall = self.card(reviews(store=3.4, previous=3.5))
        flat = self.card(reviews(store=3.5, previous=3.5))
        self.assertIn(
            '<span class="d worse"><span class="arr">▼</span>−0.10 stars', fall
        )
        self.assertIn('<span class="arr">■</span>no change', flat)

    def test_the_date_is_the_last_day_with_data(self):
        coverage = Coverage(REVIEWS_WEEK, date(2026, 10, 30))
        card = self.card(reviews(coverage=coverage))
        self.assertIn("as of 30 Oct", card)

    def test_draws_its_12_week_sparkline(self):
        html = renderer.render(report(app("first", reviews_section=reviews(3.67))))
        self.assertEqual(values(chart(html, "Store rating, 12 weeks"))[-1], 3.67)

    def test_with_no_rating_yet_it_says_none_and_compares_nothing(self):
        card = self.card(reviews(store=0, previous=0))
        self.assertIn(">none<", card)
        self.assertIn("no ratings to compare", card)
        self.assertIn('<span class="d neutral">', card)

    def test_a_rating_with_nothing_before_it_is_not_compared(self):
        card = self.card(reviews(store=4.0, previous=0))
        self.assertIn(">4.00<", card)
        self.assertIn('<span class="d neutral">', card)

    def test_a_failed_reviews_source_fails_the_card(self):
        card = self.card(Failure("Play reviews", "403 Forbidden"))
        self.assertIn("Play reviews failed", card)

    def test_an_unreachable_range_says_so(self):
        self.assertIn("not available for this range", self.card(NO_REVIEWS))

    def test_the_email_line_says_the_rating_and_its_change(self):
        lines = renderer.summary(report(app("first")))
        self.assertEqual(
            lines[-3], "  Store rating, 26 Oct to 1 Nov 2026: 3.67, +0.17 stars, better"
        )


class CrashRateCardTest(unittest.TestCase):
    def card(self, section):
        return cards(renderer.render(report(app("first", vitals_section=section))))[5]

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
            lines[-2],
            "  Play crash rate, 19 Oct to 25 Oct 2026: 0.42%, +0.07 pts, worse",
        )


class VitalsSectionTest(unittest.TestCase):
    def section(self, **kwargs):
        html = renderer.render(report(app("first", vitals_section=vitals(**kwargs))))
        return part(html, 'id="app-0-vitals"', "</section>\n</div>")

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


class CrashFreeCardTest(unittest.TestCase):
    def card(self, section):
        return cards(
            renderer.render(report(app("first", crashlytics_section=section)))
        )[6]

    def test_shows_the_percent_with_two_decimals_and_the_previous_value(self):
        card = self.card(crashlytics(free=97.5, before=96.0))
        self.assertIn(">Crash free users<", card)
        self.assertIn(">97.50%<", card)
        self.assertIn("96.00% the week before", card)
        self.assertIn("26 Oct to 1 Nov 2026", card)

    def test_a_rise_is_better_and_shows_points(self):
        card = self.card(crashlytics(free=97.5, before=96.0))
        self.assertIn(
            '<span class="d better"><span class="arr">▲</span>+1.50 pts', card
        )

    def test_a_fall_is_worse_and_no_change_is_flat(self):
        fall = self.card(crashlytics(free=95.0, before=96.0))
        flat = self.card(crashlytics(free=96.0, before=96.0))
        self.assertIn('<span class="d worse"><span class="arr">▼</span>−1.00 pts', fall)
        self.assertIn('<span class="arr">■</span>no change', flat)

    def test_a_previous_period_past_the_90_days_is_not_compared(self):
        card = self.card(crashlytics(free=97.5, before=0))
        self.assertIn("nothing to compare", card)
        self.assertIn("none the week before", card)
        self.assertIn('<span class="d neutral">', card)

    def test_a_period_with_no_users_says_none(self):
        card = self.card(crashlytics(free=0, before=0))
        self.assertIn(">none<", card)

    def test_the_note_says_what_it_counts_and_the_days_it_uses(self):
        self.assertIn("fatal crashes, UTC days", self.card(crashlytics()))

    def test_draws_its_12_week_sparkline(self):
        html = renderer.render(
            report(app("first", crashlytics_section=crashlytics(free=97.5)))
        )
        self.assertEqual(values(chart(html, "Crash free users, 12 weeks"))[-1], 97.5)

    def test_a_trend_cut_short_by_the_limit_draws_what_there_is(self):
        short = Crashlytics(
            Coverage(CRASHLYTICS_WEEK),
            Metric(97.5, 0, trend=(Point(CRASHLYTICS_WEEK.start, 97.5),)),
            (),
        )
        html = renderer.render(report(app("first", crashlytics_section=short)))
        self.assertEqual(values(chart(html, "Crash free users, 12 weeks")), [97.5])

    def test_a_failed_crashlytics_source_fails_the_card(self):
        card = self.card(Failure("Crashlytics", "403 Forbidden"))
        self.assertIn("Crashlytics failed", card)

    def test_an_unreachable_range_says_so(self):
        card = self.card(Unavailable("Crashlytics", CRASHLYTICS_WEEK))
        self.assertIn("not available for this range", card)

    def test_the_email_line_says_the_percent_and_its_change(self):
        lines = renderer.summary(report(app("first")))
        self.assertEqual(
            lines[-1],
            "  Crash free users, 26 Oct to 1 Nov 2026: 97.50%, +1.50 pts, better",
        )

    def test_the_at_a_glance_table_ends_with_crash_free_users(self):
        glance = part(renderer.render(report(app("first"))), '<section class="glance"')
        self.assertEqual(
            re.findall(r"<th>(.*?)</th>", glance)[-2:],
            ["Play crash rate", "Crash free users"],
        )


class CrashlyticsSectionTest(unittest.TestCase):
    def section(self, issues=(), **kwargs):
        section = crashlytics(issues=issues, **kwargs)
        html = renderer.render(report(app("first", crashlytics_section=section)))
        return part(html, 'id="app-0-crashlytics"', "</section>\n</div>")

    def rows(self, section):
        return section.split('<tr class="issue')[1:]

    def test_has_a_nav_link_and_names_its_range(self):
        section = self.section()
        self.assertIn(">Issues<", section)
        self.assertIn("26 Oct to 1 Nov 2026", section)
        html = renderer.render(report(app("first")))
        self.assertIn('<a href="#app-0-crashlytics">Crashlytics: issues</a>', html)

    def test_counts_the_issues(self):
        self.assertIn("2 issues", self.section([issue("a"), issue("b")]))
        self.assertIn("1 issue<", self.section([issue("a")]))

    def test_lists_every_issue_in_the_order_given(self):
        rows = self.rows(self.section([issue(f"issue-{n}") for n in range(60)]))
        self.assertEqual(len(rows), 60)
        self.assertIn("issue-0<", rows[0])
        self.assertIn("issue-59<", rows[59])

    def test_a_row_shows_users_events_and_the_version_it_was_first_seen_in(self):
        [row] = self.rows(self.section([issue(users=12, events=1034, version="2.3.0")]))
        self.assertIn('<td class="n">12</td>', row)
        self.assertIn('<td class="n">1,034</td>', row)
        self.assertIn("2.3.0", row)

    def test_a_missing_version_shows_a_dash(self):
        [row] = self.rows(self.section([issue(version=None)]))
        self.assertIn("<td>–</td>", row)

    def test_a_row_shows_the_title_the_subtitle_and_the_kind_of_error(self):
        [row] = self.rows(
            self.section(
                [issue("Widget.render", subtitle="IllegalState", kind=ErrorKind.ANR)]
            )
        )
        self.assertIn("Widget.render", row)
        self.assertIn("IllegalState", row)
        self.assertIn('<span class="tag">ANR</span>', row)

    def test_names_each_kind_of_error(self):
        kinds = self.section(
            [issue(kind=ErrorKind.FATAL), issue(kind=ErrorKind.NON_FATAL)]
        )
        self.assertIn(">Crash<", kinds)
        self.assertIn(">Non-fatal<", kinds)

    def test_the_title_links_to_the_console(self):
        [row] = self.rows(self.section([issue(link="https://console.example/x")]))
        self.assertIn('<a href="https://console.example/x"', row)

    def test_an_issue_without_a_link_has_a_plain_title(self):
        [row] = self.rows(self.section([issue("plain", link=None)]))
        self.assertNotIn("<a ", row)
        self.assertIn("plain", row)

    def test_a_new_issue_is_called_out(self):
        [row] = self.rows(self.section([issue(signals=[Signal.FRESH])]))
        self.assertIn('<span class="tag fresh">New</span>', row)
        self.assertTrue(row.startswith(" attention"))

    def test_a_regressed_issue_is_called_out(self):
        [row] = self.rows(self.section([issue(signals=[Signal.REGRESSED])]))
        self.assertIn('<span class="tag regressed">Regressed</span>', row)
        self.assertTrue(row.startswith(" attention"))

    def test_the_other_signals_are_named_but_not_called_out(self):
        [row] = self.rows(
            self.section([issue(signals=[Signal.EARLY, Signal.REPETITIVE])])
        )
        self.assertIn('<span class="tag early">Early</span>', row)
        self.assertIn('<span class="tag repetitive">Repetitive</span>', row)
        self.assertFalse(row.startswith(" attention"))

    def test_an_issue_with_no_signals_has_no_signal_tags(self):
        [row] = self.rows(self.section([issue()]))
        for name in ("New", "Regressed", "Early", "Repetitive"):
            self.assertNotIn(f">{name}<", row)

    def test_a_closed_or_muted_issue_says_so_and_an_open_one_does_not(self):
        closed, muted, open_ = self.rows(
            self.section(
                [
                    issue(state=IssueState.CLOSED),
                    issue(state=IssueState.MUTED),
                    issue(state=IssueState.OPEN),
                ]
            )
        )
        self.assertIn(">Closed<", closed)
        self.assertIn(">Muted<", muted)
        self.assertNotIn(">Open<", open_)

    def test_issue_text_is_escaped(self):
        [row] = self.rows(self.section([issue("<b>x</b>", subtitle="a & b")]))
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", row)
        self.assertIn("a &amp; b", row)

    def test_no_issues_says_so(self):
        section = self.section()
        self.assertIn("No issues in this range.", section)
        self.assertNotIn("<table", section)

    def test_a_partly_covered_section_says_where_its_data_ends(self):
        coverage = Coverage(CRASHLYTICS_WEEK, date(2026, 10, 30))
        self.assertIn("data to 30 Oct", self.section(coverage=coverage))

    def test_a_failed_source_shows_its_error_in_a_full_width_card(self):
        failure = Failure("Crashlytics", "403 Forbidden")
        html = renderer.render(report(app("first", crashlytics_section=failure)))
        section = part(html, 'id="app-0-crashlytics"')
        self.assertIn('class="card wide"', section)
        self.assertIn("Crashlytics: 403 Forbidden", section)

    def test_an_unreachable_range_says_so_and_is_no_problem(self):
        unavailable = Unavailable("Crashlytics", CRASHLYTICS_WEEK)
        html = renderer.render(report(app("first", crashlytics_section=unavailable)))
        self.assertIn(
            "not available for this range", part(html, 'id="app-0-crashlytics"')
        )
        self.assertNotIn('class="problems"', html)


class ReviewsSectionTest(unittest.TestCase):
    def section(self, **kwargs):
        html = renderer.render(report(app("first", reviews_section=reviews(**kwargs))))
        return html, part(html, 'id="app-0-reviews"', "</section>\n</div>")

    def test_shows_its_own_range(self):
        _, section = self.section()
        self.assertIn("26 Oct to 1 Nov 2026", section)

    def test_shows_the_new_ratings_average_and_count_with_changes(self):
        _, section = self.section(
            average=4.5, average_before=4.0, count=4, count_before=3
        )
        self.assertIn("Average of new ratings", section)
        self.assertIn(">4.50<", section)
        self.assertIn("+0.50 stars", section)
        self.assertIn("4.00 the week before", section)
        self.assertIn(">4<", section)
        self.assertIn("+1 (+33.3%)", section)

    def test_a_week_with_no_new_ratings_says_none(self):
        _, section = self.section(
            average=0, average_before=4.0, count=0, count_before=3
        )
        self.assertIn(">none<", section)
        self.assertIn("no ratings to compare", section)

    def test_draws_the_star_breakdown_from_five_stars_to_one(self):
        html, _ = self.section(breakdown={5: 6, 4: 3, 3: 2, 2: 1, 1: 0})
        bars = chart(html, "New ratings by star level")
        self.assertEqual(
            bars["data"]["labels"], ["5 star", "4 star", "3 star", "2 star", "1 star"]
        )
        self.assertEqual(values(bars), [6, 3, 2, 1, 0])
        self.assertEqual(bars["options"]["indexAxis"], "y")

    def test_a_card_per_review_newest_first_in_the_full_width_card(self):
        _, section = self.section(
            cards=[
                review("second text", at=datetime(2026, 10, 30)),
                review("first text", at=datetime(2026, 10, 27)),
            ]
        )
        self.assertIn('class="card wide"', section)
        self.assertEqual(section.count('class="note review"'), 2)
        self.assertLess(section.index("second text"), section.index("first text"))
        self.assertIn("2 with text", section)

    def test_a_card_shows_stars_title_text_and_date(self):
        _, section = self.section(
            cards=[
                review("Works well", stars=4, title="Solid", at=datetime(2026, 10, 28))
            ]
        )
        self.assertIn("★★★★☆", section)
        self.assertIn('aria-label="4 out of 5 stars"', section)
        self.assertIn('<p class="rtitle">Solid</p>', section)
        self.assertIn('<p class="rtext">Works well</p>', section)
        self.assertIn("28 Oct 2026", section)

    def test_a_review_without_a_title_or_a_text_leaves_those_out(self):
        _, titled = self.section(cards=[review("", title="Only a title")])
        _, texted = self.section(cards=[review("Only text")])
        self.assertIn("Only a title", titled)
        self.assertNotIn('class="rtext"', titled)
        self.assertNotIn('class="rtitle"', texted)

    def test_each_label_shows_as_a_tag(self):
        _, section = self.section(
            cards=[
                review("a", label=Label.NEW),
                review("b", label=Label.EDITED),
                review("c", label=Label.NEW_OR_EDITED),
            ]
        )
        self.assertIn('<span class="tag new">New</span>', section)
        self.assertIn('<span class="tag edited">Edited</span>', section)
        self.assertIn('<span class="tag new_or_edited">New or edited</span>', section)

    def test_a_review_only_the_report_has_shows_its_language_tag(self):
        _, tagged = self.section(cards=[review("Sehr gut", language="de")])
        _, untagged = self.section(cards=[review("Great")])
        self.assertIn('<span class="tag">de</span>', tagged)
        self.assertNotIn('<span class="tag">', untagged)

    def test_a_translation_shows_with_the_original_below_it(self):
        _, section = self.section(cards=[review("Very good", original_text="Sehr gut")])
        self.assertLess(section.index("Very good"), section.index("Sehr gut"))
        self.assertIn(
            '<p class="original"><span class="tag">original</span> Sehr gut</p>',
            section,
        )

    def test_an_untranslated_review_has_no_original(self):
        _, section = self.section(cards=[review("Great")])
        self.assertNotIn('class="original"', section)

    def test_a_replied_review_is_marked_and_shows_the_reply(self):
        _, section = self.section(
            cards=[review("Bad", reply="We are sorry"), review("Fine")]
        )
        self.assertEqual(section.count('<span class="tag replied">replied</span>'), 1)
        self.assertIn('<p class="reply"><b>Your reply</b> We are sorry</p>', section)

    def test_the_reply_text_is_left_out_of_the_printed_pdf(self):
        html, _ = self.section(cards=[review("Bad", reply="We are sorry")])
        printed = html[html.index("@media print") :]
        self.assertIn(".reply { display: none; }", printed)
        self.assertNotIn(
            ".reply { display: none; }", html[: html.index("@media print")]
        )

    def test_review_text_is_escaped(self):
        html, _ = self.section(cards=[review("<script>alert(1)</script>")])
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)

    def test_no_reviews_says_so(self):
        _, section = self.section(cards=[])
        self.assertIn("No reviews with text in this range.", section)
        self.assertIn("0 with text", section)

    def test_a_range_the_sources_miss_part_of_gets_the_too_late_notice(self):
        gaps = [Period(date(2026, 10, 26), date(2026, 10, 27))]
        _, section = self.section(uncovered=gaps)
        self.assertIn('class="caution"', section)
        self.assertIn("Reviews from 26 Oct to 27 Oct 2026 may be missing", section)

    def test_a_fully_covered_range_has_no_notice(self):
        _, section = self.section()
        self.assertNotIn("caution", section)

    def test_several_gaps_are_all_named(self):
        gaps = [
            Period(date(2026, 10, 26), date(2026, 10, 27)),
            Period(date(2026, 10, 31), date(2026, 11, 1)),
        ]
        _, section = self.section(uncovered=gaps)
        self.assertIn(
            "26 Oct to 27 Oct 2026, 31 Oct to 1 Nov 2026 may be missing", section
        )

    def test_a_failed_source_shows_its_error_in_a_full_width_card(self):
        failure = Failure("Play reviews", "403 Forbidden")
        html = renderer.render(report(app("first", reviews_section=failure)))
        section = part(html, 'id="app-0-reviews"')
        self.assertIn('class="card wide"', section)
        self.assertIn("Play reviews: 403 Forbidden", section)

    def test_an_unreachable_range_says_so_and_is_no_problem(self):
        html = renderer.render(report(app("first", reviews_section=NO_REVIEWS)))
        self.assertIn("not available for this range", part(html, 'id="app-0-reviews"'))
        self.assertNotIn('class="problems"', html)


class DefaultGlanceTest(unittest.TestCase):
    def test_is_net_growth_the_store_rating_and_both_crash_measures(self):
        html = renderer.render(report(app("first", growth(value=69, previous=52))))
        glance = part(html, '<section class="glance"')
        self.assertEqual(
            re.findall(r"<th>(.*?)</th>", glance),
            [
                "App",
                "Net growth",
                "Store rating",
                "Play crash rate",
                "Crash free users",
            ],
        )
        self.assertIn(">+49<", glance)
        self.assertIn(">3.67<", glance)
        self.assertIn(">0.42%<", glance)
        self.assertIn(">97.50%<", glance)

    def test_the_email_body_lines_are_net_growth_rating_and_both_crash_measures(self):
        lines = renderer.summary(report(app("first", growth(value=69, previous=52))))
        self.assertEqual(
            lines[2:],
            [
                "first",
                "  Net growth, 19 Oct to 25 Oct 2026: +49, +22 (+81.5%), better",
                "  Store rating, 26 Oct to 1 Nov 2026: 3.67, +0.17 stars, better",
                "  Play crash rate, 19 Oct to 25 Oct 2026: 0.42%, +0.07 pts, worse",
                "  Crash free users, 26 Oct to 1 Nov 2026: 97.50%, +1.50 pts, better",
            ],
        )

    def test_a_listing_failure_is_a_problem_but_not_a_glance_gap(self):
        failure = Failure("Play report bucket", "403 Forbidden")
        lines = renderer.summary(report(app("first", listing_section=failure)))
        self.assertIn("  first, Play report bucket: 403 Forbidden", lines)
        self.assertEqual(lines[-4][:12], "  Net growth")
        self.assertNotIn("see Problems", "".join(lines[-4:]))


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
