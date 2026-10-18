"""Private-only personal economy entry points, including stale callbacks."""
from functools import wraps


async def require_private(update):
    query = getattr(update, 'callback_query', None)
    chat = getattr(update, 'effective_chat', None)
    if chat is None:
        chat = getattr(getattr(query, 'message', None), 'chat', None)
    if getattr(chat, 'type', None) == 'private':
        return True
    if query is not None:
        await query.answer('شاپ توی پیوی رباته؛ همون‌جا /start بزن.', show_alert=True)
    return False


def private_shop(method):
    @wraps(method)
    async def wrapped(self, update, context, *args, **kwargs):
        if await require_private(update):
            return await method(self, update, context, *args, **kwargs)
    return wrapped
