"""Uplift model: how likely a customer is to order from a restaurant with and without an offer.

T-learner (two models):
  m0(x)          = P(order | customer and restaurant features, no offer shown)
  m1(x, design)  = P(order | same features, offer with this design shown)
  uplift         = m1 - m0   (extra orders the offer creates for this customer visit)
Training data must come from random assignment (the 10% holdout), so m1 - m0 is causal.
Gradient-boosted trees from scikit-learn; no special libraries needed.

Also here: the Qini curve, the standard check of whether an uplift ranking finds the customers
a discount actually moves (higher than a random ranking = better).
"""

from __future__ import annotations

import hashlib
import pickle
import platform
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingClassifier

BASE_FEATURES = [
    "c_orders_pw",
    "c_disc_share",
    "c_weeks_since",
    "c_sessions_pw",
    "c_no_order_8w",
    "cr_orders_4w",
    "cr_orders_all",
    "cr_visits_4w",
    "cr_weeks_since",
    "r_rating",
    "r_aov",
    "r_logvotes",
    "slot",
    "reward",
]
DESIGN_FEATURES = ["offer_discount", "disc_pct", "mov_ratio"]
# Tried and not adopted (A05 L8, 14 Nov): "c_offer_share_4w", the share of recently opened menus that
# showed the customer an offer. It moved the forecast slightly closer to the truth (0.908 -> 0.927 in
# today's market, quick configuration) but lowered uplift quality (Qini 0.284 -> 0.276, correlation
# 0.640 -> 0.637) and TrueLift's profit; the rule was to keep it only if both improved. It is still
# computed (features.py) for monitoring competition in the drift report.


def design_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    out["offer_discount"] = df["offer_discount"].astype(float)
    out["disc_pct"] = out["offer_discount"] / df["r_aov"]
    out["mov_ratio"] = np.where(df["min_order"] > 0, df["min_order"] / df["r_aov"], 0.0)
    return out


# Known directions (WP-24): a bigger discount or Brand Pack reward never lowers the chance of
# ordering; a higher minimum order (relative to the usual basket) never raises it.
MONOTONE = {"offer_discount": 1, "disc_pct": 1, "reward": 1, "mov_ratio": -1}
# Adopted 14 Nov (quick configuration): forecast/truth 0.908 -> 0.927, offers that pay 224 -> 229,
# Qini 0.284 -> 0.271 (one seed). The create screen quotes four depths, and the owner must never see
# a bigger discount forecast to bring fewer orders.
MONOTONE_DEFAULT = True


def _gbm(seed: int, features: list[str] | None = None, monotone: bool = False) -> HistGradientBoostingClassifier:
    cst = [MONOTONE.get(f, 0) for f in features] if monotone and features else None
    return HistGradientBoostingClassifier(
        max_iter=300,
        learning_rate=0.08,
        max_leaf_nodes=31,
        min_samples_leaf=200,
        l2_regularization=1.0,
        early_stopping=True,
        validation_fraction=0.1,
        random_state=seed,
        monotonic_cst=cst,
    )


@dataclass
class UpliftModel:
    m0: HistGradientBoostingClassifier
    m1: HistGradientBoostingClassifier

    @classmethod
    def fit(cls, rows: pd.DataFrame, seed: int = 0, monotone: bool = MONOTONE_DEFAULT) -> UpliftModel:
        """rows: exposures from a period with random holdouts. Needs columns BASE_FEATURES,
        offer_discount, min_order, shown, chosen."""
        ctrl = rows[~rows["shown"]]
        trt = rows[rows["shown"]]
        m0 = _gbm(seed, BASE_FEATURES, monotone).fit(ctrl[BASE_FEATURES], ctrl["chosen"])
        x1 = pd.concat([trt[BASE_FEATURES], design_columns(trt)], axis=1)
        m1 = _gbm(seed + 1, list(x1.columns), monotone).fit(x1, trt["chosen"])
        return cls(m0, m1)

    def p0(self, x: pd.DataFrame) -> np.ndarray:
        if len(x) == 0:  # e.g. a narrow design with no eligible visit this week
            return np.zeros(0)
        return self.m0.predict_proba(x[BASE_FEATURES])[:, 1]

    def p1(self, x: pd.DataFrame, discount, min_order) -> np.ndarray:
        if len(x) == 0:
            return np.zeros(0)
        d = pd.DataFrame({"offer_discount": discount, "min_order": min_order, "r_aov": x["r_aov"]}, index=x.index)
        return self.m1.predict_proba(pd.concat([x[BASE_FEATURES], design_columns(d)], axis=1))[:, 1]


class BundleError(RuntimeError):
    """The model bundle is missing, altered, or was built with different library versions."""


def library_versions() -> dict:
    return {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "scikit-learn": sklearn.__version__,
    }


def file_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_bundle(bundle: dict, path: Path) -> str:
    """Write the bundle and, beside it, `<name>.sha256` holding its checksum. Returns the checksum."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = pickle.dumps(bundle, protocol=pickle.HIGHEST_PROTOCOL)
    path.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    path.with_name(path.name + ".sha256").write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    return digest


def load_bundle(path: Path, check_versions: bool = True) -> dict:
    """Load a model bundle only after checking it.

    Unpickling runs code from the file, so the file must match the checksum committed beside it
    (audit TL-044); and a pickled scikit-learn model is only guaranteed to load in the version that
    wrote it, so a mismatch is refused with instructions instead of failing later (TL-021).
    """
    path = Path(path)
    if not path.exists():
        raise BundleError(
            f"No model at {path}. Run `python scripts/run_pipeline.py --quick` (about a minute), "
            "or check out the committed data/processed/model.pkl."
        )
    sidecar = path.with_name(path.name + ".sha256")
    if not sidecar.exists():
        raise BundleError(
            f"{sidecar.name} is missing, so the model file cannot be verified. "
            "Rebuild it with `python scripts/run_pipeline.py`."
        )
    data = path.read_bytes()
    expected = sidecar.read_text(encoding="utf-8").split()[0]
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        raise BundleError(
            f"{path.name} does not match its checksum ({actual[:12]} vs {expected[:12]}); refusing to load it."
        )
    art = pickle.loads(data)
    built = art.get("library_versions", {}).get("scikit-learn")
    if check_versions and built and built != sklearn.__version__:
        raise BundleError(
            f"The model was trained with scikit-learn {built} but {sklearn.__version__} is installed. "
            "Install the pinned versions (`uv sync` or `pip install -r requirements.txt`)."
        )
    return art


def qini_curve(score: np.ndarray, treated: np.ndarray, y: np.ndarray, points: int = 50):
    """Qini curve: extra outcomes gained by treating the top-k% by score, versus k.

    Returns (fraction treated, cumulative incremental outcomes, random-ranking line).
    """
    order = np.argsort(-score, kind="stable")
    t, yy = treated[order].astype(float), y[order].astype(float)
    nt, nc = np.cumsum(t), np.cumsum(1 - t)
    yt, yc = np.cumsum(yy * t), np.cumsum(yy * (1 - t))
    q = yt - yc * np.divide(nt, nc, out=np.zeros_like(nt), where=nc > 0)
    idx = np.linspace(0, len(q) - 1, points).astype(int)
    frac = (idx + 1) / len(q)
    return frac, q[idx], frac * q[-1]


def qini_coefficient(score, treated, y) -> float:
    """Area between the Qini curve and the random line, divided by the total gain.

    0 means no better than random; higher is better.
    """
    frac, q, rand = qini_curve(score, treated, y, points=200)
    total = q[-1] if q[-1] != 0 else 1.0
    return float(np.trapezoid(q - rand, frac) / abs(total))
