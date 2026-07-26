import os
import secrets

from dotenv import load_dotenv

load_dotenv()

JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = 7
AUTH_COOKIE_NAME = "access_token"

APP_ENV = os.getenv("APP_ENV", "development")
IS_PRODUCTION = APP_ENV == "production"

# Random per-process id, generated fresh on every FastAPI startup and kept
# in memory only. In development this is stamped into issued JWTs so that
# restarting the server invalidates every cookie from the previous process,
# forcing a fresh login instead of silently resuming a stale session.
SERVER_INSTANCE_ID = secrets.token_hex(32)

# Comma-separated list of allowed frontend origins for CORS in development
# (e.g. the Vite dev server). In production the frontend is expected to be
# served same-origin behind a reverse proxy, so this is dev-only.
FRONTEND_ORIGINS = [
    origin.strip()
    for origin in os.getenv("FRONTEND_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip()
]

UPLOADS_DIR = os.getenv("UPLOADS_DIR", "uploads")

# Mirrors app.py's st.file_uploader(type=[...]) allowlist exactly.
ALLOWED_UPLOAD_EXTENSIONS = {"pdf", "docx", "txt", "png", "jpg", "jpeg"}

# Streamlit's own default maxUploadSize is 200MB; matched here so the
# adapter isn't silently more permissive than the app it's replacing
# (Migration Risk #5 in the migration plan).
MAX_UPLOAD_SIZE_BYTES = 200 * 1024 * 1024
