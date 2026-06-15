from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_FILENAME = "dag_manager.json"
DEFAULT_REPO_PATH = "/opt/airflow/dags/repo/"


class ConfigurationError(RuntimeError):
    """Raised when the external DAG Manager configuration is missing or invalid."""


def _default_airflow_home() -> Path:
    try:
        from airflow.configuration import AIRFLOW_HOME  # type: ignore

        return Path(AIRFLOW_HOME).expanduser().resolve()
    except Exception:
        return Path(os.getenv("AIRFLOW_HOME", "/opt/airflow")).expanduser().resolve()


def _path_from_airflow_config() -> Path | None:
    """Read an optional path from ``[dag_manager] config_file`` in airflow.cfg."""

    try:
        from airflow.configuration import conf  # type: ignore

        value = conf.get("dag_manager", "config_file", fallback="").strip()
        return Path(value).expanduser().resolve() if value else None
    except Exception:
        return None


def resolve_config_path(config_file: str | Path | None = None) -> Path:
    """Resolve the external configuration file without storing settings in the package.

    Resolution order:
    1. Explicit path supplied by the caller (used by CLI/tests).
    2. ``[dag_manager] config_file`` from ``airflow.cfg``.
    3. ``$AIRFLOW_HOME/config/dag_manager.json``.
    """

    if config_file:
        return Path(config_file).expanduser().resolve()

    configured = _path_from_airflow_config()
    if configured:
        return configured

    return (DEFAULT_REPO_PATH / "config" / DEFAULT_CONFIG_FILENAME).resolve()


def _mapping(value: Any, key: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigurationError(f"'{key}' must be a JSON object.")
    return value


def _required_string(value: Any, key: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise ConfigurationError(f"'{key}' is required in the DAG Manager JSON configuration.")
    return result


def _optional_string(value: Any, default: str = "") -> str:
    return str(value if value is not None else default).strip()


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    raise ConfigurationError(f"Expected a boolean value, received {value!r}.")


@dataclass(frozen=True)
class Settings:
    config_file: Path
    postgres_conn_id: str
    github_conn_id: str
    github_repository: str
    github_branch: str
    github_dag_path: str
    github_api_url: str
    template_root: Path | None
    auto_create_schema: bool

    @classmethod
    def from_file(cls, config_file: str | Path | None = None) -> "Settings":
        path = resolve_config_path(config_file)
        if not path.is_file():
            raise ConfigurationError(
                f"DAG Manager configuration file was not found: {path}. "
                "Create the file or set [dag_manager] config_file in airflow.cfg."
            )

        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ConfigurationError(f"Invalid JSON in {path}: {exc}") from exc
        except OSError as exc:
            raise ConfigurationError(f"Unable to read DAG Manager configuration {path}: {exc}") from exc

        if not isinstance(document, dict):
            raise ConfigurationError("The root DAG Manager configuration value must be a JSON object.")

        connections = _mapping(document.get("connections"), "connections")
        github = _mapping(document.get("github"), "github")
        templates = _mapping(document.get("templates"), "templates")
        database = _mapping(document.get("database"), "database")

        template_root_raw = _optional_string(templates.get("root"))
        template_root: Path | None = None
        if template_root_raw:
            candidate = Path(template_root_raw).expanduser()
            if not candidate.is_absolute():
                candidate = path.parent / candidate
            template_root = candidate.resolve()

        return cls(
            config_file=path,
            postgres_conn_id=_required_string(
                connections.get("postgres_conn_id"), "connections.postgres_conn_id"
            ),
            github_conn_id=_required_string(connections.get("github_conn_id"), "connections.github_conn_id"),
            github_repository=_required_string(github.get("repository"), "github.repository"),
            github_branch=_optional_string(github.get("branch"), "main") or "main",
            github_dag_path=_optional_string(github.get("dag_path"), "dags/generated").strip("/"),
            github_api_url=(
                _optional_string(github.get("api_url"), "https://api.github.com") or "https://api.github.com"
            ).rstrip("/"),
            template_root=template_root,
            auto_create_schema=_as_bool(database.get("auto_create_schema"), default=False),
        )

    def require_database(self) -> None:
        if not self.postgres_conn_id:
            raise ConfigurationError("connections.postgres_conn_id is not configured.")

    def require_github(self) -> None:
        missing: list[str] = []
        if not self.github_conn_id:
            missing.append("connections.github_conn_id")
        if not self.github_repository:
            missing.append("github.repository")
        if missing:
            raise ConfigurationError(f"Missing GitHub configuration: {', '.join(missing)}")
