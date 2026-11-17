"""Tests for the LLM module."""

import os

import pytest

from datasheet_qa import llm


@pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set",
)
def test_ask_returns_response():
    """Confirm the API call works with a simple prompt."""
    response = llm.ask("Say hello in one word.")
    assert isinstance(response, str)
    assert len(response) > 0