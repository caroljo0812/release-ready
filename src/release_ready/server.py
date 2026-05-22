"""FastAPI server with auth and size limits."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from release_ready.llm import LLMConfig, DEFAULT_MODEL, DEFAULT_PROVIDER
from release_ready.orchestrator import render_markdown, render_text, review_diff
from release_ready.sources import diff_from_file, diff_from_github, post_github_comment

app = FastAPI(title="Release Ready", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MAX_DIFF_BYTES = int(os.environ.get("RR_MAX_DIFF_BYTES", 1_048_576))
_API_KEY = os.environ.get("RR_API_KEY")


def _check_auth(x_rr_api_key: str | None = Header(None)):
    if _API_KEY and x_rr_api_key != _API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


@app.get("/")
def root() -> dict[str, Any]:
    cfg = LLMConfig()
    return {
        "service": "Release Ready",
        "version": "0.1.0",
        "reviewer": {
            "provider": cfg.provider,
            "model": cfg.model,
            "max_tokens": cfg.max_tokens,
        },
        "endpoints": ["/review/diff", "/review/github", "/provider", "/health"],
        "max_diff_bytes": MAX_DIFF_BYTES,
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/provider")
def provider() -> dict[str, Any]:
    cfg = LLMConfig()
    return {
        "configured_provider": cfg.provider,
        "configured_model": cfg.model,
        "effective_provider": cfg.effective_provider,
        "max_tokens": cfg.max_tokens,
        "temperature": 0.3,
    }


@app.post("/review/diff")
def review_diff_endpoint(
    request: Request,
    x_rr_api_key: str | None = Header(None),
) -> dict[str, Any]:
    _check_auth(x_rr_api_key)
    body = request.app.state if hasattr(request.app.state, "body") else None
    data = request.json()
    diff_text: str = data.get("diff", "")
    specialists: list[str] | None = data.get("specialists")
    output: str = data.get("output", "json")

    if len(diff_text.encode()) > MAX_DIFF_BYTES:
        raise HTTPException(status_code=413, detail=f"Diff exceeds {MAX_DIFF_BYTES} bytes")

    cfg = LLMConfig()
    result = review_diff(
        diff_text,
        model=cfg.model,
        provider=cfg.provider,
        api_key=cfg.api_key,
        specialists=specialists,
        concurrency=int(os.environ.get("RR_CONCURRENCY", 4)),
    )

    if output == "markdown":
        return {"report": render_markdown(result)}
    if output == "text":
        return {"report": render_text(result)}
    return {
        "report": result.report,
        "file_count": result.file_count,
        "finding_count": result.finding_count,
        "duration_ms": result.duration_ms,
        "provider": result.provider,
        "specialists": result.specialists,
        "findings": result.findings,
    }


@app.post("/review/github")
def review_github_endpoint(
    request: Request,
    x_rr_api_key: str | None = Header(None),
) -> dict[str, Any]:
    _check_auth(x_rr_api_key)
    data = request.json()
    owner: str = data["owner"]
    repo: str = data["repo"]
    pr_number: int = data["pr_number"]
    post_comment: bool = data.get("post_comment", False)
    specialists: list[str] | None = data.get("specialists")
    token: str = os.environ.get("RR_GITHUB_TOKEN", "")
    output: str = data.get("output", "markdown")

    files, meta = diff_from_github(owner, repo, pr_number, token)
    # reconstruct unified diff from parsed files
    from release_ready.diff import render_for_specialist
    diff_text = render_for_specialist(files)

    if len(diff_text.encode()) > MAX_DIFF_BYTES:
        raise HTTPException(status_code=413, detail=f"Diff exceeds {MAX_DIFF_BYTES} bytes")

    cfg = LLMConfig()
    result = review_diff(
        diff_text,
        model=cfg.model,
        provider=cfg.provider,
        api_key=cfg.api_key,
        specialists=specialists,
    )

    title = meta.get("title", f"PR #{pr_number}")
    body = render_markdown(result) if output == "markdown" else render_text(result)
    body += f"\n\n_Submitted by Release Ready via GitHub Actions_"

    if post_comment and token:
        post_github_comment(owner, repo, pr_number, body, token)

    return {
        "pr": {"owner": owner, "repo": repo, "number": pr_number, "title": title},
        "report": body,
        "file_count": result.file_count,
        "finding_count": result.finding_count,
    }


def mount_static():
    dist = Path(__file__).parent / "dist"
    if dist.exists():
        app.mount("/demo", StaticFiles(directory=str(dist)), "dist")


def create_app() -> FastAPI:
    mount_static()
    return app


def main():
    import uvicorn
    host = os.environ.get("RR_HOST", "127.0.0.1")
    port = int(os.environ.get("RR_PORT", 8080))
    uvicorn.run(app, host=host, port=port)