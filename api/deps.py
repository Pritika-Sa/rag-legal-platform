from fastapi import HTTPException, Request, status

from api.config import AUTH_COOKIE_NAME, IS_PRODUCTION, SERVER_INSTANCE_ID
from api.security import decode_access_token
from database.connection import get_db


class StaleServerInstanceError(HTTPException):
    """Dev-only: raised when a JWT's server_instance_id doesn't match this
    process's SERVER_INSTANCE_ID (i.e. it was issued before a server
    restart). A dedicated type so main.py's exception handler can clear the
    stale cookie before returning 401, without duplicating that logic at
    every raise site."""

    def __init__(self):
        super().__init__(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session")


def get_current_user(request: Request) -> dict:
    """FastAPI dependency guarding every 🔒 route. Reads the httpOnly session
    cookie set at login/signup and decodes it, then confirms the account
    still exists. That existence check is a deliberate one-indexed-lookup
    trade against the original pure-JWT-decode design (no DB round trip):
    without it, a deleted account's JWT would keep authenticating
    successfully until its 7-day expiry, since nothing else revokes a JWT
    early in this stateless-token setup. Raises 401 if the cookie is
    missing/invalid or the account is gone, the HTTP equivalent of app.py's
    `if st.session_state.user is None: render_auth_gate()`."""
    token = request.cookies.get(AUTH_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    user = decode_access_token(token)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session")

    if not IS_PRODUCTION and user.get("server_instance_id") != SERVER_INSTANCE_ID:
        raise StaleServerInstanceError()

    if not get_db().users.find_one({"id": user["id"]}, {"_id": 1}):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session")

    return user
