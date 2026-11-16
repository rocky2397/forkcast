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
  // D39: the usual healthy range for this height (BMI 18.5 to 25), as context
  const m2 = (form.height_cm / 100) ** 2;
  const low = Math.ceil(18.5 * m2 * 2) / 2;
  const high = Math.floor(25 * m2 * 2) / 2;
  const hasGoal = form.goal_weight_kg != null;
  // D44: the pace is a share of body weight a week; the kilos follow from it.
  const gaining = hasGoal && (form.goal_weight_kg ?? 0) > form.weight_kg;
  const shares = gaining ? { gentle: 0.25, steady: 0.5 } : { gentle: 0.5, steady: 0.75 };
  const perWeek = (pct: number) => (Math.round(form.weight_kg * pct) / 100).toFixed(2).replace(/0$/, "");

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const res = await api.saveProfile({ ...form, pace: form.pace ?? "steady" });
      onSaved(res.profile, res.targets);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
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
        day. It starts from a widely used estimate of what your body burns, based on your sex, age, height and
        weight (
        <a href="https://doi.org/10.1093/ajcn/51.2.241" target="_blank" rel="noreferrer">
          the study behind it
        </a>
        ), adjusted for your activity and goal. Once you've logged complete days and weighed in for about two
        weeks, it learns what you really burn and uses that.
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
        Goal weight in kg (optional)
        <input
          type="number"
          inputMode="decimal"
          min={35}
          max={250}
          step={0.5}
          placeholder="e.g. 70"
          value={form.goal_weight_kg ?? ""}
          onChange={(e) => set("goal_weight_kg", e.target.value === "" ? null : Number(e.target.value))}
        />
        <span className="field-hint">
          A healthy weight for {form.height_cm} cm is about {low}–{high} kg. With a goal weight, Forkcast works out how
          much to eat each day and roughly how long it takes.
        </span>
      </label>
      {hasGoal ? (
        <label>
          Pace
          <select value={form.pace ?? "steady"} onChange={(e) => set("pace", e.target.value as Profile["pace"])}>
            <option value="gentle">
              Gentle: {shares.gentle}% of your weight a week (about {perWeek(shares.gentle)} kg)
            </option>
            <option value="steady">
              Steady: {shares.steady}% of your weight a week (about {perWeek(shares.steady)} kg)
            </option>
          </select>
        </label>
      ) : (
        <label>
          Goal
          <select value={form.goal} onChange={(e) => set("goal", e.target.value as Profile["goal"])}>
            {GOALS.map((g) => (
              <option key={g.value} value={g.value}>{g.label}</option>
            ))}
          </select>
        </label>
      )}
      {hasGoal && (
        <p className="field-hint">
          These are estimates, not medical advice. If you are pregnant, under 18 or have a health condition, talk to a
          doctor before changing how much you eat.
        </p>
      )}
      {error && <p className="feedback error">{error}</p>}
      <button type="submit" className="btn" disabled={busy}>
        {busy ? "Saving…" : "Save and work out my targets"}
      </button>
    </form>
  );
}
