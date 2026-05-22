"""Four specialist agents with strict JSON finding contract."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from release_ready.llm import LLMResponse, chat


@dataclass
class Finding:
    specialist: str
    file: str
    line: int
    severity: str  # critical / high / medium / low / info
    category: str
    title: str
    rationale: str
    suggestion: str


SPECIALISTS = ["changelog", "compatibility", "test_coverage", "deployment"]

SYSTEM_PROMPT = (
    "You are a {name} specialist reviewing a code diff. "
    "You return ONLY a valid JSON array of findings, nothing else. "
    "Each finding must have: specialist, file, line, severity, category, title, rationale, suggestion. "
    "If no findings, return []."
)

SPECIALIST_PROMPTS = {
    "changelog": """You are a changelog risk specialist reviewing a unified diff.

Flag issues that affect the project's changelog or release notes:
- Breaking changes to public APIs or CLI commands
- New public APIs, new CLI flags, new environment variables
- Deprecation notices needed
- Migration guide or upgrade notes required
- Changes to file formats, data schemas, or configuration defaults
- Security-relevant changes (even if already fixed)

For each finding, set severity:
- critical: breaking change to stable API
- high: new public API or deprecation
- medium: behavior change visible to users
- low: documentation-only change

Return ONLY a JSON array of findings. Example:
[
  {"specialist": "changelog", "file": "src/api.py", "line": 42, "severity": "high",
   "category": "new-api", "title": "New /deploy endpoint",
   "rationale": "Adds a new public endpoint not previously documented",
   "suggestion": "Add to CHANGELOG.md and release notes under [New]"}
]""",

    "compatibility": """You are a compatibility and version-risk specialist reviewing a unified diff.

Flag issues that could break existing users or conflict with other packages:
- Semver violations (removing/renaming public symbols)
- Breaking changes to function signatures
- Peer dependency conflicts
- Changes to required Python version
- Changes to configuration file formats
- Breaking changes to return types or exception types
- Changes to default values that affect existing behavior

For each finding, set severity:
- critical: removes a public symbol or changes signature
- high: changes behavior of existing public API
- medium: changes defaults or optional params
- low: internal implementation change

Return ONLY a JSON array of findings.""",

    "test_coverage": """You are a test coverage specialist reviewing a unified diff.

Flag issues related to test coverage:
- New code paths without corresponding test cases
- Missing edge case coverage for new logic
- Brittle assertions that will break on minor data changes
- Integration tests missing for new user-facing features
- Test files that need updating when source changes
- Overmocked tests that test the mock, not the code

For each finding, set severity:
- critical: new critical path with no tests
- high: new feature with no tests
- medium: edge case not covered
- low: existing tests that should be updated

Return ONLY a JSON array of findings.""",

    "deployment": """You are a deployment safety specialist reviewing a unified diff.

Flag issues that could cause problems when shipping this code:
- Build size regressions (new large dependencies, assets, bundling)
- Configuration drift between environments
- Rollback risk (stateful changes, migrations, schema changes)
- Missing environment variables or secrets
- Changes to startup / initialization order
- Rate limiting, timeouts, or circuit breaker changes
- New background jobs, cron tasks, or webhooks
- Changes to Dockerfile, docker-compose, or deployment configs

For each finding, set severity:
- critical: breaking migration or no rollback path
- high: config change or new background job
- medium: build size change or init order change
- low: documentation-only deployment note

Return ONLY a JSON array of findings.""",
}


def _build_messages(diff_text: str, specialist: str) -> list[dict[str, str]]:
    prompt = SPECIALIST_PROMPTS.get(specialist, SPECIALIST_PROMPTS["changelog"])
    return [
        {"role": "system", "content": SYSTEM_PROMPT.format(name=specialist)},
        {"role": "user", "content": f"Review this diff:\n\n{diff_text}"},
    ]


def run_specialist(
    diff_text: str,
    specialist: str,
    model: str = "mimo-v2.5-pro",
    provider: str = "mimo",
    api_key: str | None = None,
    base_url: str | None = None,
    max_tokens: int = 800,
) -> tuple[list[Finding], LLMResponse]:
    if provider == "mock" or not api_key:
        return [], LLMResponse(
            content="[]",
            usage=_mock_usage(),
            provider_info={"configured_provider": provider, "configured_model": model, "effective_provider": "mock"},
            raw={},
        )

    messages = _build_messages(diff_text, specialist)
    resp = chat(
        messages,
        model=model,
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        max_tokens=max_tokens,
        temperature=0.3,
    )

    findings = _parse_findings(resp.content, specialist)
    return findings, resp


def _parse_findings(raw: str, specialist: str) -> list[Finding]:
    import re
    text = raw.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if m:
        text = m.group(1)

    # Try primary JSON parse
    for attempt in range(2):
        try:
            data = json.loads(text)
            break
        except json.JSONDecodeError:
            import re as _re
            text = _re.sub(r",(\s*[}\]])", r"\1", text)
    else:
        return []

    if isinstance(data, dict):
        data = data.get("findings", data.get("issues", []))

    findings = []
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict):
            continue
        findings.append(Finding(
            specialist=item.get("specialist", specialist),
            file=str(item.get("file", "")),
            line=int(item.get("line", 0) or 0),
            severity=str(item.get("severity", "medium")),
            category=str(item.get("category", "")),
            title=str(item.get("title", "")),
            rationale=str(item.get("rationale", "")),
            suggestion=str(item.get("suggestion", "")),
        ))
    return findings


def _mock_usage():
    from release_ready.llm import Usage
    return Usage(prompt_tokens=100, completion_tokens=30)