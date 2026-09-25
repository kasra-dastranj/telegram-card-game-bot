"""Card abilities in the Telegram three-round fallback flow."""

import asyncio
import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from bot.handlers.battle import BattleHandlersMixin
from core.database import DatabaseManager
from core.models import Card, CardRarity


FIGHT_ID = "ab12cd34"


@pytest.fixture()
def ability_battle(tmp_path):
    db = DatabaseManager(str(tmp_path / "r3-abilities.db"))
    for user_id, card_id, card_type in ((101, "speed-card", "SPEED_TYPE"),
                                        (202, "power-card", "POWER_TYPE")):
        db.get_or_create_player(user_id)
        card = Card(card_id=card_id, name=card_id, rarity=CardRarity.NORMAL,
                    power=80, speed=70, iq=60, popularity=50,
                    abilities=[], card_type=card_type)
        assert db.add_card(card)
        assert db.add_card_to_player(user_id, card_id)
    with sqlite3.connect(db.db_path) as conn:
        conn.execute('''
            INSERT INTO battle_states (
                fight_id,challenger_id,opponent_id,challenger_card_id,opponent_card_id,
                arena,current_round,challenger_used_stats,opponent_used_stats,
                challenger_current_stats,opponent_current_stats,status,created_at
            ) VALUES (?,?,?,?,?,?,1,'[]','[]',?,?,'round_1',CURRENT_TIMESTAMP)
        ''', (FIGHT_ID, 101, 202, "speed-card", "power-card", "speed_track",
              json.dumps({"power": 80, "speed": 70, "iq": 60, "popularity": 50}),
              json.dumps({"power": 83, "speed": 73, "iq": 63, "popularity": 53})))
    handler = BattleHandlersMixin()
    handler.db = db
    return handler, db


def test_peek_reveals_current_opponent_stat_and_keeps_stat_buttons(ability_battle, monkeypatch):
    handler, db = ability_battle
    monkeypatch.setattr("bot.handlers.battle.random.choice", lambda values: "speed")
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚡ سرعت", callback_data=f"r3_stat_{FIGHT_ID}_speed")],
        [InlineKeyboardButton("👁️ شنود", callback_data=f"r3_ability_{FIGHT_ID}_peek")],
    ])
    query = SimpleNamespace(
        data=f"r3_ability_{FIGHT_ID}_peek", from_user=SimpleNamespace(id=101),
        message=SimpleNamespace(reply_markup=markup), answer=AsyncMock(),
        edit_message_text=AsyncMock(),
    )
    context = SimpleNamespace(bot_data={}, bot=SimpleNamespace(send_message=AsyncMock()))
    asyncio.run(handler.r3_ability_handler(SimpleNamespace(callback_query=query), context))
    args = query.edit_message_text.call_args
    assert "سرعت حریف: 73" in args.args[0]
    buttons = args.kwargs["reply_markup"].inline_keyboard
    assert len(buttons) == 1
    assert buttons[0][0].callback_data == f"r3_stat_{FIGHT_ID}_speed"
    assert handler._r3_pending_abilities(FIGHT_ID, 1) == ("peek", None)
    assert handler._r3_pending_abilities(FIGHT_ID, 2) == (None, None)
    with sqlite3.connect(db.db_path) as conn:
        assert conn.execute("SELECT challenger_ability_used FROM battle_states WHERE fight_id=?", (FIGHT_ID,)).fetchone()[0] == 1


def test_card_ability_cannot_be_forged_or_reused(ability_battle):
    handler, _ = ability_battle
    with pytest.raises(ValueError, match="متعلق به کارت"):
        handler._activate_r3_ability(FIGHT_ID, 101, "boost_15", {})
    handler._activate_r3_ability(FIGHT_ID, 101, "peek", {})
    with pytest.raises(ValueError, match="قبلاً مصرف"):
        handler._activate_r3_ability(FIGHT_ID, 101, "peek", {})


def test_completed_fight_rejects_old_ability_button(ability_battle):
    handler, db = ability_battle
    with sqlite3.connect(db.db_path) as conn:
        conn.execute("UPDATE battle_states SET status='completed' WHERE fight_id=?", (FIGHT_ID,))
    with pytest.raises(ValueError, match="دیگر فعال نیست"):
        handler._activate_r3_ability(FIGHT_ID, 101, "peek", {})
