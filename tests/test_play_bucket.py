import unittest
from datetime import date, timedelta

from weekly_report.model import Unavailable
from weekly_report.periods import Period
from weekly_report.sources import play_bucket
from weekly_report.sources.play_bucket import (
    SourceError,
    daily_totals,
    installs_path,
    store_performance_path,
)

PACKAGE = "com.example.app"
HEADER = (
    "Date,Package name,Daily Device Installs,Daily Device Uninstalls,"
    "Daily Device Upgrades,Total User Installs,Daily User Installs,"
    "Daily User Uninstalls,Active Device Installs,Install events,"
    "Update events,Uninstall events"
)


def installs_csv(
    rows: dict[str, int], uninstalls: dict[str, int] | None = None
) -> bytes:
    lines = [HEADER] + [
        f"{day},{PACKAGE},9,0,0,0,{installs},"
        f"{1 if uninstalls is None else uninstalls[day]},40,11,2,1"
        for day, installs in rows.items()
    ]
    return "\r\n".join(lines).encode("utf-16")


STORE_HEADER = (
    "Date,Package name,Country / region,Store listing acquisitions,"
    "Store listing visitors,Store listing conversion rate"
)


def store_csv(rows: list[tuple[str, str, int, int]]) -> bytes:
    """Rows of (day, country, visitors, acquisitions), the daily rate noisy as in the real files."""
    lines = [STORE_HEADER] + [
        f"{day},{PACKAGE},{country},{acquisitions},{visitors},0.1234567"
        for day, country, visitors, acquisitions in rows
    ]
    return "\r\n".join(lines).encode("utf-16")


class Bucket:
    def __init__(self, files: dict[str, bytes]):
        self.files = files
        self.read_paths = []

    def read(self, path: str) -> bytes | None:
        self.read_paths.append(path)
        return self.files.get(path)


class InstallsPathTest(unittest.TestCase):
    def test_names_the_monthly_overview_file(self):
        self.assertEqual(
            installs_path(PACKAGE, date(2026, 10, 1)),
            f"stats/installs/installs_{PACKAGE}_202610_overview.csv",
        )


class DailyTotalsTest(unittest.TestCase):
    def test_decodes_utf16_with_a_byte_order_mark(self):
        raw = installs_csv({"2026-10-01": 3, "2026-10-02": 5})
        self.assertEqual(raw[:2], b"\xff\xfe")
        self.assertEqual(
            daily_totals(raw, "Daily User Installs"),
            {date(2026, 10, 1): 3, date(2026, 10, 2): 5},
        )

    def test_reads_the_named_column(self):
        raw = installs_csv({"2026-10-01": 3})
        self.assertEqual(
            daily_totals(raw, "Daily User Uninstalls"), {date(2026, 10, 1): 1}
        )

    def test_rows_on_the_same_day_are_summed(self):
        raw = "\r\n".join(
            [
                "Date,Package name,Country / region,Store listing visitors",
                f"2026-10-01,{PACKAGE},AA,4",
                f"2026-10-01,{PACKAGE},BB,6",
                f"2026-10-02,{PACKAGE},AA,1",
            ]
        ).encode("utf-16")
        self.assertEqual(
            daily_totals(raw, "Store listing visitors"),
            {date(2026, 10, 1): 10, date(2026, 10, 2): 1},
        )

    def test_header_only_file_has_no_days(self):
        self.assertEqual(daily_totals(installs_csv({}), "Daily User Installs"), {})

    def test_a_missing_column_names_it(self):
        with self.assertRaises(SourceError) as raised:
            daily_totals(installs_csv({"2026-10-01": 3}), "No Such Column")
        self.assertIn("No Such Column", str(raised.exception))


