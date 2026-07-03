import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  completeOnboarding,
  hasSession,
  patchBio,
  patchContext,
  patchPsych,
} from "@/lib/api";

const SEX_OPTIONS = ["Female", "Male", "Other"];
const STRESS_OPTIONS = ["Low", "Medium", "High"];

function PillGroup({
  options,
  value,
  onChange,
}: {
  options: string[];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((opt) => (
        <button
          key={opt}
          type="button"
          onClick={() => onChange(opt)}
          className={`rounded-full border px-4 py-1.5 text-sm transition-colors ${
            value === opt
              ? "border-primary bg-primary text-primary-foreground"
              : "bg-card text-muted-foreground hover:bg-accent"
          }`}
        >
          {opt}
        </button>
      ))}
    </div>
  );
}

const Onboarding = () => {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Step 1
  const [age, setAge] = useState("");
  const [sex, setSex] = useState("");
  const [country, setCountry] = useState("");
  const [occupation, setOccupation] = useState("");
  // Step 2
  const [goalsText, setGoalsText] = useState("");
  const [stress, setStress] = useState("");

  useEffect(() => {
    if (!hasSession()) navigate("/login", { replace: true });
  }, [navigate]);

  const finish = async () => {
    setError(null);
    setBusy(true);
    try {
      const goals = goalsText
        .split("\n")
        .map((s) => s.trim())
        .filter(Boolean);
      await patchBio({
        age: age ? Number(age) : null,
        sex: sex || null,
      });
      await patchContext({
        lifestyle_notes: [],
        location_country: country || null,
        occupation: occupation || null,
      });
      await patchPsych({ goals, stress_level: stress ? stress.toLowerCase() : null });
      await completeOnboarding();
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-6">
      <motion.div
        key={step}
        initial={{ opacity: 0, x: 24 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.4 }}
        className="w-full max-w-md"
      >
        <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Step {step} of 2
        </p>

        {step === 1 ? (
          <>
            <h1 className="mb-1 text-2xl font-semibold tracking-tight text-foreground">
              A little about you
            </h1>
            <p className="mb-6 text-sm text-muted-foreground">
              This helps your future self give advice that actually fits your life.
              Everything is optional.
            </p>

            <div className="space-y-5">
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-foreground">Age</label>
                <Input
                  type="number"
                  min={0}
                  max={120}
                  value={age}
                  onChange={(e) => setAge(e.target.value)}
                  placeholder="e.g. 34"
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-foreground">Sex</label>
                <PillGroup options={SEX_OPTIONS} value={sex} onChange={setSex} />
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-foreground">Country</label>
                <Input
                  value={country}
                  onChange={(e) => setCountry(e.target.value)}
                  placeholder="e.g. Singapore"
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-foreground">Occupation</label>
                <Input
                  value={occupation}
                  onChange={(e) => setOccupation(e.target.value)}
                  placeholder="e.g. Software engineer"
                />
              </div>
            </div>

            <div className="mt-8 flex justify-end">
              <Button className="rounded-full" size="lg" onClick={() => setStep(2)}>
                Continue
              </Button>
            </div>
          </>
        ) : (
          <>
            <h1 className="mb-1 text-2xl font-semibold tracking-tight text-foreground">
              What matters to you?
            </h1>
            <p className="mb-6 text-sm text-muted-foreground">
              Your goals and stress level shape the guidance you'll get.
            </p>

            <div className="space-y-5">
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-foreground">
                  Your goals (one per line)
                </label>
                <textarea
                  value={goalsText}
                  onChange={(e) => setGoalsText(e.target.value)}
                  rows={4}
                  placeholder={"Live to 100 with energy\nLower my stress\nStay close to my family"}
                  className="w-full resize-none rounded-xl border bg-card px-4 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-foreground">
                  Current stress level
                </label>
                <PillGroup options={STRESS_OPTIONS} value={stress} onChange={setStress} />
              </div>
            </div>

            {error && (
              <p className="mt-4 text-sm text-destructive" role="alert">
                {error}
              </p>
            )}

            <div className="mt-8 flex items-center justify-between">
              <Button variant="ghost" onClick={() => setStep(1)} disabled={busy}>
                Back
              </Button>
              <Button className="rounded-full" size="lg" onClick={finish} disabled={busy}>
                {busy ? "Setting up…" : "Meet your future self"}
              </Button>
            </div>
          </>
        )}
      </motion.div>
    </div>
  );
};

export default Onboarding;
