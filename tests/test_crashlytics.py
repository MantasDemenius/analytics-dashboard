import unittest
from datetime import date, timedelta

from weekly_report.model import (
    Crashlytics,
    ErrorKind,
    IssueState,
    Point,
    Signal,
    Unavailable,
)
from weekly_report.periods import Coverage, Period
from weekly_report.sources import crashlytics

TODAY = date(2026, 11, 3)
WEEK = Period(date(2026, 10, 26), date(2026, 11, 1))


class QueryTest(unittest.TestCase):
    def test_asks_for_whole_utc_days_with_the_end_at_the_next_midnight(self):
        asked = crashlytics.query("topIssues", WEEK, None)
        self.assertEqual(asked["filter_interval_startTime"], "2026-10-26T00:00:00Z")
        self.assertEqual(asked["filter_interval_endTime"], "2026-11-02T00:00:00Z")

    def test_asks_for_a_full_page(self):
        asked = crashlytics.query("topIssues", WEEK, None)
        self.assertEqual(asked["pageSize"], crashlytics.PAGE_SIZE)

    def test_a_next_page_carries_its_token(self):
        asked = crashlytics.query("topIssues", WEEK, "abc")
        self.assertEqual(asked["pageToken"], "abc")

    def test_the_first_page_sends_no_token(self):
        self.assertNotIn("pageToken", crashlytics.query("topIssues", WEEK, None))

    def test_crash_free_users_count_fatal_crashes_only(self):
        asked = crashlytics.query("appSummary", WEEK, None)
        self.assertEqual(asked["filter_issue_errorTypes"], ["FATAL"])

    def test_the_issue_list_covers_every_kind_of_error(self):
        self.assertNotIn(
            "filter_issue_errorTypes", crashlytics.query("topIssues", WEEK, None)
        )


def group(
    title="com.example.Widget.render",
    users=3,
    events=7,
    signals=(),
    kind="FATAL",
    state="OPEN",
    **extra,
):
    return {
        "issue": {
            "id": title,
            "title": title,
            "subtitle": "NullPointerException",
            "errorType": kind,
            "state": state,
            "firstSeenVersion": "2.3.0",
            "uri": f"https://console.example/{title}",
            "signals": [{"signal": signal} for signal in signals],
            **extra,
        },
        "metrics": [
            {
                "startTime": "2026-10-26T00:00:00Z",
                "endTime": "2026-11-02T00:00:00Z",
                "eventsCount": str(events),
                "impactedUsersCount": str(users),
            }
        ],
    }


class IssueTest(unittest.TestCase):
    def test_carries_the_title_subtitle_version_and_console_link(self):
        issue = crashlytics.issue(group("Widget.render"))
        self.assertEqual(issue.title, "Widget.render")
        self.assertEqual(issue.subtitle, "NullPointerException")
        self.assertEqual(issue.first_seen_version, "2.3.0")
        self.assertEqual(issue.link, "https://console.example/Widget.render")

    def test_counts_arrive_as_strings_and_leave_as_numbers(self):
        issue = crashlytics.issue(group(users=12, events=1034))
        self.assertEqual((issue.users, issue.events), (12, 1034))

    def test_names_every_signal_crashlytics_sets(self):
        issue = crashlytics.issue(
            group(
                signals=(
                    "SIGNAL_REPETITIVE",
                    "SIGNAL_REGRESSED",
                    "SIGNAL_FRESH",
                    "SIGNAL_EARLY",
                )
            )
        )
        self.assertEqual(
            issue.signals,
            (Signal.FRESH, Signal.REGRESSED, Signal.EARLY, Signal.REPETITIVE),
        )

    def test_an_unspecified_signal_is_dropped(self):
        issue = crashlytics.issue(group(signals=("SIGNAL_UNSPECIFIED", "SIGNAL_FRESH")))
        self.assertEqual(issue.signals, (Signal.FRESH,))

    def test_an_issue_without_signals_has_none(self):
        self.assertEqual(crashlytics.issue(group()).signals, ())

    def test_new_and_regressed_issues_need_attention_and_the_rest_do_not(self):
        self.assertTrue(
            crashlytics.issue(group(signals=("SIGNAL_FRESH",))).needs_attention
        )
        self.assertTrue(
            crashlytics.issue(group(signals=("SIGNAL_REGRESSED",))).needs_attention
        )
        self.assertFalse(
            crashlytics.issue(group(signals=("SIGNAL_EARLY",))).needs_attention
        )

    def test_names_the_kind_of_error_and_the_state(self):
        issue = crashlytics.issue(group(kind="ANR", state="MUTED"))
        self.assertEqual(issue.kind, ErrorKind.ANR)
        self.assertEqual(issue.state, IssueState.MUTED)
        self.assertEqual(
            crashlytics.issue(group(kind="NON_FATAL", state="CLOSED")).kind,
            ErrorKind.NON_FATAL,
        )

    def test_an_issue_with_no_counts_in_the_range_has_zero(self):
        bare = group()
        bare["metrics"] = []
        issue = crashlytics.issue(bare)
        self.assertEqual((issue.users, issue.events), (0, 0))

    def test_an_issue_without_a_version_or_link_has_none(self):
        bare = group()
        del bare["issue"]["firstSeenVersion"], bare["issue"]["uri"]
        issue = crashlytics.issue(bare)
        self.assertIsNone(issue.first_seen_version)
        self.assertIsNone(issue.link)


