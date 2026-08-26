"""Read models for the TelBattle Mini App player hub."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from core.game_logic import GameLogic
from systems.claim_system import ClaimSystem
from systems.phase2_systems import LevelSystem


class PlayerHubSystem:
    """Collect player-management data without coupling it to Flask or Telegram."""

    RARITY_ORDER = {"normal": 0, "rare": 1, "epic": 2, "legend": 3}
    SORT_KEYS = {"name", "score", "power", "speed", "iq", "popularity", "rarity"}

    def __init__(self, db, config: Optional[dict] = None):
        self.db = db
        self.game = GameLogic(db, config)
        self.claims = ClaimSystem(db)
        self.levels = LevelSystem()

    @staticmethod
    def _rarity(card) -> str:
        rarity = getattr(card, "rarity", "normal")
        return rarity.value if hasattr(rarity, "value") else str(rarity)

    @staticmethod
    def _score(card) -> int:
        return int(card.power + card.speed + card.iq + card.popularity)

    def _missions_ready(self, user_id: int) -> int:
        try:
            conn = sqlite3.connect(self.db.db_path)
            row = conn.execute(
                """
                SELECT COUNT(*)
                FROM player_card_missions
                WHERE user_id = ? AND completed = 1
                  AND COALESCE(reward_claimed, 0) = 0
                """,
                (user_id,),
            ).fetchone()
            conn.close()
            return int(row[0]) if row else 0
        except sqlite3.Error:
            return 0

    def _claim_status(self, player) -> Dict:
        can_claim, message = self.claims.can_claim_today(player.user_id)
        remaining = 0
        if not can_claim and player.last_claim:
            now = datetime.now()
            midnight = datetime.combine(now.date() + timedelta(days=1), datetime.min.time())
            remaining = max(0, int((midnight - now).total_seconds()))
        return {
            "can_claim": can_claim,
            "remaining_seconds": remaining,
            "message": message,
        }

    def get_overview(self, user_id: int) -> Dict:
        player = self.game.check_and_reset_hearts(self.db.get_or_create_player(user_id))
        progression = self.db.get_player_progression_full(user_id) or {}
        fight_stats = self.db.get_fight_stats(user_id) or {}
        cards = self.db.get_player_cards(user_id)
        decks = self.db.get_player_decks(user_id)
        heart_remaining = self.game.get_heart_reset_time_remaining(player)
        total_xp = int(progression.get("total_xp", 0))
        calculated_level, current_xp, xp_to_next = self.levels.get_xp_progress(total_xp)
        level = int(progression.get("level", calculated_level) or calculated_level)
        best_card = max(cards, key=self._score) if cards else None

        rarity_counts = {key: 0 for key in self.RARITY_ORDER}
        for card in cards:
            rarity = self._rarity(card)
            rarity_counts[rarity] = rarity_counts.get(rarity, 0) + 1

        return {
            "user_id": user_id,
            "first_name": player.first_name,
            "username": player.username or "",
            "hearts": player.hearts,
            "max_hearts": player.max_hearts,
            "heart_reset_seconds": max(0, int(heart_remaining.total_seconds())) if heart_remaining else 0,
            "coins": player.coins,
            "total_score": player.total_score,
            "level": level,
            "current_xp": current_xp,
            "xp_to_next_level": xp_to_next,
            "current_tier": progression.get("current_tier", "Bronze"),
            "tier_points": int(progression.get("tier_points", 0)),
            "stats": fight_stats,
            "best_card_id": best_card.card_id if best_card else None,
            "claim": self._claim_status(player),
            "counts": {
                "cards": len(cards),
                "decks": len(decks),
                "missions_ready": self._missions_ready(user_id),
                "rarities": rarity_counts,
            },
        }

    def get_cards(
        self,
        user_id: int,
        *,
        page: int = 1,
        limit: int = 20,
        rarity: str = "all",
        sort: str = "rarity",
        query: str = "",
    ) -> Tuple[List, int, int, int]:
        page = max(1, int(page))
        limit = max(1, min(int(limit), 60))
        sort = sort if sort in self.SORT_KEYS else "rarity"
        cards = list(self.db.get_player_cards(user_id))

        if rarity != "all":
            cards = [card for card in cards if self._rarity(card) == rarity]

        needle = query.strip().casefold()
        if needle:
            cards = [
                card for card in cards
                if needle in card.name.casefold()
                or needle in (getattr(card, "card_type", "") or "").casefold()
                or needle in (getattr(card, "biography", "") or "").casefold()
            ]

        if sort == "name":
            cards.sort(key=lambda card: card.name.casefold())
        elif sort == "rarity":
            cards.sort(
                key=lambda card: (
                    self.RARITY_ORDER.get(self._rarity(card), -1),
                    self._score(card),
                ),
                reverse=True,
            )
        else:
            cards.sort(
                key=lambda card: self._score(card) if sort == "score" else int(getattr(card, sort, 0)),
                reverse=True,
            )

        total = len(cards)
        start = (page - 1) * limit
        return cards[start:start + limit], total, page, limit

    def get_owned_card(self, user_id: int, card_id: str):
        return self.db.get_card_by_id_for_player(card_id, user_id)
