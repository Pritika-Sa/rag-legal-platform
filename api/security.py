from datetime import datetime, timedelta, timezone

import jwt

from api.config import JWT_ALGORITHM, JWT_EXPIRE_DAYS, JWT_SECRET


def create_access_token(user: dict) -> str:
    """Wraps an existing database.auth user dict ({"id","name","email"}) in a
    signed JWT. Transport-only: the claims are exactly what auth.authenticate()/
    auth.create_user() already return, nothing computed or validated here."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user["id"]),
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "iat": now,
        "exp": now + timedelta(days=JWT_EXPIRE_DAYS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    """Returns the {"id","name","email"} claims from a valid token, or None if
    the token is missing, malformed, expired, or has a bad signature."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None
    return {"id": payload["id"], "name": payload["name"], "email": payload["email"]}
