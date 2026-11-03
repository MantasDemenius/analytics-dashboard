import tempfile
import unittest
from pathlib import Path

from weekly_report.config import (
    AppConfig,
    ConfigError,
    ReportConfig,
    load_apps,
    load_report,
)

EXAMPLE = Path(__file__).resolve().parents[1] / "config.example"


class ExampleConfigTest(unittest.TestCase):
    def test_the_example_app_config_loads(self):
        self.assertEqual(
            load_apps(EXAMPLE / "apps"),
            [
                AppConfig(
                    name="myapp",
                    firebase_project="myapp-12345",
                    firebase_app_id="1:123456789012:android:0123456789abcdef",
                    package="com.example.myapp",
                    play_bucket="pubsite_prod_rev_01234567890123456789",
                    feedback_collection="feedback",
                    service_account_key=Path("config/apps/myapp-service-account.json"),
                )
            ],
        )

    def test_the_example_report_config_loads_without_a_chrome_override(self):
        self.assertEqual(
            load_report(EXAMPLE / "report.toml"),
            ReportConfig(
                recipient="author@example.com",
                admob_publisher="pub-XXXXXXXXXXXXXXXX",
                chrome=None,
            ),
        )


class LoadAppsTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.apps = Path(self.directory.name)

    def write_app(self, name: str, text: str) -> None:
        (self.apps / f"{name}.toml").write_text(text, encoding="utf-8")

    def example_text(self) -> str:
        return (EXAMPLE / "apps" / "myapp.toml").read_text(encoding="utf-8")

    def test_every_app_file_loads_in_name_order(self):
        self.write_app("second", self.example_text())
        self.write_app("first", self.example_text())
        self.assertEqual(
            [app.name for app in load_apps(self.apps)], ["first", "second"]
        )

    def test_files_other_than_toml_are_ignored(self):
        self.write_app("first", self.example_text())
        (self.apps / "first.env").write_text("PACKAGE=x", encoding="utf-8")
        self.assertEqual([app.name for app in load_apps(self.apps)], ["first"])

    def test_a_missing_key_names_the_key_and_the_file(self):
        self.write_app("first", self.example_text().replace("play_bucket", "#"))
        with self.assertRaises(ConfigError) as raised:
            load_apps(self.apps)
        self.assertIn("play_bucket", str(raised.exception))
        self.assertIn("first.toml", str(raised.exception))

    def test_no_app_files_is_an_error(self):
        with self.assertRaises(ConfigError) as raised:
            load_apps(self.apps)
        self.assertIn("setup_app.sh", str(raised.exception))


class LoadReportTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "report.toml"

    def test_a_chrome_override_is_a_path(self):
        self.path.write_text(
            'recipient = "a@example.com"\nadmob_publisher = "pub-0"\n'
            'chrome = "D:/Apps/Chrome/chrome.exe"\n',
            encoding="utf-8",
        )
        self.assertEqual(
            load_report(self.path).chrome, Path("D:/Apps/Chrome/chrome.exe")
        )

    def test_a_missing_recipient_is_named(self):
        self.path.write_text('admob_publisher = "pub-0"\n', encoding="utf-8")
        with self.assertRaises(ConfigError) as raised:
            load_report(self.path)
        self.assertIn("recipient", str(raised.exception))

    def test_a_missing_file_is_named(self):
        with self.assertRaises(ConfigError) as raised:
            load_report(self.path)
        self.assertIn("report.toml", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
