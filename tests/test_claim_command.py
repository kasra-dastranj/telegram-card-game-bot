import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from bot.handlers.basic import BasicHandlersMixin
from core.models import CardRarity


def _claim_update(user_id=1):
    message = SimpleNamespace(reply_text=AsyncMock())
    return (
        SimpleNamespace(
            effective_user=SimpleNamespace(id=user_id),
            effective_message=message,
        ),
        message,
    )


def test_claim_command_uses_same_daily_claim_flow_as_start_menu_button():
    handler = BasicHandlersMixin()
    handler.is_user_in_channel = AsyncMock(return_value=True)
    handler.config = {"image_settings": {"enable_images": True}}
    card = SimpleNamespace(
        name="Test Hero",
        rarity=CardRarity.NORMAL,
        dialogs=["Ready"],
        power=10,
        speed=20,
        iq=30,
        popularity=40,
        abilities=["Skip"],
        get_total_stats=Mock(return_value=100),
    )
    handler.game = SimpleNamespace(
        CLAIM_COOLDOWN_HOURS=24,
        claim_daily_card=Mock(return_value=(True, card, None)),
    )
    update, message = _claim_update()
    context = SimpleNamespace(bot=SimpleNamespace())

    with (
        patch(
            "bot.handlers.basic.send_card_image_safely",
            new=AsyncMock(return_value=True),
        ) as send_image,
        patch(
            "bot.handlers.basic.get_victory_dialog",
            return_value="Ready",
        ),
    ):
        asyncio.run(handler.claim_command(update, context))

    handler.game.claim_daily_card.assert_called_once_with(1)
    send_image.assert_awaited_once()
    reply = message.reply_text.await_args
    assert "کارت روزانه دریافت شد" in reply.args[0]
    assert "Test Hero" in reply.args[0]
    assert "Skip" in reply.args[0]
    assert reply.kwargs["parse_mode"] == "Markdown"


def test_claim_command_replies_with_cooldown_error_without_callback_query():
    handler = BasicHandlersMixin()
    handler.is_user_in_channel = AsyncMock(return_value=True)
    handler.game = SimpleNamespace(
        claim_daily_card=Mock(
            return_value=(False, None, "هنوز امکان دریافت کارت روزانه نیست")
        )
    )
    update, message = _claim_update()

    with patch(
        "bot.handlers.basic.send_card_image_safely",
        new=AsyncMock(),
    ) as send_image:
        asyncio.run(
            handler.claim_command(
                update,
                SimpleNamespace(bot=SimpleNamespace()),
            )
        )

    send_image.assert_not_awaited()
    reply = message.reply_text.await_args
    assert "خطا در دریافت کارت" in reply.args[0]
    assert "هنوز امکان دریافت کارت روزانه نیست" in reply.args[0]
