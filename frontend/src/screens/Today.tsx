import { useEffect, useRef, useState } from "react";
import { api, type DayMeal, type DaySummary, type Product, type Profile, type Targets } from "../api";
import { ProfileForm } from "./ProfileForm";
import { detectBarcode } from "../barcode";
import { displayName } from "../format";
import { Guide, HelpButton } from "../Guide";
import { useGuide } from "../useGuide";
import { BackIcon, CloseIcon, ScanIcon } from "../Icons";

const GOAL_WORDS: Record<Profile["goal"], string> = {
  cut: "losing fat",
  maintain: "keeping your weight",
  bulk: "building muscle",
};

const fmt = (n: number) => Math.round(n).toLocaleString("en");

/** Calories as a ring: eaten against the daily target, what's left in the middle. */
function CalorieRing({ eaten, target }: { eaten: number; target: number }) {
  const r = 62;
  const c = 2 * Math.PI * r;
  const share = target > 0 ? Math.min(eaten / target, 1) : 0;
  const left = target - eaten;
  return (
    <figure className="ring" aria-label={`${fmt(eaten)} of ${fmt(target)} kcal eaten today`}>
      <svg viewBox="0 0 160 160" width="168" height="168" aria-hidden="true">
        <circle cx="80" cy="80" r={r} className="ring-track" />
        <circle
          cx="80"
          cy="80"
          r={r}
          className={left < 0 ? "ring-fill over" : "ring-fill"}
          strokeDasharray={`${share * c} ${c}`}
          transform="rotate(-90 80 80)"
        />
      </svg>
      <figcaption className="ring-center" aria-hidden="true">
        <span className="ring-value">{fmt(Math.abs(left))}</span>
        <span className="ring-label">{left >= 0 ? "kcal left" : "kcal over"}</span>
      </figcaption>
    </figure>
  );
}

function MacroBar({ label, value, target }: { label: string; value: number; target: number }) {
  const pct = target > 0 ? Math.min((value / target) * 100, 100) : 0;
  const diff = Math.round(target - value);
  return (
    <div className="macro">
      <div className="macro-head">
        <span className="macro-label">{label}</span>
        <span className="macro-value">
          {fmt(value)} / {fmt(target)} g
        </span>
      </div>
      <div className="meter-track" aria-hidden="true">
        <div className={diff < 0 ? "meter-fill over" : "meter-fill"} style={{ width: `${pct}%` }} />
      </div>
      <span className={diff < 0 ? "macro-note over" : "macro-note"}>
        {diff > 0 ? `${diff} g to go` : diff < 0 ? `${-diff} g over` : "Right on target"}
      </span>
    </div>
  );
}

const EMPTY_MEAL = { name: "", calories: "", protein_g: "", carbs_g: "", fat_g: "" };

