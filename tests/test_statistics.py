"""Statistical properties of the method on the quick configuration (slow: about a minute each).

Each check is a property the method promises, verified against the simulator's truth.
"""

from __future__ import annotations

import pytest

from truelift.economics import Terms
from truelift.sim import Config, Market


@pytest.fixture(scope="module")
def quick_trained(restaurants):
    from truelift.training import train

    return train(Market(restaurants, Config(customers_per_locality=2000), Terms()))


@pytest.mark.slow
def test_topup_value_recovers_truth(quick_trained):
    """TL-020: the learned top-up value is within 0.05 of the simulator's hidden value."""
    truth = quick_trained.market.cfg.topup_value
    assert abs(quick_trained.engine.topup_value - truth) <= 0.05
    lo, hi = quick_trained.topup_range
    assert lo - 0.025 <= truth <= hi + 0.025  # inside the 80% interval, up to one grid step
