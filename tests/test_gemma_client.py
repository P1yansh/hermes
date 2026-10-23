import pytest

from app.services.gemma_client import GRAMMAR_PATH, gemma_client as client


def test_deadline_grammar_file_is_present():
    assert GRAMMAR_PATH.exists()
    grammar = GRAMMAR_PATH.read_text(encoding="utf-8")
    assert "root ::= object" in grammar
    assert "category" in grammar
    assert "deadline_verbatim" in grammar
    assert "estimated_hours" in grammar
    # llama.cpp's GBNF parser rejects line breaks inside a rule. Keep each
    # production on one line so the server does not return a 400.
    for line in grammar.splitlines():
        if line.strip() and not line.startswith(" "):
            assert "::=" in line


@pytest.mark.asyncio
async def test_briefing_fallback_keeps_hinglish_persona():
    # conftest patches llama-server calls to return None.
    script = await client.generate_briefing_script(
        panic_items=[{"title": "CS401 Lab 3", "source": "CS401", "hours_left": 3.5}],
        imminent_items=[],
        top_opp=None,
    )
    assert "Uth ja, alsi" in script
    assert "ghante" in script
    assert "*" not in script
