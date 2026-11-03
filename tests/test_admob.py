import unittest
from datetime import date, timedelta

from weekly_report.model import AdMob, Point, Unavailable
from weekly_report.periods import Period
from weekly_report.sources import admob

TODAY = date(2026, 11, 3)
WEEK = Period(date(2026, 10, 26), date(2026, 11, 1))
BEFORE = WEEK.previous()
BANNER = "unit-banner"
REWARDED = "unit-rewarded"


def stamp(day: date) -> dict:
    return {"year": day.year, "month": day.month, "day": day.day}


def header(currency: str = "USD") -> dict:
    return {
        "header": {
            "dateRange": {"startDate": stamp(WEEK.start), "endDate": stamp(WEEK.end)},
            "localizationSettings": {"currencyCode": currency},
        }
    }


def footer(rows: list) -> dict:
    return {"footer": {"matchingRowCount": str(len(rows))}} if rows else {"footer": {}}


def metrics(micros: int, impressions: int) -> dict:
    return {
        "ESTIMATED_EARNINGS": {"microsValue": str(micros)},
        "IMPRESSIONS": {"integerValue": str(impressions)},
    }


def unit_row(
    day: date,
    unit: str,
    name: str,
    format_: str,
    micros: int,
    impressions: int,
) -> dict:
    return {
        "row": {
            "dimensionValues": {
                "DATE": {"value": f"{day:%Y%m%d}"},
                "AD_UNIT": {"value": unit, "displayLabel": name},
                "FORMAT": {"value": format_},
                "APP": {"value": "app-one"},
            },
            "metricValues": metrics(micros, impressions),
        }
    }


def month_row(month: date, micros: int, impressions: int = 1000) -> dict:
    return {
        "row": {
            "dimensionValues": {"MONTH": {"value": f"{month:%Y%m}"}},
            "metricValues": metrics(micros, impressions),
        }
    }


def stream(rows: list[dict], currency: str = "USD") -> list[dict]:
    return [header(currency), *rows, footer(rows)]


class FakeAdMob:
    """Answers like AdMob's networkReport: a stream of header, rows and footer per request."""

    def __init__(self, daily: list[dict], monthly: list[dict] | None = None):
        self.daily = daily
        self.monthly = monthly or []
        self.requests: list[dict] = []

    def __call__(self, body: dict) -> list[dict]:
        self.requests.append(body)
        dimensions = body["reportSpec"]["dimensions"]
        return self.daily if "DATE" in dimensions else self.monthly


def one_unit_week(micros_per_day: int = 1_500_000, impressions: int = 1000):
    return stream(
        [
            unit_row(day, BANNER, "Home banner", "banner", micros_per_day, impressions)
            for day in WEEK.days()
        ]
    )


def report(
    daily: list[dict],
    monthly: list[dict] | None = None,
    period: Period | None = WEEK,
    today: date = TODAY,
) -> AdMob | Unavailable:
    return admob.admob(FakeAdMob(daily, monthly), today, period)


class EarningsTest(unittest.TestCase):
    def test_micros_become_whole_units_of_the_account_currency(self):
        section = report(one_unit_week(micros_per_day=1_500_000))
        self.assertEqual(section.earnings.value, 10.5)

    def test_the_currency_is_the_one_the_report_header_names(self):
        self.assertEqual(report(stream([], currency="EUR")).currency, "EUR")


class RequestTest(unittest.TestCase):
    def requests(self) -> list[dict]:
        fake = FakeAdMob(one_unit_week())
        admob.admob(fake, TODAY, WEEK)
        return [request["reportSpec"] for request in fake.requests]

    def test_one_call_by_day_ad_unit_and_format_and_one_by_month(self):
        daily, monthly = self.requests()
        self.assertEqual(daily["dimensions"], ["DATE", "AD_UNIT", "FORMAT"])
        self.assertEqual(monthly["dimensions"], ["MONTH"])

    def test_both_ask_for_earnings_and_impressions_only(self):
        for spec in self.requests():
            self.assertEqual(spec["metrics"], ["ESTIMATED_EARNINGS", "IMPRESSIONS"])

    def test_the_daily_call_spans_the_12_periods_ending_with_the_covered_days(self):
        daily, _ = self.requests()
        self.assertEqual(
            daily["dateRange"],
            {"startDate": stamp(date(2026, 8, 10)), "endDate": stamp(WEEK.end)},
        )

    def test_the_daily_call_stops_at_the_last_day_with_data(self):
        fake = FakeAdMob(one_unit_week())
        admob.admob(fake, date(2026, 10, 30), WEEK)
        self.assertEqual(
            fake.requests[0]["reportSpec"]["dateRange"]["endDate"],
            stamp(date(2026, 10, 29)),
        )

    def test_the_monthly_call_spans_the_24_complete_months_before_the_range_ends(self):
        _, monthly = self.requests()
        self.assertEqual(
            monthly["dateRange"],
            {
                "startDate": stamp(date(2024, 11, 1)),
                "endDate": stamp(date(2026, 10, 31)),
            },
        )

    def test_a_range_ending_on_a_month_s_last_day_includes_that_month(self):
        fake = FakeAdMob(one_unit_week())
        october = Period(date(2026, 10, 25), date(2026, 10, 31))
        admob.admob(fake, TODAY, october)
        self.assertEqual(
            fake.requests[1]["reportSpec"]["dateRange"]["endDate"],
            stamp(date(2026, 10, 31)),
        )


