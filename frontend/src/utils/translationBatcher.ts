import { translateTexts } from "../api/translateApi";

// Session-lifetime cache: identical English strings (e.g. "High Risk",
// "Recommendation", "Authenticity" appearing on many cards) are translated
// at most once per tab session and reused everywhere else. Lives only in
// this module's memory — cleared on reload or explicitly via
// clearTranslationCache(), never written to disk/localStorage/DB.
const cache = new Map<string, string>();

// In-flight requests, keyed the same way, so two components asking for the
// same not-yet-cached string share one API call instead of firing two.
const inFlight = new Map<string, Promise<string>>();

// Requests queued for the next batched /api/translate call.
let queue: Array<{ key: string; text: string; targetLanguage: string; resolve: (v: string) => void; reject: (e: unknown) => void }> = [];

// Debounced so that toggling "View in Tamil" doesn't fire one request per
// component as each one mounts/renders — every request restarts the
// debounce window, so the whole still-settling page (including components
// whose data arrives a few renders later) collapses into one request.
// Capped by a max-wait so a page that never stops enqueueing (rare, but
// possible with rapidly re-rendering data) still flushes eventually.
const BATCH_DEBOUNCE_MS = 25;
const BATCH_MAX_WAIT_MS = 250;

let debounceTimer: ReturnType<typeof setTimeout> | null = null;
let maxWaitTimer: ReturnType<typeof setTimeout> | null = null;

function cacheKey(text: string, targetLanguage: string): string {
  return `${targetLanguage}::${text}`;
}

function scheduleFlush() {
  if (debounceTimer) clearTimeout(debounceTimer);
  debounceTimer = setTimeout(flush, BATCH_DEBOUNCE_MS);
  if (!maxWaitTimer) {
    maxWaitTimer = setTimeout(flush, BATCH_MAX_WAIT_MS);
  }
}

async function flush() {
  if (debounceTimer) {
    clearTimeout(debounceTimer);
    debounceTimer = null;
  }
  if (maxWaitTimer) {
    clearTimeout(maxWaitTimer);
    maxWaitTimer = null;
  }
  if (queue.length === 0) return;

  const batch = queue;
  queue = [];

  // Group by target language — in practice this is always a single
  // language per flush, but grouping keeps the batcher correct if a page
  // ever mixes languages.
  const byLanguage = new Map<string, typeof batch>();
  for (const item of batch) {
    const list = byLanguage.get(item.targetLanguage) ?? [];
    list.push(item);
    byLanguage.set(item.targetLanguage, list);
  }

  for (const [targetLanguage, items] of byLanguage) {
    try {
      const translations = await translateTexts(
        items.map((i) => i.text),
        targetLanguage,
      );
      items.forEach((item, i) => {
        const translated = translations[i];
        cache.set(item.key, translated);
        item.resolve(translated);
      });
    } catch (e) {
      items.forEach((item) => item.reject(e));
    } finally {
      items.forEach((item) => inFlight.delete(item.key));
    }
  }
}

// Requests translation of a single string, transparently batching,
// debouncing, and caching/deduping. Callers should catch rejections and
// fall back to the original text — this function never fabricates a
// translation on failure.
export function requestTranslation(text: string, targetLanguage: string): Promise<string> {
  const key = cacheKey(text, targetLanguage);

  const cached = cache.get(key);
  if (cached !== undefined) return Promise.resolve(cached);

  const existing = inFlight.get(key);
  if (existing) return existing;

  const promise = new Promise<string>((resolve, reject) => {
    queue.push({ key, text, targetLanguage, resolve, reject });
  });
  inFlight.set(key, promise);
  scheduleFlush();
  return promise;
}

// Called when "View in Tamil" is switched off, so translations aren't kept
// around indefinitely once they're no longer being displayed. Safe to call
// with requests still in flight — those simply repopulate an empty cache
// when they resolve, which is harmless.
export function clearTranslationCache(): void {
  cache.clear();
}
