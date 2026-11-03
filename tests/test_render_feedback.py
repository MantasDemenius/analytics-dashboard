import unittest
from datetime import UTC, date, datetime

from render_fixtures import (
    FEEDBACK_WEEK,
    app,
    feedback,
    part,
    report,
    suggestion,
    user_report,
)

from weekly_report import render as renderer
from weekly_report.model import (
    Failure,
    Unavailable,
)
from weekly_report.periods import Coverage


class FeedbackSectionTest(unittest.TestCase):
    def html(self, **kwargs):
        return renderer.render(
            report(app("first", feedback_section=feedback(**kwargs)))
        )

    def section(self, **kwargs):
        return part(self.html(**kwargs), 'id="app-0-feedback"', 'id="app-0-admob"')

    def cards(self, *reports, **kwargs):
        return self.section(reports=reports, **kwargs).split("<article")[1:]

    def test_has_a_nav_link_and_names_its_range(self):
        section = self.section()
        self.assertIn("26 Oct to 1 Nov 2026", section)
        self.assertIn('<a href="#app-0-feedback">User feedback</a>', self.html())

    def test_counts_the_reports(self):
        one = self.section(reports=[user_report()])
        two = self.section(reports=[user_report(), suggestion()])
        self.assertIn("1 report<", one)
        self.assertIn("2 reports<", two)

    def test_shows_bug_reports_and_feedback_with_their_changes(self):
        section = self.section(
            bugs=2, bugs_before=1, suggestions=3, suggestions_before=5
        )
        self.assertIn("Bug reports", section)
        self.assertIn(">2<", section)
        self.assertIn("1 the week before", section)
        self.assertIn(">3<", section)
        self.assertIn("5 the week before", section)

    def test_more_bug_reports_is_worse(self):
        section = self.section(bugs=3, bugs_before=1)
        self.assertIn(
            '<span class="d worse"><span class="arr">▲</span>+2 (+200.0%)', section
        )

    def test_fewer_bug_reports_is_better(self):
        section = self.section(bugs=0, bugs_before=4)
        self.assertIn(
            '<span class="d better"><span class="arr">▼</span>−4 (−100.0%)', section
        )

    def test_more_feedback_is_neither_better_nor_worse(self):
        section = self.section(
            bugs=1, bugs_before=1, suggestions=4, suggestions_before=2
        )
        self.assertIn(
            '<span class="d neutral"><span class="arr">▲</span>+2 (+100.0%)', section
        )

    def test_shows_how_many_reports_are_not_yet_handled(self):
        section = self.section(unhandled=7)
        self.assertIn("Not yet handled", section)
        self.assertIn(">7<", section)

    def test_nothing_unhandled_says_zero(self):
        self.assertIn(">0<", self.section(unhandled=0))

    def test_a_bug_card_shows_its_kind_date_versions_message_and_error(self):
        [card] = self.cards(
            user_report(
                message="The list is empty",
                app_version="2.4.0",
                android_version="14",
                error="FormatException: end of input",
                at=datetime(2026, 10, 28, 9, 15, tzinfo=UTC),
            )
        )
        self.assertIn('<span class="tag bug">Bug</span>', card)
        self.assertIn("28 Oct 2026", card)
        self.assertIn("App 2.4.0", card)
        self.assertIn("Android 14", card)
        self.assertIn("The list is empty", card)
        self.assertIn("FormatException: end of input", card)
        self.assertNotIn('class="stars"', card)

    def test_a_feedback_card_shows_its_kind_stars_liked_items_and_message(self):
        [card] = self.cards(
            suggestion("Please add search", rating=4, liked=["speed", "design"])
        )
        self.assertIn('<span class="tag feedback">Feedback</span>', card)
        self.assertIn('aria-label="4 out of 5 stars"', card)
        self.assertIn("★★★★☆", card)
        self.assertIn("Liked", card)
        self.assertIn('<span class="tag">speed</span>', card)
        self.assertIn('<span class="tag">design</span>', card)
        self.assertIn("Please add search", card)
        self.assertNotIn("Android", card)

    def test_a_card_shows_the_app_version_it_came_from(self):
        [card] = self.cards(suggestion(app_version="2.5.0-beta"))
        self.assertIn("App 2.5.0-beta", card)

    def test_a_bug_without_android_version_or_error_shows_neither(self):
        [card] = self.cards(user_report())
        self.assertNotIn("Android", card)
        self.assertNotIn("cause", card)

    def test_feedback_with_no_message_and_nothing_liked_shows_only_its_stars(self):
        [card] = self.cards(suggestion("", rating=5, liked=[]))
        self.assertIn("★★★★★", card)
        self.assertNotIn("rtext", card)
        self.assertNotIn("Liked", card)

    def test_a_bug_with_no_message_still_shows_its_error(self):
        [card] = self.cards(user_report("", error="Import failed"))
        self.assertNotIn("rtext", card)
        self.assertIn("Import failed", card)

    def test_a_bug_with_no_email_or_app_id_shows_neither(self):
        [card] = self.cards(user_report())
        self.assertNotIn("private", card)
        self.assertNotIn("Email", card)
        self.assertNotIn("App ID", card)

    def test_a_bug_with_only_an_email_shows_only_that(self):
        [card] = self.cards(user_report(email="someone@example.com"))
        self.assertIn("someone@example.com", card)
        self.assertNotIn("App ID", card)

    def test_lists_every_report_in_the_order_given(self):
        reports = [user_report(f"report-{number}") for number in range(40)]
        cards = self.cards(*reports)
        self.assertEqual(len(cards), 40)
        self.assertIn("report-0<", cards[0])
        self.assertIn("report-39<", cards[39])

    def test_no_reports_says_so(self):
        section = self.section()
        self.assertIn("No reports in this range.", section)
        self.assertNotIn("<article", section)

    def test_report_text_is_escaped(self):
        [card] = self.cards(
            user_report(
                "<script>alert(1)</script>",
                error="a & b",
                email="<i>x</i>@example.com",
                app_id="<b>id</b>",
            )
        )
        self.assertNotIn("<script>alert(1)</script>", card)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", card)
        self.assertIn("a &amp; b", card)
        self.assertIn("&lt;i&gt;x&lt;/i&gt;@example.com", card)
        self.assertIn("&lt;b&gt;id&lt;/b&gt;", card)

    def test_a_message_keeps_its_line_breaks_in_the_markup(self):
        [card] = self.cards(user_report("first\nsecond"))
        self.assertIn("first\nsecond", card)

    def test_a_partly_covered_section_says_where_its_data_ends(self):
        coverage = Coverage(FEEDBACK_WEEK, date(2026, 10, 30))
        self.assertIn("data to 30 Oct", self.section(coverage=coverage))

    def test_a_failed_source_shows_its_error_in_a_full_width_card(self):
        failure = Failure("Firestore feedback", "403 Forbidden")
        html = renderer.render(report(app("first", feedback_section=failure)))
        section = part(html, 'id="app-0-feedback"')
        self.assertIn('class="card wide"', section)
        self.assertIn("Firestore feedback: 403 Forbidden", section)

    def test_an_unreachable_range_says_so_and_is_no_problem(self):
        unavailable = Unavailable("Firestore feedback", FEEDBACK_WEEK)
        html = renderer.render(report(app("first", feedback_section=unavailable)))
        self.assertIn("not available for this range", part(html, 'id="app-0-feedback"'))
        self.assertNotIn('class="problems"', html)


