"""Tests for provider routing helpers."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "dashboard" / "backend"
sys.path.insert(0, str(BACKEND_DIR))

import routes.providers as providers


def test_normalize_failover_order_prioritizes_active_provider():
    provider_map = {
        "anthropic": {"name": "Anthropic"},
        "openrouter": {"name": "OpenRouter"},
        "gemini": {"name": "Gemini", "coming_soon": True},
    }

    order = providers._normalize_failover_order(  # type: ignore[attr-defined]
        ["openrouter", "gemini", "anthropic"],
        provider_map,
        "anthropic",
    )

    assert order[0] == "anthropic"
    assert order[1] == "openrouter"
    assert "gemini" not in order