class InstallsGrowthTest(unittest.TestCase):
    def test_reports_the_newest_week_complete_in_the_file(self):
        rows = {f"2026-10-{day:02d}": day for day in range(1, 29)}
        bucket = Bucket({installs_path(PACKAGE, date(2026, 10, 1)): installs_csv(rows)})
        growth = play_bucket.growth(bucket.read, PACKAGE, today=date(2026, 11, 2))
        self.assertEqual(
            growth.coverage.period, Period(date(2026, 10, 19), date(2026, 10, 25))
        )
        self.assertEqual(growth.installs.value, sum(range(19, 26)))
        self.assertEqual(growth.installs.previous, sum(range(12, 19)))

    def test_a_week_straddling_two_months_reads_both_files(self):
        october = {f"2026-10-{day:02d}": 1 for day in range(20, 32)}
        november = {f"2026-11-{day:02d}": 2 for day in range(1, 5)}
        bucket = Bucket(
            {
                installs_path(PACKAGE, date(2026, 10, 1)): installs_csv(october),
                installs_path(PACKAGE, date(2026, 11, 1)): installs_csv(november),
            }
        )
        growth = play_bucket.growth(bucket.read, PACKAGE, today=date(2026, 11, 6))
        self.assertEqual(
            growth.coverage.period, Period(date(2026, 10, 26), date(2026, 11, 1))
        )
        self.assertEqual(growth.installs.value, 6 * 1 + 1 * 2)
        self.assertEqual(growth.installs.previous, 6 * 1)

    def test_the_previous_week_in_an_older_month_is_read_too(self):
        july = {f"2026-07-{day:02d}": 3 for day in range(1, 32)}
        august = {f"2026-08-{day:02d}": 1 for day in range(1, 10)}
        bucket = Bucket(
            {
                installs_path(PACKAGE, date(2026, 7, 1)): installs_csv(july),
                installs_path(PACKAGE, date(2026, 8, 1)): installs_csv(august),
            }
        )
        growth = play_bucket.growth(bucket.read, PACKAGE, today=date(2026, 9, 1))
        self.assertEqual(
            growth.coverage.period, Period(date(2026, 8, 3), date(2026, 8, 9))
        )
        self.assertEqual(growth.installs.previous, 3 * 5 + 1 * 2)
        self.assertIn(installs_path(PACKAGE, date(2026, 7, 1)), bucket.read_paths)

    def test_a_missing_current_month_file_is_not_an_error(self):
        october = {f"2026-10-{day:02d}": 1 for day in range(1, 32)}
        bucket = Bucket(
            {installs_path(PACKAGE, date(2026, 10, 1)): installs_csv(october)}
        )
        growth = play_bucket.growth(bucket.read, PACKAGE, today=date(2026, 11, 1))
        self.assertEqual(
            growth.coverage.period, Period(date(2026, 10, 19), date(2026, 10, 25))
        )

    def test_no_rows_in_any_file_fails_the_source(self):
        bucket = Bucket({installs_path(PACKAGE, date(2026, 11, 1)): installs_csv({})})
        with self.assertRaises(SourceError) as raised:
            play_bucket.growth(bucket.read, PACKAGE, today=date(2026, 11, 2))
        self.assertIn("2026-10", str(raised.exception))

    def test_a_default_week_is_complete(self):
        rows = {f"2026-10-{day:02d}": 1 for day in range(1, 29)}
        bucket = Bucket({installs_path(PACKAGE, date(2026, 10, 1)): installs_csv(rows)})
        growth = play_bucket.growth(bucket.read, PACKAGE, today=date(2026, 11, 2))
        self.assertIsNone(growth.coverage.data_to)

    def test_names_the_source(self):
        self.assertEqual(play_bucket.SOURCE, "Play report bucket")


