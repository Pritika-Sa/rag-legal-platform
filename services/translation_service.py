"""
Reusable, presentation-layer-only translation service.

Backed by IndicTrans2 (AI4Bharat) running entirely locally via
CTranslate2 — no external API calls, no API keys, no billing. Model
weights are pulled into the local HuggingFace cache (~/.cache/huggingface)
the first time each direction is used; every call after that, including
the model-loading step itself, runs fully offline (translate_texts()
falls back to the local cache automatically if it can't reach the Hub,
so a machine that's already downloaded both directions once needs no
network at all).

Used exclusively by api/routers/translate.py to translate already-
generated response text for display — never called from anywhere in the
RAG/agents/risk/authenticity pipeline itself, and never persists a
translated string to MongoDB or any application datastore. It does
persist to one thing: a local, file-backed translation-result cache (see
_get_cache() below), which is a pure inference-result cache, not
application data — clearing it changes nothing about the app's behavior
beyond re-translating on the next request.

The module is split into three layers on purpose:
  - `TranslationEngine` — a swappable backend contract. Today only
    IndicTrans2Engine implements it, but a future engine (a different
    local model, a different API) can be swapped in by changing what
    `_get_engine()` constructs, without touching the router, the
    frontend, or the translate_text/translate_texts call sites.
  - The persistent cache (`_get_cache()` / `_cache_key()`) — sits in
    front of the engine so a previously-seen (source_language,
    target_language, text) triple never touches IndicTrans2 again, on
    this run or any future one.
  - `translate_text` / `translate_texts` — the stable public API,
    parameterized by both target_language *and* source_language (default
    "en"). The "View in Tamil" feature only ever calls these with the
    default en->ta direction, but the indic-en direction is already
    wired up (see IndicTrans2Engine._direction_for) so it can be reused
    as-is for future Tamil-document ingestion (ta->en) without any
    changes to this module.
"""
from __future__ import annotations

import hashlib
import os
import threading
from typing import Protocol

import diskcache
from dotenv import load_dotenv

load_dotenv()

DEFAULT_TARGET_LANGUAGE = "ta"
DEFAULT_SOURCE_LANGUAGE = "en"

# FLORES-200 codes IndicTrans2 expects, keyed by the plain 2-letter codes
# used throughout this app's API/frontend. Extend this map to support
# another target language later (IndicTrans2 covers all 22 scheduled
# Indic languages) - no other code needs to change.
FLORES_CODES: dict[str, str] = {
    "en": "eng_Latn",
    "ta": "tam_Taml",
    "hi": "hin_Deva",
    "te": "tel_Telu",
    "ml": "mal_Mlym",
    "kn": "kan_Knda",
    "bn": "ben_Beng",
    "gu": "guj_Gujr",
    "mr": "mar_Deva",
    "pa": "pan_Guru",
    "or": "ory_Orya",
    "as": "asm_Beng",
    "ur": "urd_Arab",
}

# Distilled 200M models converted to CTranslate2 format - small and fast
# enough for CPU inference, and self-contained (bundled SentencePiece
# vocab, no custom Python model code to execute). Re-hosted ungated on HF
# by default: the official ai4bharat/* repos are gated ("auto"-approved,
# but still requires a free HF account + access token), which conflicts
# with this feature's "no API keys" requirement. These MIT-licensed
# mirrors serve the identical weights without that step. Point these at
# your own checkpoint (local directory or HF-authenticated mirror) via
# env if you'd rather not depend on a third-party re-hosting.
EN_INDIC_REPO = os.getenv("INDICTRANS2_EN_INDIC_REPO", "adalat-ai/ct2-rotary-indictrans2-en-indic-dist-200M")
EN_INDIC_SUBDIR = os.getenv("INDICTRANS2_EN_INDIC_SUBDIR", "en-indic-200m-ct2/ctranslate2_model")
INDIC_EN_REPO = os.getenv("INDICTRANS2_INDIC_EN_REPO", "adalat-ai/ct2-rotary-indictrans2-indic-en-dist-200M")
INDIC_EN_SUBDIR = os.getenv("INDICTRANS2_INDIC_EN_SUBDIR", "indic-en-200m-ct2/ctranslate2_model")