def two_units() -> list[dict]:
    """The banner earns 2 units on each of 3 days; the rewarded unit 10 units on 2 days, one of
    them in the week before."""
    return stream(
        [
            unit_row(WEEK.start, BANNER, "Home banner", "banner", 2_000_000, 400),
            unit_row(WEEK.start, REWARDED, "Bonus", "rewarded", 10_000_000, 50),
            unit_row(
                WEEK.start + timedelta(days=2),
                BANNER,
                "Home banner",
                "banner",
                2_000_000,
                600,
            ),
            unit_row(
                WEEK.start + timedelta(days=4),
                BANNER,
                "Home banner",
                "banner",
                2_000_000,
                200,
            ),
            unit_row(BEFORE.start, REWARDED, "Bonus", "rewarded", 4_000_000, 20),
        ]
    )


class UnitsTest(unittest.TestCase):
    def setUp(self):
        self.section = report(two_units())
        self.rewarded, self.banner = self.section.units

    def test_there_is_one_entry_per_ad_unit_biggest_earner_first(self):
        self.assertEqual(
            [unit.name for unit in self.section.units], ["Bonus", "Home banner"]
        )

    def test_a_unit_s_earnings_and_impressions_are_its_own(self):
        self.assertEqual(self.banner.earnings.value, 6)
        self.assertEqual(self.banner.impressions.value, 1200)
        self.assertEqual(self.rewarded.earnings.value, 10)
        self.assertEqual(self.rewarded.impressions.value, 50)

    def test_the_account_totals_add_every_unit(self):
        self.assertEqual(self.section.earnings.value, 16)
        self.assertEqual(self.section.impressions.value, 1250)

    def test_a_unit_day_without_a_row_counts_as_zero(self):
        self.assertEqual(
            [point.value for point in self.banner.earnings.series],
            [2, 0, 2, 0, 2, 0, 0],
        )
        self.assertEqual(
            [point.value for point in self.rewarded.impressions.series],
            [50, 0, 0, 0, 0, 0, 0],
        )

    def test_a_unit_has_the_changes_against_the_week_before(self):
        self.assertEqual(self.rewarded.earnings.previous, 4)
        self.assertEqual(self.banner.earnings.previous, 0)

    def test_a_unit_keeps_the_format_its_rows_name(self):
        self.assertEqual(self.banner.formats, ("banner",))

    def test_a_unit_that_served_two_formats_lists_both_once_alphabetically(self):
        rows = [
            unit_row(WEEK.start, BANNER, "Home banner", "native", 1_000_000, 10),
            unit_row(WEEK.end, BANNER, "Home banner", "banner", 1_000_000, 10),
            unit_row(WEEK.end, BANNER, "Home banner", "native", 1_000_000, 10),
        ]
        (unit,) = report(stream(rows)).units
        self.assertEqual(unit.formats, ("banner", "native"))

    def test_the_12_period_trend_of_a_unit_is_its_total_per_period(self):
        self.assertEqual(
            self.rewarded.earnings.trend[-2:],
            (
                Point(BEFORE.start, 4),
                Point(WEEK.start, 10),
            ),
        )

    def test_a_unit_with_equal_earnings_sorts_by_name(self):
        rows = [
            unit_row(WEEK.start, REWARDED, "Bonus", "rewarded", 1_000_000, 1),
            unit_row(WEEK.start, BANNER, "Alpha", "banner", 1_000_000, 1),
        ]
        self.assertEqual(
            [unit.name for unit in report(stream(rows)).units], ["Alpha", "Bonus"]
        )

    def test_no_rows_at_all_means_no_units_and_zero_totals(self):
        section = report(stream([]))
        self.assertEqual(section.units, ())
        self.assertEqual(section.earnings.value, 0)
        self.assertEqual(section.impressions.value, 0)


