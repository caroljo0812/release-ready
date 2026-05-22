"""Test consensus / dedup logic."""
import pytest
from release_ready.consensus import dedup_findings
from release_ready.specialists import Finding


def test_dedup_single():
    findings = [
        Finding("changelog", "src/a.py", 10, "high", "breaking", "Old API removed", "", ""),
    ]
    result = dedup_findings(findings)
    assert len(result) == 1


def test_dedup_bumps_severity():
    findings = [
        Finding("changelog",    "src/a.py", 10, "medium", "breaking", "Old API removed", "", ""),
        Finding("compatibility","src/a.py", 10, "medium", "breaking", "Old API removed", "", ""),
    ]
    result = dedup_findings(findings)
    assert len(result) == 1
    assert result[0].specialist == "consensus"
    assert result[0].severity == "critical"  # medium -> critical (one rung up)


def test_dedup_different_lines():
    findings = [
        Finding("changelog", "src/a.py", 10, "medium", "breaking", "A", "", ""),
        Finding("changelog", "src/a.py", 20, "medium", "breaking", "B", "", ""),
    ]
    result = dedup_findings(findings)
    assert len(result) == 2  # different lines = no dedup
