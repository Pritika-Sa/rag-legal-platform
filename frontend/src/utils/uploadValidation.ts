// Mirrors app.py's st.file_uploader(type=[...]) allowlist and
// api/config.py's ALLOWED_UPLOAD_EXTENSIONS/MAX_UPLOAD_SIZE_BYTES — this is
// a client-side pre-check only; the adapter re-validates both regardless,
// since a client check can always be bypassed.
export const ALLOWED_UPLOAD_EXTENSIONS = ["pdf", "docx", "txt", "png", "jpg", "jpeg"];
export const MAX_UPLOAD_SIZE_BYTES = 200 * 1024 * 1024;

export function validateUploadFile(file: File): string | null {
  const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
  if (!ALLOWED_UPLOAD_EXTENSIONS.includes(extension)) {
    return `Unsupported file type '.${extension}'. Allowed: ${ALLOWED_UPLOAD_EXTENSIONS.join(", ")}.`;
  }
  if (file.size > MAX_UPLOAD_SIZE_BYTES) {
    return `File exceeds the ${MAX_UPLOAD_SIZE_BYTES / (1024 * 1024)}MB upload limit.`;
  }
  return null;
}
