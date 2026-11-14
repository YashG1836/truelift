"""What an on-call person at Zomato would watch: input drift and the weekly guardrails (audit A16 O4, O7).

`drift_report` compares every model input between the training rows and the tables the model is
used on (the quote input and the evaluation weeks): the population stability index (PSI) and the
share of values the model never saw. It fails when an input has moved enough that the model's
numbers should not be trusted, which is what happened when training and serving computed the
look-back windows differently (audit TL-007); `tests/test_monitoring.py` reintroduces that fault
and checks the report fails.

`guardrails` turns a period of weekly measurements into a handful of checks, each with a
threshold and a sentence saying what a failure would mean.
"""

from __future__ import annotations

import html
from typing import Any

import numpy as np
import pandas as pd

from .features import DISCRETE, FEATURE_NAMES

PSI_WATCH = 0.10  # common rule of thumb: below 0.1 stable, 0.1-0.25 worth a look, above 0.25 moved
PSI_FAIL = 0.25
EPS = 1e-4


def psi(train: np.ndarray, other: np.ndarray, discrete: bool, bins: int = 10) -> float:
    """Population stability index of `other` against `train`: sum of (q - p) ln(q / p) over bins.

    Discrete inputs (counts, weeks since) use their values as the bins; continuous ones use the
    training deciles, so each training bin holds a tenth of the rows."""
    train, other = np.asarray(train, float), np.asarray(other, float)
    if len(train) == 0 or len(other) == 0:
        return 0.0
    if discrete:
        values = np.union1d(np.unique(train), np.unique(other))
        p = np.array([(train == v).mean() for v in values])
        q = np.array([(other == v).mean() for v in values])
    else:
        edges = np.unique(np.quantile(train, np.linspace(0, 1, bins + 1)))
        if len(edges) < 3:  # (almost) constant in training: compare as discrete
            return psi(train, other, True)
        inner = edges[1:-1]
        p = np.bincount(np.searchsorted(inner, train, side="right"), minlength=len(inner) + 1) / len(train)
        q = np.bincount(np.searchsorted(inner, other, side="right"), minlength=len(inner) + 1) / len(other)
    p, q = np.clip(p, EPS, None), np.clip(q, EPS, None)
    return float(((q - p) * np.log(q / p)).sum())


def drift_report(train: pd.DataFrame, others: dict[str, pd.DataFrame], features=FEATURE_NAMES) -> dict:
    """PSI and share outside the training support for each input, in each table; pass or fail."""
    out: dict[str, Any] = {"psi_watch": PSI_WATCH, "psi_fail": PSI_FAIL, "features": {}, "worst_psi": 0.0}
    for f in features:
        if f not in train:
            continue
        t = train[f].to_numpy()
        disc = f in DISCRETE
        entry: dict[str, Any] = {"discrete": disc}
        for name, df in others.items():
            if f not in df:
                continue
            v = df[f].to_numpy()
            value = psi(t, v, disc)
            outside = ~np.isin(v, np.unique(t)) if disc else (v < t.min()) | (v > t.max())
            entry[name] = {
                "psi": round(value, 4),
                "share_outside_training": round(float(outside.mean()) if len(v) else 0.0, 5),
                "status": "fail" if value > PSI_FAIL else "watch" if value > PSI_WATCH else "pass",
                "mean_training": round(float(t.mean()), 4),
                "mean_here": round(float(v.mean()), 4) if len(v) else None,
            }
            out["worst_psi"] = max(out["worst_psi"], value)
        out["features"][f] = entry
    out["worst_psi"] = round(out["worst_psi"], 4)
    out["passed"] = out["worst_psi"] <= PSI_FAIL
    return out


