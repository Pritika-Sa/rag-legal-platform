import { useEffect, useRef, useState } from "react";

// Reports whether the element attached to the returned ref has ever
// intersected the viewport, then disconnects its observer — visibility is
// a one-way latch here, not a live flag, because translation should fire
// at most once per element per session (scrolling something in and back
// out must never re-trigger a translation that already happened).
//
// rootMargin defaults to a small forward buffer so content just below the
// fold finishes translating slightly before the user actually scrolls to
// it, instead of flashing English-then-Tamil at the exact moment it
// enters view.
//
// Also used for MUI Accordion/Dialog content that starts out closed:
// MUI keeps Accordion children mounted but zero-height when collapsed
// (rather than unmounting them), so those elements never intersect the
// viewport until expanded — this hook already treats that as "not visible
// yet" with no special-casing needed, since a zero-area target only
// reports isIntersecting once it's actually given size (i.e. expanded).
export function useInViewOnce<T extends Element = HTMLDivElement>(
  rootMargin = "200px",
): [React.RefObject<T | null>, boolean] {
  const ref = useRef<T>(null);
  const [inView, setInView] = useState(false);

  useEffect(() => {
    if (inView) return;
    const el = ref.current;
    if (!el) return;

    if (typeof IntersectionObserver === "undefined") {
      // No IntersectionObserver support — degrade to "always visible"
      // rather than never translating at all.
      setInView(true);
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setInView(true);
          observer.disconnect();
        }
      },
      { rootMargin, threshold: 0.01 },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [inView, rootMargin]);

  return [ref, inView];
}