def titles(issues):
    return [each.title for each in issues]


class SortedIssuesTest(unittest.TestCase):
    def order(self, *groups):
        return titles(crashlytics.sorted_issues([crashlytics.issue(g) for g in groups]))

    def test_most_users_affected_first(self):
        order = self.order(group("few", users=2), group("many", users=40))
        self.assertEqual(order, ["many", "few"])

    def test_events_break_a_tie_in_users(self):
        order = self.order(
            group("quiet", users=5, events=6), group("loud", users=5, events=60)
        )
        self.assertEqual(order, ["loud", "quiet"])

    def test_new_and_regressed_issues_come_before_bigger_ones(self):
        order = self.order(
            group("big", users=90),
            group("fresh", users=1, signals=("SIGNAL_FRESH",)),
            group("back", users=2, signals=("SIGNAL_REGRESSED",)),
        )
        self.assertEqual(order, ["back", "fresh", "big"])

    def test_a_new_and_a_regressed_issue_rank_by_users_like_any_other_pair(self):
        order = self.order(
            group("fresh", users=3, signals=("SIGNAL_FRESH",)),
            group("back", users=8, signals=("SIGNAL_REGRESSED",)),
        )
        self.assertEqual(order, ["back", "fresh"])

    def test_other_signals_do_not_lift_an_issue(self):
        order = self.order(
            group("early", users=1, signals=("SIGNAL_EARLY", "SIGNAL_REPETITIVE")),
            group("big", users=9),
        )
        self.assertEqual(order, ["big", "early"])

    def test_issues_equal_in_everything_keep_the_order_crashlytics_gave(self):
        order = self.order(
            group("a", users=4), group("b", users=4), group("c", users=4)
        )
        self.assertEqual(order, ["a", "b", "c"])

    def test_no_issues_is_an_empty_tuple(self):
        self.assertEqual(crashlytics.sorted_issues([]), ())


def crash_free_by_start(period: Period) -> float:
    return 90 + (period.start - date(2026, 1, 1)).days % 10 / 10


