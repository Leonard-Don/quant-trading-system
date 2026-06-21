import { cn } from '../cn';

const TONES = {
  success: 'text-success',
  warn: 'text-warn',
  danger: 'text-danger',
  info: 'text-info',
  neutral: 'text-muted',
};

const DOT = {
  success: 'bg-success',
  warn: 'bg-warn',
  danger: 'bg-danger',
  info: 'bg-info',
  neutral: 'bg-muted',
};

export default function StatusPill({ tone = 'neutral', className, children }) {
  const toneClass = TONES[tone] || TONES.neutral;
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border border-hairline px-2.5 py-1 text-[12px]',
        toneClass,
        className,
      )}
    >
      <span className={cn('h-1.5 w-1.5 rounded-full', DOT[tone] || DOT.neutral)} aria-hidden="true" />
      {children}
    </span>
  );
}
