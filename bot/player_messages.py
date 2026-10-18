"""Player-facing economy wording. Error codes and transaction rules stay intact."""
from core.display_text import isolate

MESSAGES = {
    'insufficient_copies': 'نسخه‌های این فرم کارت کافی نیست؛ موجودی کارتت رو ببین.',
    'insufficient_upgrade_card': 'کارت ارتقا کم داری؛ می‌تونی از فروشگاه بگیری.',
    'insufficient_silver_ticket': 'سیلور تیکت کافی نداری؛ موجودیت رو ببین.',
    'insufficient_free_silver_claim': 'سیلور کلیم نداری؛ اول یکی بساز.',
    'insufficient_coins': 'سکه‌هات کافی نیست؛ قیمت و موجودیت رو ببین.',
    'insufficient_coins_or_player_missing': 'خرید انجام نشد؛ فروشگاه رو دوباره باز کن و موجودیت رو ببین.',
    'price_changed': 'قیمت یا شرایط عوض شده؛ دوباره انتخاب کن تا مقدار تازه رو ببینی.',
    'quote_expired': 'وقت تأیید این قیمت تموم شد؛ دوباره کالا رو انتخاب کن.',
    'quote_not_found': 'این خرید برای حسابت پیدا نشد؛ از فروشگاه ادامه بده.',
    'stock_empty': 'موجودی این کالا تموم شده؛ یه کالای دیگه انتخاب کن.',
    'active_match': 'اول بازیت رو تموم کن؛ بعد کارتت رو تغییر بده.',
    'variant_unavailable': 'فرم بعدی این کارت هنوز آماده نیست؛ یه کارت دیگه انتخاب کن.',
    'legend_recipe_unset': 'روش ارتقای Legend این شخصیت هنوز تنظیم نشده؛ فعلاً یه کارت دیگه انتخاب کن.',
    'card_not_owned': 'این کارت توی موجودیت نیست؛ فهرست کارت‌هات رو دوباره باز کن.',
    'card_ineligible': 'این کارت برای این کار مجاز نیست؛ یه کارت دیگه انتخاب کن.',
    'rarity_not_sellable': 'این فرم کارت قابل فروش نیست؛ یه فرم دیگه انتخاب کن.',
    'progression_v2_disabled': 'این بخش هنوز فعال نیست؛ از منوی بازی ادامه بده.',
    'heart_cap': 'ظرفیت قلب‌هات به سقف رسیده.',
    'hearts_full': 'قلب‌هات پره؛ الان نیازی به پرکردن نیست.',
    'item_unavailable': 'این کالا فعلاً در دسترس نیست؛ یه کالای دیگه انتخاب کن.',
    'empty_pool': 'فعلاً کارتی برای دریافت آماده نیست؛ بعداً دوباره امتحان کن.',
    'already_claimed': 'پاداش این نوبت رو قبلاً گرفتی؛ نوبت بعد دوباره بیا.',
    'not_ready': 'این پاداش هنوز آماده نیست؛ پیشرفت مأموریت رو ببین.',
    'mission_incomplete_or_ineligible': 'شرایط این مأموریت هنوز کامل نشده؛ پیشرفتش رو ببین.',
    'mission_not_found': 'این مأموریت پیدا نشد؛ فهرست مأموریت‌هات رو دوباره باز کن.',
    'already_owned': 'این اسکین رو قبلاً گرفتی؛ یه اسکین دیگه انتخاب کن.',
    'invalid_request_key': 'این درخواست معتبر نیست؛ منوی این بخش رو دوباره باز کن.',
}


def error_text(result, inventory=None):
    code = result.get('error_code')
    if code == 'insufficient_silver_ticket' and inventory:
        required = inventory.get('silver_claim_tickets')
        owned = inventory.get('items', {}).get('silver_ticket', 0)
        if type(required) is int and type(owned) is int and required > owned:
            return 'سیلور تیکت‌هات کافی نیست؛ هنوز ' + isolate(required - owned) + ' تا دیگه لازم داری.'
    for error_code, need_key, have_key, label in [
        ('insufficient_copies', 'required', 'owned', 'نسخه از همین فرم کارت'),
        ('insufficient_upgrade_card', 'upgrade_cards_required', 'upgrade_cards_owned', 'کارت ارتقا'),
    ]:
        if code == error_code:
            required, owned = result.get(need_key), result.get(have_key)
            if type(required) is int and type(owned) is int and required > owned:
                return 'هنوز ' + isolate(required - owned) + ' ' + label + ' دیگه لازم داری.'
    return MESSAGES.get(code, 'انجام نشد؛ منوی این بخش رو دوباره باز کن و امتحان کن.')
