"""What the sources have in common: their error, how far they reach, and how they sign in."""

from datetime import date

from google.oauth2 import service_account

from weekly_report.config import AppConfig
from weekly_report.model import Unavailable
from weekly_report.periods import Coverage, Period, week_ending_by

CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"


class SourceError(Exception):
    pass


def reached(
    source: str, period: Period | None, data_to: date | None
) -> Coverage | Unavailable:
    """How far a source's data, which ends on `data_to`, reaches into `period`.

    With no `period` it is the newest Monday to Sunday week ending by `data_to`, which needs a
    `data_to`. A source with no data, or none reaching the period, is `Unavailable`.
    """
    chosen = period or week_ending_by(data_to)
    return Coverage.reaching(chosen, data_to) or Unavailable(source, chosen)


def service_account_credentials(
    app: AppConfig, scope: str
) -> service_account.Credentials:
    return service_account.Credentials.from_service_account_file(
        str(app.service_account_key), scopes=[scope]
    )
