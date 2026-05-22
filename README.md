# Release Ready

[![ci](https://github.com/caroljo0812/release-ready/actions/workflows/tests.yml/badge.svg)](https://github.com/caroljo0812/release-ready/actions/workflows/tests.yml)
[![python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue)](https://python.org)
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

Multi-agent PR release readiness squad. Four specialist reviewers run in
parallel against your diff (changelog risk, version compatibility, test
coverage, deployment safety), then a consensus pass writes one structured
release report ready to paste into a PR description or send to a release
channel.

Release Ready is meant to sit between "code looks fine" and "ship it" — each
specialist is narrow by design so it flags only the things that matter for
a release, not every possible issue a linter would catch.

## What it does

Given a unified diff (file, stdin, local repo, or GitHub PR), Release Ready:

1. Parses the diff into per-file hunks.
2. Fans out to four specialist agents in parallel:
   - **changelog** — breaking changes, new APIs, deprecation notices, migration guides needed
   - **compatibility** — semver risk, peer dependency conflicts, backward-incompatible surface area
   - **test_coverage** — untested new paths, brittle assertions, missing edge-case coverage
   - **deployment** — build size regressions, config drift, rollback risk, environment gaps
3. Merges findings by severity. When two specialists flag the same
   file+line the severity bumps one rung — agreement is signal.
4. Asks a consensus model to write a structured release report.

Output is available as markdown (copy-paste into PR body), plain text, or JSON.

## Reviewer model

The default reviewer model is `mimo-v2.5-pro` (Xiaomi MiMo v2.5 Pro). MiMo
stays on-task through long structured tasks and holds the JSON contract
reliably — which is what each specialist agent needs to return findings in
a shape the consensus pass can merge.

OpenAI, Together, and any OpenAI-compatible gateway are also supported via
`RR_LLM_PROVIDER`. With no API key set, Release Ready falls back to a
deterministic mock provider so the pipeline stays runnable in CI and tests.

## Install

```bash
pip install -e .
# or with dev extras
pip install -e ".[dev]"
```

Python 3.10+ required.

## Configure

Copy `.env.example` to `.env` and fill in what you need:

```env
# reviewer
RR_LLM_PROVIDER=mimo
RR_LLM_API_KEY=***
RR_LLM_MODEL=mimo-v2.5-pro
RR_MAX_TOKENS=1200
RR_CONCURRENCY=4

# github (only for posting PR comments)
RR_GITHUB_TOKEN=***

# server
RR_HOST=127.0.0.1
RR_PORT=8080
RR_API_KEY=***
RR_MAX_DIFF_BYTES=1048576
RR_CORS_ORIGINS=*
```

## Use it

### CLI

Review a diff file:

```bash
release-ready review --diff feature.diff
```

Run only a subset of specialists:

```bash
release-ready review --diff feature.diff --specialists changelog,compatibility
```

Review the diff between two refs in a local repo:

```bash
release-ready review --repo . --base main --head feature/release
```

Review a GitHub PR and post the report back as a PR comment:

```bash
export RR_GITHUB_TOKEN=***
release-ready review-pr owner/repo 42 --post-comment --markdown
```

Pipe a diff in:

```bash
git diff main..release | release-ready review --diff -
```

Inspect the active provider config:

```bash
release-ready provider
```

### HTTP

Run the FastAPI server:

```bash
release-ready serve
```

Endpoints:

- `GET  /` — service metadata, reviewer info, configured limits
- `GET  /health` — liveness
- `GET  /provider` — active provider snapshot
- `POST /review/diff` — review a unified diff text body (auth-gated when `RR_API_KEY` is set)
- `POST /review/github` — review a GitHub PR (`{owner, repo, pr_number, post_comment?, specialists?}`)
- `GET  /demo` — small static demo page

Example:

```bash
curl -s http://localhost:8080/review/diff \
  -H 'content-type: application/json' \
  -H "X-RR-API-Key: $RR_API_KEY" \
  -d "{\"diff\": $(jq -Rs . feature.diff), \"specialists\": [\"changelog\"]}" \
  | jq .report
```

See [`examples/`](examples/) for ready-to-run curl scripts and a sample diff.

## Output shape

Every reviewer call returns this shape:

```json
{
  "report": "## Release Readiness\n\n### Changelog Risk\n...",
  "file_count": 4,
  "finding_count": 7,
  "duration_ms": 3800,
  "provider": {
    "configured_provider": "mimo",
    "configured_model": "mimo-v2.5-pro",
    "effective_provider": "mimo"
  },
  "specialists": [
    {"name": "changelog",    "findings": 2, "duration_ms": 920,  "error": null},
    {"name": "compatibility","findings": 1, "duration_ms": 1040, "error": null},
    {"name": "test_coverage","findings": 2, "duration_ms": 890,  "error": null},
    {"name": "deployment",   "findings": 2, "duration_ms": 950,  "error": null}
  ],
  "findings": [
    {
      "specialist": "changelog",
      "file": "src/api/v2.py",
      "line": 42,
      "severity": "high",
      "category": "breaking-change",
      "title": "...",
      "rationale": "...",
      "suggestion": "..."
    }
  ]
}
```

## Tests

```bash
pip install -e ".[dev]"
RR_LLM_PROVIDER=mock pytest -q
```

Tests run against the mock provider so they don't hit the network.
CI runs the same suite on Python 3.10, 3.11, and 3.12, plus a `ruff check`
lint job.

## Layout

```
src/release_ready/
  llm.py            OpenAI-compatible chat client + JSON repair
  diff.py           dependency-free unified-diff parser
  sources.py        diff sources: text, file, local repo, GitHub PR
  specialists.py    4 specialist prompts + Finding shape + JSON contract
  consensus.py      dedup, severity merge, report writer
  orchestrator.py   parallel fan-out + report renderers
  server.py         FastAPI app + auth + size limits
  cli.py            Click CLI
  demo.html         static demo page (bundled with the package)
examples/           ready-to-run sample diffs + curl scripts
tests/              pytest suite
.github/workflows   CI: tests matrix + ruff lint
```

## License

MIT — see [LICENSE](LICENSE).