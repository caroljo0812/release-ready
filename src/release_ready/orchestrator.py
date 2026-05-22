"""Parallel fan-out to specialists + report rendering."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any

from release_ready.diff import DiffFile
from release_ready.llm import Usage
from release_ready.orchestrator import _thread_runner, render_for_specialist
from release_ready.specialists import Finding, SPECIALISTS, run_specialist

logger = logging.getLogger(__name__)


@dataclass
class SpecialistResult:
    name: str
    findings: list[Finding]
    duration_ms: int
    error: str | None = None


@dataclass
class ReviewResult:
    report: str
    file_count: int
    finding_count: int
    duration_ms: int
    provider: dict[str, Any]
    specialists: list[dict[str, Any]]
    findings: list[dict[str, Any]]
    diff_files: list[DiffFile] = field(default_factory=list)


def review_diff(
    diff_text: str,
    model: str = "mimo-v2.5-pro",
    provider: str = "mimo",
    api_key: str | None = None,
    base_url: str | None = None,
    specialists: list[str] | None = None,
    concurrency: int = 4,
    max_tokens: int = 800,
) -> ReviewResult:
    from release_ready.consensus import dedup_findings, write_report
    from release_ready.diff import parse_diff

    files = parse_diff(diff_text)
    diff_for_llm = render_for_specialist(files)

    active = specialists or SPECIALISTS
    start = time.monotonic()
    all_findings: list[Finding] = []
    specialist_results: list[SpecialistResult] = []
    total_usage = Usage()

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {}
        for name in active:
            fut = pool.submit(
                run_specialist,
                diff_for_llm,
                name,
                model=model,
                provider=provider,
                api_key=api_key,
                base_url=base_url,
                max_tokens=max_tokens,
            )
            futures[fut] = name

        for fut in as_completed(futures):
            name = futures[fut]
            t0 = time.monotonic()
            try:
                findings, resp = fut.result()
                all_findings.extend(findings)
                total_usage.prompt_tokens += resp.usage.prompt_tokens
                total_usage.completion_tokens += resp.usage.completion_tokens
                specialist_results.append(SpecialistResult(
                    name=name,
                    findings=findings,
                    duration_ms=int((time.monotonic() - t0) * 1000),
                    error=None,
                ))
            except Exception as exc:
                logger.warning("Specialist %s failed: %s", name, exc)
                specialist_results.append(SpecialistResult(
                    name=name,
                    findings=[],
                    duration_ms=int((time.monotonic() - t0) * 1000),
                    error=str(exc),
                ))

    deduped = dedup_findings(all_findings)
    report, _ = write_report(deduped, files, model=model, provider=provider,
                             api_key=api_key, base_url=base_url)
    total_ms = int((time.monotonic() - start) * 1000)

    return ReviewResult(
        report=report,
        file_count=len(files),
        finding_count=len(deduped),
        duration_ms=total_ms,
        provider={
            "configured_provider": provider,
            "configured_model": model,
            "effective_provider": provider if provider in ("mimo","openai","together") else "custom",
        },
        specialists=[
            {"name": s.name, "findings": len(s.findings), "duration_ms": s.duration_ms, "error": s.error}
            for s in sorted(specialist_results, key=lambda x: x.name)
        ],
        findings=[_finding_dict(f) for f in deduped],
        diff_files=files,
    )


def _finding_dict(f: Finding) -> dict[str, Any]:
    return {
        "specialist": f.specialist,
        "file": f.file,
        "line": f.line,
        "severity": f.severity,
        "category": f.category,
        "title": f.title,
        "rationale": f.rationale,
        "suggestion": f.suggestion,
    }


def render_text(result: ReviewResult) -> str:
    lines = [f"Release Ready Report ({result.file_count} files, {result.finding_count} findings, {result.duration_ms}ms)"]
    for s in result.specialists:
        err = f" [ERROR: {s['error']}]" if s["error"] else f" ({s['findings']} findings)"
        lines.append(f"  [{s['name']}]{err}")
    lines.append("")
    lines.append(result.report)
    return "\n".join(lines)


def render_markdown(result: ReviewResult) -> str:
    lines = [f"## Release Readiness Report\n"]
    lines.append(f"_{result.file_count} files, {result.finding_count} findings, {result.duration_ms}ms_\n")
    lines.append("### Specialists\n")
    for s in result.specialists:
        err = f" — ERROR" if s["error"] else f" — {s['findings']} findings"
        lines.append(f"- **{s['name']}**{err}")
    lines.append("\n" + result.report)
    return "\n".join(lines)