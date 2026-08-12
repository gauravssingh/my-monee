import { useCallback, useEffect, useRef, useState } from "react";

/** First call arms a pending confirmation; a second call within `timeoutMs` runs `action`. */
export function useConfirm(action: () => void, timeoutMs = 2500) {
  const [armed, setArmed] = useState(false);
  const timerRef = useRef<number | null>(null);
  const actionRef = useRef(action);
  actionRef.current = action;

  useEffect(() => {
    return () => {
      if (timerRef.current != null) window.clearTimeout(timerRef.current);
    };
  }, []);

  const trigger = useCallback(() => {
    if (armed) {
      if (timerRef.current != null) window.clearTimeout(timerRef.current);
      setArmed(false);
      actionRef.current();
      return;
    }
    setArmed(true);
    timerRef.current = window.setTimeout(() => setArmed(false), timeoutMs);
  }, [armed, timeoutMs]);

  return { armed, trigger };
}
