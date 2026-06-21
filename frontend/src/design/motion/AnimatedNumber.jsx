import { useEffect, useRef, useState } from 'react';

const prefersReduced = () =>
  typeof window !== 'undefined' &&
  typeof window.matchMedia === 'function' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches;

export default function AnimatedNumber({ value, duration = 600, format = (n) => String(Math.round(n)), className }) {
  const [display, setDisplay] = useState(() => (prefersReduced() ? value : 0));
  const rafRef = useRef(0);

  useEffect(() => {
    if (prefersReduced()) {
      setDisplay(value);
      return undefined;
    }
    const from = 0;
    const start = performance.now();
    const tick = (now) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      setDisplay(from + (value - from) * eased);
      if (t < 1) rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
  }, [value, duration]);

  return <span className={className}>{format(display)}</span>;
}
