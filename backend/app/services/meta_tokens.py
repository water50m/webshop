"""Helpers for encrypted Meta Page access tokens.

Legacy channels without the ``enc:`` prefix continue to work during migration,
but newly connected Pages are always encrypted before they reach the database.
"""

from app.config import settings
from app.models import Channel


class MetaTokenConfigurationError(RuntimeError):
    pass


def _fernet():
    if not settings.meta_token_encryption_key:
        raise MetaTokenConfigurationError("ยังไม่ได้ตั้งค่า META_TOKEN_ENCRYPTION_KEY")
    try:
        from cryptography.fernet import Fernet
    except ImportError as exc:  # Keep existing non-OAuth installations bootable.
        raise MetaTokenConfigurationError("ยังไม่ได้ติดตั้ง dependency cryptography") from exc
    try:
        return Fernet(settings.meta_token_encryption_key.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise MetaTokenConfigurationError("META_TOKEN_ENCRYPTION_KEY ไม่ถูกต้อง") from exc


def encrypt_access_token(access_token: str) -> str:
    return "enc:" + _fernet().encrypt(access_token.encode("utf-8")).decode("utf-8")


def decrypt_access_token(access_token: str) -> str:
    if not access_token:
        return ""
    if not access_token.startswith("enc:"):
        return access_token
    try:
        return _fernet().decrypt(access_token.removeprefix("enc:").encode("utf-8")).decode("utf-8")
    except Exception as exc:
        raise MetaTokenConfigurationError("ไม่สามารถถอดรหัส Meta access token ได้") from exc


def channel_access_token(channel: Channel) -> str:
    return decrypt_access_token(channel.access_token)
