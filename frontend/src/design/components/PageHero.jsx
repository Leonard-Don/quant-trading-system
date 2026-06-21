import Surface from './Surface';
import { cn } from '../cn';

export default function PageHero({ eyebrow, title, subtitle, metrics, className }) {
  return (
    <Surface variant="raised" className={cn('p-5', className)}>
      <div className="flex flex-wrap items-start justify-between gap-5">
        <div className="min-w-0 flex-1 basis-72">
          {eyebrow && (
            <div className="mb-2 text-xs uppercase tracking-widest text-accent">{eyebrow}</div>
          )}
          {title && <h2 className="text-2xl font-medium leading-tight text-fg">{title}</h2>}
          {subtitle && <p className="mt-2 max-w-md text-sm leading-relaxed text-muted">{subtitle}</p>}
        </div>
        {metrics && <div className="shrink-0">{metrics}</div>}
      </div>
    </Surface>
  );
}
