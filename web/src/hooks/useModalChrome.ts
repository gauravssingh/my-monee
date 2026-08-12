import { useCallback, useEffect, useRef, type MouseEvent, type RefObject } from "react";

/** Lock page scroll and Escape-to-close while a modal is open, without jumping scroll. */
export function useModalChrome(
  open: boolean,
  onClose: () => void,
  focusRef?: RefObject<HTMLElement | null>,
) {
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    if (!open) return;
    const scrollY = window.scrollY;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const focusId = window.requestAnimationFrame(() => {
      focusRef?.current?.focus({ preventScroll: true });
    });

    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCloseRef.current();
    };
    window.addEventListener("keydown", onKey);

    return () => {
      window.cancelAnimationFrame(focusId);
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
      window.scrollTo(0, scrollY);
    };
  }, [open, focusRef]);
}

/**
 * Backdrop click-to-close that ignores the opening click/tap
 * (portal mounts under the cursor and would otherwise close immediately).
 */
export function useBackdropClose(open: boolean, onClose: () => void) {
  const armedRef = useRef(false);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    if (!open) {
      armedRef.current = false;
      return;
    }
    armedRef.current = false;
    const id = window.setTimeout(() => {
      armedRef.current = true;
    }, 120);
    return () => window.clearTimeout(id);
  }, [open]);

  return useCallback((event: MouseEvent<HTMLDivElement>) => {
    if (!armedRef.current) return;
    if (event.target !== event.currentTarget) return;
    onCloseRef.current();
  }, []);
}
