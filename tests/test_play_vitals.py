import unittest
from datetime import date, timedelta

from weekly_report.model import Unavailable, Vitals
from weekly_report.periods import Period
from weekly_report.sources import play_vitals
from weekly_report.sources.play_bucket import SourceError

ZONE = {"id": "America/Los_Angeles"}
RATES = {
    play_vitals.CRASH_SET: play_vitals.CRASH_RATE,
    play_vitals.ANR_SET: play_vitals.ANR_RATE,
}
WEEK = Period(date(2026, 10, 19), date(2026, 10, 25))


def pacific(day: date, hours: int | None = None) -> dict:
    stamp = {"year": day.year, "month": day.month, "day": day.day, "timeZone": ZONE}
    return stamp if hours is None else stamp | {"hours": hours}


def metric_set(name: str, daily_end: dict | None) -> dict:
    freshnesses = [
        {
            "aggregationPeriod": "HOURLY",
            "latestEndTime": {
                "year": 2026,
                "month": 11,
                "day": 2,
                "hours": 14,
                "timeZone": {"id": "UTC"},
            },
        }
    ]
    if daily_end is not None:
        freshnesses.append({"aggregationPeriod": "DAILY", "latestEndTime": daily_end})
    return {
        "name": f"apps/com.example.app/{name}",
        "freshnessInfo": {"freshnesses": freshnesses},
    }


def metric_row(day: date, metrics: dict[str, str]) -> dict:
    return {
        "aggregationPeriod": "DAILY",
        "startTime": pacific(day),
        "metrics": [
            {"metric": name, "decimalValue": {"value": value}}
            for name, value in metrics.items()
        ],
    }


def day_of(stamp: dict) -> date:
    return date(stamp["year"], stamp["month"], stamp["day"])


class LastDataDayTest(unittest.TestCase):
    def test_the_daily_end_is_exclusive_so_the_day_before_it_is_the_last(self):
        fresh = metric_set("crashRateMetricSet", pacific(date(2026, 11, 2)))
        self.assertEqual(play_vitals.last_data_day(fresh), date(2026, 11, 1))

    def test_an_end_partway_through_a_day_leaves_that_day_out(self):
        fresh = metric_set("crashRateMetricSet", pacific(date(2026, 11, 1), hours=23))
        self.assertEqual(play_vitals.last_data_day(fresh), date(2026, 10, 31))

    def test_the_hourly_freshness_is_ignored(self):
        fresh = metric_set("crashRateMetricSet", pacific(date(2026, 10, 30)))
        self.assertEqual(play_vitals.last_data_day(fresh), date(2026, 10, 29))

    def test_a_metric_set_with_no_daily_freshness_is_a_source_error(self):
        fresh = metric_set("crashRateMetricSet", None)
        with self.assertRaisesRegex(SourceError, "daily"):
            play_vitals.last_data_day(fresh)


class QueryBodyTest(unittest.TestCase):
    def test_asks_for_daily_rows_in_pacific_time_from_start_to_the_day_after_end(self):
        body = play_vitals.query_body(
            "userPerceivedCrashRate", date(2026, 8, 3), date(2026, 10, 31)
        )
        self.assertEqual(
            body["timelineSpec"],
            {
                "aggregationPeriod": "DAILY",
                "startTime": pacific(date(2026, 8, 3)),
                "endTime": pacific(date(2026, 11, 1)),
            },
        )

    def test_the_end_rolls_over_a_month_and_a_year(self):
        body = play_vitals.query_body("rate", date(2026, 12, 1), date(2026, 12, 31))
        self.assertEqual(body["timelineSpec"]["endTime"], pacific(date(2027, 1, 1)))

    def test_asks_for_the_28_day_metric_and_the_plain_daily_one(self):
        body = play_vitals.query_body(
            "userPerceivedAnrRate", date(2026, 8, 3), date(2026, 10, 31)
        )
        self.assertEqual(
            body["metrics"],
            ["userPerceivedAnrRate28dUserWeighted", "userPerceivedAnrRate"],
        )


