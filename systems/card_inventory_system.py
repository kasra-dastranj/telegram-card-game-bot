"""Quantity-based ownership by player, character, and card form.

The legacy player_cards row remains the one active form used by battles/decks.
player_card_stacks is the authoritative count of every owned form.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timezone


RARITIES = ("normal", "rare", "epic", "legend")
RANK = {rarity: index for index, rarity in enumerate(RARITIES)}


def ensure_inventory_schema(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS player_card_stacks (
            user_id INTEGER NOT NULL,
            card_id TEXT NOT NULL,
            rarity TEXT NOT NULL CHECK(rarity IN ('normal','rare','epic','legend')),
            quantity INTEGER NOT NULL CHECK(quantity > 0),
            PRIMARY KEY(user_id,card_id,rarity),
            FOREIGN KEY(user_id) REFERENCES players(user_id),
            FOREIGN KEY(card_id) REFERENCES cards(card_id)
        )
    """)
    conn.execute("CREATE TABLE IF NOT EXISTS inventory_migrations (key TEXT PRIMARY KEY)")
    if conn.execute("SELECT 1 FROM inventory_migrations WHERE key='stacks_v1'").fetchone():
        return
    conn.execute("""
        INSERT OR IGNORE INTO player_card_stacks(user_id,card_id,rarity,quantity)
        SELECT pc.user_id,pc.card_id,COALESCE(pc.rarity_override,c.rarity),1
        FROM player_cards pc JOIN cards c ON c.card_id=pc.card_id
    """)
    conn.execute("INSERT INTO inventory_migrations(key) VALUES('stacks_v1')")


class CardInventorySystem:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def counts_in(conn, user_id: int, card_id: str) -> dict[str, int]:
        return {row[0]: int(row[1]) for row in conn.execute(
            "SELECT rarity,quantity FROM player_card_stacks WHERE user_id=? AND card_id=?",
            (user_id, card_id),
        )}

    def counts(self, user_id: int, card_id: str) -> dict[str, int]:
        with closing(sqlite3.connect(self.db.db_path)) as conn:
            return self.counts_in(conn, user_id, card_id)

    @staticmethod
    def grant_in(conn, user_id: int, card_id: str, rarity: str, quantity: int = 1) -> int:
        if rarity not in RARITIES or type(quantity) is not int or quantity <= 0:
            raise ValueError("invalid_card_quantity")
        card = conn.execute("SELECT rarity FROM cards WHERE card_id=?", (card_id,)).fetchone()
        if not card:
            raise ValueError("card_not_found")
        from systems.shared_foundation import economic_card_in
        if not economic_card_in(conn, card_id):
            raise ValueError("custom_assignment_not_implemented")
        conn.execute("""
            INSERT INTO player_card_stacks(user_id,card_id,rarity,quantity)
            VALUES(?,?,?,?)
            ON CONFLICT(user_id,card_id,rarity)
            DO UPDATE SET quantity=quantity+excluded.quantity
        """, (user_id, card_id, rarity, quantity))
        active = conn.execute(
            "SELECT 1 FROM player_cards WHERE user_id=? AND card_id=?", (user_id, card_id)
        ).fetchone()
        if not active:
            conn.execute(
                "INSERT INTO player_cards(user_id,card_id,obtained_at,rarity_override) VALUES(?,?,?,?)",
                (user_id, card_id, datetime.now(timezone.utc).isoformat(),
                 rarity if rarity != card[0] else None),
            )
        return CardInventorySystem.counts_in(conn, user_id, card_id)[rarity]

    @staticmethod
    def consume_in(conn, user_id: int, card_id: str, rarity: str, quantity: int = 1) -> bool:
        if rarity not in RARITIES or type(quantity) is not int or quantity <= 0:
            return False
        from systems.shared_foundation import economic_card_in
        if not economic_card_in(conn, card_id):
            return False
        row = conn.execute(
            "SELECT quantity FROM player_card_stacks WHERE user_id=? AND card_id=? AND rarity=?",
            (user_id, card_id, rarity),
        ).fetchone()
        if not row or int(row[0]) < quantity:
            return False
        if int(row[0]) == quantity:
            conn.execute(
                "DELETE FROM player_card_stacks WHERE user_id=? AND card_id=? AND rarity=?",
                (user_id, card_id, rarity),
            )
        else:
            conn.execute(
                "UPDATE player_card_stacks SET quantity=quantity-? WHERE user_id=? AND card_id=? AND rarity=?",
                (quantity, user_id, card_id, rarity),
            )
        return True

    @staticmethod
    def reconcile_active_in(conn, user_id: int, card_id: str) -> None:
        counts = CardInventorySystem.counts_in(conn, user_id, card_id)
        if not counts:
            conn.execute("DELETE FROM player_cards WHERE user_id=? AND card_id=?", (user_id, card_id))
            conn.execute("""UPDATE player_decks SET is_valid=0 WHERE player_id=?
                AND (card_id_1=? OR card_id_2=? OR card_id_3=?)""",
                (user_id, card_id, card_id, card_id),
            )
            return
        row = conn.execute(
            """SELECT COALESCE(pc.rarity_override,c.rarity)
               FROM player_cards pc JOIN cards c ON c.card_id=pc.card_id
               WHERE pc.user_id=? AND pc.card_id=?""",
            (user_id, card_id),
        ).fetchone()
        if row and row[0] in counts:
            return
        fallback = max(counts, key=lambda rarity: RANK[rarity])
        conn.execute(
            "UPDATE player_cards SET rarity_override=? WHERE user_id=? AND card_id=?",
            (fallback, user_id, card_id),
        )

    def activate(self, user_id: int, card_id: str, rarity: str) -> dict:
        if rarity not in RARITIES:
            return {"ok": False, "error_code": "invalid_rarity", "error": "فرم نامعتبر است"}
        with closing(sqlite3.connect(self.db.db_path, timeout=15)) as conn:
            with conn:
                conn.execute("BEGIN IMMEDIATE")
                from systems.card_upgrade_system import CardUpgradeSystem
                if CardUpgradeSystem(self.db)._active_match(conn, user_id):
                    return {"ok": False, "error_code": "active_match", "error": "تا پایان مسابقه فرم کارت را عوض نکن"}
                if self.counts_in(conn, user_id, card_id).get(rarity, 0) < 1:
                    return {"ok": False, "error_code": "form_not_owned", "error": "این فرم را نداری"}
                if not conn.execute(
                    "SELECT 1 FROM card_variants WHERE card_id=? AND rarity=?", (card_id, rarity)
                ).fetchone():
                    return {"ok": False, "error_code": "variant_unavailable", "error": "این فرم آماده نیست"}
                conn.execute(
                    "UPDATE player_cards SET rarity_override=? WHERE user_id=? AND card_id=?",
                    (rarity, user_id, card_id),
                )
        return {"ok": True, "card_id": card_id, "active_rarity": rarity}
