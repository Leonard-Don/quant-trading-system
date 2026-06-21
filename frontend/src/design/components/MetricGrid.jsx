import { cn } from '../cn';

export default function MetricGrid({ className, children }) {
  return (
    <div
      data-testid="metric-grid"
      className={cn('grid grid-cols-2 gap-2.5 sm:grid-cols-4', className)}
    >
      {children}
    </div>
  );
}
