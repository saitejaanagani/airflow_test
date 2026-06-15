from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class AirflowConnectionError(RuntimeError):
    """Raised when a required Airflow Connection cannot be loaded or is incomplete."""


def _base_hook_class():
    """Return BaseHook using the Airflow 3 public import, with a compatibility fallback."""

    try:
        from airflow.sdk.bases.hook import BaseHook  # type: ignore

        return BaseHook
    except ImportError:
        from airflow.hooks.base import BaseHook  # type: ignore

        return BaseHook


def get_airflow_connection(conn_id: str) -> Any:
    try:
        return _base_hook_class().get_connection(conn_id)
    except Exception as exc:
        raise AirflowConnectionError(f"Unable to load Airflow Connection '{conn_id}': {exc}") from exc


@dataclass(frozen=True)
class GitHubCredentials:
    token: str


def get_github_credentials(conn_id: str) -> GitHubCredentials:
    connection = get_airflow_connection(conn_id)
    extras = getattr(connection, "extra_dejson", {}) or {}
    token = str(getattr(connection, "password", None) or extras.get("token") or "").strip()
    if not token:
        raise AirflowConnectionError(
            f"Airflow Connection '{conn_id}' does not contain a GitHub token. "
            "Store the token in the Connection password field."
        )
    return GitHubCredentials(token=token)
