"""Diff sources: text, file, local repo, GitHub PR."""
from __future__ import annotations

import json
import subprocess
import urllib.request
from pathlib import Path
from typing import Any

from release_ready.diff import DiffFile, parse_diff


def diff_from_text(text: str) -> list[DiffFile]:
    return parse_diff(text)


def diff_from_file(path: str | Path) -> list[DiffFile]:
    with open(path) as f:
        return parse_diff(f.read())


def diff_from_stdin() -> list[DiffFile]:
    import sys
    return parse_diff(sys.stdin.read())


def diff_from_repo(
    repo_path: str | Path,
    base_ref: str = "main",
    head_ref: str = "HEAD",
    remote: str = "origin",
) -> list[DiffFile]:
    repo = Path(repo_path)
    result = subprocess.run(
        ["git", "diff", f"{remote}/{base_ref}...{head_ref}"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    return parse_diff(result.stdout)


def diff_from_github(
    owner: str,
    repo: str,
    pr_number: int,
    token: str | None = None,
) -> tuple[list[DiffFile], dict[str, Any]]:
    """Fetch diff + PR metadata from GitHub API."""
    headers = {"Accept": "application/vnd.github.v3.diff"}
    if token:
        headers["Authorization"] = f"token {token}"
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
    req = urllib.request.Request(url, headers=headers)
    resp = urllib.request.urlopen(req, timeout=30)
    diff_text = resp.read().decode()
    files = parse_diff(diff_text)

    # Fetch PR metadata
    meta_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
    req2 = urllib.request.Request(meta_url, headers={"Authorization": f"token {token}"} if token else {})
    meta_resp = urllib.request.urlopen(req2, timeout=15)
    meta = json.loads(meta_resp.read())
    return files, meta


def post_github_comment(
    owner: str,
    repo: str,
    pr_number: int,
    body: str,
    token: str,
) -> dict[str, Any]:
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{pr_number}/comments"
    data = json.dumps({"body": body}).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"token {token}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.github.v3+json",
        },
    )
    resp = urllib.request.urlopen(req, timeout=20)
    return json.loads(resp.read())