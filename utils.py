from __future__ import annotations

import html
import math
import re
from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def money(n: int) -> str:
    return f"{n:,}"


def esc(s: str | None) -> str:
    return html.escape(s or "", quote=False)


def remaining_text(expires_at: datetime | None, now: datetime) -> str:
    """روز و ساعت و دقیقه‌ی باقی‌مانده، یا «ندارید»."""
    if not expires_at or expires_at <= now:
        return "ندارید"
    total = int((expires_at - now).total_seconds())
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    return f"{days} روز و {hours} ساعت و {minutes} دقیقه"


def days_left(expires_at: datetime, now: datetime) -> int:
    return max(0, math.ceil((expires_at - now).total_seconds() / 86400))


def mask_phone(phone: str) -> str:
    """+989351234544 -> +9893******44"""
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 8:
        return "+" + "*" * len(digits)
    return f"+{digits[:4]}{'*' * (len(digits) - 6)}{digits[-2:]}"


_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def normalize_phone(raw: str) -> str | None:
    """شماره رو به قالب بین‌المللی (+98...) تبدیل می‌کنه؛ اگه معتبر نبود None."""
    s = re.sub(r"[\s\-().]", "", (raw or "").strip()).translate(_DIGITS)
    if s.startswith("00"):
        s = "+" + s[2:]
    elif s.startswith("09") and len(s) == 11:
        s = "+98" + s[1:]
    elif s and not s.startswith("+"):
        s = "+" + s
    return s if re.fullmatch(r"\+\d{8,15}", s) else None


def format_interval(seconds: int) -> str:
    if seconds % 3600 == 0:
        return f"{seconds // 3600} ساعت"
    if seconds % 60 == 0:
        return f"{seconds // 60} دقیقه"
    return f"{seconds} ثانیه"