function mealTime(m: DayMeal): string {
  // logged_at is SQLite datetime('now'): UTC, space-separated.
  const d = new Date(m.logged_at.replace(" ", "T") + "Z");
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export function Today() {
  const [day, setDay] = useState<DaySummary | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [editing, setEditing] = useState(false);
  const [adding, setAdding] = useState(false);
  const [meal, setMeal] = useState(EMPTY_MEAL);
  const [busy, setBusy] = useState(false);
  const [product, setProduct] = useState<Product | null>(null);
  const [grams, setGrams] = useState("100");
  const [scanBusy, setScanBusy] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const guide = useGuide("forkcast.todayguide.v1");

  const [loadError, setLoadError] = useState<string | null>(null);

  const refresh = () =>
    Promise.all([api.day(), api.profile()])
      .then(([d, p]) => {
        setDay(d);
        setProfile(p.profile);
        setLoadError(null);
        setLoaded(true);
      })
      .catch((e) => setLoadError(String(e)));
  useEffect(() => {
    refresh();
  }, []);

  function onSaved(p: Profile, _targets: Targets) {
    setProfile(p);
    setEditing(false);
    refresh();
  }

  async function addMeal() {
    if (busy) return;
    setBusy(true);
    try {
      await api.addMeal({
        name: meal.name.trim(),
        calories: Number(meal.calories) || 0,
        protein_g: Number(meal.protein_g) || 0,
        carbs_g: Number(meal.carbs_g) || 0,
        fat_g: Number(meal.fat_g) || 0,
      });
      setMeal(EMPTY_MEAL);
      setAdding(false);
      await refresh();
    } finally {
      setBusy(false);
    }
  }

  async function removeMeal(id: number) {
    await api.deleteMeal(id);
    await refresh();
  }

  async function rate(m: DayMeal, thumb: boolean) {
    // tapping the active choice clears the rating
    const next = m.liked !== null && Boolean(m.liked) === thumb ? null : thumb;
    await api.rateMeal(m.id, next);
    await refresh();
  }

  async function onProductPhoto(file: File | undefined) {
    if (!file) return;
    setScanBusy(true);
    setScanError(null);
    setProduct(null);
    try {
      // barcode-first (D9): on-device detection costs nothing when supported
      const code = await detectBarcode(file);
      const res = code
        ? await api.barcodeLookup(code).catch(() => api.scanProduct(file))
        : await api.scanProduct(file);
      setProduct(res.product);
      setGrams("100");
    } catch (e) {
      setScanError(String(e));
    } finally {
      setScanBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  function useProduct() {
    if (!product) return;
    const factor = (Number(grams) || 0) / 100;
    const scale = (v: number | null) => (v == null ? "" : String(Math.round(v * factor)));
    setMeal({
      name: [product.name, `${Number(grams) || 0} g`].filter(Boolean).join(", "),
      calories: scale(product.calories_100g),
      protein_g: scale(product.protein_g_100g),
      carbs_g: scale(product.carbs_g_100g),
      fat_g: scale(product.fat_g_100g),
    });
    setProduct(null);
  }

  if (loadError && !loaded) {
    return (
      <div className="screen">
        <p className="empty">Couldn't reach the Forkcast server.</p>
        <p className="feedback">{loadError}</p>
        <button className="btn" onClick={refresh}>Try again</button>
      </div>
    );
  }
  if (!loaded) return <div className="screen" aria-busy="true" />;

  if (!profile || editing) {
    return (
      <div className="screen narrow">
        {editing && (
          <button className="back" onClick={() => setEditing(false)}>
            <BackIcon size={20} /> Today
          </button>
        )}
        <ProfileForm initial={profile} onSaved={onSaved} />
      </div>
    );
  }

  const t = day?.targets;
  const totals = day?.totals;
  const date = new Date().toLocaleDateString("en", { weekday: "long", day: "numeric", month: "long" });
  const meals = day?.meals ?? [];

  return (
    <div className="screen">
      <p className="kicker">{date}</p>
      <div className="title-row">
        <h1 className="display">Today</h1>
        <HelpButton open={guide.open} onToggle={guide.toggle} label="How this page works" controls="today-guide" />
      </div>
      <p className="lead">
        Targets for {GOAL_WORDS[profile.goal]}, from your profile.{" "}
        <button className="link" onClick={() => setEditing(true)}>
          Edit profile
        </button>
      </p>

      {guide.open && (
        <Guide
          id="today-guide"
          title="How this page works"
          onClose={guide.close}
          items={[
            {
              term: "The ring",
              text: "Calories eaten today against your daily target. The number in the middle is what's left.",
            },
            {
              term: "Protein, carbs, fat",
              text: "What you've eaten against each target. The recipe feed puts dishes first that fill whichever is furthest behind.",
            },
            {
              term: "Your targets",
              text: "Worked out from your profile: a standard formula (Mifflin-St Jeor) for your body, then your activity level and goal. Change them under Edit profile.",
            },
            {
              term: "Liked · Not for me",
              text: "Rate the recipes you cook. Recipes close to the dishes you cook move up the feed; ones you mark Not for me stop counting.",
            },
          ]}
        />
      )}

      <div className="today-layout">
        {t && totals && (
          <section className="today-summary" aria-label="Today's totals">
            <CalorieRing eaten={totals.calories} target={t.calories} />
            <p className="ring-caption">
              {fmt(totals.calories)} of {fmt(t.calories)} kcal eaten
            </p>
            <div className="macros">
              <MacroBar label="Protein" value={totals.protein_g} target={t.protein_g} />
              <MacroBar label="Carbs" value={totals.carbs_g} target={t.carbs_g} />
              <MacroBar label="Fat" value={totals.fat_g} target={t.fat_g} />
            </div>
          </section>
        )}

        <section aria-labelledby="meals-title">
          <h2 id="meals-title" className="section-title">Today's meals</h2>
          {meals.length === 0 && (
            <p className="empty-note">
              Nothing logged yet. Cook a recipe and tap "I cooked this", or log a meal below.
            </p>
          )}
          <ol className="meal-list">
            {meals.map((m) => (
              <li key={m.id} className="meal">
                <span className="meal-time">{mealTime(m)}</span>
                <div className="meal-main">
                  <span className="meal-name">
                    {/* Clean up corpus recipe names; what you typed stays as typed. */}
                    {m.name ? (m.recipe_id !== null ? displayName(m.name) : m.name) : "Unnamed meal"}
                  </span>
                  <span className="meal-macros">
                    {fmt(m.calories ?? 0)} kcal · {fmt(m.protein_g ?? 0)} g protein · {fmt(m.carbs_g ?? 0)} g carbs ·{" "}
                    {fmt(m.fat_g ?? 0)} g fat
                  </span>
                  {m.recipe_id !== null && (
                    <span className="rate" role="group" aria-label={`Rate ${m.name}`}>
                      <button className="pill" aria-pressed={m.liked === 1} onClick={() => rate(m, true)}>
                        Liked
                      </button>
                      <button className="pill" aria-pressed={m.liked === 0} onClick={() => rate(m, false)}>
                        Not for me
                      </button>
                    </span>
                  )}
                </div>
                <button className="remove" onClick={() => removeMeal(m.id)} aria-label={`Remove ${m.name}`}>
                  <CloseIcon size={18} />
                </button>
              </li>
            ))}
          </ol>

          {adding ? (
            <form
              className="meal-form"
              onSubmit={(e) => {
                e.preventDefault();
                addMeal();
              }}
            >
              <h3 className="form-title">Log a meal</h3>
              <input
                ref={fileRef}
                type="file"
                accept="image/*"
                capture="environment"
                hidden
                onChange={(e) => onProductPhoto(e.target.files?.[0])}
              />
              <button type="button" className="scan-btn" onClick={() => fileRef.current?.click()} disabled={scanBusy}>
                <ScanIcon size={20} />
                {scanBusy ? "Reading the product…" : "Scan a barcode or nutrition label"}
              </button>
              <p className="field-hint">Or type it in. Packaged food fills in by itself from the barcode.</p>
              {scanError && <p className="feedback error">{scanError}</p>}
              {product && (
                <div className="product-card">
                  <div className="product-head">
                    <strong>{product.name ?? "Unnamed product"}</strong>
                    <span className="product-source">
                      {product.source === "openfoodfacts" ? "from Open Food Facts" : "read from the label"}
                    </span>
                  </div>
                  <p className="product-macros">
                    Per 100 g: {fmt(product.calories_100g ?? 0)} kcal · {fmt(product.protein_g_100g ?? 0)} g protein ·{" "}
                    {fmt(product.carbs_g_100g ?? 0)} g carbs · {fmt(product.fat_g_100g ?? 0)} g fat
                  </p>
                  {product.check && (
                    <p className="feedback warning" role="alert">
                      {product.check}
                    </p>
                  )}
                  <div className="product-use">
                    <label className="inline-label">
                      How much?
                      <input
                        type="number"
                        inputMode="decimal"
                        value={grams}
                        onChange={(e) => setGrams(e.target.value)}
                      />
                      g
                    </label>
                    <button type="button" className="btn" onClick={useProduct}>
                      Use
                    </button>
                  </div>
                </div>
              )}
              <label className="field">
                What did you eat?
                <input
                  placeholder="e.g. Skyr with berries"
                  value={meal.name}
                  onChange={(e) => setMeal({ ...meal, name: e.target.value })}
                  autoFocus
                />
              </label>
              <div className="meal-form-grid">
                <label className="field">
                  kcal
                  <input type="number" inputMode="decimal" value={meal.calories} onChange={(e) => setMeal({ ...meal, calories: e.target.value })} />
                </label>
                <label className="field">
                  Protein g
                  <input type="number" inputMode="decimal" value={meal.protein_g} onChange={(e) => setMeal({ ...meal, protein_g: e.target.value })} />
                </label>
                <label className="field">
                  Carbs g
                  <input type="number" inputMode="decimal" value={meal.carbs_g} onChange={(e) => setMeal({ ...meal, carbs_g: e.target.value })} />
                </label>
                <label className="field">
                  Fat g
                  <input type="number" inputMode="decimal" value={meal.fat_g} onChange={(e) => setMeal({ ...meal, fat_g: e.target.value })} />
                </label>
              </div>
              <div className="form-actions">
                <button type="submit" className="btn" disabled={busy || !meal.name.trim() || !meal.calories}>
                  Log meal
                </button>
                <button
                  type="button"
                  className="btn secondary"
                  onClick={() => {
                    setAdding(false);
                    setProduct(null);
                    setScanError(null);
                  }}
                >
                  Cancel
                </button>
              </div>
            </form>
          ) : (
            <button className="btn secondary log-btn" onClick={() => setAdding(true)}>
              Log a meal
            </button>
          )}
        </section>
      </div>
    </div>
  );
}
