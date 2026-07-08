import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Lightbulb, X } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { fetchNudges, type Nudge } from "@/lib/api";

const DISMISSED_KEY = "fs_dismissed_nudges";

function dismissedIds(): Set<string> {
  try {
    return new Set(JSON.parse(localStorage.getItem(DISMISSED_KEY) ?? "[]"));
  } catch {
    return new Set();
  }
}

function dismiss(id: string): void {
  const ids = dismissedIds();
  ids.add(id);
  // Keep the list bounded — old ids stop mattering once their nudge is gone.
  localStorage.setItem(DISMISSED_KEY, JSON.stringify([...ids].slice(-50)));
}

interface CuratorBannerProps {
  /** Bump to refetch (e.g. after the conversation is cleared). */
  refreshSignal: number;
  onReviewFacts: () => void;
}

/**
 * Shows the top non-dismissed curator nudge as a slim, dismissible banner.
 * Neutral copy — the curator is a policy layer, not a second persona.
 */
const CuratorBanner = ({ refreshSignal, onReviewFacts }: CuratorBannerProps) => {
  const navigate = useNavigate();
  const [nudge, setNudge] = useState<Nudge | null>(null);

  useEffect(() => {
    fetchNudges()
      .then((nudges) => {
        const seen = dismissedIds();
        setNudge(nudges.find((n) => !seen.has(n.id)) ?? null);
      })
      .catch(() => setNudge(null)); // nudges are never worth an error state
  }, [refreshSignal]);

  const act = () => {
    if (!nudge) return;
    if (nudge.action === "review_facts") onReviewFacts();
    else navigate("/blueprint");
    dismiss(nudge.id);
    setNudge(null);
  };

  const close = () => {
    if (!nudge) return;
    dismiss(nudge.id);
    setNudge(null);
  };

  return (
    <AnimatePresence>
      {nudge && (
        <motion.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          className="border-b bg-accent/60 px-4 py-2"
        >
          <div className="mx-auto flex max-w-2xl items-center gap-2">
            <Lightbulb className="h-3.5 w-3.5 shrink-0 text-primary" />
            <p className="flex-1 text-xs text-muted-foreground">{nudge.message}</p>
            <Button size="sm" variant="outline" className="h-7 text-xs" onClick={act}>
              {nudge.action === "review_facts" ? "Review facts" : "Open blueprint"}
            </Button>
            <button aria-label="Dismiss" onClick={close}>
              <X className="h-3.5 w-3.5 text-muted-foreground hover:text-foreground" />
            </button>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};

export default CuratorBanner;