class UninstallsAndNetGrowthTest(unittest.TestCase):
    today = date(2026, 11, 3)

    def bucket(self, **months: tuple[dict[str, int], dict[str, int]]) -> Bucket:
        return Bucket(
            {
                installs_path(PACKAGE, date.fromisoformat(f"{month}-01")): installs_csv(
                    installs, uninstalls
                )
                for month, (installs, uninstalls) in months.items()
            }
        )

    def october(self, installs: int, uninstalls: int):
        days = [f"2026-10-{day:02d}" for day in range(1, 29)]
        return (
            {day: installs for day in days},
            {day: uninstalls for day in days},
        )

    def test_counts_uninstalls_next_to_installs(self):
        result = play_bucket.growth(
            self.bucket(**{"2026-10": self.october(5, 2)}).read,
            PACKAGE,
            self.today,
            Period(date(2026, 10, 15), date(2026, 10, 18)),
        )
        self.assertEqual(result.installs.value, 20)
        self.assertEqual(result.uninstalls.value, 8)
        self.assertEqual(result.uninstalls.previous, 8)
        self.assertEqual([p.value for p in result.uninstalls.series], [2] * 4)

    def test_net_reportis_installs_minus_uninstalls_per_day(self):
        installs = {"2026-10-15": 5, "2026-10-16": 1, "2026-10-17": 0, "2026-10-28": 0}
        uninstalls = {
            "2026-10-15": 2,
            "2026-10-16": 4,
            "2026-10-17": 3,
            "2026-10-28": 0,
        }
        result = play_bucket.growth(
            self.bucket(**{"2026-10": (installs, uninstalls)}).read,
            PACKAGE,
            self.today,
            Period(date(2026, 10, 15), date(2026, 10, 17)),
        )
        self.assertEqual([p.value for p in result.net.series], [3, -3, -3])
        self.assertEqual(result.net.value, -3)
        self.assertEqual(result.net.previous, 0)

    def test_net_reportcan_be_set_against_a_negative_previous_range(self):
        installs, uninstalls = self.october(1, 3)
        result = play_bucket.growth(
            self.bucket(**{"2026-10": (installs, uninstalls)}).read,
            PACKAGE,
            self.today,
            Period(date(2026, 10, 15), date(2026, 10, 18)),
        )
        self.assertEqual((result.net.value, result.net.previous), (-8, -8))

    def test_a_missing_day_counts_as_zero_installs_and_zero_uninstalls(self):
        installs = {"2026-10-15": 4, "2026-10-17": 6, "2026-10-28": 1}
        uninstalls = {"2026-10-15": 1, "2026-10-17": 2, "2026-10-28": 1}
        result = play_bucket.growth(
            self.bucket(**{"2026-10": (installs, uninstalls)}).read,
            PACKAGE,
            self.today,
            Period(date(2026, 10, 15), date(2026, 10, 17)),
        )
        self.assertEqual([p.value for p in result.installs.series], [4, 0, 6])
        self.assertEqual([p.value for p in result.uninstalls.series], [1, 0, 2])
        self.assertEqual([p.value for p in result.net.series], [3, 0, 4])

    def test_a_range_straddling_two_monthly_files_sums_both(self):
        october = (
            {f"2026-10-{d}": 4 for d in (30, 31)},
            {f"2026-10-{d}": 1 for d in (30, 31)},
        )
        november = (
            {f"2026-11-0{d}": 2 for d in (1, 2)},
            {f"2026-11-0{d}": 3 for d in (1, 2)},
        )
        result = play_bucket.growth(
            self.bucket(**{"2026-10": october, "2026-11": november}).read,
            PACKAGE,
            self.today,
            Period(date(2026, 10, 30), date(2026, 11, 2)),
        )
        self.assertEqual(result.installs.value, 12)
        self.assertEqual(result.uninstalls.value, 8)
        self.assertEqual(result.net.value, 4)

    def test_a_fully_read_file_is_not_fetched_twice(self):
        installs, uninstalls = self.october(1, 1)
        bucket = self.bucket(**{"2026-10": (installs, uninstalls)})
        play_bucket.growth(bucket.read, PACKAGE, date(2026, 11, 2))
        self.assertEqual(len(bucket.read_paths), len(set(bucket.read_paths)))

    def test_net_reporttrend_has_twelve_periods(self):
        installs, uninstalls = self.october(3, 1)
        result = play_bucket.growth(
            self.bucket(**{"2026-10": (installs, uninstalls)}).read,
            PACKAGE,
            self.today,
            Period(date(2026, 10, 15), date(2026, 10, 21)),
        )
        self.assertEqual(len(result.net.trend), 12)
        self.assertEqual(result.net.trend[-1].value, 14)


