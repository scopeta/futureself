import { motion } from "framer-motion";

const TypingIndicator = () => {
  return (
    <div className="flex items-start gap-3">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent shadow-sm shadow-future-glow/20">
        <motion.div
          animate={{ scale: [1, 1.2, 1] }}
          transition={{ repeat: Infinity, duration: 1.5 }}
          className="h-4 w-4 rounded-full bg-primary/60"
        />
      </div>
      <div className="flex items-center gap-1.5 rounded-2xl bg-future-surface px-4 py-3 shadow-sm shadow-future-glow/10">
        {[0, 1, 2].map((i) => (
          <motion.div
            key={i}
            className="h-2 w-2 rounded-full bg-muted-foreground/40"
            animate={{ opacity: [0.3, 1, 0.3], y: [0, -3, 0] }}
            transition={{
              repeat: Infinity,
              duration: 1,
              delay: i * 0.2,
              ease: "easeInOut",
            }}
          />
        ))}
      </div>
    </div>
  );
};

export default TypingIndicator;
