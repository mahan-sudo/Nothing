from __future__ import annotations

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from .. import keyboards as K
from .. import texts as T
from ..services.users import get_dashboard_data
from ..utils import utcnow


async def render_dashboard(session, user_id: int) -> str:
    account, expires_at = await get_dashboard_data(session, user_id)
    return T.dashboard(account, expires_at, utcnow())


def cb_message(cb: CallbackQuery) -> Message | None:
    """پیام زیر دکمه، به شرطی که هنوز در دسترس باشه."""
    return cb.message if isinstance(cb.message, Message) else None


async def safe_edit(message: Message, text: str, kb: InlineKeyboardMarkup | None = None) -> None:
    try:
        await message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise


async def panel_view(session, user_id: int):
    """متن و دکمه‌های پنل سلف."""
    account, expires_at = await get_dashboard_data(session, user_id)
    text = T.dashboard(account, expires_at, utcnow(), panel=True)
    return text, K.panel(bool(account and account.self_enabled))
