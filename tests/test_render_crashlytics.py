import re
import unittest
from datetime import date

from render_fixtures import (
    CRASHLYTICS_WEEK,
    app,
    cards,
    chart,
    crashlytics,
    issue,
    part,
    report,
    values,
)

from weekly_report import render as renderer
from weekly_report.model import (
    Crashlytics,
    ErrorKind,
    Failure,
    IssueState,
    Metric,
    Point,
    Signal,
    Unavailable,
)
from weekly_report.periods import Coverage


class CrashFreeCardTest(unittest.TestCase):
    def card(self, section):
        return cards(
            renderer.render(report(app("first", crashlytics_section=section)))
        )[5]

    def test_shows_the_percent_with_two_decimals_and_the_previous_value(self):
        card = self.card(crashlytics(free=97.5, before=96.0))
        self.assertIn(">Crash free users<", card)
        self.assertIn(">97.50%<", card)
        self.assertIn("96.00% the week before", card)
        self.assertIn("26 Oct to 1 Nov 2026", card)

    def test_a_rise_is_better_and_shows_points(self):
        card = self.card(crashlytics(free=97.5, before=96.0))
        self.assertIn(
            '<span class="d better"><span class="arr">▲</span>+1.50 pts', card
        )

    def test_a_fall_is_worse_and_no_change_is_flat(self):
        fall = self.card(crashlytics(free=95.0, before=96.0))
        flat = self.card(crashlytics(free=96.0, before=96.0))
        self.assertIn('<span class="d worse"><span class="arr">▼</span>−1.00 pts', fall)
        self.assertIn('<span class="arr">■</span>no change', flat)

    def test_a_previous_period_past_the_90_days_is_not_compared(self):
        card = self.card(crashlytics(free=97.5, before=0))
        self.assertIn("nothing to compare", card)
        self.assertIn("none the week before", card)
        self.assertIn('<span class="d neutral">', card)

    def test_a_period_with_no_users_says_none(self):
        card = self.card(crashlytics(free=0, before=0))
        self.assertIn(">none<", card)

    def test_the_note_says_what_it_counts_and_the_days_it_uses(self):
        self.assertIn("fatal crashes, UTC days", self.card(crashlytics()))

    def test_draws_its_12_week_sparkline(self):
        html = renderer.render(
            report(app("first", crashlytics_section=crashlytics(free=97.5)))
        )
        self.assertEqual(values(chart(html, "Crash free users, 12 weeks"))[-1], 97.5)

    def test_a_trend_cut_short_by_the_limit_draws_what_there_is(self):
        short = Crashlytics(
            Coverage(CRASHLYTICS_WEEK),
            Metric(97.5, 0, trend=(Point(CRASHLYTICS_WEEK.start, 97.5),)),
            (),
        )
        html = renderer.render(report(app("first", crashlytics_section=short)))
        self.assertEqual(values(chart(html, "Crash free users, 12 weeks")), [97.5])

    def test_a_failed_crashlytics_source_fails_the_card(self):
        card = self.card(Failure("Crashlytics", "403 Forbidden"))
        self.assertIn("Crashlytics failed", card)

    def test_an_unreachable_range_says_so(self):
        card = self.card(Unavailable("Crashlytics", CRASHLYTICS_WEEK))
        self.assertIn("not available for this range", card)

    def test_the_email_line_says_the_percent_and_its_change(self):
        lines = renderer.summary(report(app("first")))
        self.assertEqual(
            lines[-4],
            "  Crash free users, 26 Oct to 1 Nov 2026: 97.50%, +1.50 pts, better",
        )

    def test_the_at_a_glance_table_has_crash_free_users_before_the_play_crash_rate(
        self,
    ):
        glance = part(renderer.render(report(app("first"))), '<section class="glance"')
        self.assertEqual(
            re.findall(r"<th>(.*?)</th>", glance)[-4:-1],
            ["Crash free users", "Play crash rate", "New feedback"],
        )


