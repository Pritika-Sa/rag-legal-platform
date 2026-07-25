import os

from fastapi import HTTPException, UploadFile, status

from api.config import ALLOWED_UPLOAD_EXTENSIONS, MAX_UPLOAD_SIZE_BYTES, UPLOADS_DIR


def _extension(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


async def save_uploaded_file(file: UploadFile, user_id: int) -> str:
    """Validates and writes an uploaded file to disk, then returns its path.
    Mirrors app.py's sidebar upload block verbatim: same allowed extensions
    (st.file_uploader's type=[...] allowlist), same
    UPLOADS_DIR/{user_id}/{filename} destination. The extension/size checks
    are new only in the sense that Streamlit enforced them client-side in
    the widget itself — an HTTP endpoint has to enforce them server-side
    too, which is transport-layer request validation, not business logic."""
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No file provided.")

    extension = _extension(file.filename)
    if extension not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '.{extension}'. Allowed: {', '.join(sorted(ALLOWED_UPLOAD_EXTENSIONS))}.",
        )

    contents = await file.read()
    if len(contents) > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the {MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)}MB upload limit.",
        )

    uploads_dir = os.path.join(UPLOADS_DIR, str(user_id))
    os.makedirs(uploads_dir, exist_ok=True)
    file_path = os.path.join(uploads_dir, file.filename)
    with open(file_path, "wb") as f:
        f.write(contents)

    return file_path
