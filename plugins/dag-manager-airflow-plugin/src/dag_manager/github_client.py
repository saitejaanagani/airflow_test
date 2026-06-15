from __future__ import annotations

import base64
from dataclasses import dataclass
from urllib.parse import quote

import httpx

from dag_manager.airflow_connections import get_github_credentials
from dag_manager.config import Settings


@dataclass(frozen=True)
class GitHubWriteResult:
    commit_sha: str | None
    content_sha: str | None
    html_url: str | None


class GitHubClient:
    def __init__(self, settings: Settings):
        settings.require_github()
        credentials = get_github_credentials(settings.github_conn_id)
        self.settings = settings
        self.client = httpx.Client(
            base_url=settings.github_api_url,
            timeout=30.0,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {credentials.token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "airflow-dag-manager-plugin",
            },
        )

    def close(self) -> None:
        self.client.close()

    def _contents_url(self, path: str) -> str:
        encoded_path = "/".join(quote(part, safe="") for part in path.strip("/").split("/"))
        return f"/repos/{self.settings.github_repository}/contents/{encoded_path}"

    def get_file(self, path: str) -> dict | None:
        response = self.client.get(self._contents_url(path), params={"ref": self.settings.github_branch})
        if response.status_code == 404:
            return None
        self._raise_for_status(response)
        return response.json()

    def upsert_file(self, path: str, content: str, commit_message: str) -> GitHubWriteResult:
        existing = self.get_file(path)
        payload = {
            "message": commit_message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "branch": self.settings.github_branch,
        }
        if existing:
            payload["sha"] = existing["sha"]

        response = self.client.put(self._contents_url(path), json=payload)
        self._raise_for_status(response)
        body = response.json()
        return GitHubWriteResult(
            commit_sha=(body.get("commit") or {}).get("sha"),
            content_sha=(body.get("content") or {}).get("sha"),
            html_url=(body.get("content") or {}).get("html_url"),
        )

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            message = response.text
            try:
                message = response.json().get("message", message)
            except ValueError:
                pass
            raise RuntimeError(f"GitHub API request failed ({response.status_code}): {message}") from exc