class CrashlyticsSectionTest(unittest.TestCase):
    def section(self, issues=(), **kwargs):
        section = crashlytics(issues=issues, **kwargs)
        html = renderer.render(report(app("first", crashlytics_section=section)))
        return part(html, 'id="app-0-crashlytics"', 'id="app-0-feedback"')

    def rows(self, section):
        return section.split('<tr class="issue')[1:]

    def test_has_a_nav_link_and_names_its_range(self):
        section = self.section()
        self.assertIn(">Issues<", section)
        self.assertIn("26 Oct to 1 Nov 2026", section)
        html = renderer.render(report(app("first")))
        self.assertIn('<a href="#app-0-crashlytics">Crashlytics: issues</a>', html)

    def test_counts_the_issues(self):
        self.assertIn("2 issues", self.section([issue("a"), issue("b")]))
        self.assertIn("1 issue<", self.section([issue("a")]))

    def test_lists_every_issue_in_the_order_given(self):
        rows = self.rows(self.section([issue(f"issue-{n}") for n in range(60)]))
        self.assertEqual(len(rows), 60)
        self.assertIn("issue-0<", rows[0])
        self.assertIn("issue-59<", rows[59])

    def test_a_row_shows_users_events_and_the_version_it_was_first_seen_in(self):
        [row] = self.rows(self.section([issue(users=12, events=1034, version="2.3.0")]))
        self.assertIn('<td class="n">12</td>', row)
        self.assertIn('<td class="n">1,034</td>', row)
        self.assertIn("2.3.0", row)

    def test_a_missing_version_shows_a_dash(self):
        [row] = self.rows(self.section([issue(version=None)]))
        self.assertIn("<td>–</td>", row)

    def test_a_row_shows_the_title_the_subtitle_and_the_kind_of_error(self):
        [row] = self.rows(
            self.section(
                [issue("Widget.render", subtitle="IllegalState", kind=ErrorKind.ANR)]
            )
        )
        self.assertIn("Widget.render", row)
        self.assertIn("IllegalState", row)
        self.assertIn('<span class="tag">ANR</span>', row)

    def test_names_each_kind_of_error(self):
        kinds = self.section(
            [issue(kind=ErrorKind.FATAL), issue(kind=ErrorKind.NON_FATAL)]
        )
        self.assertIn(">Crash<", kinds)
        self.assertIn(">Non-fatal<", kinds)

    def test_the_title_links_to_the_console(self):
        [row] = self.rows(self.section([issue(link="https://console.example/x")]))
        self.assertIn('<a href="https://console.example/x"', row)

    def test_an_issue_without_a_link_has_a_plain_title(self):
        [row] = self.rows(self.section([issue("plain", link=None)]))
        self.assertNotIn("<a ", row)
        self.assertIn("plain", row)

    def test_a_new_issue_is_called_out(self):
        [row] = self.rows(self.section([issue(signals=[Signal.FRESH])]))
        self.assertIn('<span class="tag fresh">New</span>', row)
        self.assertTrue(row.startswith(" attention"))

    def test_a_regressed_issue_is_called_out(self):
        [row] = self.rows(self.section([issue(signals=[Signal.REGRESSED])]))
        self.assertIn('<span class="tag regressed">Regressed</span>', row)
        self.assertTrue(row.startswith(" attention"))

    def test_the_other_signals_are_named_but_not_called_out(self):
        [row] = self.rows(
            self.section([issue(signals=[Signal.EARLY, Signal.REPETITIVE])])
        )
        self.assertIn('<span class="tag early">Early</span>', row)
        self.assertIn('<span class="tag repetitive">Repetitive</span>', row)
        self.assertFalse(row.startswith(" attention"))

    def test_an_issue_with_no_signals_has_no_signal_tags(self):
        [row] = self.rows(self.section([issue()]))
        for name in ("New", "Regressed", "Early", "Repetitive"):
            self.assertNotIn(f">{name}<", row)

    def test_a_closed_or_muted_issue_says_so_and_an_open_one_does_not(self):
        closed, muted, open_ = self.rows(
            self.section(
                [
                    issue(state=IssueState.CLOSED),
                    issue(state=IssueState.MUTED),
                    issue(state=IssueState.OPEN),
                ]
            )
        )
        self.assertIn(">Closed<", closed)
        self.assertIn(">Muted<", muted)
        self.assertNotIn(">Open<", open_)

    def test_issue_text_is_escaped(self):
        [row] = self.rows(self.section([issue("<b>x</b>", subtitle="a & b")]))
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", row)
        self.assertIn("a &amp; b", row)

    def test_no_issues_says_so(self):
        section = self.section()
        self.assertIn("No issues in this range.", section)
        self.assertNotIn("<table", section)

    def test_a_partly_covered_section_says_where_its_data_ends(self):
        coverage = Coverage(CRASHLYTICS_WEEK, date(2026, 10, 30))
        self.assertIn("data to 30 Oct", self.section(coverage=coverage))

    def test_a_failed_source_shows_its_error_in_a_full_width_card(self):
        failure = Failure("Crashlytics", "403 Forbidden")
        html = renderer.render(report(app("first", crashlytics_section=failure)))
        section = part(html, 'id="app-0-crashlytics"')
        self.assertIn('class="card wide"', section)
        self.assertIn("Crashlytics: 403 Forbidden", section)

    def test_an_unreachable_range_says_so_and_is_no_problem(self):
        unavailable = Unavailable("Crashlytics", CRASHLYTICS_WEEK)
        html = renderer.render(report(app("first", crashlytics_section=unavailable)))
        self.assertIn(
            "not available for this range", part(html, 'id="app-0-crashlytics"')
        )
        self.assertNotIn('class="problems"', html)
