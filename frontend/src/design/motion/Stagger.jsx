import { motion, useReducedMotion } from 'framer-motion';
import { Children } from 'react';

export default function Stagger({ step = 0.06, className, children }) {
  const reduce = useReducedMotion();
  if (reduce) return <div className={className}>{children}</div>;
  return (
    <motion.div
      className={className}
      initial="hidden"
      animate="show"
      variants={{ show: { transition: { staggerChildren: step } } }}
    >
      {Children.map(children, (child, i) => (
        <motion.div
          key={i}
          variants={{ hidden: { opacity: 0, y: 8 }, show: { opacity: 1, y: 0 } }}
          transition={{ duration: 0.28, ease: 'easeOut' }}
        >
          {child}
        </motion.div>
      ))}
    </motion.div>
  );
}
