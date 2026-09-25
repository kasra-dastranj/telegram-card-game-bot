"""Exercise collection buttons with real, immutable Telegram update objects."""
import asyncio
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from telegram import CallbackQuery, Chat, Message, Update, User, InlineKeyboardMarkup

from bot.handlers.basic import BasicHandlersMixin
from bot.handlers.shop import ShopHandlersMixin
from bot.handlers.pvp import PvPHandlersMixin
from core.database import DatabaseManager
from core.models import Card, CardRarity


class CollectionBot(BasicHandlersMixin, ShopHandlersMixin, PvPHandlersMixin):
    pass


@pytest.fixture
def collection(tmp_path):
    handler = CollectionBot()
    handler.db = DatabaseManager(str(tmp_path / "collection.db"))
    handler.db.get_or_create_player(101)
    for card_id in ("hero", "hero_with_underscores"):
        assert handler.db.add_card(Card(card_id, f"{card_id} Hero <&> _*", CardRarity.NORMAL,
                                 10, 20, 30, 40, [], biography="A <hero> & a_friend"))
        assert handler.db.add_card_to_player(101, card_id)
    handler.skins = SimpleNamespace(get_card_skins=Mock(return_value=[]))
    handler.missions = SimpleNamespace(get_player_mission_progress=Mock(return_value=None))
    handler.is_user_in_channel = AsyncMock(return_value=True)
    handler._is_command_allowed_in_chat = Mock(return_value=True)
    return handler


def event(data=None, age_seconds=0):
    bot = SimpleNamespace(answer_callback_query=AsyncMock(), edit_message_text=AsyncMock(), send_message=AsyncMock())
    user = User(101, "Tester", False)
    message = Message(1, datetime.now(timezone.utc) - timedelta(seconds=age_seconds), Chat(101, "private"), from_user=user, text="menu")
    message.set_bot(bot)
    if data is None:
        return Update(1, message=message), bot
    query = CallbackQuery("query", user, "chat", message=message, data=data)
    query.set_bot(bot)
    return Update(1, callback_query=query), bot


def text_of(bot):
    return bot.edit_message_text.await_args.kwargs["text"]


@pytest.mark.parametrize("command", [False, True])
def test_collection_entry_uses_valid_keyboard(collection, command):
    update, bot = event(None if command else "my_cards")
    handler = collection.cards_command if command else collection.my_cards_handler
    asyncio.run(handler(update, SimpleNamespace()))
    call = bot.send_message.await_args if command else bot.edit_message_text.await_args
    keyboard = call.kwargs["reply_markup"]
    assert isinstance(keyboard, InlineKeyboardMarkup)
    assert any(b.callback_data == "mycards_normal_1" for row in keyboard.inline_keyboard for b in row)


@pytest.mark.parametrize("card_id", ["hero", "hero_with_underscores"])
def test_card_detail_opens_and_escapes_content(collection, card_id):
    update, bot = event(f"cardinfo_{card_id}")
    asyncio.run(collection.cardinfo_handler(update, SimpleNamespace()))
    assert bot.edit_message_text.await_count == 1
    assert "&lt;&amp;&gt;" in text_of(bot)
    assert bot.edit_message_text.await_args.kwargs["parse_mode"] == "HTML"


def test_old_collection_menu_and_navigation_still_work(collection):
    for data, callback in (("my_cards", collection.my_cards_handler),
                           ("my_cards_nav_normal_1", collection.my_cards_navigation_handler)):
        update, bot = event(data, age_seconds=600)
        asyncio.run(callback(update, SimpleNamespace()))
        assert bot.edit_message_text.await_count == 1


