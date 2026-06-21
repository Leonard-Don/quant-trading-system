import Surface from './Surface';
import { cn } from '../cn';

export default function PageHero({ eyebrow, title, subtitle, metrics, className }) {
  return (
    <Surface variant="raised" className={cn('p-5', className)}>
      <div className="flex flex-wrap items-start justify-between gap-5">
        <div className="min-w-0 flex-1 basis-[280px]">
          {eyebrow && (
            <div className="mb-2 text-[11px] uppercase tracking-[0.1em] text-accent">{eyebrow}</div>
          )}
          {title && <h2 className="text-[23px] font-medium leading-tight text-fg">{title}</h2>}
          {subtitle && <p className="mt-2 max-w-[420px] text-[13px] leading-relaxed text-muted">{subtitle}</p>}
        </div>
        {metrics && <div className="shrink-0">{metrics}</div>}
      </div>
    </Surface>
  );
}
