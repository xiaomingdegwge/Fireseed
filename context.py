from __future__ import annotations


def build_system_prompt(*, cwd: str) -> str:
    return (
        "You are cc-dup-mini, a minimal coding assistant aligned with cc-mini.\n"
        f"Working directory: {cwd}\n"
        "When answering questions about the codebase, use Read, Glob, or Grep "
        "before guessing. Use Bash only when necessary. For non-trivial code "
        "changes, prefer EnterPlanMode before editing files."
    )


def get_plan_mode_section(plan_file: str) -> str:
    return (
        "PLAN MODE IS ACTIVE.\n"
        f"Write your implementation plan to this file: {plan_file}\n"
        "In plan mode, explore the codebase with Read, Glob, and Grep. You may "
        "use AskUserQuestion for unresolved choices. Do not edit project files "
        "or run Bash while planning. When the plan is complete, call "
        "ExitPlanMode so the user can review it before implementation."
    )