DEVICE = os.getenv("INDICTRANS2_DEVICE")  # "cpu" | "cuda" | unset -> auto-detect
BEAM_SIZE = int(os.getenv("INDICTRANS2_BEAM_SIZE", "5"))

# Persistent translation-result cache — file-backed (SQLite under the hood
# via diskcache), so it survives process restarts with no separate service
# to run or configure. Same relative-path convention as UPLOADS_DIR/
# CHROMA_DB_PATH in api/config.py. Deliberately NOT MongoDB: this is a pure
# inference-result cache keyed by content hash, not application data, and
# has no schema/relationship to anything the app persists there.
TRANSLATION_CACHE_DIR = os.getenv("TRANSLATION_CACHE_DIR", "cache/translations")

# Sentinel distinguishing "not cached" from "cached empty string" — a
# translation result could legitimately be "" (e.g. whitespace-only input
# handled upstream), and diskcache's own default-on-miss returns None, which
# would be indistinguishable from a real empty-string translation without a
# private sentinel like this one.
_CACHE_MISS = object()


class TranslationError(Exception):
    """Raised when the configured translation backend can't produce a translation."""


class TranslationEngine(Protocol):
    """Swappable translation backend contract."""

    def translate(self, texts: list[str], source_language: str, target_language: str) -> list[str]: ...


