from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from airflow.configuration import conf

DEFAULT_CONFIG_FILENAME = "dag_manager.json"
DEFAULT_REPO_PATH = Path("/opt/airflow/dags/repo/")


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

    env_value = os.getenv("DAG_MANAGER_CONFIG_PATH", "").strip()
    if env_value:
        return Path(env_value).expanduser().resolve()

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
    config_file: Path | None

    postgres_conn_id: str
    github_conn_id: str

    github_repository: str
    github_branch: str
    github_dag_path: str
    github_api_url: str

    storage_mode: str
    local_dag_path: Path | None

    template_root: Path | None
    auto_create_schema: bool

    @classmethod
    def from_airflow_config(cls) -> "Settings | None":
        section = "dag_manager"

        if not conf.has_section(section):
            return None

        def get_required(key: str) -> str:
            value = conf.get(section, key, fallback="").strip()
            if not value:
                raise ConfigurationError(f"Missing required [{section}] {key}")
            return value

        def get_optional(key: str, default: str | None = None) -> str | None:
            value = conf.get(section, key, fallback=default)
            if value is None:
                return None
            value = str(value).strip()
            return value or default

        def get_bool(key: str, default: bool = False) -> bool:
            return conf.getboolean(section, key, fallback=default)

        storage_mode = (get_optional("storage_mode", "github") or "github").lower()
        if storage_mode not in {"github", "local"}:
            raise ConfigurationError(
                "[dag_manager] storage_mode must be either 'github' or 'local'."
            )

        local_dag_path_raw = get_optional(
            "local_dag_path",
            "/opt/airflow/dags/repo/dags/generated",
        )
        local_dag_path = Path(local_dag_path_raw).resolve() if local_dag_path_raw else None

        templates_root_raw = get_optional("templates_root")
        template_root = Path(templates_root_raw).resolve() if templates_root_raw else None

        return cls(
            config_file=None,

            postgres_conn_id=get_required("postgres_conn_id"),
            github_conn_id=get_required("github_conn_id"),

            github_repository=get_required("github_repository"),
            github_branch=get_optional("github_branch", "main") or "main",
            github_dag_path=(get_optional("github_dag_path", "dags/generated") or "dags/generated").strip("/"),
            github_api_url=(get_optional("github_api_url", "https://api.github.com") or "https://api.github.com").rstrip("/"),

            storage_mode=storage_mode,
            local_dag_path=local_dag_path,

            template_root=template_root,
            auto_create_schema=get_bool("auto_create_schema", False),
        )

    @classmethod
    def from_file(cls, config_file: str | Path | None = None) -> "Settings":
        settings_from_airflow = cls.from_airflow_config()
        if settings_from_airflow:
            return settings_from_airflow
        
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