class StorePerformancePathTest(unittest.TestCase):
    def test_names_the_monthly_country_file(self):
        self.assertEqual(
            store_performance_path(PACKAGE, date(2026, 10, 1)),
            f"stats/store_performance/store_performance_{PACKAGE}_202610_country.csv",
        )


class ListingTest(unittest.TestCase):
    today = date(2026, 11, 3)

    def bucket(self, **months: list[tuple[str, str, int, int]]) -> Bucket:
        return Bucket(
            {
                store_performance_path(
                    PACKAGE, date.fromisoformat(f"{month}-01")
                ): store_csv(rows)
                for month, rows in months.items()
            }
        )

    def listing(self, bucket: Bucket, start: date, end: date):
        return play_bucket.listing(bucket.read, PACKAGE, self.today, Period(start, end))

    def test_sums_the_countries_of_each_day(self):
        rows = [
            ("2026-10-15", "AA", 40, 4),
            ("2026-10-15", "BB", 10, 3),
            ("2026-10-16", "AA", 25, 5),
            ("2026-10-28", "AA", 1, 0),
        ]
        result = self.listing(
            self.bucket(**{"2026-10": rows}), date(2026, 10, 15), date(2026, 10, 16)
        )
        self.assertEqual([p.value for p in result.visitors.series], [50, 25])
        self.assertEqual([p.value for p in result.acquisitions.series], [7, 5])
        self.assertEqual((result.visitors.value, result.acquisitions.value), (75, 12))

    def test_conversion_is_summed_acquisitions_over_summed_visitors(self):
        rows = [
            ("2026-10-15", "AA", 100, 10),
            ("2026-10-16", "AA", 10, 5),
            ("2026-10-28", "AA", 1, 0),
        ]
        result = self.listing(
            self.bucket(**{"2026-10": rows}), date(2026, 10, 15), date(2026, 10, 16)
        )
        self.assertAlmostEqual(result.conversion.value, 15 / 110 * 100)

    def test_conversion_ignores_the_rate_column(self):
        rows = [("2026-10-15", "AA", 50, 5), ("2026-10-28", "AA", 1, 0)]
        result = self.listing(
            self.bucket(**{"2026-10": rows}), date(2026, 10, 15), date(2026, 10, 15)
        )
        self.assertEqual(result.conversion.value, 10.0)

    def test_the_previous_range_has_its_own_conversion(self):
        rows = [
            ("2026-10-13", "AA", 100, 2),
            ("2026-10-14", "AA", 100, 4),
            ("2026-10-15", "AA", 100, 10),
            ("2026-10-16", "AA", 100, 20),
            ("2026-10-28", "AA", 1, 0),
        ]
        result = self.listing(
            self.bucket(**{"2026-10": rows}), date(2026, 10, 15), date(2026, 10, 16)
        )
        self.assertEqual(
            (result.conversion.value, result.conversion.previous), (15.0, 3.0)
        )
        self.assertEqual(len(result.conversion.trend), 12)
        self.assertEqual(result.conversion.trend[-1].value, 15.0)

    def test_missing_days_count_as_zero_visitors_and_zero_acquisitions(self):
        rows = [
            ("2026-10-15", "AA", 20, 2),
            ("2026-10-17", "AA", 30, 3),
            ("2026-10-28", "AA", 1, 0),
        ]
        result = self.listing(
            self.bucket(**{"2026-10": rows}), date(2026, 10, 15), date(2026, 10, 17)
        )
        self.assertEqual([p.value for p in result.visitors.series], [20, 0, 30])
        self.assertEqual(result.conversion.value, 10.0)

    def test_a_range_with_no_visitors_converts_at_zero(self):
        rows = [("2026-10-28", "AA", 1, 0)]
        result = self.listing(
            self.bucket(**{"2026-10": rows}), date(2026, 10, 15), date(2026, 10, 16)
        )
        self.assertEqual(result.conversion.value, 0.0)

    def test_a_range_straddling_two_monthly_files_sums_both(self):
        october = [("2026-10-30", "AA", 10, 1), ("2026-10-31", "BB", 10, 2)]
        november = [("2026-11-01", "AA", 20, 3), ("2026-11-02", "AA", 20, 4)]
        result = self.listing(
            self.bucket(**{"2026-10": october, "2026-11": november}),
            date(2026, 10, 30),
            date(2026, 11, 2),
        )
        self.assertEqual(result.visitors.value, 60)
        self.assertEqual(result.acquisitions.value, 10)
        self.assertAlmostEqual(result.conversion.value, 10 / 60 * 100)
        self.assertIsNone(result.coverage.data_to)

    def test_data_ending_inside_the_range_cuts_it_and_the_range_before(self):
        rows = [(f"2026-10-{day:02d}", "AA", day, 1) for day in range(1, 29)]
        result = self.listing(
            self.bucket(**{"2026-10": rows}), date(2026, 10, 26), date(2026, 11, 1)
        )
        self.assertEqual(result.coverage.data_to, date(2026, 10, 28))
        self.assertEqual(result.visitors.value, 26 + 27 + 28)
        self.assertEqual(result.visitors.previous, 19 + 20 + 21)

    def test_a_range_the_files_do_not_reach_is_unavailable(self):
        rows = [("2026-10-28", "AA", 1, 0)]
        period = Period(date(2026, 10, 29), date(2026, 11, 4))
        result = self.listing(
            self.bucket(**{"2026-10": rows}), period.start, period.end
        )
        self.assertEqual(result, Unavailable(play_bucket.SOURCE, period))

    def test_with_no_range_it_picks_the_newest_week_complete_in_its_own_files(self):
        rows = [(f"2026-10-{day:02d}", "AA", 10, 1) for day in range(1, 25)]
        bucket = self.bucket(**{"2026-10": rows})
        result = play_bucket.listing(bucket.read, PACKAGE, self.today)
        self.assertEqual(
            result.coverage.period, Period(date(2026, 10, 12), date(2026, 10, 18))
        )
        self.assertEqual(result.visitors.value, 70)

    def test_no_rows_in_any_file_fails_the_source(self):
        bucket = self.bucket(**{"2026-10": []})
        with self.assertRaises(SourceError):
            play_bucket.listing(bucket.read, PACKAGE, self.today)

    def test_a_file_without_the_visitors_column_names_it(self):
        raw = "\r\n".join(["Date,Package name", f"2026-10-01,{PACKAGE}"]).encode(
            "utf-16"
        )
        bucket = Bucket({store_performance_path(PACKAGE, date(2026, 10, 1)): raw})
        with self.assertRaises(SourceError) as raised:
            self.listing(bucket, date(2026, 10, 1), date(2026, 10, 2))
        self.assertIn("Store listing visitors", str(raised.exception))


