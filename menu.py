from __future__ import annotations

from aiogram import F, Router
from aiogram.types import Message

from .. import keyboards as K
from .. import texts as T
from ..config import Settings
from ..services.subscriptions import get_expires_at
from ..services.users import count_referrals
from ..services.wallet import balance
from ..utils import utcnow
from .common import panel_view

router = Router(name="menu")


@router.message(F.text == K.BTN_PANEL)
async def panel(message: Message, db) -> None:
    async with db.begin() as s:
        exp = await get_expires_at(s, message.from_user.id)
    if exp and exp > utcnow():
        async with db.begin() as s:
            text, kb = await panel_view(s, message.from_user.id)
        await message.answer(text, reply_markup=kb)
    else:
        await message.answer(T.PANEL_NO_SUB, reply_markup=K.to_subscription())


@router.message(F.text == K.BTN_FEATURES)
async def features(message: Message) -> None:
    await message.answer(T.FEATURES_SOON)


@router.message(F.text == K.BTN_HELP)
async def help_(message: Message, settings: Settings) -> None:
    await message.answer(T.HELP, reply_markup=K.support_link(settings.support_username))


@router.message(F.text == K.BTN_INVITE)
async def invite(message: Message, db, bot) -> None:
    uid = message.from_user.id
    me = await bot.me()
    async with db.begin() as s:
        count = await count_referrals(s, uid)
        bal = await balance(s, uid)
    link = f"https://t.me/{me.username}?start=ref_{uid}"
    await message.answer(T.referral(link, count, bal))
