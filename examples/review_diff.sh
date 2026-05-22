"""Example: review a local diff file.

Usage:
  # Review a diff saved to disk
  release-ready review --diff examples/simple.diff

  # Pipe git diff output
  git diff main..release | release-ready review --diff -

  # Review only changelog + compatibility specialists
  release-ready review --diff examples/simple.diff -s changelog,compatibility

  # Output JSON for automation
  release-ready review --diff examples/simple.diff -o json
"""