import unittest
from datetime import date, timedelta

from weekly_report.model import Unavailable
from weekly_report.periods import Period
from weekly_report.sources import play_bucket
from weekly_report.sources.play_bucket import (
    SourceError,
    daily_totals,
    installs_growth,
    installs_path,
)

PACKAGE = "com.example.app"
HEADER = (
    "Date,Package name,Daily Device Installs,Daily Device Uninstalls,"
    "Daily Device Upgrades,Total User Installs,Daily User Installs,"
    "Daily User Uninstalls,Active Device Installs,Install events,"
    "Update events,Uninstall events"
)


def installs_csv(rows: dict[str, int]) -> bytes:
    lines = [HEADER] + [
        f"{day},{PACKAGE},9,0,0,0,{installs},1,40,11,2,1"
        for day, installs in rows.items()
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
        growth = installs_growth(bucket.read, PACKAGE, today=date(2026, 11, 2))
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
        growth = installs_growth(bucket.read, PACKAGE, today=date(2026, 11, 6))
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
        growth = installs_growth(bucket.read, PACKAGE, today=date(2026, 9, 1))
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
        growth = installs_growth(bucket.read, PACKAGE, today=date(2026, 11, 1))
        self.assertEqual(
            growth.coverage.period, Period(date(2026, 10, 19), date(2026, 10, 25))
        )

    def test_no_rows_in_any_file_fails_the_source(self):
        bucket = Bucket({installs_path(PACKAGE, date(2026, 11, 1)): installs_csv({})})
        with self.assertRaises(SourceError) as raised:
            installs_growth(bucket.read, PACKAGE, today=date(2026, 11, 2))
        self.assertIn("2026-10", str(raised.exception))

    def test_a_default_week_is_complete(self):
        rows = {f"2026-10-{day:02d}": 1 for day in range(1, 29)}
        bucket = Bucket({installs_path(PACKAGE, date(2026, 10, 1)): installs_csv(rows)})
        growth = installs_growth(bucket.read, PACKAGE, today=date(2026, 11, 2))
        self.assertIsNone(growth.coverage.data_to)

    def test_names_the_source(self):
        self.assertEqual(play_bucket.SOURCE, "Play report bucket")


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
        return installs_growth(bucket.read, PACKAGE, self.today, Period(start, end))

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
