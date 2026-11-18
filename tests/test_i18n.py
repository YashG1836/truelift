"""Owner texts in four languages (plan M3.7): every draft has every text and placeholder of the
English source, the English output is unchanged, and the drafts stay off until reviewed (D4)."""

from __future__ import annotations

import re
import string

import pytest

from tests.conftest import DESIGN, approved_offer
from truelift.engine import BRAND_PACK_SENTENCES, VERDICT_SENTENCES, Design, weekly_message
from truelift.i18n import DRAFTS, LANGS, offer_label, texts

FIELDS = string.Formatter()


def _flat(d: dict, prefix: str = "") -> dict[str, str]:
    out = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out.update(_flat(v, f"{prefix}{k}."))
        else:
            out[f"{prefix}{k}"] = v
    return out


def _placeholders(text: str) -> set[str]:
    return {f for _, f, _, _ in FIELDS.parse(text) if f}


@pytest.mark.parametrize("lang", DRAFTS)
def test_every_draft_has_every_text_and_placeholder(lang):
    en, other = _flat(texts("en")), _flat(texts(lang))
    assert set(en) == set(other)
    for key, text in en.items():
        if key.startswith("_meta"):
            continue
        assert _placeholders(other[key]) == _placeholders(text), key
    assert "draft" in texts(lang)["_meta"]["status"]


def test_english_source_matches_the_engine():
    wa = texts("en")["wa"]
    for code, sentence in VERDICT_SENTENCES.items():
        assert wa[f"verdict_{code}"] == sentence
    for code, sentence in BRAND_PACK_SENTENCES.items():
        assert wa[f"bp_{code}"] == sentence


def _measurement():
    return {
        "orders": {"total": 41.6, "low": 12.2, "high": 70.9},
        "profit": {"total": 2310.0, "low": -480.0, "high": 5100.0},
        "report_today": {"orders_with_offer": 133},
        "verdict_code": "wait",
    }


@pytest.mark.parametrize("lang", LANGS)
def test_weekly_summary_in_each_language_has_the_numbers(lang):
    bp = {"profit": {"total": 310.0, "low": -90.0, "high": 700.0}, "verdict_code": "unclear", "verdict": "x"}
    d = Design(60, 449, "lapsed", True, 20, pct=0.3)
    text = weekly_message("Empire Restaurant", 2, _measurement(), d, 0.10, bp, lang)
    assert "{" not in text and "}" not in text
    for n in ("133", "12", "71", "42", "−₹480", "+₹5,100", "+₹2,310", "10", "+₹700"):
        assert n in text, (lang, n)
    assert text.count("\n") == 8  # title, offer, used, orders, profit, how, verdict, Brand Pack, open


def test_english_summary_is_unchanged_by_the_templates():
    text = weekly_message("Empire Restaurant", 2, _measurement(), Design(60), 0.10)
    assert text.splitlines()[0] == "TrueLift weekly summary: Empire Restaurant, week 2"
    assert "Offer: ₹60 off for everyone" in text
    assert "Extra profit for you: −₹480 to +₹5,100 (best estimate +₹2,310)" in text
    assert text.endswith("Open the Offers tab in the partner app to keep, change or stop it.")


@pytest.mark.parametrize("lang", LANGS)
def test_offer_labels_have_no_placeholders_left(lang):
    for d in (Design(0), Design(0, reward=20), Design(60, 449, "targeted", True, 20, 0.5), Design(80, pct=0.4)):
        label = offer_label(d, lang)
        assert label and not re.search(r"[{}]", label)
    assert offer_label(Design(80, pct=0.4), lang).count("80") == 1


def test_drafts_are_off_by_default_and_reach_the_page(client, session_headers):
    cfg = client.get("/api/v1/config").json()
    assert cfg["languages_enabled"] is False
    assert set(cfg["i18n"]) == set(LANGS) and "button" in cfg["i18n"]["hi"]["otp"]
    off = approved_offer(client, session_headers, design={**DESIGN, "audience": "all"})
    assert set(off["label_i18n"]) == set(DRAFTS)
    wk = client.post(f"/api/v1/offers/{off['offer_id']}/run_week", headers=session_headers).json()["weeks"][-1]
    assert set(wk["whatsapp_i18n"]) == set(DRAFTS)
    assert all(t.splitlines()[0].startswith("TrueLift") for t in wk["whatsapp_i18n"].values())
