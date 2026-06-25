from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from enum import Enum


class RuleType(Enum):
    EXACT = "exact"
    PREFIX = "prefix"
    WILDCARD = "wildcard"


@dataclass(frozen=True)
class MatchRule:
    type: RuleType
    pattern: str


def parse_rule(pattern: str) -> MatchRule:
    stripped = pattern.strip()
    if "*" in stripped or "?" in stripped:
        return MatchRule(RuleType.WILDCARD, stripped)
    if " " in stripped:
        return MatchRule(RuleType.PREFIX, stripped)
    return MatchRule(RuleType.EXACT, stripped)


def matches_rule(rule: MatchRule, command: str) -> bool:
    if rule.type == RuleType.EXACT:
        return command == rule.pattern
    if rule.type == RuleType.PREFIX:
        return command == rule.pattern or command.startswith(rule.pattern + " ")
    if rule.type == RuleType.WILDCARD:
        return fnmatch.fnmatch(command, rule.pattern)
    return False


def contains_excluded_command(command: str, excluded_patterns: list[str]) -> bool:
    if not excluded_patterns:
        return False
    rules = [parse_rule(pattern) for pattern in excluded_patterns]
    for subcommand in _split_compound_command(command):
        candidates = [subcommand, _strip_env_prefix(subcommand)]
        for rule in rules:
            if any(matches_rule(rule, candidate) for candidate in candidates):
                return True
    return False


def _split_compound_command(command: str) -> list[str]:
    return [part.strip() for part in command.split("&&") if part.strip()]


def _strip_env_prefix(command: str) -> str:
    parts = command.split()
    index = 0
    while index < len(parts) and "=" in parts[index]:
        index += 1
    return " ".join(parts[index:]) if index < len(parts) else command
