from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass(frozen=True)
class _PricingTier:
    input: float
    output: float
    cache_write: float
    cache_read: float


_TIER_SONNET = _PricingTier(input=3.0, output=15.0, cache_write=3.75, cache_read=0.30)
_TIER_OPUS = _PricingTier(input=15.0, output=75.0, cache_write=18.75, cache_read=1.50)
_TIER_HAIKU = _PricingTier(input=0.80, output=4.0, cache_write=1.0, cache_read=0.08)


@dataclass
class ModelUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cost_usd: float = 0.0


def _tier_for_model(model: str) -> _PricingTier | None:
    model_lower = model.lower()
    if "haiku" in model_lower:
        return _TIER_HAIKU
    if "opus" in model_lower:
        return _TIER_OPUS
    if "sonnet" in model_lower or model_lower.startswith("claude"):
        return _TIER_SONNET
    # OpenAI 兼容端的定价差异很大，这里先只统计 token，不猜价格。
    return None


def _fmt_tokens(n: int) -> str:
    if n >= 1_000_000:
        value = n / 1_000_000
        return f"{value:.1f}m" if value != int(value) else f"{int(value)}m"
    if n >= 1_000:
        value = n / 1_000
        return f"{value:.1f}k" if value != int(value) else f"{int(value)}k"
    return str(n)


class CostTracker:
    # 轻量 token/费用统计器。Engine 在每次模型返回 usage 后调用 add_usage()；
    # /cost 命令通过 format_cost() 把当前会话的累计统计打印出来。
    def __init__(self) -> None:
        self._total_cost_usd = 0.0
        self._model_usage: dict[str, ModelUsage] = {}
        self._started_at = time.monotonic()
        self._last_input_tokens = 0

    @property
    def last_input_tokens(self) -> int:
        return self._last_input_tokens

    @property
    def total_cost_usd(self) -> float:
        return self._total_cost_usd

    def add_usage(self, model: str, usage: dict) -> float:
        cost = self.calculate_cost(model, usage)
        self._total_cost_usd += cost
        self._last_input_tokens = int(usage.get("input_tokens", 0) or 0)

        model_usage = self._model_usage.setdefault(model, ModelUsage())
        model_usage.input_tokens += int(usage.get("input_tokens", 0) or 0)
        model_usage.output_tokens += int(usage.get("output_tokens", 0) or 0)
        model_usage.cache_read_input_tokens += int(usage.get("cache_read_input_tokens", 0) or 0)
        model_usage.cache_creation_input_tokens += int(usage.get("cache_creation_input_tokens", 0) or 0)
        model_usage.cost_usd += cost
        return cost

    @staticmethod
    def calculate_cost(model: str, usage: dict) -> float:
        tier = _tier_for_model(model)
        if tier is None:
            return 0.0
        return (
            int(usage.get("input_tokens", 0) or 0) * tier.input
            + int(usage.get("output_tokens", 0) or 0) * tier.output
            + int(usage.get("cache_read_input_tokens", 0) or 0) * tier.cache_read
            + int(usage.get("cache_creation_input_tokens", 0) or 0) * tier.cache_write
        ) / 1_000_000

    def format_cost(self) -> str:
        if not self._model_usage:
            return "No API usage recorded."

        elapsed = int(time.monotonic() - self._started_at)
        lines = [
            f"Total cost: ${self._total_cost_usd:.4f}",
            f"Elapsed wall time: {elapsed}s",
            "Usage by model:",
        ]
        for model, usage in sorted(self._model_usage.items()):
            parts = [
                f"{_fmt_tokens(usage.input_tokens)} input",
                f"{_fmt_tokens(usage.output_tokens)} output",
            ]
            if usage.cache_read_input_tokens:
                parts.append(f"{_fmt_tokens(usage.cache_read_input_tokens)} cache read")
            if usage.cache_creation_input_tokens:
                parts.append(f"{_fmt_tokens(usage.cache_creation_input_tokens)} cache write")
            if _tier_for_model(model) is None:
                parts.append("pricing unavailable")
            lines.append(f"  {model}: {', '.join(parts)} (${usage.cost_usd:.4f})")
        return "\n".join(lines)
