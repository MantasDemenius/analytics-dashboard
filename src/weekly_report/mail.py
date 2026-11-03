"""Emails the report PDF through the Gmail API, signed in by `scripts/google_login.py gmail`."""

import base64
from email.message import EmailMessage
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from weekly_report.model import Report
from weekly_report.periods import Period
from weekly_report.render import summary

GMAIL_TOKEN = Path("config/gmail-token.json")
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def subject(period: Period) -> str:
    return f"Weekly app report, {period.label()}"


def message(recipient: str, report: Report, pdf: bytes) -> EmailMessage:
    email = EmailMessage()
    email["To"] = recipient
    email["Subject"] = subject(report.period)
    email.set_content("\n".join([*summary(report), "", "The full report is attached."]))
    email.add_attachment(
        pdf,
        maintype="application",
        subtype="pdf",
        filename=(
            f"weekly-app-report-{report.period.start}-to-{report.period.end}.pdf"
        ),
    )
    return email


def send(email: EmailMessage, token_file: Path = GMAIL_TOKEN) -> None:
    credentials = Credentials.from_authorized_user_file(str(token_file), GMAIL_SCOPES)
    gmail = build("gmail", "v1", credentials=credentials, cache_discovery=False)
    raw = base64.urlsafe_b64encode(email.as_bytes()).decode("ascii")
    gmail.users().messages().send(userId="me", body={"raw": raw}).execute()
