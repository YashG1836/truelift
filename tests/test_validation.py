"""The real-data check (scripts/validate_uplift.py, scripts/get_data.py) on cases small enough to
work out by hand: the measures, the bootstrap and the checksum guard (audit TL-039, TL-040)."""

from __future__ import annotations

import hashlib

import numpy as np
import pytest

from scripts import get_data
from scripts import validate_uplift as vu


def _ranked_case():
    """2,000 customers, one treated and one untreated in each of the 1,000 groups, best first.
    Only the treated customers of the first 300 groups respond, so the top 30% holds every extra
    outcome."""
    n = 2 * vu.BINS
    score = np.arange(n, 0, -1, dtype=float)
    t = np.tile([1, 0], vu.BINS)
    y = np.zeros(n)
    y[: 2 * 300 : 2] = 1.0
    return score, t, y


def test_measures_match_a_hand_computed_case():
    score, t, y = _ranked_case()
    b = vu.binned(score, t, y)
    m = vu.curve_metrics(b["nt"], b["nc"], b["yt"], b["yc"], b["n"])
    assert m["top30_share_of_total_lift"] == pytest.approx(1.0)
    # the curve, as a share of the total, is min(f / 0.3, 1): area 0.85, minus the random line's 0.5
    assert m["qini_ours"] == pytest.approx(0.35, abs=1e-9)
    assert m["uplift_top30_per_customer"] == pytest.approx(1.0)  # 300 of 300 treated, 0 untreated
    assert m["uplift_average_per_customer"] == pytest.approx(0.3)
    assert m["top30_against_average"] == pytest.approx(1 / 0.3)


def test_random_ranking_finds_about_its_share():
    rng = np.random.default_rng(1)
    n = 200_000
    t = (rng.random(n) < 0.5).astype(int)
    y = (rng.random(n) < np.where(t == 1, 0.12, 0.10)).astype(float)
    b = vu.binned(rng.random(n), t, y)
    m = vu.curve_metrics(b["nt"], b["nc"], b["yt"], b["yc"], b["n"])
    assert abs(m["top30_share_of_total_lift"] - 0.3) < 0.1
    assert abs(m["qini_ours"]) < 0.1


def test_bootstrap_is_centred_on_the_estimate_and_both_forms_agree():
    """The cell bootstrap for 0/1 outcomes and the reweighting one for money outcomes resample the
    same thing, so on the same 0/1 data they give the same spread."""
    rng = np.random.default_rng(2)
    n = 20_000
    t = (rng.random(n) < 0.5).astype(int)
    lift = rng.random(n)
    y = (rng.random(n) < 0.05 + 0.10 * lift * t).astype(float)
    b = vu.binned(lift, t, y)
    point = vu.curve_metrics(b["nt"], b["nc"], b["yt"], b["yc"], b["n"])["top30_share_of_total_lift"]
    cells = vu.bootstrap(b, True, rng=np.random.default_rng(3))["top30_share_of_total_lift"]
    order = np.argsort(-lift, kind="stable")
    start = np.linspace(0, n, vu.BINS + 1).astype(int)[:-1]
    rows = vu.bootstrap(b, False, (t[order].astype(float), y[order], start), np.random.default_rng(4))
    rows = rows["top30_share_of_total_lift"]
    assert abs(np.median(cells) - point) < 0.05
    assert np.std(cells) == pytest.approx(np.std(rows), rel=0.3)


def test_library_qini_is_one_for_a_perfect_ranking_and_absent_for_money():
    pytest.importorskip("sklift")
    _, t, y = _ranked_case()
    perfect = y * t - y * (1 - t)
    assert vu.qini_auc_library(y, perfect, t) == pytest.approx(1.0)
    assert vu.qini_auc_library(y * 37.5, perfect, t) is None  # dollars: the library takes 0/1 only


def test_download_keeps_only_a_file_with_the_recorded_checksum(tmp_path, monkeypatch):
    src = tmp_path / "source.csv"
    src.write_bytes(b"a,b\n1,2\n")
    good = hashlib.sha256(src.read_bytes()).hexdigest()
    monkeypatch.setattr(get_data, "ROOT", tmp_path)
    spec = {"url": src.as_uri(), "path": "raw/x.csv", "sha256": "0" * 64, "bytes": 8}
    monkeypatch.setitem(get_data.DATA, "toy", spec)
    with pytest.raises(SystemExit):
        get_data.fetch("toy")
    assert not (tmp_path / "raw/x.csv").exists() and not (tmp_path / "raw/x.csv.part").exists()
    monkeypatch.setitem(get_data.DATA, "toy", {**spec, "sha256": good})
    assert get_data.fetch("toy").read_bytes() == b"a,b\n1,2\n"
    assert get_data.fetch("toy").exists()  # second call: already here, not downloaded again
