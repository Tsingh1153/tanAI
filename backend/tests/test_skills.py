"""Auto-skill detection tests (pure heuristics)."""

from __future__ import annotations

from app.skills import wants_agent, wants_web


def test_wants_web_true() -> None:
    for q in [
        "What's the latest news on the election?",
        "current price of bitcoin",
        "Who is the CEO of OpenAI right now?",
        "summarize https://example.com/article",
        "search the web for python 3.13 features",
        "what happened in 2026",
    ]:
        assert wants_web(q), q


def test_wants_web_false() -> None:
    for q in [
        "Explain how photosynthesis works",
        "Write a haiku about the ocean",
        "What is 17 * 23?",
    ]:
        assert not wants_web(q), q


def test_wants_agent_true() -> None:
    for q in [
        "run this python code and tell me the output",
        "use python to compute the factorial of 20",
        "read the file notes.md in your workspace",
        "write a file called plan.txt",
        "fetch https://example.com and summarize it",
    ]:
        assert wants_agent(q), q


def test_wants_agent_false() -> None:
    for q in [
        "Explain recursion",
        "What's a good name for a cat?",
        "Calculate the meaning of life",  # vague, no tool signal
    ]:
        assert not wants_agent(q), q
