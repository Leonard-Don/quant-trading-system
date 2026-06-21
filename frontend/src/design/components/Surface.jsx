import { cn } from '../cn';

const VARIANTS = {
  flat: 'bg-surface',
  raised: 'bg-raised',
  inset: 'bg-inset',
};

export default function Surface({ variant = 'flat', className, children, ...rest }) {
  return (
    <div
      className={cn('rounded-[14px] border border-hairline', VARIANTS[variant] || VARIANTS.flat, className)}
      {...rest}
    >
      {children}
    </div>
  );
}
