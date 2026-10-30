import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import google_login


class SignInTest(unittest.TestCase):
    def test_each_sign_in_holds_exactly_one_scope(self):
        for name, sign_in in google_login.SIGN_INS.items():
            with self.subTest(name):
                self.assertEqual(len(sign_in.scopes), 1)

    def test_admob_sign_in_cannot_send_mail(self):
        self.assertNotIn(
            "https://www.googleapis.com/auth/gmail.send",
            google_login.SIGN_INS["admob"].scopes,
        )

    def test_sign_ins_write_different_token_files(self):
        files = [sign_in.token_file for sign_in in google_login.SIGN_INS.values()]
        self.assertEqual(len(files), len(set(files)))

    def test_unknown_sign_in_exits_with_usage(self):
        with self.assertRaises(SystemExit) as raised:
            google_login.sign_in_for(["google_login.py", "drive"])
        self.assertIn("admob", str(raised.exception))

    def test_missing_argument_exits_with_usage(self):
        with self.assertRaises(SystemExit):
            google_login.sign_in_for(["google_login.py"])

    def test_known_sign_in_is_returned(self):
        sign_in = google_login.sign_in_for(["google_login.py", "gmail"])
        self.assertEqual(sign_in, google_login.SIGN_INS["gmail"])


if __name__ == "__main__":
    unittest.main()
