"""متن‌هایی که سلف داخل چت‌های کاربر می‌نویسه (ویرایش پیام دستور) و پیام‌های اعلان ربات."""
from __future__ import annotations

from ..config import MAX_ACTIVE_BANNERS, MIN_BANNER_INTERVAL
from ..utils import esc, format_interval


def backup_set(channel_id: int) -> str:
    return f"کانال پشتیبان تنظیم شد.\nپشتیبان: <code>{channel_id}</code>"


BANNER_SAVED = "بنر ذخیره شد."
TABCHI_ON = "تبچی با موفقیت روشن شد."
TABCHI_OFF = "تبچی با موفقیت خاموش شد."
BANNER_DELETED = "بنر این گروه حذف شد."


def interval_set(seconds: int) -> str:
    return f"زمان بنر هر {format_interval(seconds)} تنظیم شد."


# ---- خطاهای دستورها
BACKUP_MUST_BE_PRIVATE = "کانال پشتیبان باید یک «کانال خصوصی» باشه (بدون یوزرنیم عمومی)."
BACKUP_NEED_ADMIN = "برای کانال پشتیبان باید مالک یا ادمین باشی."
NEED_BACKUP = "اول باید کانال پشتیبان رو تنظیم کنی (دستور «تنظیم پشتیبان» داخل یک کانال خصوصی)."
NEED_REPLY = "روی پیام بنر ریپلای کن و بعد «تنظیم بنر» رو بنویس."
ONLY_OWN = "فقط پیام‌های خودت رو می‌تونی بنر کنی."
ONLY_GROUPS = "این دستور فقط داخل گروه کار می‌کنه."
NEED_BANNER = "اول برای این گروه «تنظیم بنر» رو انجام بده."
NEED_INTERVAL = "اول زمان بنر رو تنظیم کن؛ مثلاً: تنظیم زمان بنر \"2 دقیقه\""
BACKUP_UNREACHABLE = "نتونستم بنر رو داخل کانال پشتیبان ذخیره کنم؛ مطمئن شو هنوز ادمین اون کانالی."
CANT_COPY = "این نوع پیام رو نمی‌شه به‌عنوان بنر ذخیره کرد."
TOO_FAST = f"کمترین زمان مجاز {MIN_BANNER_INTERVAL} ثانیه‌ست."
TOO_SLOW = "این زمان خیلی طولانیه."
TOO_MANY_ACTIVE = f"حداکثر {MAX_ACTIVE_BANNERS} گروه می‌تونن هم‌زمان فعال باشن؛ اول تبچی یکی رو خاموش کن."
GENERIC_ERROR = "یه مشکل پیش اومد؛ چند لحظه بعد دوباره امتحان کن."


# ---- اعلان‌های ربات به کاربر (داخل بات)
def notify_forbidden(title: str | None) -> str:
    return (
        f"⚠️ ارسال بنر توی گروه «{esc(title or '—')}» ممکن نبود (دسترسی نوشتن نداری یا از گروه خارج شدی)؛ "
        "تبچی اون گروه خاموش شد."
    )


def notify_failures(title: str | None) -> str:
    return f"⚠️ چند بار پشت‌سرهم ارسال بنر توی گروه «{esc(title or '—')}» خطا داد؛ تبچی اون گروه خاموش شد."


def notify_slowmode(title: str | None, seconds: int) -> str:
    return (
        f"🐢 گروه «{esc(title or '—')}» حالت آهسته (Slow mode) داره و بازه‌ی بنر از اجازه‌ی گروه کمتره "
        f"(حدود {seconds} ثانیه). بازه‌ی بنر رو بیشتر کن تا ارسال‌ها از دست نره."
    )


def notify_flood(seconds: int) -> str:
    minutes = max(1, (seconds + 59) // 60)
    return (
        f"⚠️ تلگرام به‌خاطر ارسال زیاد، حسابت رو حدود {minutes} دقیقه محدود کرده؛ "
        "ارسال‌ها تا پایان این مدت متوقف می‌شن. برای امنیت حسابت بازه‌ی بنرها رو بیشتر کن."
    )


DEAD_SESSION = (
    "⚠️ نشست حسابت از طرف تلگرام بسته شده (شاید از بخش Devices خارجش کردی). "
    "برای ادامه از «🤖پنل من» دوباره حساب رو متصل کن."
)
BANNED_ACCOUNT = "⚠️ تلگرام این حساب رو غیرفعال یا مسدود کرده؛ سلف متوقف شد."