def test_collection_navigation_reaches_every_card_and_returns(collection):
    for index in range(9):
        card_id = f"page_card_{index}"
        assert collection.db.add_card(Card(card_id, card_id, CardRarity.NORMAL, 1, 2, 3, 4, []))
        assert collection.db.add_card_to_player(101, card_id)
    seen = set()
    for page in (1, 2):
        update, bot = event(f"mycards_normal_{page}")
        asyncio.run(collection.mycards_navigation_handler(update, SimpleNamespace()))
        markup = bot.edit_message_text.await_args.kwargs["reply_markup"]
        for row in markup.inline_keyboard:
            for button in row:
                if button.callback_data.startswith("cardinfo_"):
                    seen.add(button.callback_data.removeprefix("cardinfo_"))
    assert seen == {card.card_id for card in collection.db.get_player_cards(101)}
    update, bot = event("mycards_normal_999")
    asyncio.run(collection.mycards_navigation_handler(update, SimpleNamespace()))
    assert "2/2" in text_of(bot)
    update, bot = event("mycards_menu_1")
    asyncio.run(collection.mycards_navigation_handler(update, SimpleNamespace()))
    assert any(b.callback_data == "back_to_main" for row in bot.edit_message_text.await_args.kwargs["reply_markup"].inline_keyboard for b in row)


def test_rare_cards_are_accessible(collection):
    assert collection.db.add_card(Card("rare", "Rare", CardRarity.RARE, 1, 2, 3, 4, []))
    collection.db.add_card_to_player(101, "rare")
    markup = collection._create_mycards_keyboard(101)
    assert any(b.callback_data == "mycards_rare_1" for row in markup.inline_keyboard for b in row)
    update, bot = event("mycards_rare_1")
    asyncio.run(collection.mycards_navigation_handler(update, SimpleNamespace()))
    assert "cardinfo_rare" in str(bot.edit_message_text.await_args.kwargs["reply_markup"])


@pytest.fixture
def skin_shop(collection):
    from systems.skins_system import SkinsSystem
    collection.skins = SkinsSystem(collection.db)
    player = collection.db.get_or_create_player(101)
    player.coins = 200
    collection.db.update_player(player)
    assert collection.skins.create_skin("blue_skin", "hero_with_underscores", "Blue <&>", "normal", "", price=50)
    return collection


@pytest.mark.parametrize("legacy", [False, True])
def test_skin_purchase_activation_deactivation_end_to_end(skin_shop, legacy):
    handler = skin_shop
    suffix = "hero_with_underscores_blue_skin" if legacy else "blue_skin"
    update, bot = event(f"skin_buy_{suffix}")
    asyncio.run(handler.skin_buy_handler(update, SimpleNamespace()))
    assert handler.skins.has_skin(101, "blue_skin")
    assert handler.db.get_or_create_player(101).coins == 150
    update, bot = event(f"skin_activate_{suffix}")
    asyncio.run(handler.skin_activate_handler(update, SimpleNamespace()))
    assert handler.skins.get_active_skin(101, "hero_with_underscores") == "blue_skin"
    assert "&lt;&amp;&gt;" in text_of(bot)
    update, bot = event("skin_deactivate_hero_with_underscores")
    asyncio.run(handler.skin_deactivate_handler(update, SimpleNamespace()))
    assert handler.skins.get_active_skin(101, "hero_with_underscores") is None


def test_free_event_skin_can_be_claimed(skin_shop):
    assert skin_shop.skins.create_skin("free", "hero", "Free", "event", "")
    assert skin_shop.skins.unlock_skin(101, "free")["success"]
    assert skin_shop.db.get_or_create_player(101).coins == 200


def test_negative_skin_price_cannot_credit_coins(skin_shop):
    import sqlite3
    with sqlite3.connect(skin_shop.db.db_path) as conn:
        conn.execute("UPDATE skins SET price=-50 WHERE skin_id='blue_skin'")
    assert not skin_shop.skins.unlock_skin(101, "blue_skin")["success"]
    assert skin_shop.db.get_or_create_player(101).coins == 200
    assert not skin_shop.skins.has_skin(101, "blue_skin")


def test_legacy_card_detail_preserves_id_and_upgrade(collection, monkeypatch):
    monkeypatch.setattr("bot.handlers.basic.send_card_image_safely", AsyncMock())
    collection.config = SimpleNamespace()
    collection.db.set_player_card_rarity_override(101, "hero_with_underscores", "epic")
    update, bot = event("card_view_hero_with_underscores", age_seconds=600)
    asyncio.run(collection.card_view_handler(update, SimpleNamespace()))
    assert "Epic" in text_of(bot)
    assert "hero_with_underscores" in text_of(bot)
    assert "&lt;&amp;&gt;" in text_of(bot)
    assert bot.edit_message_text.await_args.kwargs["parse_mode"] == "HTML"