class Report:
    """Answers the way the API does from made-up data and records every question."""

    def __init__(self, pages=((),), crash_free=crash_free_by_start):
        self.pages = [list(page) for page in pages]
        self.crash_free = crash_free
        self.asked: list[tuple[str, Period, str | None]] = []

    def __call__(self, report, period, token):
        self.asked.append((report, period, token))
        if report == crashlytics.APP_SUMMARY:
            free = self.crash_free(period)
            metrics = {} if free is None else {"crashFreeUsersPercentage": free}
            return {"groups": [{"metrics": [metrics]}]}
        index = int(token) if token else 0
        page = {"groups": self.pages[index]}
        if index + 1 < len(self.pages):
            page["nextPageToken"] = str(index + 1)
        return page

    def issue_questions(self):
        return [asked for asked in self.asked if asked[0] == crashlytics.TOP_ISSUES]

    def summary_periods(self):
        return [asked[1] for asked in self.asked if asked[0] == crashlytics.APP_SUMMARY]


class PagingTest(unittest.TestCase):
    def issues(self, report):
        return titles(crashlytics.crashlytics(report, TODAY, WEEK).issues)

    def test_reads_every_page_to_the_last(self):
        report = Report(
            pages=(
                [group("a", users=9), group("b", users=8)],
                [group("c", users=7)],
                [group("d", users=6), group("e", users=5)],
            )
        )
        self.assertEqual(self.issues(report), ["a", "b", "c", "d", "e"])
        self.assertEqual(
            [token for _, _, token in report.issue_questions()], [None, "1", "2"]
        )

    def test_issues_from_later_pages_are_sorted_in_with_the_first(self):
        report = Report(
            pages=(
                [group("small", users=1)],
                [group("fresh", users=1, signals=("SIGNAL_FRESH",))],
            )
        )
        self.assertEqual(self.issues(report), ["fresh", "small"])

    def test_a_single_page_is_one_question(self):
        report = Report(pages=([group("only")],))
        self.assertEqual(self.issues(report), ["only"])
        self.assertEqual(len(report.issue_questions()), 1)

    def test_a_range_with_no_issues_has_none(self):
        report = Report(pages=([],))
        self.assertEqual(crashlytics.crashlytics(report, TODAY, WEEK).issues, ())

    def test_every_page_is_asked_for_the_same_interval(self):
        report = Report(pages=([group("a")], [group("b")]))
        crashlytics.crashlytics(report, TODAY, WEEK)
        self.assertEqual({period for _, period, _ in report.issue_questions()}, {WEEK})


class NinetyDayLimitTest(unittest.TestCase):
    def test_a_range_that_starts_90_days_back_is_available(self):
        week = Period(TODAY - timedelta(days=90), TODAY - timedelta(days=84))
        section = crashlytics.crashlytics(Report(), TODAY, week)
        self.assertIsInstance(section, Crashlytics)

    def test_a_range_that_starts_91_days_back_is_not(self):
        week = Period(TODAY - timedelta(days=91), TODAY - timedelta(days=85))
        report = Report()
        self.assertEqual(
            crashlytics.crashlytics(report, TODAY, week),
            Unavailable("Crashlytics", week),
        )
        self.assertEqual(report.asked, [])

    def test_a_long_range_starting_before_the_limit_is_not_available_either(self):
        long = Period(TODAY - timedelta(days=120), TODAY - timedelta(days=30))
        section = crashlytics.crashlytics(Report(), TODAY, long)
        self.assertIsInstance(section, Unavailable)

    def test_a_range_starting_today_has_no_data_yet(self):
        today = Period(TODAY, TODAY + timedelta(days=3))
        report = Report()
        self.assertEqual(
            crashlytics.crashlytics(report, TODAY, today),
            Unavailable("Crashlytics", today),
        )
        self.assertEqual(report.asked, [])


class CoverageTest(unittest.TestCase):
    def test_a_finished_range_is_fully_covered(self):
        section = crashlytics.crashlytics(Report(), TODAY, WEEK)
        self.assertEqual(section.coverage, Coverage(WEEK))

    def test_a_range_reaching_today_has_data_to_yesterday(self):
        week = Period(date(2026, 10, 28), date(2026, 11, 3))
        report = Report(pages=([group("a")],))
        section = crashlytics.crashlytics(report, TODAY, week)
        self.assertEqual(section.coverage, Coverage(week, date(2026, 11, 2)))
        covered = Period(week.start, date(2026, 11, 2))
        self.assertEqual(
            {period for _, period, _ in report.issue_questions()}, {covered}
        )

    def test_with_no_range_it_is_the_week_that_ended_yesterday_or_before(self):
        section = crashlytics.crashlytics(Report(), TODAY)
        self.assertEqual(section.coverage, Coverage(WEEK))

    def test_the_default_week_on_a_monday_ends_the_day_before(self):
        section = crashlytics.crashlytics(Report(), date(2026, 11, 2))
        self.assertEqual(section.coverage.period, WEEK)


