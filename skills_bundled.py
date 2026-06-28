from __future__ import annotations

from skills import Skill, register_skill


def _with_args(text: str, heading: str, args: str) -> str:
    if args:
        return text.replace("$ARGUMENTS", f"\n## {heading}\n\n{args}")
    return text.replace("$ARGUMENTS", "")


_REVIEW_PROMPT = """\
# Code Review

Review the current code changes. Do not modify files.

Steps:
1. Run `git status` and inspect relevant diffs.
2. Look for correctness, security, regression, and test coverage issues.
3. Report findings first, grouped by severity, with file/line references when possible.

$ARGUMENTS\
"""

_COMMIT_PROMPT = """\
# Git Commit

Create a concise git commit for the current work.

Steps:
1. Run `git status`.
2. Inspect staged and unstaged diffs.
3. Stage only relevant files.
4. Commit with a clear Chinese commit message unless the user asks otherwise.

$ARGUMENTS\
"""

_TEST_PROMPT = """\
# Run Tests

Find and run the appropriate test suite, then summarize the result.

If tests fail, identify the root cause and suggest or apply a focused fix.

$ARGUMENTS\
"""

_SIMPLIFY_PROMPT = """\
# Simplify

Review changed files for unnecessary complexity, duplication, and unclear names.
Apply small focused improvements only when they are clearly useful.

$ARGUMENTS\
"""


def register_bundled_skills() -> None:
    register_skill(Skill(
        name="review",
        description="Review code changes and report issues without editing",
        when_to_use="Before committing or when checking a patch",
        argument_hint="focus",
        source="bundled",
        _prompt_fn=lambda args: _with_args(_REVIEW_PROMPT, "Additional Focus", args),
    ))
    register_skill(Skill(
        name="commit",
        description="Stage relevant changes and create a git commit",
        when_to_use="When the user asks to commit current work",
        argument_hint="message",
        source="bundled",
        _prompt_fn=lambda args: _with_args(_COMMIT_PROMPT, "Commit Instructions", args),
    ))
    register_skill(Skill(
        name="test",
        description="Run tests and analyze failures",
        when_to_use="After code changes or when validating behavior",
        argument_hint="filter",
        source="bundled",
        _prompt_fn=lambda args: _with_args(_TEST_PROMPT, "Specific Instructions", args),
    ))
    register_skill(Skill(
        name="simplify",
        description="Improve changed code for clarity and reuse",
        when_to_use="After implementing a feature or fix",
        argument_hint="focus",
        source="bundled",
        _prompt_fn=lambda args: _with_args(_SIMPLIFY_PROMPT, "Additional Focus", args),
    ))
