import { cn } from '../cn';

export default function Toolbar({ className, children }) {
  return (
    <div data-testid="toolbar" className={cn('flex flex-wrap items-center gap-2', className)}>
      {children}
    </div>
  );
}
