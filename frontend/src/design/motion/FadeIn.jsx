import { motion, useReducedMotion } from 'framer-motion';

export default function FadeIn({ y = 8, delay = 0, className, children }) {
  const reduce = useReducedMotion();
  if (reduce) return <div className={className}>{children}</div>;
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28, ease: 'easeOut', delay }}
    >
      {children}
    </motion.div>
  );
}