class CrashFreeTest(unittest.TestCase):
    def section(self, crash_free=crash_free_by_start, period=WEEK):
        return crashlytics.crashlytics(Report(crash_free=crash_free), TODAY, period)

    def test_is_the_summary_of_the_range_and_of_the_range_before(self):
        free = {WEEK: 97.5, WEEK.previous(): 96.0}
        section = self.section(lambda period: free.get(period, 99.0))
        self.assertEqual(section.crash_free.value, 97.5)
        self.assertEqual(section.crash_free.previous, 96.0)

    def test_the_trend_is_12_periods_oldest_first_each_dated_by_its_start(self):
        section = self.section()
        trend = section.crash_free.trend
        self.assertEqual(len(trend), 12)
        self.assertEqual(trend[-1].day, WEEK.start)
        self.assertEqual(trend[-2].day, WEEK.previous().start)
        self.assertEqual(trend[0].day, WEEK.start - timedelta(weeks=11))
        self.assertEqual(trend[-1].value, section.crash_free.value)
        self.assertEqual(trend[-2].value, section.crash_free.previous)

    def test_one_summary_is_read_per_trend_period(self):
        report = Report()
        crashlytics.crashlytics(report, TODAY, WEEK)
        self.assertEqual(report.summary_periods(), WEEK.trailing(12))

    def test_a_period_with_no_users_counts_as_zero(self):
        section = self.section(lambda period: None)
        self.assertEqual(section.crash_free.value, 0)

    def test_periods_with_no_users_are_left_out_of_the_trend(self):
        known = {WEEK, WEEK.previous()}
        section = self.section(lambda period: 97.0 if period in known else None)
        self.assertEqual(
            section.crash_free.trend,
            (Point(WEEK.previous().start, 97.0), Point(WEEK.start, 97.0)),
        )

    def test_a_range_with_no_users_has_an_empty_trend(self):
        section = self.section(lambda period: None)
        self.assertEqual(section.crash_free.trend, ())

    def test_a_range_at_the_limit_has_no_previous_and_a_trend_of_one(self):
        start = TODAY - timedelta(days=90)
        week = Period(start, start + timedelta(days=6))
        section = self.section(period=week)
        self.assertEqual(section.crash_free.previous, 0)
        self.assertEqual(
            section.crash_free.trend, (Point(week.start, section.crash_free.value),)
        )

    def test_trend_periods_before_the_limit_are_left_out_and_never_asked_for(self):
        start = TODAY - timedelta(days=90)
        week = Period(start + timedelta(days=14), start + timedelta(days=20))
        report = Report()
        section = crashlytics.crashlytics(report, TODAY, week)
        self.assertEqual(
            [point.day for point in section.crash_free.trend],
            [
                week.start - timedelta(weeks=2),
                week.start - timedelta(weeks=1),
                week.start,
            ],
        )
        self.assertTrue(
            all(period.start >= start for period in report.summary_periods())
        )

    def test_a_partly_covered_range_is_compared_with_the_same_days_before_it(self):
        week = Period(date(2026, 10, 28), date(2026, 11, 3))
        report = Report()
        section = crashlytics.crashlytics(report, TODAY, week)
        cut = week.cut(6)
        self.assertEqual(report.summary_periods()[-1], cut)
        self.assertEqual(report.summary_periods()[-2], week.previous().cut(6))
        self.assertEqual(section.crash_free.value, crash_free_by_start(cut))


if __name__ == "__main__":
    unittest.main()
