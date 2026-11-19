"""Entirely offline, persistently simulated shopping workflow.

This database is incompatible with real/provider-reported offer history ON PURPOSE.
No network clients, API credentials, SMTP or Telegram transports are imported.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator
from uuid import NAMESPACE_URL, uuid5

from .verified.commands import parse_shopping_intent
from .verified.money import format_minor, minor_units

FIXTURES = Path(__file__).resolve().parent / "data" / "demo_products.json"
LABEL = "DEMO_FIXTURE"
SCHEMA = """
CREATE TABLE IF NOT EXISTS demo_meta (
    id INTEGER PRIMARY KEY CHECK(id=1),
    label TEXT NOT NULL CHECK(label='DEMO_FIXTURE'),
    tick INTEGER NOT NULL DEFAULT 0,
    learning_enabled INTEGER NOT NULL DEFAULT 0 CHECK(learning_enabled IN (0,1))
);
CREATE TABLE IF NOT EXISTS demo_offers (
    offer_id TEXT PRIMARY KEY,
    product_key TEXT NOT NULL,
    title TEXT NOT NULL,
    merchant TEXT NOT NULL,
    stock TEXT NOT NULL CHECK(stock IN ('IN_STOCK','OUT_OF_STOCK','UNKNOWN')),
    specs_json TEXT NOT NULL,
    currency TEXT NOT NULL CHECK(currency='INR')
);
CREATE TABLE IF NOT EXISTS demo_prices (
    offer_id TEXT NOT NULL REFERENCES demo_offers(offer_id),
    tick INTEGER NOT NULL,
    observed_at TEXT NOT NULL,
    price_minor INTEGER NOT NULL CHECK(price_minor>0),
    provenance TEXT NOT NULL DEFAULT 'DEMO_FIXTURE' CHECK(provenance='DEMO_FIXTURE'),
    PRIMARY KEY(offer_id,tick)
);
CREATE TABLE IF NOT EXISTS demo_watches (
    watch_id TEXT PRIMARY KEY,
    query_text TEXT NOT NULL,
    budget_minor INTEGER NOT NULL CHECK(budget_minor>0),
    channel TEXT NOT NULL CHECK(channel IN ('SIMULATED_EMAIL','SIMULATED_TELEGRAM')),
    enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1))
);
CREATE TABLE IF NOT EXISTS demo_alerts (
    alert_id TEXT PRIMARY KEY,
    watch_id TEXT NOT NULL REFERENCES demo_watches(watch_id),
    offer_id TEXT NOT NULL REFERENCES demo_offers(offer_id),
    tick INTEGER NOT NULL,
    price_minor INTEGER NOT NULL CHECK(price_minor>0),
    channel TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('QUEUED','SIMULATED_SENT')),
    UNIQUE(watch_id,offer_id,tick)
);
CREATE TABLE IF NOT EXISTS demo_feedback (
    offer_id TEXT PRIMARY KEY REFERENCES demo_offers(offer_id),
    preference TEXT NOT NULL CHECK(preference IN ('PREFER','AVOID'))
);
"""


def _stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _query(text: str) -> str:
    if (not isinstance(text, str) or not 2 <= len(text.strip()) <= 120
            or any(ord(c) < 32 or ord(c) == 127 for c in text)):
        raise ValueError("Product query must be 2–120 printable characters")
    return text.strip()


class DemoStore:
    """A separate, marked SQLite database for fictional shopping fixtures ONLY."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            existing = {str(row[0]) for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )}
            if existing and "demo_meta" not in existing:
                raise ValueError("Refusing to mix offline demo data with an existing non-demo database")
            with db:
                db.executescript(SCHEMA)
                marker = db.execute("SELECT label FROM demo_meta WHERE id=1").fetchone()
                if marker is not None and marker["label"] != LABEL:
                    raise ValueError("Database has an unexpected provenance marker")
                if marker is None:
                    db.execute("INSERT INTO demo_meta(id,label) VALUES(1,'DEMO_FIXTURE')")
                    self._seed(db)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=10)
        try:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA busy_timeout=10000")
            yield db
        finally:
            db.close()

    def _seed(self, db: sqlite3.Connection) -> None:
        fixtures = json.loads(FIXTURES.read_text(encoding="utf-8"))
        now = datetime.now(timezone.utc)
        for index, row in enumerate(fixtures):
            # Extra fictional retailer variants make cross-seller comparisons testable.
            for variant in range(2 if index < 4 else 1):
                merchant = str(row["retailer"]) if variant == 0 else "Fictional Outlet"
                key = f"fixture-{index}"
                offer_id = uuid5(NAMESPACE_URL, f"offline-demo:{key}:{merchant}").hex
                price = minor_units(str(row["price"]), "INR")
                if variant:
                    price = max(1, price * 96 // 100)
                db.execute("""
                    INSERT INTO demo_offers
                    (offer_id,product_key,title,merchant,stock,specs_json,currency)
                    VALUES(?,?,?,?,?,?,'INR')
                """, (offer_id, key, str(row["name"]), merchant,
                      str(row["availability"]), json.dumps(row.get("specs", {}))))
                # Actual source data is NEVER fabricated here: this is a labeled
                # simulated time series in an unrelated database.
                baseline = price * 125 // 100
                for age in range(13, -1, -1):
                    value = price if age == 0 else baseline + ((age % 3) * 50)
                    db.execute("""
                        INSERT INTO demo_prices(offer_id,tick,observed_at,price_minor)
                        VALUES(?,?,?,?)
                    """, (offer_id, -age, _stamp(now-timedelta(days=age)), value))

    def status(self) -> dict[str, Any]:
        with self.connect() as db:
            meta = db.execute("SELECT * FROM demo_meta WHERE id=1").fetchone()
            counts = {
                name: int(db.execute(f"SELECT COUNT(*) FROM demo_{name}").fetchone()[0])
                for name in ("offers", "prices", "watches", "alerts", "feedback")
            }
        return {"mode": LABEL, "offline_only": True, "network_requests": 0,
                "external_credentials_required": False, "real_notifications_sent": 0,
                "simulated_tick": int(meta["tick"]), "learning_enabled": bool(meta["learning_enabled"]),
                "counts": counts, "notice": "ALL products, sellers, prices, histories and alerts here are fictional."}

    def _offers(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("""
                SELECT o.*, p.price_minor, p.observed_at, p.tick,
                       f.preference
                FROM demo_offers o
                JOIN demo_prices p ON p.offer_id=o.offer_id AND p.tick=(
                    SELECT MAX(x.tick) FROM demo_prices x WHERE x.offer_id=o.offer_id)
                LEFT JOIN demo_feedback f ON f.offer_id=o.offer_id
                ORDER BY o.title,o.merchant
            """).fetchall()
        return [
            {**dict(row), "specs": json.loads(str(row["specs_json"])),
             "provenance": LABEL, "offer_id": str(row["offer_id"])}
            for row in rows
        ]

    def search(self, query: str, budget: str = "100000", *, limit: int = 30) -> dict[str, Any]:
        query = _query(query)
        budget_minor = minor_units(budget, "INR")
        if type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError("Search limit must be 1–50")
        enabled = self.status()["learning_enabled"]
        rows = [row for row in self._offers() if query.casefold() in
                (row["title"]+" "+row["merchant"]).casefold()][:limit]
        for row in rows:
            row["under_budget"] = row["price_minor"] <= budget_minor
            row["budget_candidate"] = row["under_budget"] and row["stock"] == "IN_STOCK"
            row["price_display"] = format_minor(int(row["price_minor"]), "INR")
            row["preference"] = row["preference"] if enabled else None
            del row["specs_json"]
        objective = sorted(rows, key=lambda r: (not r["budget_candidate"], r["price_minor"], r["offer_id"]))
        personalized = sorted(rows, key=lambda r: (
            not r["budget_candidate"],
            -{"PREFER": 1, "AVOID": -1}.get(r["preference"], 0),
            r["price_minor"], r["offer_id"],
        )) if enabled else objective
        return {"query": query, "budget_minor": budget_minor, "currency": "INR",
                "provenance": LABEL, "count": len(rows), "offers": objective,
                "personalized_offer_ids": [r["offer_id"] for r in personalized],
                "learning_enabled": enabled, "network_requests": 0,
                "notice": "Synthetic demo data. Different fictional listings are not guaranteed equivalent."}

    def history(self, offer_id: str) -> dict[str, Any]:
        with self.connect() as db:
            offer = db.execute("SELECT * FROM demo_offers WHERE offer_id=?", (offer_id,)).fetchone()
            if offer is None:
                raise ValueError("Unknown demo offer")
            rows = db.execute("""
                SELECT tick,observed_at,price_minor,provenance FROM demo_prices
                WHERE offer_id=? ORDER BY tick LIMIT 180
            """, (offer_id,)).fetchall()
        return {"offer_id": offer_id, "title": offer["title"], "merchant": offer["merchant"],
                "currency": "INR", "stock": offer["stock"], "provenance": LABEL,
                "observations": [dict(row) for row in rows],
                "network_requests": 0}

    def analyze(self, offer_id: str, budget: str) -> dict[str, Any]:
        history = self.history(offer_id)
        values = [int(x["price_minor"]) for x in history["observations"]]
        latest, low, avg = values[-1], min(values), sum(values)//len(values)
        checks = {"under_budget": latest <= minor_units(budget, "INR"),
                  "history_depth": len({x["observed_at"][:10] for x in history["observations"]}) >= 10,
                  "below_history_average": latest * 10 <= avg * 9,
                  "near_recorded_low": latest * 20 <= low * 21,
                  "stock_in_fixture": history["stock"] == "IN_STOCK"}
        decision = "SIMULATED_DEAL" if all(checks.values()) else "NO_SIMULATED_DEAL"
        return {"offer_id": offer_id, "decision": decision, "checks": checks,
                "current_minor": latest, "average_minor": avg, "low_minor": low,
                "sample_count": len(values), "currency": "INR",
                "provenance": LABEL, "price_display": format_minor(latest, "INR"),
                "notice": "Demonstration heuristic, not a real seller quote, deal guarantee or AI forecast."}

    def explain(self, offer_id: str, budget: str) -> dict[str, Any]:
        result = self.analyze(offer_id, budget)
        failed = [name.replace("_", " ") for name, ok in result["checks"].items() if not ok]
        return {"mode": "DETERMINISTIC_DEMO_EXPLANATION", "ai_model_called": False,
                "provenance": LABEL, "decision": result["decision"],
                "text": ("Simulated deal conditions met in fictional history." if not failed
                         else "Simulated deal conditions not met: " + ", ".join(failed) + "."),
                "notice": "This offline stand-in is not a Groq/OpenAI response."}

    def catalog(self) -> dict[str, Any]:
        return {"source": LABEL, "retailer_prices_real": False, "products": json.loads(
            FIXTURES.read_text(encoding="utf-8")), "notice": "Bundled fictional product catalog, not Open Food Facts."}

    def add_watch(self, query: str, budget: str, channel: str, *, confirmed: bool) -> dict[str, Any]:
        query = _query(query)
        threshold = minor_units(budget, "INR")
        if confirmed is not True or channel not in ("SIMULATED_EMAIL","SIMULATED_TELEGRAM"):
            raise ValueError("Explicit confirmation and a simulated channel are required")
        watch_id = uuid5(NAMESPACE_URL, f"watch:{query.casefold()}:{threshold}:{channel}").hex
        with self.connect() as db:
            with db:
                db.execute("""
                    INSERT INTO demo_watches(watch_id,query_text,budget_minor,channel)
                    VALUES(?,?,?,?)
                    ON CONFLICT(watch_id) DO UPDATE SET enabled=1
                """, (watch_id,query,threshold,channel))
        return {"watch_id": watch_id, "enabled": True, "mode": LABEL,
                "worker_started": False, "real_delivery_enabled": False}

    def watches(self) -> dict[str, Any]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM demo_watches ORDER BY query_text").fetchall()
        return {"watches": [dict(r) for r in rows], "provenance": LABEL}

    def disable_watch(self, watch_id: str) -> dict[str, Any]:
        with self.connect() as db:
            with db:
                n = db.execute("UPDATE demo_watches SET enabled=0 WHERE watch_id=?",
                               (watch_id,)).rowcount
        return {"disabled": bool(n), "provenance": LABEL}

    def poll_once(self, *, confirmed: bool) -> dict[str, Any]:
        """Advance simulated quotations once, then queue pretend notifications."""
        if confirmed is not True:
            raise ValueError("Explicit confirmation required to advance demo simulation")
        now = datetime.now(timezone.utc)
        queued = 0
        with self.connect() as db:
            with db:
                db.execute("BEGIN IMMEDIATE")
                current = db.execute("SELECT tick FROM demo_meta WHERE id=1").fetchone()
                step = int(current["tick"]) + 1
                watches = db.execute("SELECT * FROM demo_watches WHERE enabled=1").fetchall()
                offers = db.execute("SELECT offer_id,title,stock FROM demo_offers").fetchall()
                if step > 100:
                    raise ValueError("Demo has reached its bounded 100-step limit")
                for row in offers:
                    last = db.execute("""
                        SELECT price_minor FROM demo_prices WHERE offer_id=?
                        ORDER BY tick DESC LIMIT 1
                    """, (row["offer_id"],)).fetchone()
                    next_minor = max(1, int(last["price_minor"]) * (96 - step % 3) // 100)
                    db.execute("""
                        INSERT INTO demo_prices(offer_id,tick,observed_at,price_minor)
                        VALUES(?,?,?,?)
                    """, (row["offer_id"],step,_stamp(now),next_minor))
                    for watch in watches:
                        if (str(watch["query_text"]).casefold() in str(row["title"]).casefold()
                                and row["stock"] == "IN_STOCK"
                                and next_minor <= int(watch["budget_minor"])):
                            alert_id = uuid5(NAMESPACE_URL,
                                f"alert:{watch['watch_id']}:{row['offer_id']}:{step}").hex
                            db.execute("""
                                INSERT INTO demo_alerts(alert_id,watch_id,offer_id,
                                                        tick,price_minor,channel,status)
                                VALUES(?,?,?,?,?,?,'QUEUED')
                            """, (alert_id,watch["watch_id"],row["offer_id"],step,
                                  next_minor,watch["channel"]))
                            queued += 1
                db.execute("UPDATE demo_meta SET tick=? WHERE id=1", (step,))
        return {"simulated_tick": step, "queued_simulated_alerts": queued,
                "offers_updated": len(offers), "provenance": LABEL,
                "network_requests": 0, "real_messages_sent": 0}

    def alerts(self) -> dict[str, Any]:
        with self.connect() as db:
            rows = db.execute("""
                SELECT a.alert_id,a.watch_id,a.offer_id,o.title,a.tick,a.price_minor,
                       a.channel,a.status FROM demo_alerts a
                JOIN demo_offers o ON o.offer_id=a.offer_id
                ORDER BY a.tick DESC LIMIT 100
            """).fetchall()
        return {"alerts": [dict(r) for r in rows], "mode": LABEL,
                "real_messages_sent": 0}

    def dispatch(self, *, confirmed: bool) -> dict[str, Any]:
        if confirmed is not True:
            raise ValueError("Explicit confirmation required for simulated delivery")
        with self.connect() as db:
            with db:
                updated = db.execute("""
                    UPDATE demo_alerts SET status='SIMULATED_SENT' WHERE status='QUEUED'
                """).rowcount
        return {"simulated_sent": updated, "real_messages_sent": 0, "provenance": LABEL,
                "notice": "Only local SQLite receipts were updated. No mail, Telegram or network request."}

    def learning(self) -> dict[str, Any]:
        with self.connect() as db:
            enabled = db.execute("SELECT learning_enabled FROM demo_meta WHERE id=1").fetchone()[0]
            count = db.execute("SELECT COUNT(*) FROM demo_feedback").fetchone()[0]
        return {"enabled": bool(enabled), "count": int(count), "mode": LABEL,
                "model_weights_changed": False}

    def learning_enable(self, enabled: bool, *, confirmed: bool) -> dict[str, Any]:
        if type(enabled) is not bool or confirmed is not True:
            raise ValueError("Explicit confirmation required for preference toggle")
        with self.connect() as db:
            with db:
                db.execute("UPDATE demo_meta SET learning_enabled=? WHERE id=1", (int(enabled),))
        return self.learning()

    def feedback(self, offer_id: str, preference: str) -> dict[str, Any]:
        if preference not in ("PREFER","AVOID"):
            raise ValueError("Only PREFER or AVOID are accepted")
        with self.connect() as db:
            with db:
                db.execute("BEGIN IMMEDIATE")
                enabled = db.execute("SELECT learning_enabled FROM demo_meta WHERE id=1").fetchone()[0]
                if not enabled:
                    raise ValueError("Enable local learning before saving preference")
                if db.execute("SELECT 1 FROM demo_offers WHERE offer_id=?", (offer_id,)).fetchone() is None:
                    raise ValueError("Unknown demo offer")
                db.execute("""
                    INSERT INTO demo_feedback(offer_id,preference) VALUES(?,?)
                    ON CONFLICT(offer_id) DO UPDATE SET preference=excluded.preference
                """, (offer_id,preference))
        return {"offer_id": offer_id, "preference": preference,
                "source": "DEMO_USER_EXPLICIT", "mode": LABEL}

    def forget(self, offer_id: str) -> dict[str, Any]:
        with self.connect() as db:
            with db:
                n = db.execute("DELETE FROM demo_feedback WHERE offer_id=?",(offer_id,)).rowcount
        return {"forgotten": bool(n), "mode": LABEL}

    def clear(self, *, confirmed: bool) -> dict[str, Any]:
        if confirmed is not True:
            raise ValueError("Explicit confirmation required to delete demo feedback")
        with self.connect() as db:
            with db:
                db.execute("DELETE FROM demo_feedback")
                db.execute("UPDATE demo_meta SET learning_enabled=0 WHERE id=1")
        return self.learning()

    def assistant(self, command: str, *, confirmed: bool) -> dict[str, Any]:
        intent = parse_shopping_intent(command)
        if intent.action == "CREATE_WATCH":
            if not confirmed:
                return {"status": "CONFIRMATION_REQUIRED", "intent": intent.as_dict(),
                        "mode": LABEL, "network_requests": 0}
            saved = self.add_watch(intent.query,
                str(intent.budget_minor//100) + "." + f"{intent.budget_minor%100:02d}",
                "SIMULATED_EMAIL", confirmed=True)
            return {"status": "SIMULATED_WATCH_SAVED", "watch": saved, "mode": LABEL}
        query = self.search(intent.query,
                           str(intent.budget_minor//100) + "." + f"{intent.budget_minor%100:02d}")
        return {"status": "SIMULATED_RESEARCH", "research": query,
                "mode": LABEL, "network_requests": 0}

    def audit(self) -> dict[str, Any]:
        with self.connect() as db:
            integrity = db.execute("PRAGMA quick_check(1)").fetchone()[0]
            provenance = db.execute("""
                SELECT COUNT(*) FROM demo_prices WHERE provenance!='DEMO_FIXTURE'
            """).fetchone()[0]
            foreign = db.execute("PRAGMA foreign_key_check").fetchall()
        ok = integrity == "ok" and provenance == 0 and not foreign
        return {"status": "PASS" if ok else "FAIL", "sqlite_quick_check": integrity,
                "invalid_provenance": provenance, "foreign_key_errors": len(foreign),
                "mode": LABEL, "network_requests": 0, "production_certification": False}
