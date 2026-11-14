import { useState } from "react";
import { api, type Profile, type Targets } from "../api";

const ACTIVITIES: { value: Profile["activity"]; label: string }[] = [
  { value: "sedentary", label: "Sedentary (desk job, little exercise)" },
  { value: "light", label: "Light (1–3 workouts/week)" },
  { value: "moderate", label: "Moderate (3–5 workouts/week)" },
  { value: "active", label: "Active (6–7 workouts/week)" },
  { value: "very_active", label: "Very active (hard training + physical job)" },
];

const GOALS: { value: Profile["goal"]; label: string }[] = [
  { value: "cut", label: "Lose fat (eat a little less)" },
  { value: "maintain", label: "Keep my weight" },
  { value: "bulk", label: "Build muscle (eat a little more)" },
];

export function ProfileForm({
  initial,
  onSaved,
}: {
  initial: Profile | null;
  onSaved: (profile: Profile, targets: Targets) => void;
}) {
  const [form, setForm] = useState<Profile>(
    initial ?? { sex: "m", age: 30, height_cm: 175, weight_kg: 75, activity: "moderate", goal: "maintain" },
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const set = <K extends keyof Profile>(key: K, value: Profile[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const res = await api.saveProfile(form);
      onSaved(res.profile, res.targets);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      className="profile-form"
      onSubmit={(e) => {
        e.preventDefault();
        save();
      }}
    >
      <p className="kicker">{initial ? "Your profile" : "One-time setup"}</p>
      <h1 className="display">Your daily targets</h1>
      <p className="lead">
        Forkcast uses this only to work out how many calories and how much protein, carbs and fat suit you each
        day: a standard formula (Mifflin-St Jeor) for your body, adjusted for your activity and goal.
        {initial && " Targets update when you save."}
      </p>
      <div className="form-grid">
      <label>
        Sex
        <select value={form.sex} onChange={(e) => set("sex", e.target.value as Profile["sex"])}>
          <option value="m">Male</option>
          <option value="f">Female</option>
        </select>
      </label>
      <label>
        Age
        <input type="number" min={14} max={100} value={form.age} onChange={(e) => set("age", Number(e.target.value))} />
      </label>
      <label>
        Height (cm)
        <input type="number" min={120} max={230} value={form.height_cm} onChange={(e) => set("height_cm", Number(e.target.value))} />
      </label>
      <label>
        Weight (kg)
        <input type="number" min={35} max={250} value={form.weight_kg} onChange={(e) => set("weight_kg", Number(e.target.value))} />
      </label>
      </div>
      <label>
        Activity
        <select value={form.activity} onChange={(e) => set("activity", e.target.value as Profile["activity"])}>
          {ACTIVITIES.map((a) => (
            <option key={a.value} value={a.value}>{a.label}</option>
          ))}
        </select>
      </label>
      <label>
        Goal
        <select value={form.goal} onChange={(e) => set("goal", e.target.value as Profile["goal"])}>
          {GOALS.map((g) => (
            <option key={g.value} value={g.value}>{g.label}</option>
          ))}
        </select>
      </label>
      {error && <p className="feedback error">{error}</p>}
      <button type="submit" className="btn" disabled={busy}>
        {busy ? "Saving…" : "Save and work out my targets"}
      </button>
    </form>
  );
}
