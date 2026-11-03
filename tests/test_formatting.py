import unittest

from weekly_report.formatting import signed


class SignedTest(unittest.TestCase):
    def test_marks_a_rise_and_a_fall(self):
        self.assertEqual(signed(2.5, 1, " pts"), "+2.5 pts")
        self.assertEqual(signed(-2.5, 1, " pts"), "−2.5 pts")

    def test_a_change_that_rounds_to_nothing_has_no_sign(self):
        self.assertEqual(signed(0.04, 1, " pts"), "0.0 pts")
        self.assertEqual(signed(-0.04, 1, " pts"), "0.0 pts")

    def test_no_change_has_no_sign(self):
        self.assertEqual(signed(0), "0")
