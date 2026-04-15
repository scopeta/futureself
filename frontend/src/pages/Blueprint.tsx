import { useEffect, useState } from "react";
import { ArrowLeft, Plus, X, Activity, Target, Leaf, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import {
  addBiomarker,
  fetchBlueprint,
  fetchQuality,
  hasSession,
  patchContext,
  patchPsych,
} from "@/lib/api";

interface BiomarkerEntry {
  marker: string;
  value: number;
  unit: string;
  date: string;
  source?: string | null;
}

interface QualityReport {
  score: number;
  flags: Array<{ field: string; severity: string; message: string }>;
  recommendations: string[];
}

interface PsychState {
  goals: string[];
  fears: string[];
  stress_level: string | null;
  mental_health_flags: string[];
}

interface ContextState {
  lifestyle_notes: string[];
  location_city: string | null;
  location_country: string | null;
  occupation: string | null;
  income_usd_annual: number | null;
  family_situation: string | null;
}

const Blueprint = () => {
  const navigate = useNavigate();

  // Backend state — full objects preserved to avoid partial overwrites
  const [biomarkers, setBiomarkers] = useState<BiomarkerEntry[]>([]);
  const [psych, setPsych] = useState<PsychState>({ goals: [], fears: [], stress_level: null, mental_health_flags: [] });
  const [ctx, setCtx] = useState<ContextState>({ lifestyle_notes: [], location_city: null, location_country: null, occupation: null, income_usd_annual: null, family_situation: null });
  const [quality, setQuality] = useState<QualityReport | null>(null);
  const [loading, setLoading] = useState(true);

  // Form state
  const [newBiomarker, setNewBiomarker] = useState({ marker: "", value: "", unit: "" });
  const [newGoal, setNewGoal] = useState("");
  const [newLifestyle, setNewLifestyle] = useState("");

  // Saving indicator per section
  const [saving, setSaving] = useState<string | null>(null);

  useEffect(() => {
    if (!hasSession()) {
      navigate("/");
      return;
    }
    Promise.all([fetchBlueprint(), fetchQuality()])
      .then(([bp, q]) => {
        const raw = bp as Record<string, Record<string, unknown>>;
        const bio = raw.bio ?? {};
        setBiomarkers((bio.biomarker_history as BiomarkerEntry[]) ?? []);
        setPsych({
          goals: (raw.psych?.goals as string[]) ?? [],
          fears: (raw.psych?.fears as string[]) ?? [],
          stress_level: (raw.psych?.stress_level as string | null) ?? null,
          mental_health_flags: (raw.psych?.mental_health_flags as string[]) ?? [],
        });
        setCtx({
          lifestyle_notes: (raw.context?.lifestyle_notes as string[]) ?? [],
          location_city: (raw.context?.location_city as string | null) ?? null,
          location_country: (raw.context?.location_country as string | null) ?? null,
          occupation: (raw.context?.occupation as string | null) ?? null,
          income_usd_annual: (raw.context?.income_usd_annual as number | null) ?? null,
          family_situation: (raw.context?.family_situation as string | null) ?? null,
        });
        setQuality(q);
      })
      .catch(() => {/* non-fatal — show empty state */})
      .finally(() => setLoading(false));
  }, [navigate]);

  const handleAddBiomarker = async () => {
    if (!newBiomarker.marker.trim() || !newBiomarker.value.trim()) return;
    const entry: BiomarkerEntry = {
      marker: newBiomarker.marker.trim(),
      value: parseFloat(newBiomarker.value),
      unit: newBiomarker.unit.trim(),
      date: new Date().toISOString().split("T")[0],
    };
    setSaving("biomarkers");
    try {
      await addBiomarker(entry);
      setBiomarkers((prev) => [...prev, entry]);
      setNewBiomarker({ marker: "", value: "", unit: "" });
    } finally {
      setSaving(null);
    }
  };

  const handleAddGoal = async () => {
    if (!newGoal.trim()) return;
    const updated = { ...psych, goals: [...psych.goals, newGoal.trim()] };
    setSaving("goals");
    try {
      await patchPsych(updated);
      setPsych(updated);
      setNewGoal("");
    } finally {
      setSaving(null);
    }
  };

  const handleRemoveGoal = async (idx: number) => {
    const updated = { ...psych, goals: psych.goals.filter((_, i) => i !== idx) };
    setSaving("goals");
    try {
      await patchPsych(updated);
      setPsych(updated);
    } finally {
      setSaving(null);
    }
  };

  const handleAddLifestyle = async () => {
    if (!newLifestyle.trim()) return;
    const updated = { ...ctx, lifestyle_notes: [...ctx.lifestyle_notes, newLifestyle.trim()] };
    setSaving("lifestyle");
    try {
      await patchContext(updated);
      setCtx(updated);
      setNewLifestyle("");
    } finally {
      setSaving(null);
    }
  };

  const handleRemoveLifestyle = async (idx: number) => {
    const updated = { ...ctx, lifestyle_notes: ctx.lifestyle_notes.filter((_, i) => i !== idx) };
    setSaving("lifestyle");
    try {
      await patchContext(updated);
      setCtx(updated);
    } finally {
      setSaving(null);
    }
  };

  const qualityColor = (score: number) =>
    score >= 70 ? "text-green-500" : score >= 40 ? "text-yellow-500" : "text-red-500";

  return (
    <div className="flex min-h-screen flex-col">
      {/* Header */}
      <div className="flex items-center gap-3 border-b px-4 py-3">
        <Button variant="ghost" size="icon" onClick={() => navigate("/")} className="shrink-0">
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <h1 className="text-sm font-medium tracking-wide text-muted-foreground">User Blueprint</h1>
        {quality && (
          <span className={`ml-auto text-sm font-semibold ${qualityColor(quality.score)}`}>
            Quality {quality.score}/100
          </span>
        )}
      </div>

      <div className="mx-auto w-full max-w-2xl flex-1 px-4 py-6">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
        >
          <h2 className="text-xl font-semibold text-foreground">Your Blueprint</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            The data that helps your Future Self give personalized guidance.
          </p>
        </motion.div>

        {/* Quality recommendations */}
        {quality && quality.recommendations.length > 0 && (
          <Card className="mt-4 border-yellow-200 bg-yellow-50 dark:border-yellow-800 dark:bg-yellow-950">
            <CardContent className="p-4 space-y-1">
              <p className="text-xs font-medium text-yellow-700 dark:text-yellow-300 flex items-center gap-1.5">
                <ShieldCheck className="h-3.5 w-3.5" /> Recommendations
              </p>
              {quality.recommendations.map((r, i) => (
                <p key={i} className="text-xs text-yellow-700 dark:text-yellow-300">• {r}</p>
              ))}
            </CardContent>
          </Card>
        )}

        {loading ? (
          <p className="mt-8 text-center text-sm text-muted-foreground">Loading…</p>
        ) : (
          <Tabs defaultValue="biomarkers" className="mt-6">
            <TabsList className="w-full">
              <TabsTrigger value="biomarkers" className="flex-1 gap-1.5">
                <Activity className="h-3.5 w-3.5" /> Biomarkers
              </TabsTrigger>
              <TabsTrigger value="goals" className="flex-1 gap-1.5">
                <Target className="h-3.5 w-3.5" /> Goals
              </TabsTrigger>
              <TabsTrigger value="lifestyle" className="flex-1 gap-1.5">
                <Leaf className="h-3.5 w-3.5" /> Lifestyle
              </TabsTrigger>
            </TabsList>

            {/* Biomarkers */}
            <TabsContent value="biomarkers" className="space-y-3 mt-4">
              {biomarkers.length === 0 && (
                <p className="text-sm text-muted-foreground text-center py-4">No biomarkers yet.</p>
              )}
              {biomarkers.map((b, i) => (
                <Card key={i} className="group">
                  <CardContent className="flex items-center justify-between p-4">
                    <div>
                      <p className="text-sm font-medium text-foreground">{b.marker}</p>
                      <p className="text-xs text-muted-foreground">
                        {b.value} {b.unit} · {b.date}
                      </p>
                    </div>
                  </CardContent>
                </Card>
              ))}
              <Card className="border-dashed">
                <CardContent className="p-4">
                  <div className="flex flex-wrap gap-2">
                    <Input
                      placeholder="Name (e.g. LDL)"
                      value={newBiomarker.marker}
                      onChange={(e) => setNewBiomarker((p) => ({ ...p, marker: e.target.value }))}
                      className="flex-1 min-w-[120px] h-9 text-sm"
                    />
                    <Input
                      placeholder="Value"
                      value={newBiomarker.value}
                      onChange={(e) => setNewBiomarker((p) => ({ ...p, value: e.target.value }))}
                      className="w-20 h-9 text-sm"
                      type="number"
                    />
                    <Input
                      placeholder="Unit"
                      value={newBiomarker.unit}
                      onChange={(e) => setNewBiomarker((p) => ({ ...p, unit: e.target.value }))}
                      className="w-20 h-9 text-sm"
                    />
                    <Button
                      size="sm"
                      onClick={handleAddBiomarker}
                      disabled={!newBiomarker.marker.trim() || !newBiomarker.value.trim() || saving === "biomarkers"}
                    >
                      <Plus className="h-3.5 w-3.5 mr-1" />
                      {saving === "biomarkers" ? "Saving…" : "Add"}
                    </Button>
                  </div>
                </CardContent>
              </Card>
            </TabsContent>

            {/* Goals */}
            <TabsContent value="goals" className="space-y-3 mt-4">
              {psych.goals.length === 0 && (
                <p className="text-sm text-muted-foreground text-center py-4">No goals yet.</p>
              )}
              {psych.goals.map((g, i) => (
                <Card key={i} className="group">
                  <CardContent className="flex items-center justify-between p-4">
                    <p className="text-sm font-medium text-foreground">{g}</p>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 opacity-0 transition-opacity group-hover:opacity-100"
                      onClick={() => handleRemoveGoal(i)}
                      disabled={saving === "goals"}
                    >
                      <X className="h-3.5 w-3.5" />
                    </Button>
                  </CardContent>
                </Card>
              ))}
              <Card className="border-dashed">
                <CardContent className="p-4">
                  <div className="flex gap-2">
                    <Input
                      placeholder="Describe your goal (e.g. Run a half marathon by Dec 2026)"
                      value={newGoal}
                      onChange={(e) => setNewGoal(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && handleAddGoal()}
                      className="flex-1 h-9 text-sm"
                    />
                    <Button
                      size="sm"
                      onClick={handleAddGoal}
                      disabled={!newGoal.trim() || saving === "goals"}
                    >
                      <Plus className="h-3.5 w-3.5 mr-1" />
                      {saving === "goals" ? "Saving…" : "Add"}
                    </Button>
                  </div>
                </CardContent>
              </Card>
            </TabsContent>

            {/* Lifestyle */}
            <TabsContent value="lifestyle" className="space-y-3 mt-4">
              {ctx.lifestyle_notes.length === 0 && (
                <p className="text-sm text-muted-foreground text-center py-4">No lifestyle notes yet.</p>
              )}
              {ctx.lifestyle_notes.map((l, i) => (
                <Card key={i} className="group">
                  <CardContent className="flex items-center justify-between p-4">
                    <p className="text-sm font-medium text-foreground">{l}</p>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 opacity-0 transition-opacity group-hover:opacity-100"
                      onClick={() => handleRemoveLifestyle(i)}
                      disabled={saving === "lifestyle"}
                    >
                      <X className="h-3.5 w-3.5" />
                    </Button>
                  </CardContent>
                </Card>
              ))}
              <Card className="border-dashed">
                <CardContent className="p-4">
                  <div className="flex gap-2">
                    <Input
                      placeholder="Add a lifestyle note (e.g. Sleep 7–8h, 10:30 PM bedtime)"
                      value={newLifestyle}
                      onChange={(e) => setNewLifestyle(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && handleAddLifestyle()}
                      className="flex-1 h-9 text-sm"
                    />
                    <Button
                      size="sm"
                      onClick={handleAddLifestyle}
                      disabled={!newLifestyle.trim() || saving === "lifestyle"}
                    >
                      <Plus className="h-3.5 w-3.5 mr-1" />
                      {saving === "lifestyle" ? "Saving…" : "Add"}
                    </Button>
                  </div>
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        )}
      </div>
    </div>
  );
};

export default Blueprint;
