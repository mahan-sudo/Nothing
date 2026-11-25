from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str | None] = mapped_column(String(128))
    referrer_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    months: Mapped[int] = mapped_column(Integer, unique=True)
    price: Mapped[int] = mapped_column(BigInteger)  # تومان
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))

    __table_args__ = (CheckConstraint("price > 0", name="ck_plans_price_positive"),)


class Subscription(Base):
    """هر کاربر فقط یک ردیف داره؛ تمدید یعنی جلو بردن expires_at."""

    __tablename__ = "subscriptions"

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SelfAccount(Base):
    """حساب تلگرامِ متصل‌شده‌ی کاربر. سشن و شماره فقط رمزنگاری‌شده ذخیره می‌شن."""

    __tablename__ = "self_accounts"

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    phone_masked: Mapped[str | None] = mapped_column(String(32))
    phone_enc: Mapped[str | None] = mapped_column(Text)
    session_enc: Mapped[str | None] = mapped_column(Text)
    is_connected: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    self_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ref: Mapped[str] = mapped_column(String(16), unique=True)  # کد پیگیری عمومی
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    plan_months: Mapped[int] = mapped_column(Integer)
    base_amount: Mapped[int] = mapped_column(BigInteger)       # قیمت پلن
    unique_amount: Mapped[int | None] = mapped_column(BigInteger)  # مبلغ دقیق واریز (فقط کارت‌به‌کارت)
    method: Mapped[str] = mapped_column(String(16))             # card | gift
    # pending -> awaiting_receipt -> in_review -> approved | rejected
    # pending/awaiting_receipt -> expired | cancelled
    status: Mapped[str] = mapped_column(String(16), index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    receipt_file_id: Mapped[str | None] = mapped_column(String(256))
    chat_id: Mapped[int | None] = mapped_column(BigInteger)
    message_id: Mapped[int | None] = mapped_column(BigInteger)
    reviewed_by: Mapped[int | None] = mapped_column(BigInteger)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        # دو پرداخت فعال هیچ‌وقت نمی‌تونن مبلغ یکسان داشته باشن (تضمین توسط خود دیتابیس)
        Index(
            "uq_payments_active_amount",
            "unique_amount",
            unique=True,
            postgresql_where=text("status IN ('pending','awaiting_receipt','in_review')"),
        ),
        Index("ix_payments_status_expires", "status", "expires_at"),
        CheckConstraint("base_amount > 0", name="ck_payments_base_positive"),
    )


class WalletEntry(Base):
    """دفتر حساب موجودی هدیه. موجودی = جمع همه‌ی ردیف‌ها. هیچ ردیفی ویرایش یا حذف نمی‌شه."""

    __tablename__ = "wallet_entries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    amount: Mapped[int] = mapped_column(BigInteger)  # مثبت: واریز، منفی: برداشت
    kind: Mapped[str] = mapped_column(String(32))
    payment_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("payments.id", ondelete="SET NULL"))
    # کلید یکتا: هر عملیات فقط یک‌بار ثبت می‌شه حتی اگه کد دوبار اجرا بشه
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (CheckConstraint("amount <> 0", name="ck_wallet_nonzero"),)


class BackupChannel(Base):
    """کانال خصوصی پشتیبانِ هر کاربر (نسخه‌ی بنرها و تنظیمات اونجا نگه‌داری می‌شه)."""

    __tablename__ = "backup_channels"

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    channel_id: Mapped[int] = mapped_column(BigInteger)
    access_hash: Mapped[int | None] = mapped_column(BigInteger)
    title: Mapped[str | None] = mapped_column(String(256))


class Banner(Base):
    """بنر یک گروه برای یک کاربر: چی، کجا، هر چند ثانیه، و وقت ارسال بعدی."""

    __tablename__ = "banners"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    chat_id: Mapped[int] = mapped_column(BigInteger)            # آیدی عددی گروه هدف
    chat_access_hash: Mapped[int | None] = mapped_column(BigInteger)
    chat_title: Mapped[str | None] = mapped_column(String(256))
    backup_channel_id: Mapped[int] = mapped_column(BigInteger)
    backup_access_hash: Mapped[int | None] = mapped_column(BigInteger)
    backup_msg_id: Mapped[int] = mapped_column(BigInteger)      # پیام بنر داخل پشتیبان
    info_msg_id: Mapped[int | None] = mapped_column(BigInteger)  # پیام خلاصه‌ی تنظیمات داخل پشتیبان
    interval_seconds: Mapped[int | None] = mapped_column(BigInteger)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    send_count: Mapped[int] = mapped_column(BigInteger, default=0, server_default=text("0"))
    fail_streak: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "chat_id", name="uq_banners_user_chat"),
        CheckConstraint("interval_seconds IS NULL OR interval_seconds > 0", name="ck_banners_interval_positive"),
        Index("ix_banners_enabled", "user_id", "enabled"),
    )
