import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import smoke_check


def failing():
    raise RuntimeError("permission denied")


class RunChecksTest(unittest.TestCase):
    def run_quietly(self, checks):
        output = io.StringIO()
        with redirect_stdout(output):
            code = smoke_check.run_checks(checks)
        return code, output.getvalue()

    def test_all_passing_exits_zero(self):
        code, output = self.run_quietly({"a": lambda: "1 row", "b": lambda: "2 rows"})
        self.assertEqual(code, 0)
        self.assertIn("OK    a: 1 row", output)
        self.assertIn("OK    b: 2 rows", output)

    def test_one_failure_exits_non_zero_and_reports_the_error(self):
        code, output = self.run_quietly({"a": failing})
        self.assertEqual(code, 1)
        self.assertIn("FAIL  a: permission denied", output)

    def test_a_failure_does_not_stop_later_checks(self):
        code, output = self.run_quietly({"a": failing, "b": lambda: "ok"})
        self.assertEqual(code, 1)
        self.assertIn("OK    b: ok", output)

    def test_no_checks_exits_zero(self):
        code, output = self.run_quietly({})
        self.assertEqual(code, 0)
        self.assertEqual(output, "")


class LoadAppConfigTest(unittest.TestCase):
    def test_missing_app_names_the_expected_file(self):
        with self.assertRaises(SystemExit) as raised:
            smoke_check.load_app_config("no-such-app", Path("does/not/exist"))
        self.assertIn("no-such-app.toml", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
