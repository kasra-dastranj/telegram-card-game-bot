import asyncio
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from bot.main import TelegramCardBot
from core.database import DatabaseManager
from core.game_logic import GameLogic
from core.models import Card, CardRarity
from systems.card_inventory_system import CardInventorySystem
from systems.player_rewards_system import PlayerRewardsSystem
from systems.progression_config import config_in, save_config_in
import web.miniapp_api as miniapp


def claim_db(tmp_path, v2, base, active):
    db = DatabaseManager(str(tmp_path / 'claim-form.db'))
    db.get_or_create_player(101)
    db.add_card(Card('tony', 'Tony Soprano', CardRarity(base), 75, 60, 88, 85, ['base-ability']))
    for rarity, stats, ability in [('normal',(20,30,40,50),'normal-ability'),
                                  ('epic',(55,65,75,85),'epic-ability'),
                                  ('legend',(75,60,88,85),'legend-ability')]:
        form = db.get_card_variant('tony', rarity)
        db.save_card_variant('tony', rarity, dict(form, power=stats[0],speed=stats[1],iq=stats[2],
            popularity=stats[3],abilities=[ability],image_path='assets/card_images/tony-'+rarity+'.webp'))
    with sqlite3.connect(db.db_path) as conn:
        conn.execute("UPDATE foundation_settings SET value_json=? WHERE key='progression_v2_enabled'", ('true' if v2 else 'false',))
        if v2:
            _, config = config_in(conn)
            config['claim']['daily_ticket_percent'] = 0
            save_config_in(conn, config, 'offline-test')
        if active:
            CardInventorySystem.grant_in(conn,101,'tony',active)
    return db


def invoke_claim(db, entry, monkeypatch):
    if entry == 'miniapp':
        monkeypatch.setattr(miniapp, 'db', db)
        monkeypatch.setitem(miniapp.app.config, 'TESTING', True)
        monkeypatch.setitem(miniapp.app.config, 'DEBUG', True)
        response = miniapp.app.test_client().post('/api/v1/claim', headers={'X-Debug-User-Id':'101'})
        assert response.status_code == 200, response.get_json()
        result = response.get_json()['data']['card']
        assert result['rarity'] == 'normal'
        assert (result['power'],result['speed'],result['iq'],result['popularity']) == (20,30,40,50)
        assert result['abilities'] == ['normal-ability'] and result['score'] == 140
        assert 'tony-normal.webp' in result['image_url']
    else:
        bot = TelegramCardBot.__new__(TelegramCardBot)
        bot.db, bot.game, bot.config = db, GameLogic(db), {}
        bot.is_user_in_channel = AsyncMock(return_value=True)
        monkeypatch.setattr('bot.card_reward_presentation.send_card_image_safely', AsyncMock(return_value=True))
        monkeypatch.setattr('bot.handlers.pvp.ensure_not_expired', lambda *args: True)
        message = SimpleNamespace(reply_text=AsyncMock())
        query = SimpleNamespace(from_user=SimpleNamespace(id=101),message=message,answer=AsyncMock())
        update = SimpleNamespace(effective_user=query.from_user,effective_message=message,callback_query=query)
        asyncio.run((bot.claim_command if entry=='command' else bot.daily_claim_handler)(update,SimpleNamespace()))
        raw_text = message.reply_text.await_args.args[0]
        assert '\u2068(Normal)\u2069' in raw_text
        text = raw_text.translate(str.maketrans('', '', '\u2066\u2068\u2069'))
        assert 'Tony Soprano** (Normal)' in text and '(Legend)' not in text and '(Epic)' not in text
        assert '💪 قدرت: 20' in text and '⚡ سرعت: 30' in text and '🧠 آی‌کیو: 40' in text
        assert '❤️ محبوبیت: 50' in text and 'مجموع: 140' in text and 'normal-ability' in text


@pytest.mark.parametrize('entry', ['command','button','miniapp'])
@pytest.mark.parametrize('base', ['normal','legend'])
@pytest.mark.parametrize('active', [None,'epic','legend'])
def test_daily_claim_shows_granted_normal_form_and_preserves_existing_upgrades(tmp_path, monkeypatch, entry, base, active):
    db = claim_db(tmp_path, True, base, active)
    cached_base = db.get_card_by_id('tony')
    invoke_claim(db, entry, monkeypatch)
    expected = {'normal':1, **({active:1} if active else {})}
    assert CardInventorySystem(db).counts(101,'tony') == expected
    assert db.get_card_by_id_for_player('tony',101).rarity.value == (active or 'normal')
    assert cached_base.rarity.value == base and cached_base.power == 75
    with sqlite3.connect(db.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM reward_ledger WHERE user_id=101 AND event_type='daily_claim'").fetchone()[0] == 1
        assert conn.execute('SELECT SUM(quantity) FROM player_ability_inventory WHERE user_id=101').fetchone()[0] == 1
    assert not PlayerRewardsSystem(db).claim_daily(101)['ok']
    assert CardInventorySystem(db).counts(101,'tony') == expected


@pytest.mark.parametrize('entry', ['command','button','miniapp'])
def test_legacy_daily_claim_also_uses_normal_variant_without_downgrading_owned_legend(tmp_path, monkeypatch, entry):
    db = claim_db(tmp_path, False, 'normal', 'legend')
    invoke_claim(db, entry, monkeypatch)
    assert CardInventorySystem(db).counts(101,'tony') == {'normal':1,'legend':1}
    assert db.get_card_by_id_for_player('tony',101).rarity == CardRarity.LEGEND


def test_daily_claim_without_a_normal_definition_does_not_grant_legend_or_spend_turn(tmp_path):
    db = claim_db(tmp_path, True, 'legend', None)
    with sqlite3.connect(db.db_path) as conn:
        conn.execute("DELETE FROM card_variants WHERE card_id='tony' AND rarity='normal'")
    result = PlayerRewardsSystem(db).claim_daily(101)
    assert not result['ok'] and result['error_code'] == 'empty_pool'
    assert CardInventorySystem(db).counts(101,'tony') == {}
    assert db.get_or_create_player(101).last_claim is None


@pytest.mark.parametrize('media', ['cache','file','missing','disabled'])
def test_claim_media_uses_normal_form_and_never_borrows_base_legend_image(tmp_path, media):
    from bot.utils import send_card_image_safely
    db = claim_db(tmp_path, True, 'legend', 'legend')
    db.set_card_variant_media_file_id('tony','legend','legend-sticker','sticker')
    form = db.get_card_variant('tony','normal')
    image = tmp_path / 'normal.webp'
    image.write_bytes(b'offline-test-only')
    db.save_card_variant('tony','normal',dict(form,image_path=str(image) if media=='file' else ''))
    if media in ('cache','disabled'):
        db.set_card_variant_media_file_id('tony','normal','normal-sticker','sticker')
    message = SimpleNamespace(reply_sticker=AsyncMock(),reply_photo=AsyncMock())
    config = {'image_settings':{'enable_images':media!='disabled','card_images_path':str(tmp_path)}}
    result = asyncio.run(send_card_image_safely(message,'Tony Soprano',config,
        card=db.get_card_by_id_for_rarity('tony','normal'),db=db))
    assert result == (media in ('cache','file'))
    if media=='cache':
        message.reply_sticker.assert_awaited_once_with('normal-sticker')
    elif media=='file':
        assert message.reply_sticker.await_args.args[0].name == str(image)
    else:
        message.reply_sticker.assert_not_awaited()
    message.reply_photo.assert_not_awaited()
