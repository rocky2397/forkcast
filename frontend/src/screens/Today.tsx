import { useEffect, useRef, useState } from "react";
import { api, type DaySummary, type Product, type Profile, type Targets } from "../api";
import { ProfileForm } from "./ProfileForm";
import { detectBarcode } from "../barcode";

function Meter({ label, value, target, unit }: { label: string; value: number; target: number; unit: string }) {
  const pct = target > 0 ? Math.min((value / target) * 100, 100) : 0;
  const over = value > target;
  const overBy = Math.round(value - target);
  return (
    <div className="meter" title={`${label}: ${Math.round(value)} of ${target} ${unit}`}>
      <div className="meter-head">
        <span className="meter-label">{label}</span>
        <span className="meter-value">
          {Math.round(value)} / {target} {unit}
          {over && <em className="meter-over"> +{overBy} over</em>}
        </span>
      </div>
      <div className="meter-track">
        <div className={over ? "meter-fill over" : "meter-fill"} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

const EMPTY_MEAL = { name: "", calories: "", protein_g: "", carbs_g: "", fat_g: "" };

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

  const refresh = () =>
    Promise.all([api.day(), api.profile()]).then(([d, p]) => {
      setDay(d);
      setProfile(p.profile);
      setLoaded(true);
    });
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

  async function rate(m: { id: number; liked: 0 | 1 | null }, thumb: boolean) {
    // tapping the active thumb clears the rating
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

  if (!loaded) return <div className="screen" />;

  if (!profile || editing) {
    return (
      <div className="screen">
        {editing && (
          <button className="back" onClick={() => setEditing(false)}>← Back</button>
        )}
        <ProfileForm initial={profile} onSaved={onSaved} />
      </div>
    );
  }

  const t = day?.targets;
  const totals = day?.totals;

  return (
    <div className="screen">
      {t && totals && (
        <div className="meters">
          <Meter label="Calories" value={totals.calories} target={t.calories} unit="kcal" />
          <Meter label="Protein" value={totals.protein_g} target={t.protein_g} unit="g" />
          <Meter label="Carbs" value={totals.carbs_g} target={t.carbs_g} unit="g" />
          <Meter label="Fat" value={totals.fat_g} target={t.fat_g} unit="g" />
        </div>
      )}
      <p className="taste-note">
        Targets for your {profile.goal === "maintain" ? "maintenance" : profile.goal} goal ·{" "}
        <button className="link" onClick={() => setEditing(true)}>edit profile</button>
      </p>

      <h2 className="section-title">Today's meals</h2>
      <ul className="meal-list">
        {day?.meals.map((m) => (
          <li key={m.id}>
            <div className="meal-main">
              <span className="meal-name">{m.name ?? "(unnamed meal)"}</span>
              <span className="meal-macros">
                {Math.round(m.calories ?? 0)} kcal · P {Math.round(m.protein_g ?? 0)} · C{" "}
                {Math.round(m.carbs_g ?? 0)} · F {Math.round(m.fat_g ?? 0)}
              </span>
            </div>
            {m.recipe_id !== null && (
              <span className="rate">
                <button
                  className={m.liked === 1 ? "thumb active" : "thumb"}
                  onClick={() => rate(m, true)}
                  aria-label={`like ${m.name}`}
                >
                  👍
                </button>
                <button
                  className={m.liked === 0 ? "thumb active" : "thumb"}
                  onClick={() => rate(m, false)}
                  aria-label={`dislike ${m.name}`}
                >
                  👎
                </button>
              </span>
            )}
            <button className="remove" onClick={() => removeMeal(m.id)} aria-label={`remove ${m.name}`}>
              ×
            </button>
          </li>
        ))}
      </ul>
      {day?.meals.length === 0 && (
        <p className="empty">Nothing logged today — cook a recipe or add a meal below.</p>
      )}

      {adding ? (
        <div className="meal-form">
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            capture="environment"
            hidden
            onChange={(e) => onProductPhoto(e.target.files?.[0])}
          />
          <button className="scan-btn" onClick={() => fileRef.current?.click()} disabled={scanBusy}>
            {scanBusy ? "Reading product…" : "📷 Scan barcode / Nährwerttabelle"}
          </button>
          {scanError && <p className="feedback">{scanError}</p>}
          {product && (
            <div className="product-card">
              <div className="product-head">
                <strong>{product.name ?? "Unnamed product"}</strong>
                <span className="product-source">
                  {product.source === "openfoodfacts" ? "Open Food Facts" : "read from label"}
                </span>
              </div>
              <p className="product-macros">
                per 100 g: {Math.round(product.calories_100g ?? 0)} kcal · P{" "}
                {Math.round(product.protein_g_100g ?? 0)} · C {Math.round(product.carbs_g_100g ?? 0)} · F{" "}
                {Math.round(product.fat_g_100g ?? 0)}
              </p>
              <div className="product-use">
                <input
                  type="number"
                  inputMode="decimal"
                  value={grams}
                  onChange={(e) => setGrams(e.target.value)}
                  aria-label="amount in grams"
                />
                <span>g</span>
                <button onClick={useProduct}>Use</button>
              </div>
            </div>
          )}
          <input
            placeholder="Meal name (e.g. Skyr mit Beeren)"
            value={meal.name}
            onChange={(e) => setMeal({ ...meal, name: e.target.value })}
            autoFocus
          />
          <div className="meal-form-grid">
            <input type="number" inputMode="decimal" placeholder="kcal" value={meal.calories} onChange={(e) => setMeal({ ...meal, calories: e.target.value })} />
            <input type="number" inputMode="decimal" placeholder="protein g" value={meal.protein_g} onChange={(e) => setMeal({ ...meal, protein_g: e.target.value })} />
            <input type="number" inputMode="decimal" placeholder="carbs g" value={meal.carbs_g} onChange={(e) => setMeal({ ...meal, carbs_g: e.target.value })} />
            <input type="number" inputMode="decimal" placeholder="fat g" value={meal.fat_g} onChange={(e) => setMeal({ ...meal, fat_g: e.target.value })} />
          </div>
          <div className="meal-form-actions">
            <button className="cooked" onClick={addMeal} disabled={busy || !meal.name.trim() || !meal.calories}>
              Log meal
            </button>
            <button
              className="back"
              onClick={() => {
                setAdding(false);
                setProduct(null);
                setScanError(null);
              }}
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <button className="scan-btn" onClick={() => setAdding(true)}>＋ Log a meal</button>
      )}
    </div>
  );
}
