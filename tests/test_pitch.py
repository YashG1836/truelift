"""The pitch deck, its notes and the one-pager are generated from reports/ (scripts/make_deck.py):
the committed files must say exactly what the reports say now, so a slide can never keep an old
number. Rebuild with `python tasks.py deck`."""

from __future__ import annotations

import pytest


def test_pitch_files_match_the_reports():
    pytest.importorskip("qrcode")  # uv group `media`
    from scripts import make_deck

    ss = make_deck.slides()
    expected = {
        "deck.html": make_deck.deck_html(ss),
        "speaker_notes.md": make_deck.notes_md(ss),
        "one_page.html": make_deck.one_page_html(ss),
    }
    for name, text in expected.items():
        path = make_deck.OUT / name
        assert path.read_text(encoding="utf-8") == text, f"{name} is stale: run python tasks.py deck"


def test_deck_has_twelve_slides_and_says_outcomes_are_simulated():
    pytest.importorskip("qrcode")
    from scripts import make_deck

    ss = make_deck.slides()
    assert sum(not s.appendix for s in ss) == 12
    assert [k for k, s in enumerate(ss, 1) if s.cut] == [1, 3, 6, 7, 8, 12]
    results = [s for s in ss if "evaluation.json" in s.source]
    assert results and all("simulated" in s.source for s in results)
