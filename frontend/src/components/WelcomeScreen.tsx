import { motion } from "framer-motion";
import { Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";

interface WelcomeScreenProps {
  onStart: () => void;
}

const WelcomeScreen = ({ onStart }: WelcomeScreenProps) => {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-6">
      <motion.div
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.8, ease: "easeOut" }}
        className="flex max-w-md flex-col items-center text-center"
      >
        <motion.div
          initial={{ scale: 0.8, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ delay: 0.2, duration: 0.6 }}
          className="mb-8 flex h-20 w-20 items-center justify-center rounded-full bg-accent"
        >
          <Sparkles className="h-10 w-10 text-primary" />
        </motion.div>

        <motion.h1
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.4, duration: 0.6 }}
          className="mb-4 text-3xl font-semibold tracking-tight text-foreground"
        >
          FutureSelf
        </motion.h1>

        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.6, duration: 0.6 }}
          className="mb-2 text-lg font-light leading-relaxed text-muted-foreground"
        >
          I am you, from the future.
        </motion.p>

        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.8, duration: 0.6 }}
          className="mb-10 text-base font-light leading-relaxed text-muted-foreground"
        >
          Let's talk about your path to a long, vibrant life.
        </motion.p>

        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 1, duration: 0.5 }}
        >
          <Button
            onClick={onStart}
            size="lg"
            className="rounded-full px-8 text-base font-medium shadow-lg shadow-primary/20 transition-all hover:shadow-xl hover:shadow-primary/30"
          >
            Begin the conversation
          </Button>
        </motion.div>
      </motion.div>
    </div>
  );
};

export default WelcomeScreen;
