import logging

from fastapi import APIRouter, Depends, HTTPException, Response, status

from api.config import AUTH_COOKIE_NAME, IS_PRODUCTION, JWT_EXPIRE_DAYS
from api.deps import get_current_user
from api.schemas.auth import (
    DeleteAccountRequest,
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    ResetPasswordRequest,
    SignupRequest,
    UserResponse,
)
from api.security import create_access_token
from database import auth, crud

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

_COOKIE_MAX_AGE = JWT_EXPIRE_DAYS * 24 * 60 * 60


def _set_session_cookie(response: Response, user: dict) -> None:
    token = create_access_token(user)
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=IS_PRODUCTION,
        samesite="lax",
        max_age=_COOKIE_MAX_AGE,
        path="/",
    )


@router.post("/signup", response_model=UserResponse)
def signup(body: SignupRequest, response: Response):
    try:
        user = auth.create_user(body.name, body.email, body.password)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    _set_session_cookie(response, user)
    return user


@router.post("/login", response_model=UserResponse)
def login(body: LoginRequest, response: Response):
    user = auth.authenticate(body.email, body.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")

    _set_session_cookie(response, user)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response):
    response.delete_cookie(key=AUTH_COOKIE_NAME, path="/")


@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(body: ForgotPasswordRequest):
    token = auth.request_password_reset(body.email)
    if token:
        auth.send_reset_email(body.email.strip().lower(), token)
    # Same message whether or not the email is registered — mirrors app.py's
    # anti-enumeration behavior exactly.
    return {"message": "If an account exists for that email, a reset link has been sent."}


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(body: ResetPasswordRequest):
    if not auth.reset_password(body.token, body.new_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This reset link is invalid or has expired. Request a new one from the Forgot Password tab.",
        )
    return {"message": "Password reset. You can now log in."}


@router.get("/me", response_model=UserResponse)
def me(current_user: dict = Depends(get_current_user)):
    return current_user


@router.post("/delete-account", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(body: DeleteAccountRequest, response: Response, current_user: dict = Depends(get_current_user)):
    """Password re-verification is the authorization check here, in place of
    an ownership lookup (there's no other account to compare against - the
    JWT already scopes this to current_user's own id, so this can never
    delete another user's account). 403, not 401, on a wrong password:
    apiClient's response interceptor (frontend/src/api/client.ts) treats any
    401 as "session expired" and force-redirects to /login, which would
    yank the user away before they ever saw the "incorrect password"
    message."""
    if not auth.verify_password(current_user["id"], body.password):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Incorrect password.")

    try:
        crud.delete_user_account(current_user["id"])
    except Exception:
        logger.exception(f"Account deletion failed for user {current_user['id']}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Account deletion failed. Please try again.",
        )

    response.delete_cookie(key=AUTH_COOKIE_NAME, path="/")
