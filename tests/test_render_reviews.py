import unittest
from datetime import date, datetime

from render_fixtures import (
    NO_REVIEWS,
    REVIEWS_WEEK,
    app,
    cards,
    chart,
    part,
    report,
    review,
    reviews,
    values,
)

from weekly_report import render as renderer
from weekly_report.model import (
    Failure,
    Label,
)
from weekly_report.periods import Coverage, Period


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
            lines[-5], "  Store rating, 26 Oct to 1 Nov 2026: 3.67, +0.17 stars, better"
        )


class ReviewsSectionTest(unittest.TestCase):
    def section(self, **kwargs):
        html = renderer.render(report(app("first", reviews_section=reviews(**kwargs))))
        return html, part(html, 'id="app-0-reviews"', 'id="app-0-vitals"')

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