class DailyValuesTest(unittest.TestCase):
    def test_reads_the_named_metric_per_day_from_its_decimal_string(self):
        rows = [
            metric_row(date(2026, 10, 30), {"m28": "0.4120", "m": "0.9"}),
            metric_row(date(2026, 10, 31), {"m28": "0.4300", "m": "0.1"}),
        ]
        self.assertEqual(
            play_vitals.daily_values(rows, "m28"),
            {date(2026, 10, 30): 0.412, date(2026, 10, 31): 0.43},
        )

    def test_a_row_without_the_metric_is_skipped(self):
        rows = [
            metric_row(date(2026, 10, 30), {"m": "0.9"}),
            metric_row(date(2026, 10, 31), {"m28": "0.5"}),
        ]
        self.assertEqual(
            play_vitals.daily_values(rows, "m28"), {date(2026, 10, 31): 0.5}
        )

    def test_no_rows_is_no_values(self):
        self.assertEqual(play_vitals.daily_values([], "m28"), {})


def rising(last: date, start: float, step: float) -> dict[date, float]:
    first = last - timedelta(days=120)
    return {
        day: round(start + step * offset, 4)
        for offset, day in enumerate(Period(first, last).days())
    }


class Play:
    """API shaped answers for both metric sets, rows cut to each request's days."""

    def __init__(self, crash: dict[date, float], anr: dict[date, float]):
        self.daily = {play_vitals.CRASH_SET: crash, play_vitals.ANR_SET: anr}
        self.requests: list[tuple[str, dict]] = []

    @classmethod
    def steady(cls, last: date) -> Play:
        return cls(rising(last, 0.5, 0.0001), rising(last, 0.2, 0.0001))

    def metric_set(self, name: str) -> dict:
        return metric_set(name, pacific(max(self.daily[name]) + timedelta(days=1)))

    def rows(self, name: str, body: dict) -> list[dict]:
        self.requests.append((name, body))
        spec = body["timelineSpec"]
        first, end = day_of(spec["startTime"]), day_of(spec["endTime"])
        rate = RATES[name]
        return [
            metric_row(day, {rate + play_vitals.WEIGHTED: str(value), rate: "9.9999"})
            for day, value in self.daily[name].items()
            if first <= day < end
        ]

    def vitals(self, period: Period | None = None) -> Vitals | Unavailable:
        return play_vitals.vitals(self.metric_set, self.rows, period)


class VitalsPeriodTest(unittest.TestCase):
    def test_the_newest_complete_week_in_the_freshness_is_the_period(self):
        found = Play.steady(date(2026, 10, 31)).vitals()
        self.assertEqual(found.coverage.period, WEEK)
        self.assertIsNone(found.coverage.data_to)

    def test_data_to_a_sunday_gives_the_week_ending_then(self):
        found = Play.steady(date(2026, 11, 1)).vitals()
        self.assertEqual(
            found.coverage.period, Period(date(2026, 10, 26), date(2026, 11, 1))
        )

    def test_the_older_metric_set_decides(self):
        play = Play.steady(date(2026, 11, 1))
        anr = play.daily[play_vitals.ANR_SET]
        play.daily[play_vitals.ANR_SET] = {
            day: value for day, value in anr.items() if day <= date(2026, 10, 24)
        }
        self.assertEqual(
            play.vitals().coverage.period,
            Period(date(2026, 10, 12), date(2026, 10, 18)),
        )

    def test_a_requested_range_is_used_whatever_the_freshness(self):
        requested = Period(date(2026, 10, 1), date(2026, 10, 14))
        found = Play.steady(date(2026, 10, 31)).vitals(requested)
        self.assertEqual(found.coverage.period, requested)

    def test_a_range_the_data_stops_inside_says_where(self):
        requested = Period(date(2026, 10, 26), date(2026, 11, 1))
        found = Play.steady(date(2026, 10, 29)).vitals(requested)
        self.assertEqual(found.coverage.period, requested)
        self.assertEqual(found.coverage.data_to, date(2026, 10, 29))

    def test_a_range_the_data_does_not_reach_is_unavailable(self):
        requested = Period(date(2026, 11, 1), date(2026, 11, 7))
        found = Play.steady(date(2026, 10, 31)).vitals(requested)
        self.assertEqual(found, Unavailable(play_vitals.SOURCE, requested))

    def test_metric_sets_with_no_rows_are_unavailable(self):
        play = Play.steady(date(2026, 10, 31))
        play.rows = lambda name, body: []
        self.assertEqual(play.vitals(), Unavailable(play_vitals.SOURCE, WEEK))


