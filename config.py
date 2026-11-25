from __future__ import annotations

import re
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# ---- ثابت‌های کسب‌وکار (یک‌جا، که راحت تغییرشون بدی) ----
PAYMENT_TTL_MINUTES = 30        # مهلت واریز کارت‌به‌کارت
RECEIPT_TTL_MINUTES = 30        # مهلت ارسال عکس رسید بعد از زدن «پرداخت کردم»
COMMISSION_PERCENT = 15         # پورسانت دعوت
DAYS_PER_MONTH = 30
LOGIN_IDLE_SECONDS = 90         # بعد از این مدت بی‌حرکتی، اتصال حساب لغو می‌شه
MAX_PENDING_LOGINS = 30         # حداکثر اتصال‌های هم‌زمان در حال انجام
# اگه False باشه، خریدی که با «موجودی هدیه» انجام بشه پورسانت نمی‌سازه
# (جلوگیری از ساخته‌شدن پول از هیچ). فقط خرید واقعی (کارت‌به‌کارت) پورسانت می‌ده.
COMMISSION_ON_GIFT_BALANCE_PURCHASES = False

# ---- تبچی ----
MIN_BANNER_INTERVAL = 30                 # ثانیه؛ کمترین بازه‌ی ارسال
MAX_BANNER_INTERVAL = 10 * 365 * 86400   # عملاً «بی‌نهایت»
MAX_ACTIVE_BANNERS = 25                  # حداکثر گروه فعال برای هر حساب
ACCOUNT_MIN_GAP_SECONDS = 2.0            # حداقل فاصله‌ی دو ارسال پشت‌سرهم از یک حساب
FAIL_STREAK_LIMIT = 3                    # بعد از چند خطای پشت‌سرهم، تبچی اون گروه خاموش می‌شه
RECONCILE_SECONDS = 15                   # هر چند ثانیه وضعیت حساب‌های روشن بررسی بشه


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bot_token: str
    admin_ids: str
    database_url: str
    redis_url: str
    webhook_secret: str
    encryption_secret: str
    telegram_api_id: int
    telegram_api_hash: str
    card_number: str
    card_holder: str
    support_username: str = ""
    public_url: str = ""
    railway_public_domain: str = ""
    port: int = 8080
    run_worker: bool = True  # موتور سلف داخل همین پردازش اجرا بشه؟

    @field_validator("database_url")
    @classmethod
    def _fix_db_url(cls, v: str) -> str:
        v = v.strip()
        if v.startswith("postgres://"):
            return "postgresql+asyncpg://" + v[len("postgres://"):]
        if v.startswith("postgresql://"):
            return "postgresql+asyncpg://" + v[len("postgresql://"):]
        return v

    @field_validator("admin_ids")
    @classmethod
    def _check_admins(cls, v: str) -> str:
        ids = [x for x in re.split(r"[,\s]+", v.strip()) if x]
        if not ids or not all(x.isdigit() for x in ids):
            raise ValueError("ADMIN_IDS باید آیدی‌های عددی باشه، با کاما جدا شده")
        return v

    @field_validator("webhook_secret")
    @classmethod
    def _check_webhook_secret(cls, v: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_-]{32,256}", v.strip()):
            raise ValueError("WEBHOOK_SECRET باید 32 تا 256 کاراکتر از حروف انگلیسی، عدد، _ و - باشه")
        return v.strip()

    @field_validator("encryption_secret")
    @classmethod
    def _check_enc(cls, v: str) -> str:
        if len(v.strip()) < 32:
            raise ValueError("ENCRYPTION_SECRET باید حداقل 32 کاراکتر باشه")
        return v.strip()

    @property
    def admin_id_set(self) -> set[int]:
        return {int(x) for x in re.split(r"[,\s]+", self.admin_ids.strip()) if x}

    @property
    def base_url(self) -> str:
        if self.public_url.strip():
            return self.public_url.strip().rstrip("/")
        if self.railway_public_domain.strip():
            return f"https://{self.railway_public_domain.strip()}"
        return ""


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
