import hashlib
import os
import re
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText

from database.connection import get_db
from database.models import _get_next_id

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
RESET_TOKEN_TTL_MINUTES = 30


def _now():
    return datetime.now(timezone.utc)


# ── Password hashing (PBKDF2-HMAC-SHA256, stdlib only) ──────────────────────

def _hash_password(password: str, salt: bytes = None) -> tuple[str, str]:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
    return digest.hex(), salt.hex()


def _verify_password(password: str, password_hash: str, salt_hex: str) -> bool:
    digest, _ = _hash_password(password, bytes.fromhex(salt_hex))
    return secrets.compare_digest(digest, password_hash)


# ── Signup / login ───────────────────────────────────────────────────────────

def create_user(name: str, email: str, password: str) -> dict:
    """Creates a new user account. Raises ValueError on invalid input or if
    the email is already registered."""
    name = (name or "").strip()
    email = (email or "").strip().lower()

    if not name:
        raise ValueError("Name is required.")
    if not EMAIL_RE.match(email):
        raise ValueError("Enter a valid email address.")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long.")

    db = get_db()
    if db.users.find_one({"email": email}):
        raise ValueError("An account with this email already exists.")

    password_hash, salt = _hash_password(password)
    user_id = _get_next_id("users")
    db.users.insert_one({
        "id": user_id,
        "name": name,
        "email": email,
        "password_hash": password_hash,
        "salt": salt,
        "reset_token_hash": None,
        "reset_token_expires": None,
        "created_at": _now(),
    })
    return {"id": user_id, "name": name, "email": email}


def authenticate(email: str, password: str) -> dict | None:
    """Returns {"id", "name", "email"} on success, None on bad credentials."""
    email = (email or "").strip().lower()
    db = get_db()
    user = db.users.find_one({"email": email})
    if not user:
        return None
    if not _verify_password(password, user["password_hash"], user["salt"]):
        return None
    return {"id": user["id"], "name": user["name"], "email": user["email"]}


# ── Forgot / reset password ──────────────────────────────────────────────────

def request_password_reset(email: str) -> str | None:
    """Generates a reset token for the given email (if it exists), stores its
    hash + expiry, and returns the raw token for the caller to email out.
    Returns None if no account matches — callers should show the same
    generic "check your inbox" message either way, so this isn't used to
    probe which emails are registered."""
    email = (email or "").strip().lower()
    db = get_db()
    user = db.users.find_one({"email": email})
    if not user:
        return None

    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    db.users.update_one(
        {"id": user["id"]},
        {"$set": {
            "reset_token_hash": token_hash,
            "reset_token_expires": _now() + timedelta(minutes=RESET_TOKEN_TTL_MINUTES),
        }},
    )
    return token


def reset_password(token: str, new_password: str) -> bool:
    """Consumes a reset token and sets the new password. Returns False if the
    token is missing, unknown, or expired."""
    if not token or len(new_password) < 8:
        return False

    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    db = get_db()
    user = db.users.find_one({"reset_token_hash": token_hash})
    if not user or not user.get("reset_token_expires"):
        return False

    expires = user["reset_token_expires"]
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < _now():
        return False

    password_hash, salt = _hash_password(new_password)
    db.users.update_one(
        {"id": user["id"]},
        {"$set": {"password_hash": password_hash, "salt": salt},
         "$unset": {"reset_token_hash": "", "reset_token_expires": ""}},
    )
    return True


def send_reset_email(to_email: str, token: str) -> tuple[bool, str]:
    """Emails the reset link via SMTP. Returns (sent, message) - message is a
    user-facing status string. If SMTP isn't configured, the token is printed
    to the server console instead so local/dev use still works."""
    reset_link = f"{os.getenv('APP_BASE_URL', 'http://localhost:8501')}/?reset_token={token}"

    smtp_user = os.getenv("SMTP_USERNAME", "").strip()
    smtp_password = os.getenv("SMTP_PASSWORD", "").strip()
    if not smtp_user or not smtp_password:
        print(f"[password reset] SMTP not configured. Reset link for {to_email}: {reset_link}")
        return False, "Email isn't configured on this server. Ask the admin to check the server console for your reset link."

    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    from_email = os.getenv("SMTP_FROM_EMAIL", smtp_user).strip()

    body = (
        f"Hi,\n\nA password reset was requested for your LQ-LegalAI account.\n"
        f"Click the link below to set a new password (expires in {RESET_TOKEN_TTL_MINUTES} minutes):\n\n"
        f"{reset_link}\n\n"
        f"If you didn't request this, you can safely ignore this email."
    )
    msg = MIMEText(body)
    msg["Subject"] = "LQ-LegalAI Password Reset"
    msg["From"] = from_email
    msg["To"] = to_email

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(from_email, [to_email], msg.as_string())
        return True, "A password reset link has been sent to your email."
    except Exception as e:
        print(f"[password reset] Failed to send email to {to_email}: {e}")
        return False, "Couldn't send the reset email right now. Please try again later."
