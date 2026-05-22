"""Deduplicate findings, merge severity, write the final report."""
from __future__ import annotations

from dataclasses import dataclass, field

from release_ready.diff import DiffFile
from release_ready.llm import LLMResponse, chat
from release_ready.specialists import Finding


SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}

REPORT_TEMPLATE = """## Release Readiness Report

{files_summary}

### Findings by Specialist

{by_specialist}

### Action Items

{action_items}

---
_Reviewed by Release Ready (multi-agent squad). Total findings: {total_findings}_
"""


def dedup_findings(findings: list[Finding]) -> list[Finding]:
    """When 2+ specialists flag the same file+line, bump severity one rung."""
    # Group by (file, line, category)
    from collections import defaultdict
    groups: dict[tuple, list[Finding]] = defaultdict(list)
    for f in findings:
        groups[(f.file, f.line, f.category)].append(f)

    seen: dict[tuple, Finding] = {}
    for key, group in groups.items():
        if len(group) > 1:
            # Sort by severity order
            group_sorted = sorted(group, key=lambda x: SEVERITY_ORDER.get(x.severity, 99))
            base = group_sorted[0]
            # Bump severity
            sev_list = list(SEVERITY_ORDER.keys())
            try:
                idx = sev_list.index(base.severity)
                new_sev = sev_list[max(0, idx - 1)]
            except (ValueError, IndexError):
                new_sev = base.severity
            deduped = Finding(
                specialist="consensus",
                file=base.file,
                line=base.line,
                severity=new_sev,
                category=base.category + "-consensus",
                title=f"[{len(group)}x] {base.title}",
                rationale=f"Flagged by {', '.join(set(g.specialist for g in group))}: {base.rationale}",
                suggestion=base.suggestion,
            )
            seen[key] = deduped
        else:
            seen[key] = group[0]

    return sorted(seen.values(), key=lambda x: SEVERITY_ORDER.get(x.severity, 99))


def write_report(
    findings: list[Finding],
    files: list[DiffFile],
    model: str = "mimo-v2.5-pro",
    provider: str = "mimo",
    api_key: str | None = None,
    base_url: str | None = None,
) -> tuple[str, LLMResponse]:
    if not findings:
        return "## Release Readiness Report\n\nNo release risks found.", LLMResponse(
            content="",
            usage=_mock_usage(),
            provider_info={"configured_provider": provider, "configured_model": model, "effective_provider": "mock"},
            raw={},
        )

    files_summary = "\n".join(f"- {f.path_after or f.path_before}" for f in files)

    by_specialist: dict[str, list[Finding]] = {}
    for f in findings:
        by_specialist.setdefault(f.specialist, []).append(f)

    specialist_blocks = []
    for name, fgs in by_specialist.items():
        lines = [f"**{name}** ({len(fgs)} finding{'s' if len(fgs) != 1 else ''})"]
        for fg in sorted(fgs, key=lambda x: SEVERITY_ORDER.get(x.severity, 99)):
            lines.append(f"  - [{fg.severity.upper()}] `{fg.file}:{fg.line}` — {fg.title}")
            if fg.rationale:
                lines.append(f"    _{fg.rationale}_")
            if fg.suggestion:
                lines.append(f"    → {fg.suggestion}")
        specialist_blocks.append("\n".join(lines))

    action_items = []
    for f in sorted(findings, key=lambda x: SEVERITY_ORDER.get(x.severity, 99)):
        if f.severity in ("critical", "high"):
            action_items.append(f"- **[{f.severity}]** {f.title} (`{f.file}:{f.line}`)")

    template_vars = {
        "files_summary": files_summary or "_No files changed_",
        "by_specialist": "\n\n".join(specialist_blocks),
        "action_items": "\n".join(action_items) or "_No critical or high severity items._",
        "total_findings": len(findings),
    }

    # Ask consensus model to write a clean report
    messages = [
        {"role": "system", "content": "You are a release engineering expert. Write a concise, well-structured release readiness report in markdown. Be specific, actionable, and concise."},
        {"role": "user", "content": f"Write a release readiness report based on these findings:\n\n{json.dumps(template_vars, indent=2)}"},
    ]
    resp = chat(messages, model=model, provider=provider, api_key=api_key, base_url=base_url,
                max_tokens=1200, temperature=0.4)
    report = resp.content if resp.content.strip() else REPORT_TEMPLATE.format(**template_vars)
    return report, resp


def _mock_usage():
    from release_ready.llm import Usage
    return Usage(prompt_tokens=50, completion_tokens=20)