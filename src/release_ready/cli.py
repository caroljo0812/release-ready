"""Click CLI for Release Ready."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import click

from release_ready.diff import parse_diff
from release_ready.llm import LLMConfig
from release_ready.orchestrator import render_markdown, render_text, review_diff
from release_ready.sources import diff_from_file, diff_from_github, diff_from_repo, diff_from_stdin, post_github_comment


@click.group()
@click.version_option()
def cli():
    """Release Ready — multi-agent PR release readiness squad."""


@cli.command()
@click.option("--diff", "-d", type=click.Path(exists=False), help="Path to diff file, or '-' for stdin")
@click.option("--repo", "-r", type=click.Path(exists=True, file_okay=False), help="Local repo path")
@click.option("--base", default="main", help="Base ref for local repo diff")
@click.option("--head", default="HEAD", help="Head ref for local repo diff")
@click.option("--specialists", "-s", help="Comma-separated list: changelog,compatibility,test_coverage,deployment")
@click.option("--output", "-o", type=click.Choice(["json", "markdown", "text"]), default="markdown")
@click.option("--post-comment", is_flag=True, help="Post result as GitHub PR comment")
@click.option("--model", help="Override model")
@click.option("--provider", help="Override provider")
def review(
    diff: str | None,
    repo: str | None,
    base: str,
    head: str,
    specialists: str | None,
    output: str,
    post_comment: bool,
    model: str | None,
    provider: str | None,
):
    """Review a diff with the release readiness squad."""
    cfg = LLMConfig()
    model = model or cfg.model
    prov = provider or cfg.provider

    # Resolve diff source
    if diff == "-":
        diff_text = diff_from_stdin()
    elif diff:
        diff_text = diff_from_file(diff)
    elif repo:
        files = diff_from_repo(repo, base, head)
        from release_ready.diff import render_for_specialist
        diff_text_str = render_for_specialist(files)
        result = _do_review(diff_text_str, specialists, model, prov, cfg.api_key)
        _print_result(result, output)
        return
    else:
        click.echo("Error: pass --diff, --repo, or pipe via stdin", err=True)
        sys.exit(1)

    from release_ready.diff import render_for_specialist
    diff_str = render_for_specialist(diff_text)
    result = _do_review(diff_str, specialists, model, prov, cfg.api_key)
    _print_result(result, output)


def _do_review(
    diff_text: str,
    specialists: str | None,
    model: str,
    provider: str,
    api_key: str | None,
):
    active = [s.strip() for s in specialists.split(",")] if specialists else None
    return review_diff(
        diff_text,
        model=model,
        provider=provider,
        api_key=api_key,
        specialists=active,
        concurrency=int(os.environ.get("RR_CONCURRENCY", 4)),
    )


def _print_result(result, output: str):
    if output == "json":
        click.echo(json.dumps({
            "report": result.report,
            "file_count": result.file_count,
            "finding_count": result.finding_count,
            "duration_ms": result.duration_ms,
            "provider": result.provider,
            "specialists": result.specialists,
            "findings": result.findings,
        }, indent=2))
    elif output == "text":
        click.echo(render_text(result))
    else:
        click.echo(render_markdown(result))


@cli.command()
@click.argument("owner_repo")
@click.argument("pr_number", type=int)
@click.option("--post-comment", is_flag=True, help="Post the report as a PR comment")
@click.option("--output", "-o", type=click.Choice(["json", "markdown", "text"]), default="markdown")
@click.option("--specialists", "-s", help="Comma-separated specialist list")
@click.option("--model", help="Override model")
@click.option("--provider", help="Override provider")
def review_pr(
    owner_repo: str,
    pr_number: int,
    post_comment: bool,
    output: str,
    specialists: str | None,
    model: str | None,
    provider: str | None,
):
    """Review a GitHub PR by owner/repo and PR number."""
    cfg = LLMConfig()
    model = model or cfg.model
    prov = provider or cfg.provider
    token = os.environ.get("RR_GITHUB_TOKEN", "")
    if not token:
        click.echo("Error: RR_GITHUB_TOKEN not set", err=True)
        sys.exit(1)

    owner, repo = owner_repo.split("/", 1)
    files, meta = diff_from_github(owner, repo, pr_number, token)
    from release_ready.diff import render_for_specialist
    diff_str = render_for_specialist(files)

    active = [s.strip() for s in specialists.split(",")] if specialists else None
    result = review_diff(
        diff_str,
        model=model,
        provider=prov,
        api_key=cfg.api_key,
        specialists=active,
    )

    body = render_markdown(result) if output != "text" else render_text(result)
    body += "\n\n_Submitted by Release Ready_"

    if post_comment:
        post_github_comment(owner, repo, pr_number, body, token)
        click.echo(f"Comment posted to {owner}/{repo} PR #{pr_number}")

    _print_result(result, output)


@cli.command()
def provider():
    """Show active LLM provider configuration."""
    cfg = LLMConfig()
    click.echo(f"Provider:    {cfg.provider}")
    click.echo(f"Model:       {cfg.model}")
    click.echo(f"Effective:   {cfg.effective_provider}")
    click.echo(f"Max tokens:  {cfg.max_tokens}")
    click.echo(f"Temperature: {cfg.temperature}")


def main():
    cli()