def test_mission_reward_preserves_card_id_and_escapes_name(collection):
    collection.missions.claim_mission_reward = Mock(return_value={"success": True, "card_name": "Hero <&>"})
    update, bot = event("mission_claim_hero_with_underscores")
    asyncio.run(collection.mission_claim_handler(update, SimpleNamespace()))
    collection.missions.claim_mission_reward.assert_called_once_with(101, "hero_with_underscores")
    assert "&lt;&amp;&gt;" in text_of(bot)
    assert bot.edit_message_text.await_args.kwargs["parse_mode"] == "HTML"


def test_skin_cannot_be_activated_on_another_card(skin_shop):
    assert skin_shop.skins.unlock_skin(101, "blue_skin")["success"]
    assert not skin_shop.skins.set_active_skin(101, "hero", "blue_skin")["success"]
    assert skin_shop.skins.get_active_skin(101, "hero") is None


def test_failed_skin_inventory_write_keeps_coins(skin_shop):
    import sqlite3
    with sqlite3.connect(skin_shop.db.db_path) as conn:
        conn.execute("CREATE TRIGGER fail_skin BEFORE INSERT ON player_skins BEGIN SELECT RAISE(ABORT, 'injected failure'); END")
    assert not skin_shop.skins.unlock_skin(101, "blue_skin")["success"]
    assert skin_shop.db.get_or_create_player(101).coins == 200


def test_concurrent_skin_purchase_only_charges_once(skin_shop):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    gate = Barrier(4)

    def purchase(_):
        gate.wait(timeout=10)
        return skin_shop.skins.unlock_skin(101, "blue_skin")["success"]

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(purchase, range(4)))
    assert sum(results) == 1
    assert skin_shop.db.get_or_create_player(101).coins == 150


@pytest.mark.parametrize("card_id", ["hero", "hero_with_underscores"])
def test_favorite_toggles_and_refreshes_same_card(collection, card_id):
    update, bot = event(f"toggle_fav_{card_id}")
    asyncio.run(collection.toggle_favorite_handler(update, SimpleNamespace()))
    assert bot.answer_callback_query.await_count == 1
    assert "حذف از علاقه" in str(bot.edit_message_text.await_args.kwargs["reply_markup"])
    assert update.callback_query.data == f"toggle_fav_{card_id}"
    asyncio.run(collection.toggle_favorite_handler(update, SimpleNamespace()))
    assert "افزودن به علاقه" in str(bot.edit_message_text.await_args.kwargs["reply_markup"])


def test_upgraded_card_counts_and_favorites_match_collection(collection):
    db = collection.db
    db.set_player_card_rarity_override(101, "hero", "epic")
    db.toggle_favorite_card(101, "hero")
    counts = db.get_rarity_counts(101)
    assert counts["epic"] == 1 and counts["normal"] == 1
    favorites, count = db.get_favorite_cards(101)
    assert count == 1
    assert favorites[0].rarity == CardRarity.EPIC
    assert favorites[0].power == db.get_card_by_id_for_player("hero", 101).power


def test_empty_category_is_not_page_one_of_zero(collection):
    update, bot = event("mycards_legend_1")
    asyncio.run(collection.mycards_navigation_handler(update, SimpleNamespace()))
    assert "1/0" not in text_of(bot)
    assert "کارتی" in text_of(bot)


@pytest.mark.parametrize("action", ["activate", "deactivate"])
def test_skin_buttons_refresh_without_mutating_callback(collection, action):
    skin = {"skin_id": "blue_skin", "card_id": "hero", "name": "Blue", "price": 10, "skin_type": "normal"}
    collection.skins = SimpleNamespace(
        get_skin=Mock(side_effect=lambda key: skin if key == "blue_skin" else None),
        get_card_skins=Mock(return_value=[skin]), get_player_skins=Mock(return_value=[skin]),
        get_active_skin=Mock(return_value=None), set_active_skin=Mock(return_value={"success": True}),
    )
    data = "skin_activate_hero_blue_skin" if action == "activate" else "skin_deactivate_hero"
    update, bot = event(data)
    handler = collection.skin_activate_handler if action == "activate" else collection.skin_deactivate_handler
    asyncio.run(handler(update, SimpleNamespace()))
    assert update.callback_query.data == data
    assert bot.edit_message_text.await_count == 1
