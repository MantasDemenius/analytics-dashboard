import csv
import io
import unittest
from datetime import UTC, date, datetime

from weekly_report.model import Label, Unavailable
from weekly_report.periods import Period
from weekly_report.sources import play_reviews
from weekly_report.sources.play_bucket import SourceError
from weekly_report.sources.play_reviews import all_pages, reviews_path

PACKAGE = "com.example.app"
TODAY = date(2026, 11, 3)
WEEK = Period(date(2026, 10, 26), date(2026, 11, 1))
COLUMNS = [
    "Package Name",
    "App Version Code",
    "App Version Name",
    "Reviewer Language",
    "Device",
    "Review Submit Date and Time",
    "Review Submit Millis Since Epoch",
    "Review Last Update Date and Time",
    "Review Last Update Millis Since Epoch",
    "Star Rating",
    "Review Title",
    "Review Text",
    "Developer Reply Date and Time",
    "Developer Reply Millis Since Epoch",
    "Developer Reply Text",
    "Review Link",
]


def csv_row(
    submitted,
    stars,
    text="",
    title="",
    updated=None,
    language="en",
    review_id=None,
    reply="",
):
    link = (
        "https://play.google.com/console/developers/1/app/2/user-feedback/"
        f"review-details?reviewId={review_id}&corpus=PUBLIC_REVIEWS"
        if review_id
        else ""
    )
    return {
        "Package Name": PACKAGE,
        "Reviewer Language": language,
        "Review Submit Date and Time": f"{submitted}T12:00:00Z",
        "Review Last Update Date and Time": f"{updated or submitted}T12:00:00Z",
        "Star Rating": stars,
        "Review Title": title,
        "Review Text": text,
        "Developer Reply Date and Time": "2026-10-30T09:00:00Z" if reply else "",
        "Developer Reply Text": reply,
        "Review Link": link,
    }


