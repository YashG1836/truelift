"""Owner-facing words in English, Hindi, Kannada and Gujarati (audit A20 W3, plan M3.7).

The texts live in `truelift/static/i18n/<code>.json`, so the service (the weekly WhatsApp summary,
offer labels) and the page (the approval screen) read the same words. English is the source text.
The other three are drafts: they stay switched off until a native speaker on the team has
reviewed them (decision D4). `TRUELIFT_LANGUAGES=1` switches them on; until then a reviewer can
open the page with `#lang=hi` (or kn, gu).
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

LANGS = ("en", "hi", "kn", "gu")
DRAFTS = ("hi", "kn", "gu")
DIR = Path(__file__).resolve().parent / "static" / "i18n"


@cache
def texts(lang: str) -> dict[str, Any]:
    """All texts of one language (the files are read once)."""
    if lang not in LANGS:
        raise ValueError(f"unknown language {lang!r}; expected one of {LANGS}")
    return json.loads((DIR / f"{lang}.json").read_text(encoding="utf-8"))


def offer_label(d, lang: str = "en") -> str:
    """The offer in one line, as `Design.label` writes it in English."""
    if lang == "en":
        return d.label()
    t = texts(lang)["label"]
    if not d.discount:
        return t["reward_only"].format(reward=f"{d.reward:.0f}") if d.reward else t["no_offer"]
    if d.pct > 0:
        parts = [t["pct"].format(pct=f"{d.pct * 100:.0f}", cap=f"{d.discount:.0f}")]
    else:
        parts = [t["flat"].format(amount=f"{d.discount:.0f}")]
    if d.min_order:
        parts.append(t["above"].format(min=f"{d.min_order:.0f}"))
    parts.append(t[f"aud_{d.audience}"])
    if d.offpeak_only:
        parts[-1] += " " + t["offpeak"]
    if d.reward:
        parts.append(t["reward"].format(reward=f"{d.reward:.0f}"))
    if d.zomato_share:
        parts[-1] += " " + t["zomato_share"].format(share=f"{d.zomato_share * 100:.0f}")
    return t["sep"].join(parts)


def labels(d) -> dict[str, str]:
    """The offer's label in each draft language (English is the response's own `label`)."""
    return {lang: offer_label(d, lang) for lang in DRAFTS}


def page_texts() -> dict[str, dict]:
    """What the page needs to show the approval screen in each language."""
    return {lang: {"_meta": texts(lang)["_meta"], "otp": texts(lang)["otp"]} for lang in LANGS}
