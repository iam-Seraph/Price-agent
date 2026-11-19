"""Opt-in, local single-operator preference memory; not model training.

Untrusted provider text never becomes an instruction. Only explicit PREFER/AVOID
votes tied to existing source-backed offer IDs are stored. Users can delete
individual feedback or clear all feedback and opt out.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .store import VerifiedPriceStore, utc_now

MIGRATION = Path(__file__).resolve().parents[2] / "migrations" / "006_learning.sql"
_OFFER_ID = re.compile(r"[0-9a-f]{64}\Z")
_MAX_FEEDBACK = 500


def _validate_offer_id(offer_id: str) -> str:
    if not isinstance(offer_id, str) or not _OFFER_ID.fullmatch(offer_id):
        raise ValueError("Feedback requires an existing 64-character offer ID")
    return offer_id


class LearningStore:
    """One machine operator, no background ingestion or identity management."""

    def __init__(self, path: str | Path) -> None:
        self.prices = VerifiedPriceStore(path)
        with self.prices.connect() as db:
            db.executescript("BEGIN IMMEDIATE;\n" + MIGRATION.read_text(encoding="utf-8")
                             + "\nCOMMIT;")

    def status(self) -> dict[str, Any]:
        with self.prices.connect_readonly() as db:
            row = db.execute(
                "SELECT enabled FROM verified_learning_settings WHERE id=1"
            ).fetchone()
            count = db.execute("SELECT COUNT(*) FROM verified_offer_feedback").fetchone()[0]
        return {
            "enabled": bool(row["enabled"]) if row is not None else False,
            "saved_feedback_count": int(count),
            "local_only": True,
            "model_weights_changed": False,
            "provider_requests": 0,
            "notice": "Explicit product preferences only; no raw chat, website text, or personal details are stored.",
        }

    def set_enabled(self, enabled: bool, *, confirmed: bool = False) -> dict[str, Any]:
        if type(enabled) is not bool or confirmed is not True:
            raise ValueError("Explicit confirmation is required to change learning mode")
        with self.prices.connect() as db:
            with db:
                db.execute("UPDATE verified_learning_settings SET enabled=?,updated_at=? WHERE id=1",
                           (int(enabled), utc_now()))
        return self.status()

    def give_feedback(self, offer_id: str, preference: str) -> dict[str, str]:
        offer_id = _validate_offer_id(offer_id)
        if preference not in ("PREFER", "AVOID") or not isinstance(preference, str):
            raise ValueError("Choose PREFER or AVOID")
        with self.prices.connect() as db:
            with db:
                db.execute("BEGIN IMMEDIATE")
                enabled = db.execute(
                    "SELECT enabled FROM verified_learning_settings WHERE id=1"
                ).fetchone()
                if enabled is None or not enabled["enabled"]:
                    raise ValueError("Enable opt-in learning before providing feedback")
                if db.execute("SELECT 1 FROM verified_offers WHERE offer_id=?",
                              (offer_id,)).fetchone() is None:
                    raise ValueError("Feedback requires a previously saved provider offer")
                already = db.execute(
                    "SELECT 1 FROM verified_offer_feedback WHERE offer_id=?",
                    (offer_id,)).fetchone()
                if already is None:
                    count = db.execute(
                        "SELECT COUNT(*) FROM verified_offer_feedback").fetchone()[0]
                    if count >= _MAX_FEEDBACK:
                        raise ValueError("Local feedback capacity reached")
                db.execute("""
                    INSERT INTO verified_offer_feedback(offer_id,preference,source,updated_at)
                    VALUES (?,?,'USER_EXPLICIT',?)
                    ON CONFLICT(offer_id) DO UPDATE SET
                      preference=excluded.preference,updated_at=excluded.updated_at
                """, (offer_id, preference, utc_now()))
        return {"offer_id": offer_id, "preference": preference, "source": "USER_EXPLICIT"}

    def forget_offer(self, offer_id: str) -> bool:
        offer_id = _validate_offer_id(offer_id)
        with self.prices.connect() as db:
            with db:
                return db.execute(
                    "DELETE FROM verified_offer_feedback WHERE offer_id=?",
                    (offer_id,)).rowcount == 1

    def clear_all(self, *, confirmed: bool = False) -> dict[str, Any]:
        if confirmed is not True:
            raise ValueError("Explicit confirmation required to erase feedback")
        with self.prices.connect() as db:
            with db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("DELETE FROM verified_offer_feedback")
                db.execute("UPDATE verified_learning_settings SET enabled=0,updated_at=? WHERE id=1",
                           (utc_now(),))
        return self.status()

    def preferences_for(self, offer_ids: list[str]) -> dict[str, str]:
        """Read only structured preferences when operator has opted in."""
        if not isinstance(offer_ids, list) or len(offer_ids) > 100:
            raise ValueError("At most 100 offer IDs may be personalized")
        if not offer_ids:
            return {}
        ids = list(dict.fromkeys(_validate_offer_id(value) for value in offer_ids))
        with self.prices.connect_readonly() as db:
            flag = db.execute(
                "SELECT enabled FROM verified_learning_settings WHERE id=1"
            ).fetchone()
            if flag is None or not flag["enabled"]:
                return {}
            placeholders = ",".join("?" for _ in ids)
            rows = db.execute(
                "SELECT offer_id,preference FROM verified_offer_feedback WHERE offer_id IN ("
                + placeholders + ")", ids).fetchall()
            return {str(row["offer_id"]): str(row["preference"]) for row in rows}