class InstallsGrowthForARangeTest(unittest.TestCase):
    today = date(2026, 11, 3)

    def bucket(self, **months: dict[str, int]) -> Bucket:
        return Bucket(
            {
                installs_path(PACKAGE, date.fromisoformat(f"{month}-01")): installs_csv(
                    rows
                )
                for month, rows in months.items()
            }
        )

    def growth(self, bucket: Bucket, start: date, end: date):
        return play_bucket.growth(bucket.read, PACKAGE, self.today, Period(start, end))

    def test_a_full_range_sums_it_against_the_range_before(self):
        rows = {f"2026-10-{day:02d}": day for day in range(1, 29)}
        growth = self.growth(
            self.bucket(**{"2026-10": rows}), date(2026, 10, 15), date(2026, 10, 18)
        )
        self.assertEqual(
            growth.coverage.period, Period(date(2026, 10, 15), date(2026, 10, 18))
        )
        self.assertIsNone(growth.coverage.data_to)
        self.assertEqual(growth.installs.value, 15 + 16 + 17 + 18)
        self.assertEqual(growth.installs.previous, 11 + 12 + 13 + 14)
        self.assertEqual(len(growth.installs.series), 4)

    def test_a_range_does_not_have_to_be_a_week_or_start_on_a_monday(self):
        rows = {f"2026-10-{day:02d}": 1 for day in range(1, 29)}
        growth = self.growth(
            self.bucket(**{"2026-10": rows}), date(2026, 10, 14), date(2026, 10, 14)
        )
        self.assertEqual((growth.installs.value, growth.installs.previous), (1, 1))

    def test_a_range_partly_covered_is_cut_and_the_previous_range_is_cut_to_match(self):
        rows = {f"2026-10-{day:02d}": day for day in range(1, 29)}
        growth = self.growth(
            self.bucket(**{"2026-10": rows}), date(2026, 10, 26), date(2026, 11, 1)
        )
        self.assertEqual(growth.coverage.data_to, date(2026, 10, 28))
        self.assertEqual(growth.installs.value, 26 + 27 + 28)
        self.assertEqual(growth.installs.previous, 19 + 20 + 21)
        self.assertEqual(len(growth.installs.series), 3)

    def test_a_range_the_files_do_not_reach_is_unavailable(self):
        rows = {f"2026-10-{day:02d}": 1 for day in range(1, 29)}
        period = Period(date(2026, 10, 29), date(2026, 11, 4))
        growth = self.growth(self.bucket(**{"2026-10": rows}), period.start, period.end)
        self.assertEqual(growth, Unavailable(play_bucket.SOURCE, period))

    def test_a_range_before_the_bucket_has_any_file_is_unavailable(self):
        rows = {f"2026-10-{day:02d}": 1 for day in range(1, 29)}
        period = Period(date(2025, 3, 3), date(2025, 3, 9))
        growth = self.growth(self.bucket(**{"2026-10": rows}), period.start, period.end)
        self.assertEqual(growth, Unavailable(play_bucket.SOURCE, period))

    def test_a_range_across_a_month_boundary_reads_both_months(self):
        october = {f"2026-10-{day:02d}": 1 for day in range(1, 32)}
        november = {f"2026-11-{day:02d}": 5 for day in range(1, 8)}
        growth = self.growth(
            self.bucket(**{"2026-10": october, "2026-11": november}),
            date(2026, 10, 30),
            date(2026, 11, 2),
        )
        self.assertEqual(growth.installs.value, 1 + 1 + 5 + 5)
        self.assertEqual(growth.installs.previous, 4)
        self.assertIsNone(growth.coverage.data_to)

    def test_a_quiet_stretch_inside_the_data_counts_as_zero(self):
        rows = {"2026-10-01": 3, "2026-10-28": 3}
        growth = self.growth(
            self.bucket(**{"2026-10": rows}), date(2026, 10, 10), date(2026, 10, 12)
        )
        self.assertEqual(growth.installs.value, 0)
        self.assertEqual(growth.coverage.data_to, None)

    def test_a_ten_day_range_has_twelve_ten_day_periods_in_its_trend(self):
        july = {f"2026-07-{day:02d}": 1 for day in range(1, 32)}
        august = {f"2026-08-{day:02d}": 1 for day in range(1, 32)}
        september = {f"2026-09-{day:02d}": 2 for day in range(1, 31)}
        growth = self.growth(
            self.bucket(**{"2026-07": july, "2026-08": august, "2026-09": september}),
            date(2026, 9, 21),
            date(2026, 9, 30),
        )
        trend = growth.installs.trend
        self.assertEqual(
            [point.value for point in trend], [0, 0, 2] + [10] * 6 + [20] * 3
        )
        self.assertEqual(trend[0].day, date(2026, 9, 21) - timedelta(days=110))

    def test_the_trend_reads_every_month_it_needs(self):
        rows = {f"2026-10-{day:02d}": 1 for day in range(1, 29)}
        bucket = self.bucket(**{"2026-10": rows})
        self.growth(bucket, date(2026, 10, 15), date(2026, 10, 21))
        self.assertIn(installs_path(PACKAGE, date(2026, 7, 1)), bucket.read_paths)


if __name__ == "__main__":
    unittest.main()
