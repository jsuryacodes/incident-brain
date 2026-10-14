"""THE ONLY place that talks to an LLM provider.

LLMClient(mode, model): mode from env LLM_MODE (default 'mock'), model from env LLM_MODEL (default claude-haiku-5-5).
Mock mode never touches the SDK: it asks backend.agents.mock_policy (or an injected policy) for the next turn and
returns the same LLMResponse shape at zero cost. Live mode uses the official anthropic SDK with prompt caching on the
system block and the last tool. ANTHROPIC_API_KEY is read only from .env / the environment and is never printed.
"""
import copy
import os
import warnings
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL = "claude-haiku-5-5"
# USD per million tokens
PRICES = {
    "claude-haiku-5-5": {"input": 0.10, "output": 0.50, "cache_write": 0.125, "cache_read": 0.01},
    "claude-sonnet-5-5": {"input": 2.00, "output": 10.00, "cache_write": 2.50, "cache_read": 0.10},
}
USAGE_KEYS = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")


def cost_usd(model, usage):
    p = PRICES.get(model)
    if p is None:
        warnings.warn(f"no price for model {model!r}; cost unknown")
        return None
    return (usage.get("input_tokens", 0) * p["input"] + usage.get("output_tokens", 0) * p["output"]
            + usage.get("cache_creation_input_tokens", 0) * p["cache_write"]
            + usage.get("cache_read_input_tokens", 0) * p["cache_read"]) / 1e6


def max_run_cost():
    return float(os.getenv("MAX_RUN_COST_USD", "0.05"))


@dataclass
class LLMResponse:
    content: list  # provider-neutral blocks: {"type":"text","text"} | {"type":"tool_use","id","name","input"}
    stop_reason: str
    usage: dict = field(default_factory=lambda: dict.fromkeys(USAGE_KEYS, 0))
    cost_usd: float | None = 0.0


class LLMClient:
    def __init__(self, mode=None, model=None, policy=None):
        self.mode = mode or os.getenv("LLM_MODE", "mock")
        if self.mode not in ("mock", "live"):
            raise ValueError("LLM mode must be 'mock' or 'live'")
        self.model = model or os.getenv("LLM_MODEL", DEFAULT_MODEL)
        self.policy = policy  # mock only: fn(agent, system, tools, messages) -> blocks | LLMResponse
        self._sdk = None

    def build_request(self, system, tools, messages, max_tokens=1024):
        """The exact live payload. Cache breakpoints: the system block and the LAST tool (tools render before system)."""
        tools = copy.deepcopy(tools)
        if tools:
            tools[-1]["cache_control"] = {"type": "ephemeral"}
        return {"model": self.model, "max_tokens": max_tokens,
                "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                "tools": tools, "messages": messages}

    def complete(self, system, tools, messages, max_tokens=1024, agent=None):
        if self.mode == "mock":
            from backend.agents import mock_policy
            out = (self.policy or mock_policy.respond)(agent, system, tools, messages)
            if isinstance(out, LLMResponse):
                return out
            stop = "tool_use" if any(b["type"] == "tool_use" for b in out) else "end_turn"
            return LLMResponse(out, stop)
        if self._sdk is None:
            import anthropic
            key = os.getenv("ANTHROPIC_API_KEY")
            if not key:
                raise RuntimeError("live mode needs ANTHROPIC_API_KEY in .env")
            self._sdk = anthropic.Anthropic(api_key=key)
        r = self._sdk.messages.create(**self.build_request(system, tools, messages, max_tokens))
        content = []
        for b in r.content:
            if b.type == "text":
                content.append({"type": "text", "text": b.text})
            elif b.type == "tool_use":
                content.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
        usage = {k: getattr(r.usage, k, 0) or 0 for k in USAGE_KEYS}
        return LLMResponse(content, r.stop_reason, usage, cost_usd(self.model, usage))
