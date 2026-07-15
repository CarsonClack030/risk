#!/usr/bin/env python3
"""Create or update a Gitee Release and upload desktop installers."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


API_BASE_URL = "https://gitee.com/api/v5"
RELEASE_SUFFIXES = {".dmg", ".exe"}


class GiteeApiError(RuntimeError):
    """Preserve the HTTP status so callers can distinguish a missing resource."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


class GiteeClient:
    """Small Gitee API client using only Python's standard library."""

    def __init__(self, token: str, owner: str, repo: str) -> None:
        self.token = token
        self.owner = quote(owner, safe="")
        self.repo = quote(repo, safe="")
        self.repo_path = f"/repos/{self.owner}/{self.repo}"

    def _request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        body: bytes | None = None,
        content_type: str = "application/json",
        timeout_seconds: int = 120,
    ) -> Any:
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        request = Request(
            f"{API_BASE_URL}{path}",
            data=body,
            method=method,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self.token}",
                "Content-Type": content_type,
                "User-Agent": "Risk-Studio-Gitee-Publisher/1.0",
            },
        )
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                raw = response.read()
        except HTTPError as exc:
            details = exc.read().decode("utf-8", "replace").strip()
            raise GiteeApiError(
                exc.code,
                f"Gitee API {method} {path} failed ({exc.code}): {details}",
            ) from exc
        except URLError as exc:
            raise RuntimeError(f"Unable to connect to Gitee: {exc.reason}") from exc

        if not raw:
            return None
        return json.loads(raw.decode("utf-8"))

    def tag_exists(self, tag: str) -> bool:
        tags = self._request_json(
            "GET", f"{self.repo_path}/tags?page=1&per_page=100&direction=desc"
        )
        return any(item.get("name") == tag for item in tags)

    def get_release(self, tag: str) -> dict[str, Any] | None:
        encoded_tag = quote(tag, safe="")
        try:
            return self._request_json(
                "GET", f"{self.repo_path}/releases/tags/{encoded_tag}"
            )
        except GiteeApiError as exc:
            if exc.status == 404:
                return None
            raise

    def upsert_release(self, tag: str, name: str, notes: str) -> dict[str, Any]:
        release = self.get_release(tag)
        payload = {
            "tag_name": tag,
            "name": name,
            "body": notes,
            "prerelease": False,
        }
        if release is None:
            payload["target_commitish"] = "main"
            return self._request_json("POST", f"{self.repo_path}/releases", payload)

        return self._request_json(
            "PATCH", f"{self.repo_path}/releases/{release['id']}", payload
        )

    def list_attachments(self, release_id: int) -> list[dict[str, Any]]:
        result = self._request_json(
            "GET",
            f"{self.repo_path}/releases/{release_id}/attach_files?per_page=100",
        )
        return result or []

    def delete_attachment(self, release_id: int, attachment_id: int) -> None:
        self._request_json(
            "DELETE",
            f"{self.repo_path}/releases/{release_id}/attach_files/{attachment_id}",
        )

    def upload_attachment(self, release_id: int, file_path: Path) -> dict[str, Any]:
        boundary = f"----risk-studio-{uuid.uuid4().hex}"
        mime_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        body = b"".join(
            [
                f"--{boundary}\r\n".encode(),
                (
                    'Content-Disposition: form-data; name="file"; '
                    f'filename="{file_path.name}"\r\n'
                ).encode(),
                f"Content-Type: {mime_type}\r\n\r\n".encode(),
                file_path.read_bytes(),
                f"\r\n--{boundary}--\r\n".encode(),
            ]
        )
        return self._request_json(
            "POST",
            f"{self.repo_path}/releases/{release_id}/attach_files",
            body=body,
            content_type=f"multipart/form-data; boundary={boundary}",
            # Gitee may need several minutes to receive and process installer files.
            timeout_seconds=600,
        )


def release_assets(directory: Path) -> list[Path]:
    """Only publish the two installer formats produced by the release workflow."""
    if not directory.is_dir():
        raise FileNotFoundError(f"Release assets directory does not exist: {directory}")

    assets = sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in RELEASE_SUFFIXES
    )
    suffixes = {path.suffix.lower() for path in assets}
    missing = RELEASE_SUFFIXES - suffixes
    if missing:
        expected = ", ".join(sorted(missing))
        raise RuntimeError(f"Missing required release package type(s): {expected}")
    return assets


def wait_for_tag(
    client: GiteeClient, tag: str, timeout_seconds: int, interval_seconds: int
) -> None:
    """The Pull mirror can finish a few minutes after GitHub receives a tag."""
    deadline = time.monotonic() + timeout_seconds
    while True:
        if client.tag_exists(tag):
            print(f"Gitee tag is ready: {tag}")
            return
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"Gitee tag {tag} did not appear within {timeout_seconds} seconds"
            )
        print(f"Waiting for Gitee Pull mirror to sync tag {tag}...")
        time.sleep(interval_seconds)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner", default="CarsonClack030")
    parser.add_argument("--repo", default="risk")
    parser.add_argument("--tag", required=True)
    parser.add_argument("--notes-file", type=Path, required=True)
    parser.add_argument("--assets-dir", type=Path, required=True)
    parser.add_argument("--tag-timeout", type=int, default=600)
    parser.add_argument("--tag-poll-interval", type=int, default=20)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    token = os.environ.get("GITEE_ACCESS_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "GITEE_ACCESS_TOKEN is missing; add it as a GitHub Actions secret"
        )

    notes = args.notes_file.read_text(encoding="utf-8").strip()
    if not notes:
        raise RuntimeError(f"Release notes file is empty: {args.notes_file}")
    assets = release_assets(args.assets_dir)

    client = GiteeClient(token, args.owner, args.repo)
    wait_for_tag(client, args.tag, args.tag_timeout, args.tag_poll_interval)
    release = client.upsert_release(args.tag, f"Risk Studio {args.tag}", notes)
    release_id = int(release["id"])

    existing = {item.get("name"): item for item in client.list_attachments(release_id)}
    for asset in assets:
        old_attachment = existing.get(asset.name)
        if old_attachment is not None:
            print(f"Replacing existing Gitee asset: {asset.name}")
            client.delete_attachment(release_id, int(old_attachment["id"]))
        else:
            print(f"Uploading Gitee asset: {asset.name} ({asset.stat().st_size} bytes)")
        uploaded = client.upload_attachment(release_id, asset)
        print(f"Uploaded: {uploaded.get('browser_download_url', asset.name)}")

    print(f"Gitee Release published: https://gitee.com/{args.owner}/{args.repo}/releases/tag/{args.tag}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (GiteeApiError, OSError, RuntimeError, TimeoutError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
