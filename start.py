from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import CallbackQuery, Message
from redis.exceptions import RedisError

from ..keyboards import Nav, main_menu
from ..services.users import ensure_user
from .common import cb_message, render_dashboard, safe_edit

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, db, redis) -> None:
    ref_id: int | None = None
    if command.args and command.args.startswith("ref_"):
        tail = command.args[4:]
        if tail.isdigit() and len(tail) <= 15:
            ref_id = int(tail)

    uid = message.from_user.id
    async with db.begin() as session:
        await ensure_user(session, message.from_user, ref_id)
        text = await render_dashboard(session, uid)
    try:
        await redis.set(f"known:{uid}", "1", ex=600)
    except RedisError:
        pass
    await message.answer(text, reply_markup=main_menu())


@router.callback_query(Nav.filter(F.to == "home"))
async def cb_home(cb: CallbackQuery, db) -> None:
    msg = cb_message(cb)
    if msg is None:
        await cb.answer()
        return
    async with db.begin() as session:
        text = await render_dashboard(session, cb.from_user.id)
    await safe_edit(msg, text, None)
    await cb.answer()
