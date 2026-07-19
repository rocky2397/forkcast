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
  { value: "cut", label: "Cut (lose fat)" },
  { value: "maintain", label: "Maintain" },
  { value: "bulk", label: "Bulk (build muscle)" },
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
    <div className="profile-form">
      <p className="profile-intro">
        {initial ? "Update your profile — targets recompute on save." : "Tell Forkcast about yourself and it will suggest your daily calorie and macro targets."}
      </p>
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
      {error && <p className="feedback">{error}</p>}
      <button className="cooked" onClick={save} disabled={busy}>
        {busy ? "Saving…" : "Save & compute my targets"}
      </button>
    </div>
  );
}
