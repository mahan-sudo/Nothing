from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message

from .. import keyboards as K
from .. import texts as T
from ..db.models import SelfAccount
from ..keyboards import LoginKey, Nav
from ..login import LoginManager
from ..services.accounts import toggle_self
from ..services.subscriptions import get_expires_at
from ..utils import normalize_phone, utcnow
from .common import cb_message, panel_view, safe_edit

router = Router(name="login")


class InStage(BaseFilter):
    def __init__(self, stage: str) -> None:
        self.stage = stage

    async def __call__(self, message: Message, logins: LoginManager) -> bool:
        ctx = logins.get(message.from_user.id)
        return bool(ctx and ctx.stage == self.stage)


NOT_COMMAND = ~F.text.startswith("/")
NOT_MENU = ~F.text.in_(K.MENU_TEXTS)


# ------------------------------------------------------------ پنل
@router.callback_query(Nav.filter(F.to == "panel"))
async def cb_panel(cb: CallbackQuery, db) -> None:
    msg = cb_message(cb)
    if msg is None:
        await cb.answer()
        return
    async with db.begin() as s:
        text, kb = await panel_view(s, cb.from_user.id)
    await safe_edit(msg, text, kb)
    await cb.answer()


@router.callback_query(Nav.filter(F.to == "toggle"))
async def cb_toggle(cb: CallbackQuery, db) -> None:
    msg = cb_message(cb)
    async with db.begin() as s:
        status, _ = await toggle_self(s, cb.from_user.id, utcnow())
        text, kb = await panel_view(s, cb.from_user.id)
    if status == "no_account":
        await cb.answer("اول حساب رو متصل کن 🌱", show_alert=True)
        return
    if status == "no_sub":
        await cb.answer("اشتراکت تموم شده؛ اول تمدیدش کن 🌱", show_alert=True)
        return
    if msg is not None:
        await safe_edit(msg, text, kb)
    await cb.answer()


# ------------------------------------------------------------ شروع اتصال
@router.callback_query(Nav.filter(F.to == "connect"))
async def cb_connect(cb: CallbackQuery, db, logins: LoginManager) -> None:
    msg = cb_message(cb)
    if msg is None:
        await cb.answer()
        return
    uid = cb.from_user.id
    async with db.begin() as s:
        exp = await get_expires_at(s, uid)
        acct = await s.get(SelfAccount, uid)
    if not exp or exp <= utcnow():
        await cb.answer(T.LOGIN_NEED_SUB, show_alert=True)
        return
    if acct and acct.is_connected:
        await cb.answer(T.LOGIN_ALREADY, show_alert=True)
        return
    await cb.answer()
    await logins.start(msg.chat.id, uid)


# ------------------------------------------------------------ شماره
@router.message(F.contact, InStage("phone"))
async def on_contact(message: Message, logins: LoginManager) -> None:
    c = message.contact
    if c.user_id != message.from_user.id:
        await logins.restart(message, T.NOTE_NOT_OWN)
        return
    phone = normalize_phone(c.phone_number)
    if not phone:
        await logins.restart(message, T.NOTE_BAD_PHONE)
        return
    await logins.submit_phone(message, phone)


@router.message(F.text, InStage("phone"), NOT_COMMAND, NOT_MENU)
async def on_phone_text(message: Message, logins: LoginManager) -> None:
    phone = normalize_phone(message.text)
    if not phone:
        await logins.restart(message, T.NOTE_BAD_PHONE)
        return
    await logins.submit_phone(message, phone)


# ------------------------------------------------------------ کد و رمز
@router.callback_query(LoginKey.filter())
async def cb_key(cb: CallbackQuery, callback_data: LoginKey, logins: LoginManager) -> None:
    await logins.press(cb, callback_data)


@router.message(F.text, InStage("password"), NOT_COMMAND)
async def on_password(message: Message, logins: LoginManager) -> None:
    await logins.submit_password(message)


@router.message(InStage("code"), NOT_COMMAND, NOT_MENU)
async def on_stray_in_code_stage(message: Message, logins: LoginManager) -> None:
    await logins.drop_stray(message)