class EcpmTest(unittest.TestCase):
    def setUp(self):
        self.section = report(two_units())
        self.rewarded, self.banner = self.section.units

    def test_a_unit_s_ecpm_is_its_earnings_per_1000_impressions_over_the_period(self):
        self.assertEqual(self.banner.ecpm.value, 5)
        self.assertEqual(self.rewarded.ecpm.value, 200)

    def test_it_is_not_the_average_of_the_daily_ecpms(self):
        daily = [2 / 400 * 1000, 2 / 600 * 1000, 2 / 200 * 1000]
        self.assertNotAlmostEqual(self.banner.ecpm.value, sum(daily) / 3)

    def test_the_account_ecpm_divides_the_summed_earnings_by_the_summed_impressions(
        self,
    ):
        self.assertAlmostEqual(self.section.ecpm.value, 12.8)

    def test_the_previous_period_s_ecpm_is_from_that_period_s_sums(self):
        self.assertEqual(self.rewarded.ecpm.previous, 200)
        self.assertEqual(self.section.ecpm.previous, 200)

    def test_a_period_without_impressions_has_an_ecpm_of_zero(self):
        self.assertEqual(self.banner.ecpm.previous, 0)

    def test_each_period_of_the_trend_divides_its_own_sums(self):
        trend = {point.day: point.value for point in self.section.ecpm.trend}
        self.assertEqual(trend[BEFORE.start], 200)
        self.assertAlmostEqual(trend[WEEK.start], 12.8)
        self.assertEqual(trend[BEFORE.previous().start], 0)


class MonthlyTest(unittest.TestCase):
    def months(self, monthly: list[dict], **extra):
        return report(one_unit_week(), stream(monthly), **extra).monthly

    def test_each_month_is_its_earnings_dated_by_its_first_day(self):
        monthly = self.months(
            [
                month_row(date(2026, 8, 1), 120_500_000),
                month_row(date(2026, 9, 1), 130_000_000),
                month_row(date(2026, 10, 1), 90_250_000),
            ]
        )
        self.assertEqual(
            monthly,
            (
                Point(date(2026, 8, 1), 120.5),
                Point(date(2026, 9, 1), 130),
                Point(date(2026, 10, 1), 90.25),
            ),
        )

    def test_months_come_oldest_first_whatever_order_the_api_answers_in(self):
        monthly = self.months(
            [
                month_row(date(2026, 10, 1), 3_000_000),
                month_row(date(2026, 9, 1), 2_000_000),
            ]
        )
        self.assertEqual(
            [point.day for point in monthly], [date(2026, 9, 1), date(2026, 10, 1)]
        )

    def test_a_month_the_api_has_no_row_for_is_left_out(self):
        monthly = self.months(
            [
                month_row(date(2026, 8, 1), 1_000_000),
                month_row(date(2026, 10, 1), 1_000_000),
            ]
        )
        self.assertEqual([point.day.month for point in monthly], [8, 10])

    def test_no_rows_means_no_months(self):
        self.assertEqual(self.months([]), ())


class CoverageTest(unittest.TestCase):
    def test_a_range_that_starts_today_or_later_is_unavailable(self):
        range_ = Period(TODAY, TODAY + timedelta(days=6))
        self.assertEqual(
            report(stream([]), period=range_), Unavailable(admob.SOURCE, range_)
        )

    def test_an_unavailable_range_calls_nothing(self):
        fake = FakeAdMob(stream([]))
        admob.admob(fake, TODAY, Period(TODAY, TODAY))
        self.assertEqual(fake.requests, [])

    def test_a_range_running_past_yesterday_is_covered_to_yesterday(self):
        section = report(one_unit_week(), period=Period(WEEK.start, TODAY))
        self.assertEqual(section.coverage.data_to, date(2026, 11, 2))

    def test_the_week_before_is_cut_to_the_covered_days(self):
        rows = [
            unit_row(day, BANNER, "Home banner", "banner", 1_000_000, 100)
            for day in [*BEFORE.days(), *WEEK.days(), date(2026, 11, 2)]
        ]
        section = report(stream(rows), period=Period(WEEK.start, TODAY))
        self.assertEqual(section.earnings.value, 8)
        self.assertEqual(section.earnings.previous, 6)

    def test_without_a_range_it_is_the_week_that_just_ended(self):
        section = report(one_unit_week(), period=None)
        self.assertEqual(section.coverage.period, WEEK)

    def test_an_ordinary_week_has_complete_data(self):
        self.assertIsNone(report(one_unit_week()).coverage.data_to)


if __name__ == "__main__":
    unittest.main()
