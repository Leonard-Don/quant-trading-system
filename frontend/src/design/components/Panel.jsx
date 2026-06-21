import Surface from './Surface';
import { cn } from '../cn';

export default function Panel({ title, icon, actions, variant = 'flat', className, testId, children }) {
  const hasHeader = title || actions;
  return (
    <Surface variant={variant} className={cn('p-4', className)} data-testid={testId}>
      {hasHeader && (
        <div data-testid="panel-header" className="mb-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            {icon && <span className="text-accent" aria-hidden="true">{icon}</span>}
            {title && <span className="text-sm font-medium text-fg">{title}</span>}
          </div>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </div>
      )}
      {children}
    </Surface>
  );
}
