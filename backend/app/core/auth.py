import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings

bearer = HTTPBearer(auto_error=False)


def issue_session_token() -> tuple[str, str]:
    user_id = f"user-{secrets.token_urlsafe(18)}"
    payload = {"sub": user_id, "exp": int(time.time()) + get_settings().auth_token_ttl}
    encoded = _encode(payload)
    signature = _signature(encoded)
    return f"{encoded}.{signature}", user_id


def authenticated_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Authentication required.")
    try:
        encoded, signature = credentials.credentials.split(".", 1)
        expected = _signature(encoded)
        if not hmac.compare_digest(signature, expected):
            raise ValueError
        payload = json.loads(_decode(encoded))
        if not isinstance(payload.get("sub"), str) or payload["exp"] <= int(time.time()):
            raise ValueError
        return payload["sub"]
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise HTTPException(status_code=401, detail="Invalid or expired session.") from None


def _encode(payload: dict[str, object]) -> str:
    return base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")


def _decode(value: str) -> str:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)).decode()


def _signature(value: str) -> str:
    secret = get_settings().auth_secret.encode()
    return hmac.new(secret, value.encode(), hashlib.sha256).hexdigest()