class NewFeedbackGlanceTest(unittest.TestCase):
    def test_is_the_count_of_new_reports_of_both_kinds_with_its_change(self):
        html = renderer.render(
            report(app("first", feedback_section=feedback(new=5, new_before=3)))
        )
        row = part(html, "<tbody>", "</tbody>")
        self.assertIn(">5<", row)
        self.assertIn("+2 (+66.7%)", row)

    def test_more_reports_are_neither_better_nor_worse(self):
        row = part(
            renderer.render(
                report(app("first", feedback_section=feedback(new=9, new_before=3)))
            ),
            "<tbody>",
            "</tbody>",
        )
        self.assertIn('<span class="d neutral"><span class="arr">▲</span>+6', row)

    def test_the_email_line_says_the_count_and_its_change(self):
        lines = renderer.summary(report(app("first")))
        self.assertEqual(
            lines[-2], "  New feedback, 26 Oct to 1 Nov 2026: 5, +2 (+66.7%)"
        )

    def test_the_email_line_carries_no_report_text(self):
        reports = [
            user_report("secret words", email="someone@example.com", app_id="id-1")
        ]
        page = report(app("first", feedback_section=feedback(reports=reports)))
        text = "\n".join(renderer.summary(page))
        for private in ("secret words", "someone@example.com", "id-1"):
            self.assertNotIn(private, text)

    def test_a_failed_source_says_so_in_the_email(self):
        failure = Failure("Firestore feedback", "403 Forbidden")
        lines = renderer.summary(report(app("first", feedback_section=failure)))
        self.assertEqual(
            lines[-2], "  New feedback: Firestore feedback failed, see Problems"
        )
