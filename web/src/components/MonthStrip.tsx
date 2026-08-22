import { useEffect, useRef, useMemo, useCallback } from "react";

interface MonthStripProps {
  year: number;
  month: number; // 1-12
  onChange: (year: number, month: number) => void;
  disabled?: boolean;
}

interface MonthItem {
  year: number;
  month: number;
  monthName: string;
  yearLabel: string;
  label: string;
  key: string;
  isCurrent: boolean;
  isSelected: boolean;
}

export default function MonthStrip({ year, month, onChange, disabled }: MonthStripProps) {
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const itemRefs = useRef<Map<string, HTMLButtonElement>>(new Map());
  const isProgrammaticScroll = useRef(false);
  const scrollTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isInitialMount = useRef(true);

  const isTouchingRef = useRef(false);
  const isDraggingRef = useRef(false);

  const now = useMemo(() => new Date(), []);
  const currentYear = now.getFullYear();
  const currentMonth = now.getMonth() + 1;
  const isCurrentMonth = year === currentYear && month === currentMonth;

  // Generate dynamic window of months centered around selected/current date
  const months = useMemo(() => {
    const minYear = Math.min(year - 2, currentYear - 2);
    const maxYear = Math.max(year + 1, currentYear + 1);
    const list: MonthItem[] = [];

    for (let y = minYear; y <= maxYear; y++) {
      for (let m = 1; m <= 12; m++) {
        const d = new Date(y, m - 1, 1);
        const monthName = d.toLocaleDateString("en-IN", { month: "short" });
        const yearLabel = String(y);
        const label = `${monthName} ${yearLabel}`;
        const isCurrent = y === currentYear && m === currentMonth;
        const isSelected = y === year && m === month;
        list.push({
          year: y,
          month: m,
          monthName,
          yearLabel,
          label,
          key: `${y}-${m}`,
          isCurrent,
          isSelected,
        });
      }
    }
    return list;
  }, [year, currentYear, currentMonth, month]);

  const scrollToMonth = useCallback((targetYear: number, targetMonth: number, smooth = true) => {
    const key = `${targetYear}-${targetMonth}`;
    const el = itemRefs.current.get(key);
    const container = scrollContainerRef.current;

    if (!el || !container) return;

    isProgrammaticScroll.current = true;
    const targetLeft = el.offsetLeft;
    const targetWidth = el.offsetWidth;
    const containerWidth = container.offsetWidth;
    const scrollLeft = targetLeft - containerWidth / 2 + targetWidth / 2;

    container.scrollTo({
      left: scrollLeft,
      behavior: smooth ? "smooth" : "instant",
    });

    if (scrollTimeoutRef.current) clearTimeout(scrollTimeoutRef.current);
    scrollTimeoutRef.current = setTimeout(() => {
      isProgrammaticScroll.current = false;
    }, smooth ? 450 : 50);
  }, []);

  // Center selected month when year/month changes or on initial mount
  useEffect(() => {
    const smooth = !isInitialMount.current;
    scrollToMonth(year, month, smooth);
    isInitialMount.current = false;
  }, [year, month, scrollToMonth]);

  // Re-center on window resize
  useEffect(() => {
    function handleResize() {
      scrollToMonth(year, month, false);
    }
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [year, month, scrollToMonth]);

  const getClosestMonth = useCallback(() => {
    const container = scrollContainerRef.current;
    if (!container) return null;

    const containerCenter = container.scrollLeft + container.offsetWidth / 2;
    let closestItem: MonthItem | null = null;
    let minDistance = Infinity;

    for (const item of months) {
      const el = itemRefs.current.get(item.key);
      if (!el) continue;
      const itemCenter = el.offsetLeft + el.offsetWidth / 2;
      const distance = Math.abs(itemCenter - containerCenter);
      if (distance < minDistance) {
        minDistance = distance;
        closestItem = item;
      }
    }
    return closestItem;
  }, [months]);

  const commitMonthChange = useCallback(() => {
    if (isProgrammaticScroll.current) return;
    const closest = getClosestMonth();
    if (closest && (closest.year !== year || closest.month !== month)) {
      onChange(closest.year, closest.month);
    }
  }, [getClosestMonth, year, month, onChange]);

  // Handle user scroll / swipe interaction (only fires after touch lift-off or inertia end)
  const handleScroll = useCallback(() => {
    if (isProgrammaticScroll.current) return;
    if (scrollTimeoutRef.current) clearTimeout(scrollTimeoutRef.current);

    // If user is currently touching or dragging, wait until finger lifts
    if (isTouchingRef.current || isDraggingRef.current) {
      return;
    }

    scrollTimeoutRef.current = setTimeout(() => {
      if (isProgrammaticScroll.current || isTouchingRef.current || isDraggingRef.current) return;
      commitMonthChange();
    }, 140);
  }, [commitMonthChange]);

  const handleTouchStart = useCallback(() => {
    isTouchingRef.current = true;
    if (scrollTimeoutRef.current) clearTimeout(scrollTimeoutRef.current);
  }, []);

  const handleTouchEnd = useCallback(() => {
    isTouchingRef.current = false;
    isDraggingRef.current = false;
    // Allow inertia and native snap to settle slightly after touch lift-off
    if (scrollTimeoutRef.current) clearTimeout(scrollTimeoutRef.current);
    scrollTimeoutRef.current = setTimeout(() => {
      if (!isTouchingRef.current && !isDraggingRef.current) {
        commitMonthChange();
      }
    }, 120);
  }, [commitMonthChange]);

  // Native scrollend event listener for instant response when browser supports it
  useEffect(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    const onScrollEnd = () => {
      if (!isTouchingRef.current && !isDraggingRef.current && !isProgrammaticScroll.current) {
        commitMonthChange();
      }
    };
    el.addEventListener("scrollend", onScrollEnd);
    return () => el.removeEventListener("scrollend", onScrollEnd);
  }, [commitMonthChange]);

  function prevMonth() {
    if (disabled) return;
    if (month === 1) {
      onChange(year - 1, 12);
    } else {
      onChange(year, month - 1);
    }
  }

  function nextMonth() {
    if (disabled) return;
    if (month === 12) {
      onChange(year + 1, 1);
    } else {
      onChange(year, month + 1);
    }
  }

  function goToCurrentMonth() {
    if (disabled) return;
    onChange(currentYear, currentMonth);
  }

  function setRef(key: string, el: HTMLButtonElement | null) {
    if (el) {
      itemRefs.current.set(key, el);
    } else {
      itemRefs.current.delete(key);
    }
  }

  return (
    <div className="month-strip-container">
      <div className="month-strip-main">
        {/* Left chevron */}
        <button
          type="button"
          className="month-strip-arrow left"
          onClick={prevMonth}
          disabled={disabled}
          title="Previous month"
          aria-label="Previous month"
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="15 18 9 12 15 6" />
          </svg>
        </button>

        {/* Scrollable Month Strip */}
        <div
          className="month-strip-scroll"
          ref={scrollContainerRef}
          onScroll={handleScroll}
          onTouchStart={handleTouchStart}
          onTouchEnd={handleTouchEnd}
          onTouchCancel={handleTouchEnd}
          onMouseDown={() => { isDraggingRef.current = true; }}
          onMouseUp={handleTouchEnd}
          onMouseLeave={() => { if (isDraggingRef.current) handleTouchEnd(); }}
          role="region"
          aria-label="Month selector"
        >
          <div className="month-strip-track">
            {months.map((item) => {
              const isSelected = item.isSelected;
              return (
                <button
                  key={item.key}
                  ref={(el) => setRef(item.key, el)}
                  type="button"
                  className={`month-strip-item ${isSelected ? "active" : ""} ${item.isCurrent ? "is-now" : ""}`}
                  onClick={() => {
                    if (!disabled && !isSelected) {
                      onChange(item.year, item.month);
                    }
                  }}
                  disabled={disabled}
                  aria-pressed={isSelected}
                  aria-label={`${item.label}${item.isCurrent ? " (Current Month)" : ""}`}
                >
                  <span className="month-item-month">{item.monthName}</span>
                  <span className="month-item-year">{item.yearLabel}</span>
                  {isSelected && <span className="month-item-indicator" />}
                </button>
              );
            })}
          </div>
        </div>

        {/* Right chevron */}
        <button
          type="button"
          className="month-strip-arrow right"
          onClick={nextMonth}
          disabled={disabled}
          title="Next month"
          aria-label="Next month"
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="9 18 15 12 9 6" />
          </svg>
        </button>
      </div>

      {/* Contextual 'This Month' badge with reserved layout slot to prevent layout shifts */}
      <div className="month-strip-today-wrapper" aria-hidden={isCurrentMonth}>
        <button
          type="button"
          className={`month-strip-today-btn ${!isCurrentMonth ? "visible" : ""}`}
          onClick={goToCurrentMonth}
          disabled={disabled || isCurrentMonth}
          tabIndex={isCurrentMonth ? -1 : 0}
          title="Jump to current month"
        >
          <span className="today-dot" /> This Month
        </button>
      </div>
    </div>
  );
}
