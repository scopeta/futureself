import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { confirmFacts, fetchFactCandidates } from "@/lib/api";

interface FactsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Called when the conversation was pruned as part of saving. */
  onConversationCleared: () => void;
}

/** Review & save facts: distill → user picks → confirm → optional prune. */
const FactsDialog = ({ open, onOpenChange, onConversationCleared }: FactsDialogProps) => {
  const [loading, setLoading] = useState(false);
  const [candidates, setCandidates] = useState<string[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [pruneAfter, setPruneAfter] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    setError(null);
    setCandidates([]);
    fetchFactCandidates()
      .then(({ candidates: found, degraded }) => {
        setCandidates(found);
        setSelected(new Set(found));
        if (degraded) setError("Extraction was incomplete — you can retry later.");
      })
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Extraction failed."),
      )
      .finally(() => setLoading(false));
  }, [open]);

  const save = async () => {
    setSaving(true);
    try {
      await confirmFacts([...selected], pruneAfter);
      if (pruneAfter) onConversationCleared();
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Saving failed.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Review &amp; save facts</DialogTitle>
          <DialogDescription>
            Distilled from your recent conversation. Save the ones that are true —
            they become part of your blueprint so the conversation can be pruned
            without losing what matters.
          </DialogDescription>
        </DialogHeader>

        {loading ? (
          <div className="flex justify-center py-6">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-muted border-t-primary" />
          </div>
        ) : candidates.length === 0 ? (
          <p className="py-2 text-sm text-muted-foreground">
            Nothing new to save — either the conversation is empty or everything
            durable is already in your blueprint.
          </p>
        ) : (
          <div className="max-h-64 space-y-2 overflow-y-auto py-1">
            {candidates.map((fact) => (
              <label key={fact} className="flex cursor-pointer items-start gap-2 text-sm">
                <input
                  type="checkbox"
                  className="mt-0.5"
                  checked={selected.has(fact)}
                  onChange={(e) => {
                    const next = new Set(selected);
                    if (e.target.checked) next.add(fact);
                    else next.delete(fact);
                    setSelected(next);
                  }}
                />
                <span>{fact}</span>
              </label>
            ))}
          </div>
        )}

        {!loading && (
          <label className="flex cursor-pointer items-center gap-2 text-sm text-muted-foreground">
            <input
              type="checkbox"
              checked={pruneAfter}
              onChange={(e) => setPruneAfter(e.target.checked)}
            />
            Clear the conversation after saving
          </label>
        )}

        {error && <p className="text-sm text-destructive">{error}</p>}

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={saving}>
            Cancel
          </Button>
          <Button
            onClick={save}
            disabled={loading || saving || (candidates.length === 0 && !pruneAfter)}
          >
            {saving
              ? "Saving…"
              : candidates.length === 0
                ? "Clear conversation"
                : `Save ${selected.size} fact${selected.size === 1 ? "" : "s"}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default FactsDialog;
