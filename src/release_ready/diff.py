"""Dependency-free unified diff parser."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterator


@dataclass
class Hunk:
    """One contiguous block of changed lines in a file."""
    file_before: str
    file_after: str
    hunks_before: list[tuple[int, int]] = field(default_factory=list)  # (start, count)
    hunks_after:  list[tuple[int, int]] = field(default_factory=list)
    lines: list[tuple[str, str, int]] = field(default_factory=list)  # (op, content, line_no)
    context_start: int = 0
    context_end: int = 0


@dataclass
class DiffFile:
    """One file in a unified diff."""
    path_before: str
    path_after: str
    is_new: bool = False
    is_deleted: bool = False
    is_renamed: bool = False
    hunks: list[Hunk] = field(default_factory=list)

    def render_for_llm(self, max_lines: int = 150) -> str:
        """Render the file diff as a compact block for LLM consumption."""
        lines = []
        path = self.path_after or self.path_before
        lines.append(f"--- {self.path_before}")
        lines.append(f"+++ {self.path_after or self.path_before}")

        total = 0
        for hunk in self.hunks:
            for op, content, _ in hunk.lines:
                marker = {"add": "+", "del": "-", "ctx": " "}.get(op, " ")
                lines.append(f"{marker}{content}")
                total += 1
                if total >= max_lines:
                    lines.append(f"... ({sum(1 for h in self.hunks for _, _, _ in h.lines) - total} more lines)")
                    break
            if total >= max_lines:
                break

        return "\n".join(lines)


def parse_diff(text: str) -> list[DiffFile]:
    """Parse a unified diff into structured DiffFile objects."""
    files: list[DiffFile] = []
    current: DiffFile | None = None
    hunk_lines: list[tuple[str, str, int]] = []
    hunk_context_start = 0
    hunk_context_end = 0
    pending_before_range: tuple[int, int] | None = None
    pending_after_range:  tuple[int, int] | None = None
    pending_before_file: str = ""
    pending_after_file: str = ""

    def _commit_hunk():
        nonlocal current, hunk_lines, hunk_context_start, hunk_context_end
        if not current:
            return
        hunk = Hunk(
            file_before=current.path_before,
            file_after=current.path_after,
            hunks_before=[pending_before_range] if pending_before_range else [],
            hunks_after=[pending_after_range] if pending_after_range else [],
            lines=list(hunk_lines),
            context_start=hunk_context_start,
            context_end=hunk_context_end,
        )
        current.hunks.append(hunk)
        hunk_lines = []
        hunk_context_start = 0
        hunk_context_end = 0
        pending_before_range = None
        pending_after_range = None

    def _parse_range(line: str) -> tuple[int, int]:
        m = re.match(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
        if not m:
            return 1, 1
        b_start = int(m.group(1))
        b_count = int(m.group(2) or 1)
        a_start = int(m.group(3))
        a_count = int(m.group(4) or 1)
        return b_start, a_start

    for raw_line in text.splitlines():
        line = raw_line.rstrip("\n")

        # File header
        m = re.match(r"^--- (?:a/)?(.+)", line)
        if m:
            if current:
                _commit_hunk()
                files.append(current)
            pending_before_file = m.group(1).strip()
            pending_before_range = None
            pending_after_file = ""
            current = DiffFile(path_before=pending_before_file, path_after="")
            hunk_lines = []
            continue

        m = re.match(r"^\+\+\+ (?:b/)?(.+)", line)
        if m:
            pending_after_file = m.group(1).strip()
            if current:
                current.path_after = pending_after_file
                current.path_before = pending_before_file
            pending_after_range = None
            continue

        # Hunk header
        m = re.match(r"^@@ -(\d+(?:,\d+)?) \+(\d+(?:,\d+)?) @@", line)
        if m:
            _commit_hunk()
            b_start, a_start = _parse_range(line)
            pending_before_range = (b_start, a_start)
            pending_after_range = (a_start, a_start)
            hunk_context_start = a_start
            hunk_lines = []
            continue

        # Content lines
        if current and line.startswith(("+", "-", " ")):
            op = {"+": "add", "-": "del", " ": "ctx"}.get(line[0], "ctx")
            content = line[1:]
            if pending_after_range:
                line_no = pending_after_range[1]
                pending_after_range = (pending_after_range[0] + 1, line_no + (1 if op != "del" else 0))
            else:
                line_no = 0
            hunk_lines.append((op, content, line_no))
            continue

        # Binary / no newline marker
        if current and (line.startswith("Binary files") or line.startswith("\\ No newline")):
            continue

    if current:
        _commit_hunk()
        files.append(current)

    return files


def render_diff(files: list[DiffFile], max_lines_per_file: int = 150) -> str:
    """Render a list of DiffFiles into unified diff format for LLM."""
    out = []
    for f in files:
        out.append(f.render_for_llm(max_lines=max_lines_per_file))
    return "\n".join(out)


def render_for_specialist(files: list[DiffFile], max_lines: int = 120) -> str:
    """Render all files as a single unified diff block for LLM specialist consumption."""
    if not files:
        return ""
    blocks = []
    for f in files:
        path = f.path_after or f.path_before
        blocks.append(f"File: {path}\n" + f.render_for_llm(max_lines=max_lines))
    return "\n\n".join(blocks)