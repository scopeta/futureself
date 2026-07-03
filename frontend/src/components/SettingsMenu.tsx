import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Eraser,
  ListChecks,
  LogOut,
  MessageCircle,
  Settings,
  Trash2,
  User,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  clearConversation,
  confirmFacts,
  fetchFactCandidates,
  logout,
  resetAllData,
  whatsappLink,
  whatsappStatus,
  whatsappUnlink,
} from "@/lib/api";

interface SettingsMenuProps {
  /** Called after the conversation history is cleared, so the chat UI can reset. */
  onConversationCleared: () => void;
}

const SettingsMenu = ({ onConversationCleared }: SettingsMenuProps) => {
  const navigate = useNavigate();

  // Delete-everything dialog
  const [confirmReset, setConfirmReset] = useState(false);
  const [resetting, setResetting] = useState(false);
  // Clear-conversation dialog
  const [confirmClear, setConfirmClear] = useState(false);
  const [clearing, setClearing] = useState(false);
  // Facts dialog
  const [factsOpen, setFactsOpen] = useState(false);
  const [factsLoading, setFactsLoading] = useState(false);
  const [candidates, setCandidates] = useState<string[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [pruneAfter, setPruneAfter] = useState(true);
  const [factsSaving, setFactsSaving] = useState(false);
  const [factsError, setFactsError] = useState<string | null>(null);
  // WhatsApp dialog
  const [waOpen, setWaOpen] = useState(false);
  const [waLoading, setWaLoading] = useState(false);
  const [waEnabled, setWaEnabled] = useState(false);
  const [waPhone, setWaPhone] = useState<string | null>(null);
  const [waCode, setWaCode] = useState<string | null>(null);
  const [waError, setWaError] = useState<string | null>(null);

  const handleReset = async () => {
    setResetting(true);
    try {
      await resetAllData();
      navigate("/onboarding", { replace: true });
    } catch {
      setResetting(false);
      setConfirmReset(false);
    }
  };

  const handleClear = async () => {
    setClearing(true);
    try {
      await clearConversation();
      onConversationCleared();
    } finally {
      setClearing(false);
      setConfirmClear(false);
    }
  };

  const openFacts = async () => {
    setFactsOpen(true);
    setFactsLoading(true);
    setFactsError(null);
    setCandidates([]);
    try {
      const { candidates: found, degraded } = await fetchFactCandidates();
      setCandidates(found);
      setSelected(new Set(found));
      if (degraded) setFactsError("Extraction was incomplete — you can retry later.");
    } catch (err) {
      setFactsError(err instanceof Error ? err.message : "Extraction failed.");
    } finally {
      setFactsLoading(false);
    }
  };

  const saveFacts = async () => {
    setFactsSaving(true);
    try {
      await confirmFacts([...selected], pruneAfter);
      if (pruneAfter) onConversationCleared();
      setFactsOpen(false);
    } catch (err) {
      setFactsError(err instanceof Error ? err.message : "Saving failed.");
    } finally {
      setFactsSaving(false);
    }
  };

  const openWhatsApp = async () => {
    setWaOpen(true);
    setWaLoading(true);
    setWaError(null);
    setWaCode(null);
    try {
      const status = await whatsappStatus();
      setWaEnabled(status.enabled);
      setWaPhone(status.phone);
    } catch {
      setWaError("Could not load WhatsApp status.");
    } finally {
      setWaLoading(false);
    }
  };

  const generateCode = async () => {
    setWaError(null);
    try {
      const { code } = await whatsappLink();
      setWaCode(code);
    } catch (err) {
      setWaError(err instanceof Error ? err.message : "Could not generate a code.");
    }
  };

  const unlink = async () => {
    await whatsappUnlink();
    setWaPhone(null);
    setWaCode(null);
  };

  const handleLogout = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon" className="h-9 w-9" aria-label="Menu">
            <Settings className="h-4 w-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-60">
          <DropdownMenuItem onClick={() => navigate("/blueprint")}>
            <User className="mr-2 h-4 w-4" /> Blueprint
          </DropdownMenuItem>
          <DropdownMenuItem onClick={openWhatsApp}>
            <MessageCircle className="mr-2 h-4 w-4" /> Link WhatsApp
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={openFacts}>
            <ListChecks className="mr-2 h-4 w-4" /> Review &amp; save facts
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => setConfirmClear(true)}>
            <Eraser className="mr-2 h-4 w-4" /> Clear conversation
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            className="text-destructive focus:text-destructive"
            onClick={() => setConfirmReset(true)}
          >
            <Trash2 className="mr-2 h-4 w-4" /> Delete all data &amp; restart
          </DropdownMenuItem>
          <DropdownMenuItem onClick={handleLogout}>
            <LogOut className="mr-2 h-4 w-4" /> Log out
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      {/* Clear conversation (keeps blueprint + onboarding) */}
      <AlertDialog open={confirmClear} onOpenChange={setConfirmClear}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Clear the conversation?</AlertDialogTitle>
            <AlertDialogDescription>
              This deletes your conversation history. Your blueprint (profile, goals,
              measurements, saved facts) is kept — no re-onboarding needed. Tip: run
              “Review &amp; save facts” first so nothing important is lost.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={clearing}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => {
                e.preventDefault();
                handleClear();
              }}
              disabled={clearing}
            >
              {clearing ? "Clearing…" : "Clear conversation"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Delete everything */}
      <AlertDialog open={confirmReset} onOpenChange={setConfirmReset}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete all your data?</AlertDialogTitle>
            <AlertDialogDescription>
              This permanently deletes your blueprint and conversation history, then
              restarts onboarding. Your account stays signed in, but this can't be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={resetting}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => {
                e.preventDefault();
                handleReset();
              }}
              disabled={resetting}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {resetting ? "Deleting…" : "Delete everything"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Review & save facts */}
      <Dialog open={factsOpen} onOpenChange={setFactsOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Review &amp; save facts</DialogTitle>
            <DialogDescription>
              Distilled from your recent conversation. Save the ones that are true —
              they become part of your blueprint so the conversation can be pruned
              without losing what matters.
            </DialogDescription>
          </DialogHeader>

          {factsLoading ? (
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

          {!factsLoading && (
            <label className="flex cursor-pointer items-center gap-2 text-sm text-muted-foreground">
              <input
                type="checkbox"
                checked={pruneAfter}
                onChange={(e) => setPruneAfter(e.target.checked)}
              />
              Clear the conversation after saving
            </label>
          )}

          {factsError && <p className="text-sm text-destructive">{factsError}</p>}

          <DialogFooter>
            <Button variant="ghost" onClick={() => setFactsOpen(false)} disabled={factsSaving}>
              Cancel
            </Button>
            <Button
              onClick={saveFacts}
              disabled={factsLoading || factsSaving || (candidates.length === 0 && !pruneAfter)}
            >
              {factsSaving
                ? "Saving…"
                : candidates.length === 0
                  ? "Clear conversation"
                  : `Save ${selected.size} fact${selected.size === 1 ? "" : "s"}`}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Link WhatsApp */}
      <Dialog open={waOpen} onOpenChange={setWaOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>WhatsApp</DialogTitle>
            <DialogDescription>
              Talk to your future self from WhatsApp — same profile, same conversation.
            </DialogDescription>
          </DialogHeader>

          {waLoading ? (
            <div className="flex justify-center py-6">
              <div className="h-6 w-6 animate-spin rounded-full border-2 border-muted border-t-primary" />
            </div>
          ) : !waEnabled ? (
            <p className="py-2 text-sm text-muted-foreground">
              WhatsApp isn't configured on this deployment yet.
            </p>
          ) : waPhone ? (
            <div className="space-y-3 py-1">
              <p className="text-sm">
                Linked to <span className="font-medium">{waPhone}</span>
              </p>
              <Button variant="outline" onClick={unlink}>
                Unlink this number
              </Button>
            </div>
          ) : (
            <div className="space-y-3 py-1">
              {waCode ? (
                <>
                  <p className="text-sm">
                    Send this message to the FutureSelf WhatsApp number:
                  </p>
                  <p className="rounded-lg bg-accent px-4 py-3 text-center font-mono text-lg tracking-widest">
                    LINK {waCode}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    The code is one-time. Once you send it, this account is linked to
                    your WhatsApp number.
                  </p>
                </>
              ) : (
                <Button onClick={generateCode}>Generate link code</Button>
              )}
            </div>
          )}

          {waError && <p className="text-sm text-destructive">{waError}</p>}
        </DialogContent>
      </Dialog>
    </>
  );
};

export default SettingsMenu;
