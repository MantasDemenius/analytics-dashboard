"""Reads `config/apps/*.toml` (one per app) and `config/report.toml`; `config.example/` shows every key."""

import tomllib
from dataclasses import dataclass
from pathlib import Path

APPS_DIR = Path("config/apps")
REPORT_CONFIG = Path("config/report.toml")
APP_KEYS = [
    "firebase_project",
    "firebase_app_id",
    "package",
    "play_bucket",
    "feedback_collection",
]


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class AppConfig:
    name: str
    firebase_project: str
    firebase_app_id: str
    package: str
    play_bucket: str
    feedback_collection: str
    service_account_key: Path


@dataclass(frozen=True)
class ReportConfig:
    recipient: str
    admob_publisher: str
    chrome: Path | None = None


def _read(path: Path) -> dict:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConfigError(f"no config at {path}; run scripts/setup_app.sh first")


def _require(data: dict, keys: list[str], path: Path) -> None:
    missing = [key for key in keys if key not in data]
    if missing:
        raise ConfigError(f"{path} is missing {', '.join(missing)}")


def load_apps(apps_dir: Path = APPS_DIR) -> list[AppConfig]:
    paths = sorted(apps_dir.glob("*.toml"))
    if not paths:
        raise ConfigError(f"no app config in {apps_dir}; run scripts/setup_app.sh APP")
    apps = []
    for path in paths:
        data = _read(path)
        _require(data, ["service_account_key", *APP_KEYS], path)
        apps.append(
            AppConfig(
                name=path.stem,
                service_account_key=Path(data["service_account_key"]),
                **{key: data[key] for key in APP_KEYS},
            )
        )
    return apps


def load_report(path: Path = REPORT_CONFIG) -> ReportConfig:
    data = _read(path)
    _require(data, ["recipient", "admob_publisher"], path)
    chrome = data.get("chrome")
    return ReportConfig(
        recipient=data["recipient"],
        admob_publisher=data["admob_publisher"],
        chrome=Path(chrome) if chrome else None,
    )