class IndicTrans2Engine:
    """Local, fully offline neural MT backend using AI4Bharat's IndicTrans2.

    IndicTrans2 ships as two directional models (English->Indic and
    Indic->English) rather than one bidirectional model, so this engine
    lazily loads whichever direction is first requested and caches it as
    a singleton — loading model weights per-request would make every
    translation call pay a multi-second load cost.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._loaded: dict[str, object] = {}

    @staticmethod
    def _direction_for(source_language: str, target_language: str) -> str:
        if source_language == "en" and target_language != "en":
            return "en-indic"
        if source_language != "en" and target_language == "en":
            return "indic-en"
        raise TranslationError(
            f"Unsupported translation direction: '{source_language}' -> '{target_language}' "
            "(IndicTrans2 only supports direct English<->Indic pairs)"
        )

    @staticmethod
    def _resolve_checkpoint_dir(repo_id: str, subdir: str) -> str:
        """Local directory containing this direction's CTranslate2 checkpoint.

        Tries a normal (network-checking) download first so a missing or
        updated model gets fetched; if that fails (offline machine, no
        connectivity) falls back to whatever's already in the local
        HuggingFace cache from a previous run — satisfying "works
        completely offline after the model is installed".
        """
        from huggingface_hub import snapshot_download

        try:
            local_dir = snapshot_download(repo_id=repo_id)
        except Exception:
            try:
                local_dir = snapshot_download(repo_id=repo_id, local_files_only=True)
            except Exception as e:
                raise TranslationError(
                    f"IndicTrans2 model '{repo_id}' is not available locally and couldn't be "
                    f"downloaded (no network?): {e}"
                ) from e

        return os.path.join(local_dir, subdir) if subdir else local_dir

    def _load(self, direction: str):
        if direction in self._loaded:
            return self._loaded[direction]

        with self._lock:
            if direction in self._loaded:  # re-check: another thread may have loaded it while we waited
                return self._loaded[direction]

            try:
                from services.indictrans2.model import Model
            except ImportError as e:
                raise TranslationError(
                    "IndicTrans2 dependencies are not installed - run `pip install -r requirements.txt`"
                ) from e

            repo_id, subdir = (
                (EN_INDIC_REPO, EN_INDIC_SUBDIR) if direction == "en-indic" else (INDIC_EN_REPO, INDIC_EN_SUBDIR)
            )
            ckpt_dir = self._resolve_checkpoint_dir(repo_id, subdir)
            # Defaults to CPU (matching the rest of this app's ML stack,
            # which already runs on CPU-only torch) rather than
            # auto-detecting a GPU: CTranslate2's own CUDA device-count
            # probe can report a device present but then fail to load
            # cuBLAS if the CUDA toolkit isn't fully installed, which is
            # a worse failure mode than just defaulting to CPU. Set
            # INDICTRANS2_DEVICE=cuda explicitly if you have a working
            # CUDA + cuBLAS install and want GPU inference.
            device = DEVICE or "cpu"

            try:
                model = Model(ckpt_dir, device=device, beam_size=BEAM_SIZE)
            except Exception as e:
                raise TranslationError(f"Failed to load IndicTrans2 model from '{ckpt_dir}': {e}") from e

            self._loaded[direction] = model
            return model

    def translate(self, texts: list[str], source_language: str, target_language: str) -> list[str]:
        direction = self._direction_for(source_language, target_language)
        src_code = FLORES_CODES.get(source_language)
        tgt_code = FLORES_CODES.get(target_language)
        if not src_code or not tgt_code:
            raise TranslationError(f"Unsupported language code: '{source_language}' -> '{target_language}'")

        model = self._load(direction)

        try:
            return model.batch_translate(list(texts), src_code, tgt_code)
        except TranslationError:
            raise
        except Exception as e:
            raise TranslationError(f"IndicTrans2 inference failed: {e}") from e


_engine: TranslationEngine | None = None
_engine_lock = threading.Lock()


def _get_engine() -> TranslationEngine:
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _engine = IndicTrans2Engine()
    return _engine


_cache: diskcache.Cache | None = None
_cache_lock = threading.Lock()


def _get_cache() -> diskcache.Cache:
    """Lazily opens the on-disk cache, same singleton-with-double-checked-lock
    pattern as _get_engine() above. diskcache.Cache is itself safe for
    concurrent access (SQLite-backed with file locking), including from
    multiple worker processes sharing TRANSLATION_CACHE_DIR."""
    global _cache
    if _cache is None:
        with _cache_lock:
            if _cache is None:
                _cache = diskcache.Cache(TRANSLATION_CACHE_DIR)
    return _cache


def _cache_key(source_language: str, target_language: str, text: str) -> str:
    """Deterministic cache key: SHA256(source_language + target_language +
    text). Same (source, target, text) triple always hashes to the same
    key, regardless of process/restart, which is what makes the cache
    hit-or-miss lookup below correct and stable across app restarts."""
    digest = source_language + target_language + text
    return hashlib.sha256(digest.encode("utf-8")).hexdigest()


def translate_texts(
    texts: list[str],
    target_language: str = DEFAULT_TARGET_LANGUAGE,
    source_language: str = DEFAULT_SOURCE_LANGUAGE,
) -> list[str]:
    """Batch-translate a list of strings, checking the persistent cache
    before ever calling IndicTrans2.

    Empty/whitespace-only entries are passed through unchanged (no point
    spending inference on them, and nothing to cache). For the rest: any
    text whose (source_language, target_language, text) triple is already
    in the cache is returned immediately without touching the engine; only
    genuine cache misses are sent to IndicTrans2, and their results are
    written back to the cache before returning. Raises TranslationError on
    any failure so the router can decide how to respond — this function
    does not silently fall back, so callers can't mistake a failed
    translation for a real one.
    """
    indices_to_translate = [i for i, t in enumerate(texts) if t and t.strip()]
    if not indices_to_translate:
        return list(texts)

    cache = _get_cache()
    result = list(texts)

    keys = {i: _cache_key(source_language, target_language, texts[i]) for i in indices_to_translate}
    misses = []
    for i in indices_to_translate:
        cached = cache.get(keys[i], default=_CACHE_MISS)
        if cached is _CACHE_MISS:
            misses.append(i)
        else:
            result[i] = cached

    if misses:
        engine = _get_engine()
        translated = engine.translate([texts[i] for i in misses], source_language, target_language)
        for i, t in zip(misses, translated):
            result[i] = t
            cache.set(keys[i], t)

    return result


def translate_text(
    text: str,
    target_language: str = DEFAULT_TARGET_LANGUAGE,
    source_language: str = DEFAULT_SOURCE_LANGUAGE,
) -> str:
    """Single-string convenience wrapper around translate_texts."""
    return translate_texts([text], target_language, source_language)[0]
