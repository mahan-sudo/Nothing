"""رمزنگاری سشن‌ها و شماره‌ها قبل از ذخیره در دیتابیس.

کلید از ENCRYPTION_SECRET ساخته می‌شه که فقط توی Variables ریلوی می‌مونه.
"""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet


class Vault:
    def __init__(self, secret: str) -> None:
        digest = hashlib.sha256(("selfbot-vault-v1:" + secret).encode()).digest()
        self._fernet = Fernet(base64.urlsafe_b64encode(digest))

    def encrypt(self, plain: str) -> str:
        return self._fernet.encrypt(plain.encode()).decode()

    def decrypt(self, token: str) -> str:
        return self._fernet.decrypt(token.encode()).decode()