def reviews_csv(*rows) -> bytes:
    out = io.StringIO()
    writer = csv.DictWriter(out, COLUMNS, restval="", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode("utf-16")


class Bucket:
    def __init__(self, files: dict[str, bytes]):
        self.files = files

    def read(self, path: str) -> bytes | None:
        return self.files.get(path)


def october(*rows) -> dict[str, bytes]:
    return {reviews_path(PACKAGE, date(2026, 10, 1)): reviews_csv(*rows)}


def november(*rows) -> dict[str, bytes]:
    return {reviews_path(PACKAGE, date(2026, 11, 1)): reviews_csv(*rows)}


def timestamp(day: str, hour: int = 12) -> dict:
    moment = datetime.fromisoformat(f"{day}T{hour:02d}:00:00").replace(tzinfo=UTC)
    return {"seconds": str(int(moment.timestamp())), "nanos": 0}


def api_review(
    review_id,
    text,
    modified,
    stars=5,
    original=None,
    reply=None,
    hour=12,
):
    user = {
        "text": text,
        "lastModified": timestamp(modified, hour),
        "starRating": stars,
        "reviewerLanguage": "xx",
        "device": "phone",
    }
    if original is not None:
        user["originalText"] = original
    comments = [{"userComment": user}]
    if reply is not None:
        comments.append(
            {"developerComment": {"text": reply, "lastModified": timestamp(modified)}}
        )
    return {"reviewId": review_id, "authorName": "A Person", "comments": comments}


def no_api() -> list[dict]:
    return []


def api_of(*raw):
    return lambda: list(raw)


def run(files, api=no_api, period=None, today=TODAY):
    return play_reviews.reviews(Bucket(files).read, api, PACKAGE, today, period)


class ReviewsPathTest(unittest.TestCase):
    def test_names_the_monthly_reviews_file(self):
        self.assertEqual(
            reviews_path(PACKAGE, date(2026, 10, 1)),
            f"reviews/reviews_{PACKAGE}_202610.csv",
        )


class NewRatingsTest(unittest.TestCase):
    def test_counts_and_averages_the_ratings_submitted_in_the_range(self):
        files = october(
            csv_row("2026-10-26", 5),
            csv_row("2026-10-28", 4, text="fine", review_id="a"),
            csv_row("2026-10-30", 3),
            csv_row("2026-10-20", 1),
        )
        section = run(files)
        self.assertEqual(section.coverage.period, WEEK)
        self.assertEqual(section.new_ratings.value, 3)
        self.assertEqual(section.new_average.value, 4.0)

    def test_star_only_rows_count_as_ratings_and_make_no_review(self):
        files = october(csv_row("2026-10-27", 5), csv_row("2026-10-28", 2))
        section = run(files)
        self.assertEqual(section.new_ratings.value, 2)
        self.assertEqual(section.reviews, ())

    def test_compares_with_the_range_before(self):
        files = october(
            csv_row("2026-10-27", 5),
            csv_row("2026-10-20", 2),
            csv_row("2026-10-21", 3),
            csv_row("2026-10-22", 4),
        ) | november(csv_row("2026-11-01", 5))
        section = run(files)
        self.assertEqual(
            (section.new_ratings.value, section.new_ratings.previous), (2, 3)
        )
        self.assertEqual(section.new_average.previous, 3.0)

    def test_the_star_breakdown_counts_every_level_from_five_to_one(self):
        files = october(
            csv_row("2026-10-27", 5),
            csv_row("2026-10-28", 5),
            csv_row("2026-10-29", 3),
            csv_row("2026-10-30", 1),
        )
        self.assertEqual(run(files).breakdown, {5: 2, 4: 0, 3: 1, 2: 0, 1: 1})

    def test_no_ratings_in_the_range_is_zero_not_an_error(self):
        section = run(october(csv_row("2026-10-01", 5)))
        self.assertEqual(section.new_ratings.value, 0)
        self.assertEqual(section.new_average.value, 0)
        self.assertEqual(section.breakdown, {5: 0, 4: 0, 3: 0, 2: 0, 1: 0})

    def test_a_week_straddling_two_months_reads_both_files(self):
        files = october(csv_row("2026-10-30", 5)) | november(csv_row("2026-11-01", 3))
        section = run(files)
        self.assertEqual(section.new_ratings.value, 2)
        self.assertEqual(section.new_average.value, 4.0)

    def test_the_trend_holds_twelve_ranges(self):
        section = run(october(csv_row("2026-10-27", 5)))
        self.assertEqual(len(section.new_ratings.trend), 12)
        self.assertEqual(section.new_ratings.trend[-1].value, 1)
        self.assertEqual(section.new_ratings.trend[0].day, date(2026, 8, 10))


class StoreRatingTest(unittest.TestCase):
    def test_is_the_average_of_the_28_days_ending_on_the_last_day(self):
        files = october(
            csv_row("2026-10-04", 1),
            csv_row("2026-10-05", 5),
            csv_row("2026-10-20", 5),
            csv_row("2026-11-01", 5),
        )
        self.assertEqual(run(files).store_rating.value, 5.0)

    def test_a_rating_29_days_old_has_dropped_out(self):
        files = october(csv_row("2026-10-04", 1), csv_row("2026-10-05", 5))
        files |= november(csv_row("2026-11-01", 4))
        self.assertEqual(run(files).store_rating.value, 4.5)

    def test_includes_star_only_ratings_and_the_ratings_behind_review_text(self):
        files = october(
            csv_row("2026-10-27", 5),
            csv_row("2026-10-28", 2, text="meh", review_id="a"),
            csv_row("2026-10-29", 5),
        )
        self.assertEqual(run(files).store_rating.value, 4.0)

    def test_is_compared_with_the_rating_one_range_earlier(self):
        files = october(csv_row("2026-10-10", 3), csv_row("2026-10-30", 5))
        rating = run(files).store_rating
        self.assertEqual((rating.value, rating.previous), (4.0, 3.0))

    def test_carries_the_last_rating_through_a_stretch_with_none(self):
        section = run(october(csv_row("2026-08-20", 4), csv_row("2026-08-21", 2)))
        self.assertEqual(section.store_rating.value, 3.0)
        self.assertEqual(section.store_rating.previous, 3.0)

    def test_is_zero_before_any_rating_exists(self):
        self.assertEqual(run(october()).store_rating.value, 0)

    def test_is_not_compared_when_no_rating_came_before_the_window(self):
        rating = run(october(csv_row("2026-10-30", 5))).store_rating
        self.assertFalse(rating.comparable)
        self.assertEqual(rating.value, 5.0)

    def test_is_compared_when_a_rating_came_before_the_window(self):
        files = october(csv_row("2026-10-10", 3), csv_row("2026-10-30", 5))
        self.assertTrue(run(files).store_rating.comparable)

    def test_trends_over_twelve_ranges_ending_with_the_value(self):
        files = october(csv_row("2026-10-10", 3), csv_row("2026-10-30", 5))
        trend = run(files).store_rating.trend
        self.assertEqual(len(trend), 12)
        self.assertEqual(trend[-1].value, 4.0)
        self.assertEqual(trend[-2].value, 3.0)
        self.assertEqual(trend[0].value, 0)


class CsvReviewsTest(unittest.TestCase):
    def test_a_review_submitted_in_the_range_is_new_and_carries_its_language(self):
        files = october(
            csv_row(
                "2026-10-28",
                4,
                text="Works well",
                title="Good",
                language="de",
                review_id="a",
            )
        )
        [review] = run(files).reviews
        self.assertEqual(
            (review.stars, review.title, review.text, review.language, review.label),
            (4, "Good", "Works well", "de", Label.NEW),
        )
        self.assertEqual(review.at.date(), date(2026, 10, 28))
        self.assertIsNone(review.original_text)

    def test_a_review_submitted_before_and_updated_in_the_range_is_edited(self):
        files = october(
            csv_row("2026-10-10", 2, text="Bad", updated="2026-10-29", review_id="a")
        )
        [review] = run(files).reviews
        self.assertEqual(review.label, Label.EDITED)
        self.assertEqual(review.at.date(), date(2026, 10, 29))

    def test_a_review_neither_submitted_nor_updated_in_the_range_is_left_out(self):
        files = october(
            csv_row("2026-10-10", 2, text="Old", updated="2026-10-12", review_id="a"),
            csv_row("2026-10-20", 3, text="Older", review_id="b"),
        )
        self.assertEqual(run(files).reviews, ())

    def test_a_review_edited_after_the_range_is_still_new_in_it(self):
        files = october(
            csv_row("2026-10-28", 5, text="Nice", updated="2026-11-02", review_id="a")
        )
        [review] = run(files).reviews
        self.assertEqual(review.label, Label.NEW)

    def test_a_review_with_a_title_and_no_text_is_a_card(self):
        files = october(csv_row("2026-10-28", 1, title="Broken", review_id="a"))
        [review] = run(files).reviews
        self.assertEqual((review.title, review.text), ("Broken", ""))

    def test_the_newest_review_comes_first(self):
        files = october(
            csv_row("2026-10-27", 3, text="first", review_id="a"),
            csv_row("2026-10-30", 3, text="third", review_id="c"),
            csv_row("2026-10-28", 3, text="second", review_id="b"),
        )
        self.assertEqual(
            [review.text for review in run(files).reviews], ["third", "second", "first"]
        )

    def test_a_reply_marks_the_review_replied_and_keeps_its_text(self):
        files = october(
            csv_row(
                "2026-10-28", 1, text="Bad", review_id="a", reply="Sorry about that"
            ),
            csv_row("2026-10-29", 5, text="Great", review_id="b"),
        )
        replied, unreplied = run(files).reviews[::-1]
        self.assertTrue(replied.replied)
        self.assertEqual(replied.reply, "Sorry about that")
        self.assertFalse(unreplied.replied)
        self.assertIsNone(unreplied.reply)


class ApiReviewsTest(unittest.TestCase):
    def test_a_review_only_the_api_has_is_new_or_edited_with_no_language_tag(self):
        api = api_of(api_review("a", "Lovely", "2026-10-31", stars=5))
        [review] = run({}, api).reviews
        self.assertEqual(
            (review.stars, review.text, review.label, review.language),
            (5, "Lovely", Label.NEW_OR_EDITED, None),
        )
        self.assertEqual(review.at.date(), date(2026, 10, 31))

    def test_an_api_review_modified_outside_the_range_is_left_out(self):
        api = api_of(api_review("a", "Too new", "2026-11-02"))
        self.assertEqual(run({}, api).reviews, ())

    def test_a_title_in_the_text_is_split_off_at_the_tab(self):
        api = api_of(api_review("a", "Great app\tWorks every time", "2026-10-31"))
        [review] = run({}, api).reviews
        self.assertEqual((review.title, review.text), ("Great app", "Works every time"))

    def test_a_translated_review_shows_the_translation_and_keeps_the_original(self):
        api = api_of(
            api_review(
                "a", "Great\tVery good", "2026-10-31", original="Super\tSehr gut"
            )
        )
        [review] = run({}, api).reviews
        self.assertEqual((review.title, review.text), ("Great", "Very good"))
        self.assertEqual(review.original_text, "Super\nSehr gut")

    def test_an_untranslated_review_has_no_original(self):
        [review] = run({}, api_of(api_review("a", "Fine", "2026-10-31"))).reviews
        self.assertIsNone(review.original_text)

    def test_the_developer_comment_is_the_reply_not_the_review(self):
        api = api_of(api_review("a", "Bad", "2026-10-31", reply="We fixed it"))
        [review] = run({}, api).reviews
        self.assertEqual((review.text, review.reply), ("Bad", "We fixed it"))
        self.assertTrue(review.replied)

    def test_an_unreplied_review_is_not_replied(self):
        [review] = run({}, api_of(api_review("a", "Fine", "2026-10-31"))).reviews
        self.assertFalse(review.replied)

    def test_an_api_review_does_not_count_as_a_new_rating(self):
        section = run({}, api_of(api_review("a", "Fine", "2026-10-31")))
        self.assertEqual(section.new_ratings.value, 0)


class MergeTest(unittest.TestCase):
    def test_a_review_in_both_is_one_card_labelled_by_the_reports_submit_date(self):
        files = october(csv_row("2026-10-28", 4, text="old text", review_id="a"))
        api = api_of(api_review("a", "old text", "2026-10-28", stars=4))
        [review] = run(files, api).reviews
        self.assertEqual(review.label, Label.NEW)
        self.assertIsNone(review.language)

    def test_a_review_in_both_submitted_earlier_is_edited(self):
        files = october(
            csv_row("2026-10-10", 4, text="x", updated="2026-10-29", review_id="a")
        )
        api = api_of(api_review("a", "x", "2026-10-29", stars=4))
        [review] = run(files, api).reviews
        self.assertEqual(review.label, Label.EDITED)

    def test_the_apis_newer_text_and_stars_win_over_the_reports(self):
        files = october(csv_row("2026-10-28", 2, text="before", review_id="a"))
        api = api_of(api_review("a", "after", "2026-10-30", stars=5))
        [review] = run(files, api).reviews
        self.assertEqual((review.stars, review.text), (5, "after"))
        self.assertEqual(review.at.date(), date(2026, 10, 30))

    def test_a_review_edited_only_in_the_api_is_included_and_labelled_edited(self):
        files = october(csv_row("2026-10-10", 2, text="before", review_id="a"))
        api = api_of(api_review("a", "after", "2026-10-30", stars=4))
        [review] = run(files, api).reviews
        self.assertEqual(review.label, Label.EDITED)
        self.assertEqual(review.text, "after")

    def test_reviews_each_source_alone_has_are_all_kept(self):
        files = october(csv_row("2026-10-27", 3, text="csv only", review_id="c"))
        api = api_of(api_review("a", "api only", "2026-10-31"))
        labels = {review.text: review.label for review in run(files, api).reviews}
        self.assertEqual(
            labels, {"csv only": Label.NEW, "api only": Label.NEW_OR_EDITED}
        )

    def test_the_apis_reply_is_used_when_the_review_is_in_both(self):
        files = october(csv_row("2026-10-28", 1, text="Bad", review_id="a"))
        api = api_of(api_review("a", "Bad", "2026-10-28", stars=1, reply="Sorry"))
        [review] = run(files, api).reviews
        self.assertEqual(review.reply, "Sorry")

    def test_the_apis_translation_is_used_when_the_review_is_in_both(self):
        files = october(csv_row("2026-10-28", 5, text="Sehr gut", review_id="a"))
        api = api_of(api_review("a", "Very good", "2026-10-28", original="Sehr gut"))
        [review] = run(files, api).reviews
        self.assertEqual((review.text, review.original_text), ("Very good", "Sehr gut"))

    def test_a_review_in_both_counts_once_as_a_rating(self):
        files = october(csv_row("2026-10-28", 4, text="x", review_id="a"))
        api = api_of(api_review("a", "x", "2026-10-28", stars=4))
        self.assertEqual(run(files, api).new_ratings.value, 1)


class ApiWindowTest(unittest.TestCase):
    def test_the_api_is_not_asked_for_a_range_that_ended_before_its_window(self):
        calls = []

        def api():
            calls.append(1)
            return []

        old = Period(date(2026, 9, 1), date(2026, 9, 7))
        files = {reviews_path(PACKAGE, date(2026, 9, 1)): reviews_csv()}
        run(files, api, period=old)
        self.assertEqual(calls, [])

    def test_the_api_is_asked_for_the_week_that_just_ended(self):
        calls = []

        def api():
            calls.append(1)
            return []

        run(october(), api)
        self.assertEqual(calls, [1])


class PrivacyTest(unittest.TestCase):
    def test_nothing_that_identifies_a_review_or_its_author_reaches_the_section(self):
        files = october(
            csv_row("2026-10-28", 4, text="Works well", review_id="secret-review-id")
        )
        api = api_of(api_review("secret-review-id", "Works well", "2026-10-28"))
        shown = repr(run(files, api))
        self.assertNotIn("secret-review-id", shown)
        self.assertNotIn("play.google.com", shown)
        self.assertNotIn("A Person", shown)


class TooLateTest(unittest.TestCase):
    def test_a_week_both_sources_cover_has_no_notice(self):
        files = october(csv_row("2026-10-27", 5))
        self.assertEqual(run(files).uncovered, ())

    def test_the_days_the_api_has_dropped_need_the_report_file(self):
        section = run({}, api_of(api_review("a", "Fine", "2026-10-31")))
        self.assertEqual(
            section.uncovered, (Period(date(2026, 10, 26), date(2026, 10, 27)),)
        )
        self.assertEqual(len(section.reviews), 1)

    def test_a_run_a_week_late_misses_the_days_before_the_apis_window(self):
        files = october(csv_row("2026-10-27", 5))
        section = run(files, today=date(2026, 11, 10), period=WEEK)
        self.assertEqual(
            section.uncovered, (Period(date(2026, 11, 1), date(2026, 11, 1)),)
        )

    def test_a_missing_month_is_reported_per_month(self):
        period = Period(date(2026, 10, 28), date(2026, 11, 4))
        section = run(
            october(csv_row("2026-10-29", 5)), period=period, today=date(2026, 11, 20)
        )
        self.assertEqual(
            section.uncovered, (Period(date(2026, 11, 1), date(2026, 11, 4)),)
        )

    def test_a_range_no_source_reaches_is_unavailable(self):
        old = Period(date(2026, 9, 1), date(2026, 9, 7))
        self.assertEqual(run({}, period=old), Unavailable(play_reviews.SOURCE, old))

    def test_a_range_spanning_months_with_no_file_at_all_is_unavailable(self):
        old = Period(date(2026, 9, 28), date(2026, 10, 4))
        self.assertEqual(run({}, period=old), Unavailable(play_reviews.SOURCE, old))

    def test_a_range_with_one_month_covered_is_available(self):
        old = Period(date(2026, 9, 28), date(2026, 10, 4))
        files = october(csv_row("2026-10-02", 5))
        section = run(files, period=old)
        self.assertEqual(
            section.uncovered, (Period(date(2026, 9, 28), date(2026, 9, 30)),)
        )

    def test_a_range_the_report_file_holds_is_available_even_with_no_reviews(self):
        old = Period(date(2026, 9, 1), date(2026, 9, 7))
        files = {reviews_path(PACKAGE, date(2026, 9, 1)): reviews_csv()}
        section = run(files, period=old)
        self.assertEqual(section.uncovered, ())
        self.assertEqual(section.new_ratings.value, 0)


class ReportLagTest(unittest.TestCase):
    def test_a_report_that_stops_inside_the_range_says_where_its_data_ends(self):
        section = run(october(csv_row("2026-10-29", 5)))
        self.assertEqual(section.coverage.data_to, date(2026, 10, 29))

    def test_a_report_through_the_whole_range_has_no_data_to(self):
        section = run(
            october(csv_row("2026-10-29", 5)) | november(csv_row("2026-11-01", 4))
        )
        self.assertIsNone(section.coverage.data_to)

    def test_the_newest_day_counts_a_late_edit(self):
        files = october(csv_row("2026-10-20", 5, text="Fine", updated="2026-10-30"))
        self.assertEqual(run(files).coverage.data_to, date(2026, 10, 30))

    def test_the_previous_range_is_cut_to_the_days_the_report_covers(self):
        files = october(
            csv_row("2026-10-19", 5),
            csv_row("2026-10-22", 3),
            csv_row("2026-10-23", 1),
            csv_row("2026-10-29", 4),
        )
        section = run(files)
        self.assertEqual(
            (section.new_ratings.value, section.new_ratings.previous), (1, 2)
        )

    def test_days_older_than_the_apis_window_are_trusted_to_be_complete(self):
        old = Period(date(2026, 10, 5), date(2026, 10, 11))
        section = run(october(csv_row("2026-10-08", 5)), period=old)
        self.assertIsNone(section.coverage.data_to)

    def test_a_range_starting_after_the_report_ends_is_unavailable(self):
        late = Period(date(2026, 11, 2), date(2026, 11, 3))
        self.assertEqual(
            run(october(csv_row("2026-10-29", 5)), period=late),
            Unavailable(play_reviews.SOURCE, late),
        )

    def test_a_report_with_no_rows_claims_no_lag(self):
        self.assertIsNone(run(october()).coverage.data_to)


class AllPagesTest(unittest.TestCase):
    def test_follows_the_page_token_to_the_last_page(self):
        pages = {
            None: {
                "reviews": [{"reviewId": "a"}],
                "tokenPagination": {"nextPageToken": "t1"},
            },
            "t1": {
                "reviews": [{"reviewId": "b"}],
                "tokenPagination": {"nextPageToken": "t2"},
            },
            "t2": {"reviews": [{"reviewId": "c"}]},
        }
        self.assertEqual(
            [each["reviewId"] for each in all_pages(pages.__getitem__)], ["a", "b", "c"]
        )

    def test_an_empty_window_has_no_reviews_key(self):
        self.assertEqual(all_pages(lambda token: {}), [])


class SourceErrorTest(unittest.TestCase):
    def test_a_reviews_file_without_a_known_column_names_it(self):
        raw = "Date,Other\r\n2026-10-01,1".encode("utf-16")
        files = {reviews_path(PACKAGE, date(2026, 10, 1)): raw}
        with self.assertRaises(SourceError) as raised:
            run(files)
        self.assertIn("Reviewer Language", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
