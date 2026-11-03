import unittest
from datetime import date

from weekly_report.model import Metric, Point
from weekly_report.periods import Period
from weekly_report.sources import play_bucket
from weekly_report.sources.play_bucket import (
    SourceError,
    daily_totals,
    installs_growth,
    installs_path,
    summarise,
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


class SummariseTest(unittest.TestCase):
    period = Period(date(2026, 10, 19), date(2026, 10, 21))

    def test_sums_the_period_and_the_one_before(self):
        daily = {
            date(2026, 10, 16): 1,
            date(2026, 10, 17): 2,
            date(2026, 10, 18): 3,
            date(2026, 10, 19): 4,
            date(2026, 10, 20): 5,
            date(2026, 10, 21): 6,
            date(2026, 10, 22): 100,
        }
        self.assertEqual(
            summarise(daily, self.period),
            Metric(
                value=15,
                previous=6,
                series=(
                    Point(date(2026, 10, 19), 4),
                    Point(date(2026, 10, 20), 5),
                    Point(date(2026, 10, 21), 6),
                ),
            ),
        )

    def test_missing_days_count_as_zero(self):
        daily = {date(2026, 10, 17): 2, date(2026, 10, 20): 5}
        self.assertEqual(
            summarise(daily, self.period),
            Metric(
                value=5,
                previous=2,
                series=(
                    Point(date(2026, 10, 19), 0),
                    Point(date(2026, 10, 20), 5),
                    Point(date(2026, 10, 21), 0),
                ),
            ),
        )

    def test_no_days_at_all_is_zero_against_zero(self):
        metric = summarise({}, self.period)
        self.assertEqual((metric.value, metric.previous), (0, 0))
        self.assertEqual([point.value for point in metric.series], [0, 0, 0])


class InstallsGrowthTest(unittest.TestCase):
    def test_reports_the_newest_week_complete_in_the_file(self):
        rows = {f"2026-10-{day:02d}": day for day in range(1, 29)}
        bucket = Bucket({installs_path(PACKAGE, date(2026, 10, 1)): installs_csv(rows)})
        growth = installs_growth(bucket.read, PACKAGE, today=date(2026, 11, 2))
        self.assertEqual(growth.period, Period(date(2026, 10, 19), date(2026, 10, 25)))
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
        self.assertEqual(growth.period, Period(date(2026, 10, 26), date(2026, 11, 1)))
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
        self.assertEqual(growth.period, Period(date(2026, 8, 3), date(2026, 8, 9)))
        self.assertEqual(growth.installs.previous, 3 * 5 + 1 * 2)
        self.assertIn(installs_path(PACKAGE, date(2026, 7, 1)), bucket.read_paths)

    def test_a_missing_current_month_file_is_not_an_error(self):
        october = {f"2026-10-{day:02d}": 1 for day in range(1, 32)}
        bucket = Bucket(
            {installs_path(PACKAGE, date(2026, 10, 1)): installs_csv(october)}
        )
        growth = installs_growth(bucket.read, PACKAGE, today=date(2026, 11, 1))
        self.assertEqual(growth.period, Period(date(2026, 10, 19), date(2026, 10, 25)))

    def test_no_rows_in_any_file_fails_the_source(self):
        bucket = Bucket({installs_path(PACKAGE, date(2026, 11, 1)): installs_csv({})})
        with self.assertRaises(SourceError) as raised:
            installs_growth(bucket.read, PACKAGE, today=date(2026, 11, 2))
        self.assertIn("2026-10", str(raised.exception))

    def test_names_the_source(self):
        self.assertEqual(play_bucket.SOURCE, "Play report bucket")


if __name__ == "__main__":
    unittest.main()
