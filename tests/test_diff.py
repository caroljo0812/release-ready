"""Test the diff parser."""
import pytest
from release_ready.diff import parse_diff, DiffFile


SIMPLE_DIFF = """--- a/src/api.py
+++ b/src/api.py
@@ -1,3 +1,4 @@
 def hello():
-    return "hi"
+    return "hello"
+    print("world")
"""

COMPLEX_DIFF = """--- a/src/main.py
+++ b/src/main.py
@@ -5,8 +5,10 @@
 def main():
     run()
--- a/src/utils.py
+++ b/src/utils.py
@@ -12,4 +12,5 @@
     return x * 2
+    print("debug")
"""


def test_parse_simple():
    files = parse_diff(SIMPLE_DIFF)
    assert len(files) == 1
    assert files[0].path_before == "src/api.py"
    assert files[0].path_after == "src/api.py"
    assert len(files[0].hunks) == 1
    hunk = files[0].hunks[0]
    ops = [op for op, _, _ in hunk.lines]
    assert "del" in ops
    assert "add" in ops


def test_parse_multiple_files():
    files = parse_diff(COMPLEX_DIFF)
    assert len(files) == 2
    paths = {f.path_before for f in files}
    assert paths == {"src/main.py", "src/utils.py"}


def test_parse_no_newline():
    text = """--- a/f.py
+++ b/f.py
@@ -1 +1 @@
-old
\\ No newline at end of file
+new
"""
    files = parse_diff(text)
    assert len(files) == 1
