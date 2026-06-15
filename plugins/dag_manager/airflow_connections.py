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
    api_url: str


def get_github_credentials(conn_id: str) -> GitHubCredentials:
    connection = get_airflow_connection(conn_id)
    extras = getattr(connection, "extra_dejson", {}) or {}
    conn_type = str(getattr(connection, "conn_type", "") or "").strip().lower()
    if conn_type and conn_type != "github":
        raise AirflowConnectionError(
            f"Airflow Connection '{conn_id}' must use connection type 'github', not '{conn_type}'."
        )
    access_token = str(getattr(connection, "password", None) or extras.get("token") or "").strip()
    host = str(getattr(connection, "host", None) or extras.get("api_url") or extras.get("github_api_url") or "").strip()
    api_url = _normalize_api_url(
        host
        or "https://api.github.com"
    )
    if not access_token:
        raise AirflowConnectionError(
            f"Airflow Connection '{conn_id}' does not contain a GitHub token. "
            "Store the token in the Connection password field."
        )
    return GitHubCredentials(token=access_token, api_url=api_url)


def _normalize_api_url(value: Any) -> str:
    api_url = str(value or "").strip().rstrip("/")
    if not api_url:
        return "https://api.github.com"
    if not api_url.startswith(("http://", "https://")):
        api_url = f"https://{api_url}"
    return api_url
