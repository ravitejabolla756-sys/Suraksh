from datetime import datetime, timedelta, timezone
from jose import jwt
from passlib.context import CryptContext

from app.core.config import get_settings


pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_access_token(subject: str) -> str:
    settings = get_settings()
    if not settings.jwt_secret:
        raise RuntimeError("VISIONGUARD_JWT_SECRET must be configured")
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_minutes)
    return jwt.encode(
        {"sub": subject, "exp": expires},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> str:
    settings = get_settings()
    if not settings.jwt_secret:
        raise RuntimeError("VISIONGUARD_JWT_SECRET must be configured")
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    return str(payload["sub"])


def hash_machine_key(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def verify_machine_key(value: str, digest: str) -> bool:
    import hmac

    return hmac.compare_digest(hash_machine_key(value), digest)
