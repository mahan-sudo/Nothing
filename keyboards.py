from __future__ import annotations

import re

from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    CopyTextButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

BTN_SUB = "⭐️اشتراک"
BTN_PANEL = "🤖پنل من"
BTN_HELP = "🆘️راهنما و پشتیبانی"
BTN_FEATURES = "🎛امکانات"
BTN_INVITE = "👥️دعوت دوستان"

BACK = "بازگشت «"


class Nav(CallbackData, prefix="nav"):
    to: str  # home | sub | card | gift | panel | toggle | connect


class PlanPick(CallbackData, prefix="pl"):
    method: str  # card | gift
    months: int


class GiftConfirm(CallbackData, prefix="gc"):
    months: int


class PayAction(CallbackData, prefix="pay"):
    act: str  # paid
    id: int


class LoginKey(CallbackData, prefix="lg"):
    act: str  # d (digit) | b (backspace) | c (clear) | ok | x (cancel)
    d: str = ""


class AdmPay(CallbackData, prefix="adm"):
    act: str  # ok | no
    id: int


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_SUB), KeyboardButton(text=BTN_PANEL)],
            [KeyboardButton(text=BTN_HELP), KeyboardButton(text=BTN_FEATURES)],
            [KeyboardButton(text=BTN_INVITE)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def _btn(text: str, data: CallbackData) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data.pack())


def sub_methods() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn("کارت به کارت", Nav(to="card"))],
            [_btn("پرداخت با موجودی هدیه", Nav(to="gift"))],
            [_btn(BACK, Nav(to="home"))],
        ]
    )


def plans(method: str, plan_list) -> InlineKeyboardMarkup:
    row = [_btn(f"{p.months} ماهه", PlanPick(method=method, months=p.months)) for p in plan_list]
    return InlineKeyboardMarkup(inline_keyboard=[row, [_btn(BACK, Nav(to="sub"))]])


def gift_confirm(months: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn("✅️ تأیید و پرداخت", GiftConfirm(months=months))],
            [_btn(BACK, Nav(to="gift"))],
        ]
    )


def payment(payment_id: int, amount: int, card_number: str) -> InlineKeyboardMarkup:
    card_digits = re.sub(r"\D", "", card_number)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="کپی مبلغ", copy_text=CopyTextButton(text=str(amount))),
                InlineKeyboardButton(text="کپی شماره کارت", copy_text=CopyTextButton(text=card_digits)),
            ],
            [_btn("✅️ پرداخت کردم | ارسال رسید", PayAction(act="paid", id=payment_id))],
        ]
    )


def admin_review(payment_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _btn("✅️ تأیید", AdmPay(act="ok", id=payment_id)),
                _btn("❌️ رد", AdmPay(act="no", id=payment_id)),
            ]
        ]
    )


def to_subscription() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_btn("⭐️ خرید اشتراک", Nav(to="sub"))]])


def support_link(username: str) -> InlineKeyboardMarkup | None:
    username = username.strip().lstrip("@")
    if not username:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="💬 پیام به پشتیبانی", url=f"https://t.me/{username}")]]
    )


MENU_TEXTS = {BTN_SUB, BTN_PANEL, BTN_HELP, BTN_FEATURES, BTN_INVITE}


def panel(self_on: bool) -> InlineKeyboardMarkup:
    toggle = "🟢 سلف روشنه" if self_on else "🔴 سلف خاموشه"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn(toggle, Nav(to="toggle"))],
            [_btn("📲اتصال حساب", Nav(to="connect")), _btn("🤖پنل من", Nav(to="panel"))],
            [_btn(BACK, Nav(to="home"))],
        ]
    )


def phone_request() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱ارسال شماره", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


_NUM = ["0️⃣", "1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣"]


def keypad() -> InlineKeyboardMarkup:
    def d(n: int) -> InlineKeyboardButton:
        return _btn(_NUM[n], LoginKey(act="d", d=str(n)))

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [d(1), d(2), d(3)],
            [d(4), d(5), d(6)],
            [d(7), d(8), d(9)],
            [_btn("⌫", LoginKey(act="b")), d(0), _btn("پاک", LoginKey(act="c"))],
            [_btn("✅️ تایید کد", LoginKey(act="ok"))],
            [_btn("لغو عملیات »", LoginKey(act="x"))],
        ]
    )


def cancel_only() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_btn("لغو عملیات »", LoginKey(act="x"))]])


def back_home() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_btn(BACK, Nav(to="home"))]])
