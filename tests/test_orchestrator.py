"""Test the orchestrator with mock provider."""
import os

from release_ready.orchestrator import review_diff

# Sample diff for testing
SAMPLE_DIFF = """--- a/src/api.py
+++ b/src/api.py
@@ -1,3 +1,4 @@
 def hello():
-    return "hi"
+    return "hello"
+    print("debug")
--- a/src/main.py
+++ b/src/main.py
@@ -5,8 +5,10 @@
 def main():
     run()
"""


def test_review_diff_mock():
    # Force mock provider so no real API call
    old = os.environ.get("RR_LLM_PROVIDER")
    os.environ["RR_LLM_PROVIDER"] = "mock"
    try:
        result = review_diff(
            SAMPLE_DIFF,
            model="mock",
            provider="mock",
            api_key=None,
        )
        assert result.file_count == 2
        assert result.finding_count == 0
        assert result.duration_ms > 0
        assert result.provider["effective_provider"] == "mock"
    finally:
        if old is not None:
            os.environ["RR_LLM_PROVIDER"] = old
        else:
            os.environ.pop("RR_LLM_PROVIDER", None)


def test_review_diff_single_specialist():
    old = os.environ.get("RR_LLM_PROVIDER")
    os.environ["RR_LLM_PROVIDER"] = "mock"
    try:
        result = review_diff(
            SAMPLE_DIFF,
            specialists=["changelog"],
            provider="mock",
            api_key=None,
        )
        assert result.file_count == 2
        assert len(result.specialists) == 1
        assert result.specialists[0]["name"] == "changelog"
    finally:
        if old is not None:
            os.environ["RR_LLM_PROVIDER"] = old
        else:
            os.environ.pop("RR_LLM_PROVIDER", None)
