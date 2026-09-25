"""Persistent two-player, three-round Mini App matches."""

from __future__ import annotations

import json
import random
from contextlib import closing
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from systems.battle_system_3rounds import ARENAS


MODE = "mini_three_round"
STATS = ("power", "speed", "iq", "popularity")
CHOICE_SECONDS = 60


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat()


class MiniThreeRoundSystem:
    def __init__(self, db, modes, arena_registry, battle_system):
        self.db = db
        self.modes = modes
        self.arena_registry = arena_registry
        self.battle_system = battle_system

    def _arena(self) -> Dict[str, Any]:
        selected = self.arena_registry.select_for_match("three_round", "miniapp")
        if selected:
            return self.arena_registry.snapshot_for_match(
                selected["arena_id"], "three_round", "miniapp", selected["version"]
            )
        arena_id = random.choice(list(ARENAS))
        return {"arena_id": arena_id, "version": None, "mode": "three_round", **ARENAS[arena_id]}

    def start(self, request_id: str) -> Dict[str, Any]:
        with closing(self.modes._connect()) as conn:
            with conn:
                conn.execute("BEGIN IMMEDIATE")
                request = conn.execute(
                    "SELECT * FROM game_requests WHERE request_id=?", (request_id,)
                ).fetchone()
                if not request or request["mode"] != MODE or request["status"] not in ("accepted", "active"):
                    raise ValueError("match_not_ready")
                row = conn.execute(
                    "SELECT state_json FROM game_match_states WHERE request_id=?", (request_id,)
                ).fetchone()
                if row:
                    return json.loads(row[0])
                players = [request["creator_id"], request["opponent_id"]]
                if not all(players) or players[0] == players[1]:
                    raise ValueError("invalid_players")
                state = {
                    "mode": MODE, "players": players, "phase": "card_selection",
                    "round": 1, "cards": {}, "stat_choices": {},
                    "used_stats": {str(uid): [] for uid in players},
                    "current_stats": {}, "rounds_won": {str(uid): 0 for uid in players},
                    "history": [], "arena": self._arena(),
                    "deadline": _iso(_now() + timedelta(seconds=CHOICE_SECONDS)),
                }
                self.modes._save_state(conn, request_id, state)
                conn.execute(
                    "UPDATE game_requests SET status='active', updated_at=? WHERE request_id=?",
                    (_iso(_now()), request_id),
                )
                return state

    @staticmethod
    def _check_choice(state: Dict[str, Any], user_id: int, phase: str) -> str:
        if state.get("phase") != phase or user_id not in state.get("players", []):
            raise ValueError("invalid_phase_or_player")
        if datetime.fromisoformat(state["deadline"]) <= _now():
            raise ValueError("deadline_passed")
        return str(user_id)

    def choose_card(self, request_id: str, user_id: int, card_id: str) -> Dict[str, Any]:
        with closing(self.modes._connect()) as conn:
            with conn:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    "SELECT state_json FROM game_match_states WHERE request_id=?", (request_id,)
                ).fetchone()
                state = json.loads(row[0]) if row else None
                if not state:
                    raise ValueError("match_not_ready")
                key = self._check_choice(state, user_id, "card_selection")
                if key in state["cards"]:
                    raise ValueError("choice_locked")
                card = self.db.get_card_by_id_for_player(card_id, user_id)
                if not card:
                    raise ValueError("card_not_owned")
                state["cards"][key] = card_id
                state["current_stats"][key] = {stat: int(getattr(card, stat)) for stat in STATS}
                if len(state["cards"]) == 2:
                    state["phase"] = "stat_selection"
                    state["deadline"] = _iso(_now() + timedelta(seconds=CHOICE_SECONDS))
                self.modes._save_state(conn, request_id, state)
                return state

    def _complete(self, conn, request_id: str, state: Dict[str, Any], *, winner_id=None,
                  forfeit=False, reason=None) -> None:
        report = {
            "request_id": request_id, "mode": MODE, "winner_id": winner_id,
            "is_tie": winner_id is None, "forfeit": forfeit, "reason": reason,
            "rounds_won": state["rounds_won"], "rounds": state["history"],
            "completed_at": _iso(_now()),
        }
        state.update({"phase": "completed", "deadline": None, "report": report})
        self.modes._save_state(conn, request_id, state)
        conn.execute(
            "UPDATE game_requests SET status='completed', updated_at=? WHERE request_id=?",
            (_iso(_now()), request_id),
        )
        conn.execute(
            "INSERT OR REPLACE INTO game_match_reports(request_id,report_json,created_at) VALUES (?,?,?)",
            (request_id, json.dumps(report, ensure_ascii=False), _iso(_now())),
        )

    def choose_stat(self, request_id: str, user_id: int, stat: str) -> Dict[str, Any]:
        with closing(self.modes._connect()) as conn:
            with conn:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    "SELECT state_json FROM game_match_states WHERE request_id=?", (request_id,)
                ).fetchone()
                state = json.loads(row[0]) if row else None
                if not state:
                    raise ValueError("match_not_ready")
                key = self._check_choice(state, user_id, "stat_selection")
                if key in state["stat_choices"]:
                    raise ValueError("choice_locked")
                if stat not in STATS or stat in state["used_stats"][key]:
                    raise ValueError("stat_not_allowed")
                state["stat_choices"][key] = stat
                if len(state["stat_choices"]) < 2:
                    self.modes._save_state(conn, request_id, state)
                    return state

                first, second = state["players"]
                entries = {}
                arena = state["arena"]
                arena_id = arena["arena_id"]
                for player_id in (first, second):
                    player_key = str(player_id)
                    chosen_stat = state["stat_choices"][player_key]
                    card = self.db.get_card_by_id_for_player(state["cards"][player_key], player_id)
                    if not card:
                        raise ValueError("card_not_owned")
                    base = state["current_stats"][player_key][chosen_stat]
                    boost = self.battle_system.calculate_boost(card, arena_id, chosen_stat, arena)
                    entries[player_key] = {
                        "stat": chosen_stat, "base": base, "boost": boost,
                        "total": base + boost,
                    }
                first_total = entries[str(first)]["total"]
                second_total = entries[str(second)]["total"]
                winner_id = first if first_total > second_total else second if second_total > first_total else None
                if winner_id is not None:
                    loser_id = second if winner_id == first else first
                    loser_key = str(loser_id)
                    loser_stat = state["stat_choices"][loser_key]
                    reduction = 2 if abs(first_total - second_total) >= 5 else 1
                    state["current_stats"][loser_key][loser_stat] = max(
                        0, state["current_stats"][loser_key][loser_stat] - reduction
                    )
                    state["rounds_won"][str(winner_id)] += 1
                state["history"].append({
                    "round": state["round"], "winner_id": winner_id, "values": entries,
                })
                for player_id in (first, second):
                    player_key = str(player_id)
                    state["used_stats"][player_key].append(state["stat_choices"][player_key])
                if max(state["rounds_won"].values()) >= 2 or state["round"] == 3:
                    first_wins = state["rounds_won"][str(first)]
                    second_wins = state["rounds_won"][str(second)]
                    overall = first if first_wins > second_wins else second if second_wins > first_wins else None
                    self._complete(conn, request_id, state, winner_id=overall)
                else:
                    state["round"] += 1
                    state["stat_choices"] = {}
                    state["deadline"] = _iso(_now() + timedelta(seconds=CHOICE_SECONDS))
                    self.modes._save_state(conn, request_id, state)
                return state

    def settle_deadline(self, request_id: str) -> Optional[Dict[str, Any]]:
        with closing(self.modes._connect()) as conn:
            with conn:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    "SELECT state_json FROM game_match_states WHERE request_id=?", (request_id,)
                ).fetchone()
                state = json.loads(row[0]) if row else None
                if not state or state.get("phase") == "completed" or not state.get("deadline"):
                    return state
                if datetime.fromisoformat(state["deadline"]) > _now():
                    return state
                choices = state["cards"] if state["phase"] == "card_selection" else state["stat_choices"]
                winners = [uid for uid in state["players"] if str(uid) in choices]
                winner_id = winners[0] if len(winners) == 1 else None
                self._complete(
                    conn, request_id, state, winner_id=winner_id,
                    forfeit=True, reason=f"{state['phase']}_timeout",
                )
                return state

    def snapshot(self, game_request: dict, user_id: int) -> Dict[str, Any]:
        request_id = game_request["request_id"]
        if game_request["status"] in ("accepted", "active"):
            state = self.start(request_id) if game_request["status"] == "accepted" else None
            state = self.settle_deadline(request_id) or state
            game_request = self.modes.get_request(request_id) or game_request
        else:
            state = self.modes.get_state(request_id)
        response = {
            "request_id": request_id, "user_id": user_id,
            "status": game_request["status"], "source": game_request["source"],
            "expires_at": game_request["expires_at"],
            "opponent_id": game_request["opponent_id"] if game_request["creator_id"] == user_id else game_request["creator_id"],
        }
        if not state:
            return response
        mine = str(user_id)
        opponent = str(response["opponent_id"])
        show_opponent = len(state["cards"]) == 2 or state["phase"] == "completed"
        own_card = self.db.get_card_by_id_for_player(state["cards"][mine], user_id) if mine in state["cards"] else None
        boosts = ({stat: self.battle_system.calculate_boost(
            own_card, state["arena"]["arena_id"], stat, state["arena"]
        ) for stat in STATS} if own_card else {})
        response.update({
            "phase": state["phase"], "round": state["round"],
            "deadline": state["deadline"], "arena": state["arena"],
            "my_card_id": state["cards"].get(mine),
            "opponent_card_id": state["cards"].get(opponent) if show_opponent else None,
            "my_card_locked": mine in state["cards"],
            "opponent_card_selected": opponent in state["cards"],
            "my_stat_locked": mine in state["stat_choices"],
            "opponent_stat_selected": opponent in state["stat_choices"],
            "my_values": state["current_stats"].get(mine),
            "my_boosts": boosts,
            "available_stats": [stat for stat in STATS if stat not in state["used_stats"][mine]],
            "rounds_won": state["rounds_won"],
            "last_round": state["history"][-1] if state["history"] else None,
            "report": state.get("report") if state["phase"] == "completed" else None,
        })
        return response
