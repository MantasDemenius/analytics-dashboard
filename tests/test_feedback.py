import unittest
from datetime import UTC, date, datetime, timedelta, timezone

from weekly_report.model import ReportKind, Unavailable
from weekly_report.periods import Period
from weekly_report.sources import feedback

TODAY = date(2026, 11, 3)
WEEK = Period(date(2026, 10, 26), date(2026, 11, 1))


def bug(**extra):
    return {
        "kind": "bug",
        "appVersion": "2.4.0",
        "handled": False,
        "createdAt": datetime(2026, 10, 28, 9, 15, tzinfo=UTC),
        "message": "The list is empty after an import",
        "androidVersion": "14",
        "appId": "made-up-installation-id",
        "email": "someone@example.com",
        "error": "FormatException: unexpected end of input",
    } | extra


def suggestion(**extra):
    return {
        "kind": "feedback",
        "appVersion": "2.4.0",
        "handled": False,
        "createdAt": datetime(2026, 10, 29, 18, 0, tzinfo=UTC),
        "rating": 4,
        "message": "Nice, but I would like a search",
        "liked": ["speed", "design"],
    } | extra


def without(document, *names):
    return {key: value for key, value in document.items() if key not in names}


class BoundsTest(unittest.TestCase):
    def test_a_window_is_whole_utc_days_ending_at_the_next_midnight(self):
        start, end = feedback.bounds(WEEK)
        self.assertEqual(start, datetime(2026, 10, 26, tzinfo=UTC))
        self.assertEqual(end, datetime(2026, 11, 2, tzinfo=UTC))


class UserReportTest(unittest.TestCase):
    def test_a_bug_carries_every_field(self):
        report = feedback.user_report(bug())
        self.assertEqual(report.kind, ReportKind.BUG)
        self.assertEqual(report.at, datetime(2026, 10, 28, 9, 15, tzinfo=UTC))
        self.assertEqual(report.app_version, "2.4.0")
        self.assertEqual(report.android_version, "14")
        self.assertEqual(report.message, "The list is empty after an import")
        self.assertEqual(report.error, "FormatException: unexpected end of input")
        self.assertEqual(report.email, "someone@example.com")
        self.assertEqual(report.app_id, "made-up-installation-id")
        self.assertIsNone(report.rating)
        self.assertEqual(report.liked, ())

    def test_a_bug_without_an_email_has_none(self):
        self.assertIsNone(feedback.user_report(without(bug(), "email")).email)

    def test_a_bug_without_an_error_has_none(self):
        self.assertIsNone(feedback.user_report(without(bug(), "error")).error)

    def test_a_bug_with_an_empty_message_keeps_its_error(self):
        report = feedback.user_report(bug(message=""))
        self.assertEqual(report.message, "")
        self.assertEqual(report.error, "FormatException: unexpected end of input")

    def test_a_bug_with_a_null_app_id_has_none(self):
        self.assertIsNone(feedback.user_report(bug(appId=None)).app_id)

    def test_an_empty_email_or_error_counts_as_missing(self):
        report = feedback.user_report(bug(email="", error=""))
        self.assertIsNone(report.email)
        self.assertIsNone(report.error)

    def test_a_bug_without_an_app_id_key_has_none(self):
        self.assertIsNone(feedback.user_report(without(bug(), "appId")).app_id)

    def test_feedback_carries_its_rating_message_and_liked_items(self):
        report = feedback.user_report(suggestion())
        self.assertEqual(report.kind, ReportKind.FEEDBACK)
        self.assertEqual(report.rating, 4)
        self.assertEqual(report.message, "Nice, but I would like a search")
        self.assertEqual(report.liked, ("speed", "design"))
        self.assertEqual(report.app_version, "2.4.0")

    def test_feedback_has_no_bug_fields(self):
        report = feedback.user_report(suggestion())
        self.assertIsNone(report.android_version)
        self.assertIsNone(report.error)
        self.assertIsNone(report.email)
        self.assertIsNone(report.app_id)

    def test_feedback_may_have_no_message_and_nothing_liked(self):
        report = feedback.user_report(suggestion(message="", liked=[]))
        self.assertEqual(report.message, "")
        self.assertEqual(report.liked, ())

    def test_the_time_is_kept_in_utc_whatever_zone_the_client_returns(self):
        local = timezone(timedelta(hours=2))
        report = feedback.user_report(
            bug(createdAt=datetime(2026, 10, 28, 1, 0, tzinfo=local))
        )
        self.assertEqual(report.at, datetime(2026, 10, 27, 23, 0, tzinfo=UTC))
        self.assertEqual(report.at.utcoffset(), timedelta(0))


def at(day, hour=12, minute=0):
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=UTC)


def read_from(documents):
    asked = []

    def read(window):
        asked.append(window)
        return list(documents)

    read.asked = asked
    return read


def section(documents, unhandled=0, today=TODAY, period=WEEK):
    return feedback.feedback(read_from(documents), lambda: unhandled, today, period)


