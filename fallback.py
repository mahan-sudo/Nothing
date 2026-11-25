from __future__ import annotations

from aiogram import Router
from aiogram.types import Message

from .. import keyboards as K
from .. import texts as T
from ..services.payments import has_awaiting_receipt
from ..utils import utcnow

router = Router(name="fallback")


@router.message()
async def fallback(message: Message, db) -> None:
    async with db.begin() as s:
        awaiting = await has_awaiting_receipt(s, message.from_user.id, utcnow())
    if awaiting:
        await message.answer(T.RECEIPT_ONLY_PHOTO)
    elif message.text and not message.text.startswith("/"):
        await message.answer(T.USE_MENU, reply_markup=K.main_menu())
