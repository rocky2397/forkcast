import { useEffect, useRef, useState } from "react";
import { api, isDemo, scansOn, type CookableRecipe, type DaySummary, type MacroFocus } from "../api";
import { CookingCard } from "../CookingCard";
import { mealOfDay } from "../format";
import { ScanIcon } from "../Icons";
import { errorText } from "../LoadError";
import { RecipeCard } from "./Recipes";

const MACRO = { protein_g: "protein", carbs_g: "carbs", fat_g: "fat" } as const;

/** D72: the home screen. What's left of today, the fridge (one tap from the
 *  kitchen list and the shopping list), the three meals that fit best, and a
 *  way to log anything else. Fridge, pick, ate it. */
export function Cook({
  onOpenRecipe,
  onKitchen,
  onScan,
  onAllMeals,
  onLog,
  onDay,
}: {
  onOpenRecipe: (id: number) => void;
  onKitchen: () => void;
  /** A photo to read, or the demo's sample fridge; the Kitchen screen takes it from there. */
  onScan: (start: { file: File } | { sample: true }) => void;
  onAllMeals: () => void;
  onLog: () => void;
  onDay: () => void;
}) {
  const [day, setDay] = useState<DaySummary | null>(null);
  const [fridge, setFridge] = useState<{ items: number; list: number } | null>(null);
  const [meals, setMeals] = useState<{ recipes: CookableRecipe[]; away: boolean } | null>(null);
  const [focus, setFocus] = useState<MacroFocus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.day().then(setDay).catch(() => {});
    // Cookable now first; if fewer than three, the ones a single item away.
    // An empty kitchen gets no suggestions: "one thing away" would be any
    // one-ingredient recipe, which helps nobody.
    Promise.all([api.inventory(), api.list(), api.cookable(0, true)])
      .then(async ([inv, list, now]) => {
        setFridge({ items: inv.items.length, list: list.items.length });
        setFocus(now.macro_focus);
        if (inv.items.length === 0) return setMeals({ recipes: [], away: false });
        if (now.recipes.length >= 3) return setMeals({ recipes: now.recipes.slice(0, 3), away: false });
        const near = await api.cookable(1, true);
        setMeals({ recipes: [...now.recipes, ...near.recipes].slice(0, 3), away: now.recipes.length === 0 });
      })
      .catch((e) => setError(errorText(e)));
  }, []);

  const left = day?.targets ? Math.round(day.targets.calories - day.totals.calories) : null;
  const meal = mealOfDay();

  return (
    <div className="screen cook">
      <p className="kicker">{new Date().toLocaleDateString("en", { weekday: "long" })}</p>
      <h1 className="display">What's for {meal}?</h1>
      {left != null && (
        <p className="lead">
          {left >= 0 ? (
            <>
              <strong>{left.toLocaleString("en")} kcal</strong> left today
            </>
          ) : (
            <>
              <strong>{(-left).toLocaleString("en")} kcal</strong> over today
            </>
          )}
          {focus && focus.grams > 0 && (
            <>
              , {focus.grams} g {MACRO[focus.macro]} to go
            </>
          )}
          .{" "}
          <button className="link" onClick={onDay}>
            See your day
          </button>
        </p>
      )}

      <CookingCard onOpen={onOpenRecipe} />

      <section className="fridge-card" aria-labelledby="fridge-title">
        <h2 id="fridge-title" className="group-label">
          Your fridge
        </h2>
        <p>
          {fridge
            ? `${fridge.items} ${fridge.items === 1 ? "thing" : "things"} in your kitchen${
                fridge.list ? `, ${fridge.list} on your shopping list` : ""
              }.`
            : " "}
        </p>
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          capture="environment"
          hidden
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) onScan({ file });
          }}
        />
        <div className="fridge-actions">
          {scansOn() && (
            <button className="btn scan-primary" onClick={() => fileRef.current?.click()}>
              <ScanIcon size={20} /> Scan your fridge
            </button>
          )}
          {isDemo() && (
            <button className={scansOn() ? "btn secondary" : "btn"} onClick={() => onScan({ sample: true })}>
              Use a sample fridge
            </button>
          )}
          <button className="link" onClick={onKitchen}>
            See what's in your fridge
          </button>
        </div>
      </section>

      <section aria-labelledby="fits-title">
        <h2 id="fits-title" className="section-title">
          {meals?.away ? "One thing away" : "Meals that fit"}
        </h2>
        {error && <p className="error">{error}</p>}
        {meals && meals.recipes.length === 0 && (
          <p className="empty-note">
            {fridge?.items === 0
              ? "Your kitchen is empty. Scan your fridge or add a few things to see meals that fit."
              : "Nothing fits what's in your kitchen yet. Update your fridge to see meals."}
          </p>
        )}
        <div className="cook-picks">
          {meals?.recipes.map((r) => (
            <RecipeCard key={r.id} recipe={r} focus={focus} current={false} onOpen={() => onOpenRecipe(r.id)} />
          ))}
        </div>
        <button className="btn secondary see-all" onClick={onAllMeals}>
          See all meals
        </button>
      </section>

      <p className="cook-log">
        Ate something else?{" "}
        <button className="link" onClick={onLog}>
          Log it
        </button>
      </p>
    </div>
  );
}
