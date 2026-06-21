import { cn } from '../cn';

export default function SectionHeader({ eyebrow, title, actions, className }) {
  return (
    <div className={cn('flex items-end justify-between gap-3', className)}>
      <div>
        {eyebrow && (
          <div className="text-xs uppercase tracking-widest text-subtle">{eyebrow}</div>
        )}
        {title && <div className="mt-1 text-sm font-medium text-fg">{title}</div>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}
