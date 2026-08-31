import secrets

from fastapi import Header, HTTPException, status

from app.core.config import settings


def require_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, bool]:
    provided_key_bytes = x_api_key.encode("utf-8") if x_api_key else b""
    expected_key_bytes = settings.api_key.encode("utf-8")

    if not secrets.compare_digest(provided_key_bytes, expected_key_bytes):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    return {"ok": True}
