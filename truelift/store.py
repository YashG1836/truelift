"""Persistence for the two records an incrementality system lives on (SQLite, standard library).

1. The consent ledger. Every OTP approval is appended with exactly what the owner was shown
   (design, forecast, who pays, validity, model version) and chained by SHA-256 to the record
   before it. Changing one byte of any past record breaks the chain, which `verify` reports
   (audit TL-025). OTP generation and checking stay Zomato's existing flow; this stores
   evidence, not credentials.
2. The exposure log. Each eligible menu visit is logged when the decision is taken (held out or
   shown, with the model's predictions), and each order is logged when it happens. The weekly
   measurement is computed from the join of the two, the way it would be from Zomato's own event
   logs (audit TL-028).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time

import numpy as np
import pandas as pd

GENESIS = "0" * 64


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=float)


class Store:
    def __init__(self, path: str = ":memory:"):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        with self.lock, self.conn:
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS consents (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    session TEXT NOT NULL, offer_id INTEGER NOT NULL,
                    payload TEXT NOT NULL, created_at TEXT NOT NULL,
                    prev_hash TEXT NOT NULL, hash TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS consents_offer ON consents(offer_id);
                CREATE TABLE IF NOT EXISTS exposures (
                    offer_id INTEGER NOT NULL, week INTEGER NOT NULL, visit_id INTEGER NOT NULL,
                    customer_id INTEGER NOT NULL, slot INTEGER NOT NULL,
                    eligible INTEGER NOT NULL, assignment TEXT NOT NULL,
                    p0 REAL, p1 REAL, gain REAL, base_profit REAL,
                    model_version TEXT, source TEXT NOT NULL, logged_at REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS exposures_offer ON exposures(offer_id, week);
                CREATE TABLE IF NOT EXISTS orders (
                    offer_id INTEGER NOT NULL, week INTEGER NOT NULL, visit_id INTEGER NOT NULL,
                    customer_id INTEGER NOT NULL, used_offer INTEGER NOT NULL,
                    basket REAL NOT NULL, discount REAL NOT NULL, profit REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS orders_offer ON orders(offer_id, week);
            """)

    # ---------------- consent ledger ----------------
    @staticmethod
    def _hash(prev_hash: str, session: str, offer_id: int, payload: str, created_at: str) -> str:
        body = canonical({"session": session, "offer_id": offer_id, "payload": payload, "created_at": created_at})
        return hashlib.sha256((prev_hash + body).encode("utf-8")).hexdigest()

    def append_consent(self, session: str, offer_id: int, record: dict, created_at: str) -> dict:
        payload = canonical(record)
        with self.lock, self.conn:
            row = self.conn.execute("SELECT hash FROM consents ORDER BY seq DESC LIMIT 1").fetchone()
            prev = row[0] if row else GENESIS
            h = self._hash(prev, session, offer_id, payload, created_at)
            cur = self.conn.execute(
                "INSERT INTO consents(session, offer_id, payload, created_at, prev_hash, hash) VALUES (?,?,?,?,?,?)",
                (session, offer_id, payload, created_at, prev, h),
            )
            return {"seq": cur.lastrowid, "hash": h, "prev_hash": prev}

    def consent(self, offer_id: int) -> dict | None:
        with self.lock:
            row = self.conn.execute(
                "SELECT seq, payload, prev_hash, hash FROM consents WHERE offer_id=? ORDER BY seq DESC LIMIT 1",
                (offer_id,),
            ).fetchone()
        if row is None:
            return None
        return {"seq": row[0], "record": json.loads(row[1]), "prev_hash": row[2], "hash": row[3]}

    def verify(self) -> tuple[bool, int | None]:
        """Recompute the whole chain. Returns (ok, first bad sequence number)."""
        with self.lock:
            rows = self.conn.execute(
                "SELECT seq, session, offer_id, payload, created_at, prev_hash, hash FROM consents ORDER BY seq"
            ).fetchall()
        prev = GENESIS
        for seq, session, offer_id, payload, created_at, prev_hash, h in rows:
            if prev_hash != prev or self._hash(prev, session, offer_id, payload, created_at) != h:
                return False, seq
            prev = h
        return True, None

    # ---------------- exposure log ----------------
    def log_serve(self, offer_id: int, customer_id: int, slot: int, decision: dict, model_version: str) -> None:
        assignment = "control" if decision["control_group"] else "show" if decision["show_offer"] else "not_eligible"
        with self.lock, self.conn:
            self.conn.execute(
                "INSERT INTO exposures VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    offer_id,
                    0,
                    -1,
                    int(customer_id),
                    int(slot),
                    int(assignment != "not_eligible"),
                    assignment,
                    decision.get("p_order_without"),
                    decision.get("p_order_with"),
                    decision.get("expected_profit_gain"),
                    None,
                    model_version,
                    "serve",
                    time.time(),
                ),
            )

    def log_week(self, offer_id: int, week: int, rows: pd.DataFrame, model_version: str) -> None:
        """Log one simulated week: an exposure per eligible visit, an order per visit that ordered.

        rows: eligible visits with visit_id, cust, slot, shown, holdout, chosen, takes, basket,
        discount, profit and the model's p0, p1, gain, base_profit for each visit.
        """
        assign = np.where(rows["holdout"].to_numpy(), "control", "show")
        now = time.time()
        exp = list(
            zip(
                [offer_id] * len(rows),
                [week] * len(rows),
                rows["visit_id"].astype(int),
                rows["cust"].astype(int),
                rows["slot"].astype(int),
                [1] * len(rows),
                assign,
                rows["p0"].astype(float),
                rows["p1"].astype(float),
                rows["gain"].astype(float),
                rows["base_profit"].astype(float),
                [model_version] * len(rows),
                ["simulated_week"] * len(rows),
                [now] * len(rows),
                strict=True,
            )
        )
        ordered = rows[rows["chosen"].to_numpy()]
        ords = list(
            zip(
                [offer_id] * len(ordered),
                [week] * len(ordered),
                ordered["visit_id"].astype(int),
                ordered["cust"].astype(int),
                ordered["takes"].astype(int),
                ordered["basket"].astype(float),
                ordered["discount"].astype(float),
                ordered["profit"].astype(float),
                strict=True,
            )
        )
        with self.lock, self.conn:
            self.conn.executemany(
                "INSERT INTO exposures VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", [tuple(_py(v) for v in r) for r in exp]
            )
            self.conn.executemany(
                "INSERT INTO orders VALUES (?,?,?,?,?,?,?,?)", [tuple(_py(v) for v in r) for r in ords]
            )

    def measurement_rows(self, offer_id: int) -> pd.DataFrame:
        """Exposures joined to orders: the input of the weekly measurement."""
        with self.lock:
            df = pd.read_sql_query(
                """
                SELECT e.week, e.visit_id, e.customer_id AS cust, e.assignment, e.p0, e.p1, e.gain,
                       e.base_profit, o.used_offer, o.basket, o.discount, o.profit
                FROM exposures e
                LEFT JOIN orders o ON o.offer_id = e.offer_id AND o.week = e.week AND o.visit_id = e.visit_id
                WHERE e.offer_id = ? AND e.source = 'simulated_week'
                ORDER BY e.week, e.visit_id""",
                self.conn,
                params=(offer_id,),
            )
        df["shown"] = (df["assignment"] == "show").to_numpy()
        df["holdout"] = (df["assignment"] == "control").to_numpy()
        df["chosen"] = df["profit"].notna().to_numpy()
        df["takes"] = df["used_offer"].fillna(0).astype(bool).to_numpy()
        for col in ("basket", "discount", "profit"):
            df[col] = df[col].fillna(0.0)
        return df

    def exposure_count(self, offer_id: int, source: str | None = None) -> int:
        q = "SELECT COUNT(*) FROM exposures WHERE offer_id=?" + (" AND source=?" if source else "")
        with self.lock:
            return int(self.conn.execute(q, (offer_id, source) if source else (offer_id,)).fetchone()[0])


def _py(v):
    """numpy scalars to plain Python for sqlite3."""
    if isinstance(v, np.generic):
        return v.item()
    return v
