from fastapi import APIRouter, Depends, HTTPException, Response, status

from api.config import AUTH_COOKIE_NAME, IS_PRODUCTION, JWT_EXPIRE_DAYS
from api.deps import get_current_user
from api.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    ResetPasswordRequest,
    SignupRequest,
    UserResponse,
)
from api.security import create_access_token
from database import auth

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
