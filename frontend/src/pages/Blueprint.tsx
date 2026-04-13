import { useState } from "react";
import { ArrowLeft, Plus, X, Activity, Target, Leaf } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";

interface Biomarker {
  id: string;
  name: string;
  value: string;
  unit: string;
  date: string;
}

interface Goal {
  id: string;
  category: string;
  text: string;
  target: string;
}

interface LifestyleEntry {
  id: string;
  category: string;
  detail: string;
}

const LIFESTYLE_CATEGORIES = ["Sleep", "Nutrition", "Exercise", "Stress", "Social", "Environment"];

const Blueprint = () => {
  const navigate = useNavigate();

  const [biomarkers, setBiomarkers] = useState<Biomarker[]>([
    { id: "1", name: "Resting Heart Rate", value: "68", unit: "bpm", date: "2026-04-10" },
    { id: "2", name: "HbA1c", value: "5.2", unit: "%", date: "2026-03-28" },
  ]);
  const [goals, setGoals] = useState<Goal[]>([
    { id: "1", category: "Physical", text: "Run a half marathon", target: "Dec 2026" },
    { id: "2", category: "Mental", text: "Daily meditation practice", target: "30 days streak" },
  ]);
  const [lifestyle, setLifestyle] = useState<LifestyleEntry[]>([
    { id: "1", category: "Sleep", detail: "7–8 hours, 10:30 PM bedtime" },
    { id: "2", category: "Nutrition", detail: "Mostly plant-based, intermittent fasting 16:8" },
  ]);

  // New item forms
  const [newBiomarker, setNewBiomarker] = useState({ name: "", value: "", unit: "" });
  const [newGoal, setNewGoal] = useState({ category: "Physical", text: "", target: "" });
  const [newLifestyle, setNewLifestyle] = useState({ category: "Sleep", detail: "" });

  const addBiomarker = () => {
    if (!newBiomarker.name.trim() || !newBiomarker.value.trim()) return;
    setBiomarkers((prev) => [
      ...prev,
      { ...newBiomarker, id: Date.now().toString(), date: new Date().toISOString().split("T")[0] },
    ]);
    setNewBiomarker({ name: "", value: "", unit: "" });
  };

  const addGoal = () => {
    if (!newGoal.text.trim()) return;
    setGoals((prev) => [...prev, { ...newGoal, id: Date.now().toString() }]);
    setNewGoal({ category: "Physical", text: "", target: "" });
  };

  const addLifestyle = () => {
    if (!newLifestyle.detail.trim()) return;
    setLifestyle((prev) => [...prev, { ...newLifestyle, id: Date.now().toString() }]);
    setNewLifestyle({ category: "Sleep", detail: "" });
  };

  const remove = <T extends { id: string }>(
    setter: React.Dispatch<React.SetStateAction<T[]>>,
    id: string
  ) => setter((prev) => prev.filter((item) => item.id !== id));

  return (
    <div className="flex min-h-screen flex-col">
      {/* Header */}
      <div className="flex items-center gap-3 border-b px-4 py-3">
        <Button variant="ghost" size="icon" onClick={() => navigate("/")} className="shrink-0">
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <h1 className="text-sm font-medium tracking-wide text-muted-foreground">
          User Blueprint
        </h1>
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
            {biomarkers.map((b) => (
              <Card key={b.id} className="group">
                <CardContent className="flex items-center justify-between p-4">
                  <div>
                    <p className="text-sm font-medium text-foreground">{b.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {b.value} {b.unit} · {b.date}
                    </p>
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 opacity-0 transition-opacity group-hover:opacity-100"
                    onClick={() => remove(setBiomarkers, b.id)}
                  >
                    <X className="h-3.5 w-3.5" />
                  </Button>
                </CardContent>
              </Card>
            ))}
            <Card className="border-dashed">
              <CardContent className="p-4">
                <div className="flex flex-wrap gap-2">
                  <Input
                    placeholder="Name (e.g. LDL)"
                    value={newBiomarker.name}
                    onChange={(e) => setNewBiomarker((p) => ({ ...p, name: e.target.value }))}
                    className="flex-1 min-w-[120px] h-9 text-sm"
                  />
                  <Input
                    placeholder="Value"
                    value={newBiomarker.value}
                    onChange={(e) => setNewBiomarker((p) => ({ ...p, value: e.target.value }))}
                    className="w-20 h-9 text-sm"
                  />
                  <Input
                    placeholder="Unit"
                    value={newBiomarker.unit}
                    onChange={(e) => setNewBiomarker((p) => ({ ...p, unit: e.target.value }))}
                    className="w-20 h-9 text-sm"
                  />
                  <Button size="sm" onClick={addBiomarker} disabled={!newBiomarker.name.trim() || !newBiomarker.value.trim()}>
                    <Plus className="h-3.5 w-3.5 mr-1" /> Add
                  </Button>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Goals */}
          <TabsContent value="goals" className="space-y-3 mt-4">
            {goals.map((g) => (
              <Card key={g.id} className="group">
                <CardContent className="flex items-center justify-between p-4">
                  <div>
                    <p className="text-sm font-medium text-foreground">{g.text}</p>
                    <p className="text-xs text-muted-foreground">
                      {g.category} · Target: {g.target}
                    </p>
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 opacity-0 transition-opacity group-hover:opacity-100"
                    onClick={() => remove(setGoals, g.id)}
                  >
                    <X className="h-3.5 w-3.5" />
                  </Button>
                </CardContent>
              </Card>
            ))}
            <Card className="border-dashed">
              <CardContent className="p-4">
                <div className="flex flex-wrap gap-2">
                  <select
                    value={newGoal.category}
                    onChange={(e) => setNewGoal((p) => ({ ...p, category: e.target.value }))}
                    className="h-9 rounded-md border border-input bg-background px-3 text-sm"
                  >
                    {["Physical", "Mental", "Financial", "Social", "Environmental"].map((c) => (
                      <option key={c}>{c}</option>
                    ))}
                  </select>
                  <Input
                    placeholder="Goal description"
                    value={newGoal.text}
                    onChange={(e) => setNewGoal((p) => ({ ...p, text: e.target.value }))}
                    className="flex-1 min-w-[140px] h-9 text-sm"
                  />
                  <Input
                    placeholder="Target"
                    value={newGoal.target}
                    onChange={(e) => setNewGoal((p) => ({ ...p, target: e.target.value }))}
                    className="w-28 h-9 text-sm"
                  />
                  <Button size="sm" onClick={addGoal} disabled={!newGoal.text.trim()}>
                    <Plus className="h-3.5 w-3.5 mr-1" /> Add
                  </Button>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Lifestyle */}
          <TabsContent value="lifestyle" className="space-y-3 mt-4">
            {lifestyle.map((l) => (
              <Card key={l.id} className="group">
                <CardContent className="flex items-center justify-between p-4">
                  <div>
                    <p className="text-sm font-medium text-foreground">{l.detail}</p>
                    <p className="text-xs text-muted-foreground">{l.category}</p>
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 opacity-0 transition-opacity group-hover:opacity-100"
                    onClick={() => remove(setLifestyle, l.id)}
                  >
                    <X className="h-3.5 w-3.5" />
                  </Button>
                </CardContent>
              </Card>
            ))}
            <Card className="border-dashed">
              <CardContent className="p-4">
                <div className="flex flex-wrap gap-2">
                  <select
                    value={newLifestyle.category}
                    onChange={(e) => setNewLifestyle((p) => ({ ...p, category: e.target.value }))}
                    className="h-9 rounded-md border border-input bg-background px-3 text-sm"
                  >
                    {LIFESTYLE_CATEGORIES.map((c) => (
                      <option key={c}>{c}</option>
                    ))}
                  </select>
                  <Input
                    placeholder="Details (e.g. 8 hours sleep, 10 PM)"
                    value={newLifestyle.detail}
                    onChange={(e) => setNewLifestyle((p) => ({ ...p, detail: e.target.value }))}
                    className="flex-1 min-w-[180px] h-9 text-sm"
                  />
                  <Button size="sm" onClick={addLifestyle} disabled={!newLifestyle.detail.trim()}>
                    <Plus className="h-3.5 w-3.5 mr-1" /> Add
                  </Button>
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
};

export default Blueprint;
