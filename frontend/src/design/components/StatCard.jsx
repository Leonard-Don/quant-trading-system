import { cn } from '../cn';

export default function StatCard({ label, value, delta, accent = false, className }) {
  return (
    <div className={cn('rounded-md border border-hairline bg-surface px-3 py-2.5', className)}>
      <div className="text-xs uppercase tracking-widest text-subtle">{label}</div>
      <div className="mt-0.5 flex items-baseline gap-2">
        <span className={cn('text-2xl font-medium tabular-nums', accent ? 'text-accent' : 'text-fg')}>
          {value}
        </span>
        {delta != null && <span className="text-xs tabular-nums text-muted">{delta}</span>}
      </div>
    </div>
  );
}
