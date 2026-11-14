"""Who is in an offer's control group. One function, used by serving, by the customer panel and by
the simulated weeks, so a customer shown as "control group" is exactly a customer the weekly
measurement holds out (audit TL-004).

The assignment is a hash of (customer, offer): stable for the offer's whole life, independent
across offers, and impossible to steer by anything about the customer.
"""

from __future__ import annotations

import numpy as np

HOLDOUT_SALT = 2  # restaurant offers: serving, measurement and the customer panel
REWARD_SALT = 3  # Brand Pack reward: its own control group among regulars (audit TL-016)
DEPTH_SALT = 5  # depth tests: which of two discount sizes a customer is offered


def stable_uniform(a: np.ndarray, b: np.ndarray, salt: int) -> np.ndarray:
    """Deterministic U(0,1) per (a, b) pair: the hashed holdout assignment."""
    a = np.asarray(a)
    b = np.asarray(b)
    x = (
        a.astype(np.uint64) * np.uint64(2654435761)
        + b.astype(np.uint64) * np.uint64(40503)
        + np.uint64(salt % 4294967296) * np.uint64(97531)
    ) & np.uint64(0xFFFFFFFF)
    x ^= x >> np.uint64(16)
    x = (x * np.uint64(0x45D9F3B)) & np.uint64(0xFFFFFFFF)
    x ^= x >> np.uint64(16)
    return x.astype(np.float64) / 4294967296.0


def in_control_group(customer_ids, offer_ids, share: float, salt: int = HOLDOUT_SALT) -> np.ndarray:
    """True for customers held out of this offer (they see the normal menu price).

    customer_ids and offer_ids broadcast against each other (one offer id for many customers, or
    one per exposure).
    """
    c = np.atleast_1d(np.asarray(customer_ids))
    o = np.broadcast_to(np.atleast_1d(np.asarray(offer_ids)), c.shape)
    return stable_uniform(c, o, salt) < share