class VitalsValuesTest(unittest.TestCase):
    def setUp(self):
        self.play = Play.steady(date(2026, 10, 31))
        self.crash = self.play.daily[play_vitals.CRASH_SET]
        self.found = self.play.vitals()

    def test_the_value_is_the_rate_on_the_periods_last_day(self):
        anr = self.play.daily[play_vitals.ANR_SET]
        self.assertEqual(self.found.crash_rate.value, self.crash[date(2026, 10, 25)])
        self.assertEqual(self.found.anr_rate.value, anr[date(2026, 10, 25)])

    def test_previous_is_the_rate_one_period_earlier(self):
        self.assertEqual(self.found.crash_rate.previous, self.crash[date(2026, 10, 18)])

    def test_the_change_is_the_rise_over_the_week(self):
        self.assertAlmostEqual(self.found.crash_rate.change, 0.0007)

    def test_the_trend_samples_the_rate_at_the_end_of_each_of_12_weeks(self):
        trend = self.found.crash_rate.trend
        self.assertEqual(len(trend), 12)
        self.assertEqual(trend[0].day, date(2026, 8, 3))
        self.assertEqual(trend[-1].day, date(2026, 10, 19))
        self.assertEqual(trend[0].value, self.crash[date(2026, 8, 9)])
        self.assertEqual(trend[-1].value, self.crash[date(2026, 10, 25)])

    def test_the_plain_daily_rate_is_never_the_value(self):
        self.assertNotEqual(self.found.crash_rate.value, 9.9999)

    def test_a_day_with_no_row_carries_the_newest_rate_before_it(self):
        del self.crash[date(2026, 10, 25)]
        self.crash[date(2026, 10, 26)] = 3.0
        found = self.play.vitals(WEEK)
        self.assertEqual(found.crash_rate.value, self.crash[date(2026, 10, 24)])

    def test_a_partly_covered_range_reads_the_last_covered_day(self):
        play = Play.steady(date(2026, 10, 29))
        crash = play.daily[play_vitals.CRASH_SET]
        found = play.vitals(Period(date(2026, 10, 26), date(2026, 11, 1)))
        self.assertEqual(found.crash_rate.value, crash[date(2026, 10, 29)])
        self.assertEqual(found.crash_rate.previous, crash[date(2026, 10, 22)])


class VitalsComparableTest(unittest.TestCase):
    def test_a_rate_with_no_row_before_the_window_is_not_compared(self):
        play = Play.steady(date(2026, 10, 31))
        for name in play.daily:
            play.daily[name] = {
                day: value
                for day, value in play.daily[name].items()
                if day >= date(2026, 10, 19)
            }
        found = play.vitals()
        self.assertFalse(found.crash_rate.comparable)
        self.assertFalse(found.anr_rate.comparable)
        self.assertEqual(found.crash_rate.previous, 0.0)

    def test_a_rate_with_rows_before_the_window_is_compared(self):
        found = Play.steady(date(2026, 10, 31)).vitals()
        self.assertTrue(found.crash_rate.comparable)


class VitalsRequestTest(unittest.TestCase):
    def test_each_set_is_queried_once_for_the_trend_days_up_to_the_last_one(self):
        play = Play.steady(date(2026, 10, 31))
        play.vitals()
        asked = dict(play.requests)
        self.assertEqual(len(play.requests), 2)
        self.assertEqual(sorted(asked), sorted(RATES))
        spec = asked[play_vitals.CRASH_SET]["timelineSpec"]
        self.assertEqual(spec["startTime"], pacific(date(2026, 8, 3)))
        self.assertEqual(spec["endTime"], pacific(date(2026, 10, 26)))

    def test_a_partly_covered_range_asks_only_up_to_the_last_data_day(self):
        play = Play.steady(date(2026, 10, 29))
        play.vitals(Period(date(2026, 10, 26), date(2026, 11, 1)))
        spec = play.requests[0][1]["timelineSpec"]
        self.assertEqual(spec["endTime"], pacific(date(2026, 10, 30)))

    def test_nothing_is_queried_when_the_range_is_out_of_reach(self):
        play = Play.steady(date(2026, 10, 31))
        play.vitals(Period(date(2026, 11, 1), date(2026, 11, 7)))
        self.assertEqual(play.requests, [])


if __name__ == "__main__":
    unittest.main()
