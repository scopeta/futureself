import { useMemo, useState } from "react";
import { Plus, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { addBiomarker, putBiomarkers, type BiomarkerEntry } from "@/lib/api";

interface BiomarkerHistoryProps {
  entries: BiomarkerEntry[];
  onChange: (entries: BiomarkerEntry[]) => void;
}

const today = () => new Date().toISOString().split("T")[0];

/**
 * Biomarkers as data points over time: entries are grouped by marker, each
 * marker shows its dated measurement history, and a new measurement is added
 * to the existing marker (unit inherited). Every measurement can be deleted.
 */
const BiomarkerHistory = ({ entries, onChange }: BiomarkerHistoryProps) => {
  const [saving, setSaving] = useState(false);
  // Per-marker "add measurement" inline form: marker name → {value, date}
  const [adding, setAdding] = useState<Record<string, { value: string; date: string }>>({});
  // New-marker form
  const [draft, setDraft] = useState({ marker: "", value: "", unit: "", date: today() });

  const groups = useMemo(() => {
    const byMarker = new Map<string, BiomarkerEntry[]>();
    for (const e of entries) {
      const list = byMarker.get(e.marker) ?? [];
      list.push(e);
      byMarker.set(e.marker, list);
    }
    for (const list of byMarker.values()) {
      list.sort((a, b) => a.date.localeCompare(b.date));
    }
    return [...byMarker.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [entries]);

  const addMeasurement = async (marker: string, unit: string) => {
    const form = adding[marker];
    if (!form?.value.trim()) return;
    const entry: BiomarkerEntry = {
      marker,
      value: parseFloat(form.value),
      unit,
      date: form.date || today(),
      source: null,
    };
    setSaving(true);
    try {
      await addBiomarker(entry);
      onChange([...entries, entry]);
      setAdding((p) => ({ ...p, [marker]: { value: "", date: today() } }));
    } finally {
      setSaving(false);
    }
  };

  const addNewMarker = async () => {
    if (!draft.marker.trim() || !draft.value.trim()) return;
    const entry: BiomarkerEntry = {
      marker: draft.marker.trim(),
      value: parseFloat(draft.value),
      unit: draft.unit.trim(),
      date: draft.date || today(),
      source: null,
    };
    setSaving(true);
    try {
      await addBiomarker(entry);
      onChange([...entries, entry]);
      setDraft({ marker: "", value: "", unit: "", date: today() });
    } finally {
      setSaving(false);
    }
  };

  const removeMeasurement = async (target: BiomarkerEntry) => {
    const remaining = entries.filter((e) => e !== target);
    setSaving(true);
    try {
      await putBiomarkers(remaining);
      onChange(remaining);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-3">
      {groups.length === 0 && (
        <p className="py-4 text-center text-sm text-muted-foreground">
          No measurements yet. Add your first marker below — each marker collects
          dated data points over time.
        </p>
      )}

      {groups.map(([marker, history]) => {
        const latest = history[history.length - 1];
        const form = adding[marker] ?? { value: "", date: today() };
        return (
          <Card key={marker}>
            <CardContent className="p-4">
              <div className="flex items-baseline justify-between">
                <p className="text-sm font-medium text-foreground">{marker}</p>
                <p className="text-xs text-muted-foreground">
                  latest: <span className="font-medium text-foreground">{latest.value} {latest.unit}</span> · {latest.date}
                </p>
              </div>

              <div className="mt-2 space-y-1">
                {history.map((e, i) => (
                  <div
                    key={`${e.date}-${e.value}-${i}`}
                    className="group flex items-center justify-between rounded px-2 py-1 text-xs hover:bg-accent"
                  >
                    <span className="text-muted-foreground">{e.date}</span>
                    <span className="flex items-center gap-1">
                      <span className="text-foreground">{e.value} {e.unit}</span>
                      <button
                        aria-label={`Delete ${marker} ${e.date}`}
                        className="opacity-0 transition-opacity group-hover:opacity-100"
                        onClick={() => removeMeasurement(e)}
                        disabled={saving}
                      >
                        <X className="h-3 w-3 text-muted-foreground hover:text-destructive" />
                      </button>
                    </span>
                  </div>
                ))}
              </div>

              <div className="mt-2 flex gap-2">
                <Input
                  placeholder={`New value (${latest.unit || "unit"})`}
                  type="number"
                  value={form.value}
                  onChange={(e) => setAdding((p) => ({ ...p, [marker]: { ...form, value: e.target.value } }))}
                  className="h-8 flex-1 text-xs"
                />
                <Input
                  type="date"
                  value={form.date}
                  onChange={(e) => setAdding((p) => ({ ...p, [marker]: { ...form, date: e.target.value } }))}
                  className="h-8 w-36 text-xs"
                />
                <Button
                  size="sm"
                  variant="outline"
                  className="h-8"
                  onClick={() => addMeasurement(marker, latest.unit)}
                  disabled={!form.value.trim() || saving}
                >
                  <Plus className="mr-1 h-3 w-3" /> Add
                </Button>
              </div>
            </CardContent>
          </Card>
        );
      })}

      {/* New marker */}
      <Card className="border-dashed">
        <CardContent className="p-4">
          <p className="mb-2 text-xs font-medium text-muted-foreground">New marker</p>
          <div className="flex flex-wrap gap-2">
            <Input
              placeholder="Name (e.g. Testosterone)"
              value={draft.marker}
              onChange={(e) => setDraft((p) => ({ ...p, marker: e.target.value }))}
              className="h-9 min-w-[130px] flex-1 text-sm"
            />
            <Input
              placeholder="Value"
              type="number"
              value={draft.value}
              onChange={(e) => setDraft((p) => ({ ...p, value: e.target.value }))}
              className="h-9 w-20 text-sm"
            />
            <Input
              placeholder="Unit"
              value={draft.unit}
              onChange={(e) => setDraft((p) => ({ ...p, unit: e.target.value }))}
              className="h-9 w-20 text-sm"
            />
            <Input
              type="date"
              value={draft.date}
              onChange={(e) => setDraft((p) => ({ ...p, date: e.target.value }))}
              className="h-9 w-36 text-sm"
            />
            <Button
              size="sm"
              onClick={addNewMarker}
              disabled={!draft.marker.trim() || !draft.value.trim() || saving}
            >
              <Plus className="mr-1 h-3.5 w-3.5" />
              {saving ? "Saving…" : "Add"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default BiomarkerHistory;