def drift_html(report: dict, title: str = "TrueLift input drift") -> str:
    """The drift report as one self-contained page (no scripts, no external files)."""
    tables = sorted({k for e in report["features"].values() for k in e if isinstance(e[k], dict)})
    head = "".join(f"<th>{html.escape(t.replace('_', ' '))}</th>" for t in tables)
    rows = []
    for f, e in report["features"].items():
        cells = []
        for t in tables:
            c = e.get(t)
            if not c:
                cells.append("<td>-</td>")
                continue
            cells.append(
                f'<td class="{c["status"]}">{c["status"]} · PSI {c["psi"]:.3f}'
                f"<br><small>outside training {c['share_outside_training']:.2%}</small></td>"
            )
        rows.append(f"<tr><th>{html.escape(f)}</th>{''.join(cells)}</tr>")
    verdict = "All inputs are stable." if report["passed"] else "At least one input moved: do not trust the numbers."
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>body{{font:15px/1.5 system-ui,sans-serif;margin:24px;color:#1c1c1c}}table{{border-collapse:collapse}}
th,td{{border:1px solid #e8e8e8;padding:6px 10px;text-align:left;vertical-align:top}}td.pass{{background:#f1fbf3}}
td.watch{{background:#fff8e6}}td.fail{{background:#fdecee}}small{{color:#696969}}</style></head><body>
<h1>{html.escape(title)}</h1>
<p>Each model input in the tables the model is used on, against the rows it was trained on. PSI (population
stability index) below {report["psi_watch"]} means stable; above {report["psi_fail"]} means the input has moved and
the forecasts should not be trusted. Simulated data.</p>
<p><b>{verdict}</b> Largest PSI: {report["worst_psi"]:.3f}.</p>
<table><tr><th>Input</th>{head}</tr>{"".join(rows)}</table></body></html>
"""


def guardrails(records: pd.DataFrame, forecast_per_week: dict[int, float], weeks_per_table: int = 4) -> dict:
    """Checks on a period of weekly measurements (one record per offer and week so far).

    records: columns rest, weeks, est_profit, w_own, verdict, srm_ok (scripts/measurement_study).
    forecast_per_week: the weekly profit change each offer was approved on, by restaurant.
    """
    last = int(records["weeks"].max())
    g = records[records["weeks"] == last]
    f = np.array([forecast_per_week.get(int(r), 0.0) * last for r in g["rest"]])
    m = g["est_profit"].to_numpy(float)
    ratio = float(f.sum() / m.sum()) if abs(m.sum()) > 1e-9 else None
    verdicts = g["verdict"].value_counts(normalize=True).round(3).to_dict()
    w = g["w_own"].to_numpy(float)
    flags = int((~g["srm_ok"].astype(bool)).sum())
    checks = [
        {
            "check": "sample_ratio",
            "value": flags,
            "threshold": "at most 1 offer in 1,000",
            "passed": flags <= max(1, len(g) // 1000),
            "meaning": "Customers held out in the planned share. A failure means the split or the logging is "
            "broken, and that offer's number cannot be used until it is fixed.",
        },
        {
            "check": "forecast_against_measured",
            "value": None if ratio is None else round(ratio, 3),
            "threshold": "between 0.67 and 1.5",
            "passed": ratio is not None and 0.67 <= ratio <= 1.5,
            "meaning": "Forecasts shown at approval against what the offers measured. Outside the band, the "
            "quotes owners approve are off and the model needs retraining.",
        },
        {
            "check": "verdict_mix",
            "value": verdicts,
            "threshold": "paused and probably losing together under 25%",
            "passed": verdicts.get("pause", 0) + verdicts.get("probably_losing", 0) < 0.25,
            "meaning": "Share of offers by weekly verdict. Many losing offers means the selection is letting "
            "bad versions through.",
        },
        {
            "check": "weight_on_own_data",
            "value": {
                "p10": round(float(np.quantile(w, 0.1)), 3),
                "median": round(float(np.median(w)), 3),
                "p90": round(float(np.quantile(w, 0.9)), 3),
            },
            "threshold": f"median above 0.2 by week {last}",
            "passed": float(np.median(w)) > 0.2,
            "meaning": "How much each estimate rests on the offer's own control group rather than the model. "
            "If it stays near zero, the weekly numbers are mostly the forecast repeated.",
        },
        {
            "check": "decision_table_age",
            "value": last,
            "threshold": f"at most {weeks_per_table} weeks (rebuilt at each renewal)",
            "passed": last <= weeks_per_table,
            "meaning": "Weeks since each offer's decision table was built. An old table serves customers on "
            "an old snapshot of their history.",
        },
    ]
    return {"weeks": last, "offers": int(len(g)), "checks": checks, "passed": all(c["passed"] for c in checks)}