class FeedbackRangeTest(unittest.TestCase):
    def test_keeps_the_reports_created_in_the_range(self):
        inside = bug(createdAt=at(date(2026, 10, 30)), message="inside")
        before = bug(createdAt=at(date(2026, 10, 25)), message="before")
        after = bug(createdAt=at(date(2026, 11, 2)), message="after")
        found = section([before, inside, after], today=date(2026, 11, 9))
        self.assertEqual([each.message for each in found.reports], ["inside"])

    def test_the_first_and_last_second_of_the_range_are_inside(self):
        first = bug(createdAt=datetime(2026, 10, 26, 0, 0, 0, tzinfo=UTC), message="a")
        last = bug(createdAt=datetime(2026, 11, 1, 23, 59, 59, tzinfo=UTC), message="b")
        found = section([first, last])
        self.assertEqual({each.message for each in found.reports}, {"a", "b"})

    def test_midnight_after_the_range_belongs_to_the_next_range(self):
        next_day = bug(createdAt=datetime(2026, 11, 2, 0, 0, 0, tzinfo=UTC))
        self.assertEqual(section([next_day]).reports, ())

    def test_a_local_morning_of_the_first_day_that_is_still_the_day_before_in_utc_is_outside(
        self,
    ):
        local = timezone(timedelta(hours=5))
        early = bug(createdAt=datetime(2026, 10, 26, 1, 0, tzinfo=local))
        self.assertEqual(section([early]).reports, ())

    def test_a_local_evening_before_the_range_that_is_already_inside_in_utc_is_inside(
        self,
    ):
        local = timezone(timedelta(hours=-5))
        late = bug(createdAt=datetime(2026, 10, 25, 22, 0, tzinfo=local))
        self.assertEqual(len(section([late]).reports), 1)

    def test_newest_first(self):
        old = bug(createdAt=at(date(2026, 10, 27)), message="old")
        new = suggestion(createdAt=at(date(2026, 10, 31)), message="new")
        mid = bug(createdAt=at(date(2026, 10, 29)), message="mid")
        found = section([old, new, mid])
        self.assertEqual(
            [each.message for each in found.reports], ["new", "mid", "old"]
        )

    def test_a_range_with_no_reports_is_an_empty_section(self):
        found = section([])
        self.assertIsInstance(found, feedback.Feedback)
        self.assertEqual(found.reports, ())
        self.assertEqual((found.new.value, found.new.previous), (0, 0))

    def test_reads_one_window_from_the_range_before_to_the_range_end(self):
        read = read_from([])
        feedback.feedback(read, lambda: 0, TODAY, WEEK)
        self.assertEqual(read.asked, [Period(date(2026, 10, 19), date(2026, 11, 1))])

    def test_with_no_range_it_is_the_week_that_ended_yesterday_or_before(self):
        found = feedback.feedback(read_from([]), lambda: 0, TODAY)
        self.assertEqual(found.coverage.period, WEEK)


class FeedbackCountsTest(unittest.TestCase):
    def test_counts_both_kinds_and_each_kind(self):
        found = section(
            [
                bug(createdAt=at(date(2026, 10, 27))),
                bug(createdAt=at(date(2026, 10, 28))),
                suggestion(createdAt=at(date(2026, 10, 29))),
            ]
        )
        self.assertEqual(found.new.value, 3)
        self.assertEqual(found.bugs.value, 2)
        self.assertEqual(found.suggestions.value, 1)

    def test_compares_with_the_range_before(self):
        found = section(
            [
                bug(createdAt=at(date(2026, 10, 27))),
                bug(createdAt=at(date(2026, 10, 20))),
                suggestion(createdAt=at(date(2026, 10, 21))),
                suggestion(createdAt=at(date(2026, 10, 25))),
            ]
        )
        self.assertEqual((found.new.value, found.new.previous), (1, 3))
        self.assertEqual((found.bugs.value, found.bugs.previous), (1, 1))
        self.assertEqual((found.suggestions.value, found.suggestions.previous), (0, 2))

    def test_reports_older_than_the_range_before_are_not_counted(self):
        found = section([bug(createdAt=at(date(2026, 10, 18)))])
        self.assertEqual((found.new.value, found.new.previous), (0, 0))

    def test_the_unhandled_count_is_the_one_the_source_gives(self):
        self.assertEqual(section([], unhandled=7).unhandled, 7)

    def test_the_unhandled_count_ignores_the_range(self):
        old = bug(createdAt=at(date(2026, 1, 5)))
        found = section([old], unhandled=1)
        self.assertEqual((found.new.value, found.unhandled), (0, 1))


class FeedbackCoverageTest(unittest.TestCase):
    def test_a_finished_range_is_fully_covered(self):
        self.assertIsNone(section([]).coverage.data_to)

    def test_a_range_reaching_today_has_data_to_yesterday(self):
        period = Period(date(2026, 10, 28), date(2026, 11, 3))
        found = section([], period=period)
        self.assertEqual(found.coverage.data_to, date(2026, 11, 2))

    def test_reports_after_yesterday_are_left_out(self):
        period = Period(date(2026, 10, 28), date(2026, 11, 3))
        today = bug(createdAt=at(TODAY, hour=1))
        self.assertEqual(section([today], period=period).reports, ())

    def test_a_partly_covered_range_is_compared_with_the_same_days_before_it(self):
        period = Period(date(2026, 10, 28), date(2026, 11, 3))
        found = section(
            [
                bug(createdAt=at(date(2026, 10, 30))),
                bug(createdAt=at(date(2026, 10, 21))),
                bug(createdAt=at(date(2026, 10, 27))),
            ],
            period=period,
        )
        self.assertEqual((found.new.value, found.new.previous), (1, 1))

    def test_a_range_starting_today_has_no_data_yet(self):
        found = section([], period=Period(TODAY, TODAY + timedelta(days=6)))
        self.assertEqual(
            found,
            Unavailable(feedback.SOURCE, Period(TODAY, TODAY + timedelta(days=6))),
        )

    def test_a_range_in_the_future_is_unavailable(self):
        period = Period(date(2026, 11, 9), date(2026, 11, 15))
        self.assertIsInstance(section([], period=period), Unavailable)

    def test_an_unavailable_range_reads_nothing(self):
        read = read_from([])
        feedback.feedback(read, lambda: 0, TODAY, Period(TODAY, TODAY))
        self.assertEqual(read.asked, [])


if __name__ == "__main__":
    unittest.main()
