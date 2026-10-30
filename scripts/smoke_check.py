"""Reads one value from every source an app's report needs, to prove its credentials work.

  smoke_check.py APP   APP names `config/apps/APP.toml`, written by `scripts/setup_app.sh`

Prints counts only, never review or feedback text. Exits non-zero if any check fails.
"""

import subprocess
import sys
import tomllib
from collections.abc import Callable
from pathlib import Path

from google.api_core.exceptions import GoogleAPIError
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request
from google.cloud import firestore, storage
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google_login import CLIENT_FILE, SCOPES, TOKEN_FILE
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

APPS_DIR = Path("config/apps")
SERVICE_ACCOUNT_SCOPES = [
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/androidpublisher",
    "https://www.googleapis.com/auth/playdeveloperreporting",
    "https://www.googleapis.com/auth/devstorage.read_only",
]
CHECK_ERRORS = (
    GoogleAPIError,
    GoogleAuthError,
    HttpError,
    OSError,
    KeyError,
    ValueError,
    RuntimeError,
)
CRASHLYTICS_DISCOVERY = (
    "https://firebasecrashlytics.googleapis.com/$discovery/rest?version=v1alpha"
)


def load_app_config(app: str, apps_dir: Path = APPS_DIR) -> dict:
    path = apps_dir / f"{app}.toml"
    if not path.is_file():
        raise SystemExit(f"No config at {path}; run scripts/setup_app.sh {app} first")
    return tomllib.loads(path.read_text())


def run_checks(checks: dict[str, Callable[[], str]]) -> int:
    failed = 0
    for name, check in checks.items():
        try:
            print(f"OK    {name}: {check()}")
        except CHECK_ERRORS as error:
            failed += 1
            print(f"FAIL  {name}: {error}")
    return 1 if failed else 0


def app_checks(config: dict) -> dict[str, Callable[[], str]]:
    project = config["firebase_project"]
    package = config["package"]
    credentials = service_account.Credentials.from_service_account_file(
        config["service_account_key"], scopes=SERVICE_ACCOUNT_SCOPES
    )

    def crashlytics() -> str:
        client = build(
            "firebasecrashlytics",
            "v1alpha",
            credentials=credentials,
            discoveryServiceUrl=CRASHLYTICS_DISCOVERY,
            static_discovery=False,
        )
        name = f"projects/{project}/apps/{config['firebase_app_id']}/reports/topIssues"
        report = client.projects().apps().reports().get(name=name, pageSize=1).execute()
        return f"{report.get('totalSize', 0)} issues in the last 7 days"

    def firestore_feedback() -> str:
        client = firestore.Client(project=project, credentials=credentials)
        result = client.collection(config["feedback_collection"]).count().get()
        return f"{int(result[0][0].value)} feedback documents"

    def play_vitals() -> str:
        client = build("playdeveloperreporting", "v1beta1", credentials=credentials)
        name = f"apps/{package}/crashRateMetricSet"
        metric_set = client.vitals().crashrate().get(name=name).execute()
        return f"crash rate data fresh to {metric_set['freshnessInfo']['freshnesses'][0]['latestEndTime']}"

    def play_reviews() -> str:
        client = build("androidpublisher", "v3", credentials=credentials)
        response = client.reviews().list(packageName=package, maxResults=100).execute()
        return f"{len(response.get('reviews', []))} reviews in the API window"

    def play_bucket() -> str:
        client = storage.Client(project=project, credentials=credentials)
        blobs = client.list_blobs(
            config["play_bucket"], prefix="reviews/", max_results=50
        )
        return f"{sum(1 for _ in blobs)} review report files"

    return {
        "Crashlytics": crashlytics,
        "Firestore feedback": firestore_feedback,
        "Play vitals": play_vitals,
        "Play reviews": play_reviews,
        "Play report bucket": play_bucket,
    }


def account_checks() -> dict[str, Callable[[], str]]:
    def admob() -> str:
        credentials = Credentials.from_authorized_user_file(str(TOKEN_FILE))
        credentials.refresh(Request())
        accounts = (
            build("admob", "v1", credentials=credentials).accounts().list().execute()
        )
        return f"{len(accounts.get('account', []))} AdMob account(s)"

    def gmail_scope() -> str:
        credentials = Credentials.from_authorized_user_file(str(TOKEN_FILE))
        missing = set(SCOPES) - set(credentials.scopes or [])
        if missing:
            raise RuntimeError(f"sign-in is missing {', '.join(sorted(missing))}")
        return "sign-in may send mail"

    return {"AdMob": admob, "Gmail send": gmail_scope}


def private_files_ignored(config: dict) -> Callable[[], str]:
    def check() -> str:
        paths = [config["service_account_key"], str(CLIENT_FILE), str(TOKEN_FILE)]
        visible = [
            path
            for path in paths
            if subprocess.run(
                ["git", "check-ignore", "-q", path], check=False
            ).returncode
            != 0
        ]
        if visible:
            raise RuntimeError(f"not gitignored: {', '.join(visible)}")
        return "keys and tokens are gitignored"

    return check


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    config = load_app_config(sys.argv[1])
    checks = app_checks(config) | account_checks()
    checks["Git"] = private_files_ignored(config)
    sys.exit(run_checks(checks))


if __name__ == "__main__":
    main()
