import { useEffect, useMemo, useState } from "react";
import { api, pretty, type RecipeDetail } from "../api";
import { displayName, sentence } from "../format";
import { BackIcon, CloseIcon, NextIcon } from "../Icons";

type Ingredient = RecipeDetail["ingredients"][number];

export function RecipeView({ id, onBack }: { id: number; onBack: () => void }) {
  const [recipe, setRecipe] = useState<RecipeDetail | null>(null);
  const [cooked, setCooked] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [usedUp, setUsedUp] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [cooking, setCooking] = useState(false);

  useEffect(() => {
    api.recipe(id).then(setRecipe);
  }, [id]);

  // What the cook could have run out of: in-inventory recipe ingredients
  // (staples excluded — nobody finishes the salt on one dish) plus any
  // suggested substitute, which is in the inventory by construction.
  const depletable = useMemo(() => {
    if (!recipe) return [];
    const seen = new Set<string>();
    const out: { canonical: string; usedFor: string | null }[] = [];
    for (const ing of recipe.ingredients) {
      const c = ing.in_inventory && !ing.staple ? ing.canonical : ing.sub;
      if (c && !seen.has(c)) {
        seen.add(c);
        out.push({ canonical: c, usedFor: ing.in_inventory ? null : ing.canonical });
      }
    }
    return out;
  }, [recipe]);

  function toggle(c: string) {
    setUsedUp((prev) => {
      const next = new Set(prev);
      if (next.has(c)) next.delete(c);
      else next.add(c);
      return next;
    });
  }

  async function logCooked() {
    if (busy || cooked) return;
    if (!confirming && depletable.length > 0) {
      setConfirming(true);
      return;
    }
    setBusy(true);
    try {
      await api.logCooked(id, [...usedUp]);
      setCooked(true);
      setConfirming(false);
    } finally {
      setBusy(false);
    }
  }

  if (!recipe) {
    return (
      <div className="recipe-detail" aria-busy="true">
        <div className="skeleton" aria-hidden="true">
          <span style={{ width: 140 }} />
          <span />
          <span />
        </div>
      </div>
    );
  }

  // Staples are assumed present when recipes are ranked, so they are listed
  // apart rather than as missing. Rows show the recipe's own wording: "lime
  // zest" and "lime juice" both match lime and would otherwise read twice.
  const have = recipe.ingredients.filter((i) => i.in_inventory);
  const missing = recipe.ingredients.filter((i) => !i.in_inventory && !i.staple);
  const pantry = recipe.ingredients.filter((i) => !i.in_inventory && i.staple);
  const missingFoods = [...new Set(missing.map((i) => i.canonical ?? i.raw))];
  const swaps = [...new Map(missing.filter((i) => i.sub).map((i) => [i.canonical, i.sub as string]))];
  const status =
    missingFoods.length === 0
      ? "Ready to cook"
      : `${missingFoods.length} ingredient${missingFoods.length > 1 ? "s" : ""} away`;
  const steps = recipe.steps.map(sentence);

  return (
    <article className="recipe-detail">
      <button className="back" onClick={onBack}>
        <BackIcon size={20} /> Recipes
      </button>
      <p className="kicker">
        {status} · {recipe.minutes} min
      </p>
      <h1>{displayName(recipe.name)}</h1>
      {recipe.description && <p className="description">“{sentence(recipe.description)}”</p>}

      <dl className="stats">
        {recipe.calories != null && <Stat value={Math.round(recipe.calories)} label="kcal" />}
        {recipe.protein_g != null && <Stat value={`${Math.round(recipe.protein_g)} g`} label="protein" />}
        {recipe.carbs_g != null && <Stat value={`${Math.round(recipe.carbs_g)} g`} label="carbs" />}
        {recipe.fat_g != null && <Stat value={`${Math.round(recipe.fat_g)} g`} label="fat" />}
      </dl>

      <div className="detail-columns">
        <section aria-labelledby="ingredients">
          <h2 id="ingredients" className="section-title">Ingredients</h2>
          <IngredientGroup label="In your kitchen" kind="have" items={have} />
          <IngredientGroup label="Missing" kind="missing" items={missing} />
          {swaps.map(([food, sub]) => (
            <p key={food} className="swap-note">
              Use your <strong>{pretty(sub)}</strong> instead of {pretty(food ?? "")}.
            </p>
          ))}
          <IngredientGroup label="Pantry" kind="pantry" items={pantry} />
        </section>

        <section aria-labelledby="method">
          <h2 id="method" className="section-title">Method</h2>
          <ol className="steps">
            {steps.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ol>

          {confirming && !cooked ? (
            <div>
              <h3>Did anything run out?</h3>
              <p className="feedback">Tick what's used up and it comes off your kitchen list.</p>
              <ul className="scan-list">
                {depletable.map((d) => (
                  <li key={d.canonical}>
                    <label>
                      <input
                        type="checkbox"
                        checked={usedUp.has(d.canonical)}
                        onChange={() => toggle(d.canonical)}
                      />
                      <span className="scan-name">
                        {pretty(d.canonical)}
                        {d.usedFor && <span className="sub-hint"> (used for {pretty(d.usedFor)})</span>}
                      </span>
                    </label>
                  </li>
                ))}
              </ul>
              <div className="detail-actions">
                <button className="btn" onClick={logCooked} disabled={busy}>
                  {usedUp.size > 0 ? `Log cook, remove ${usedUp.size}` : "Log cook, nothing ran out"}
                </button>
                <button className="btn secondary" onClick={() => setConfirming(false)} disabled={busy}>
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <div className="detail-actions">
              {steps.length > 0 && (
                <button className="btn" onClick={() => setCooking(true)}>
                  Start cook mode
                </button>
              )}
              <button className="btn secondary" onClick={logCooked} disabled={busy || cooked}>
                {cooked ? "Logged. Enjoy!" : "I cooked this"}
              </button>
            </div>
          )}
        </section>
      </div>

      {cooking && (
        <CookMode title={displayName(recipe.name)} steps={steps} onClose={() => setCooking(false)} />
      )}
    </article>
  );
}

function Stat({ value, label }: { value: string | number; label: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function IngredientGroup({ label, kind, items }: { label: string; kind: string; items: Ingredient[] }) {
  if (items.length === 0) return null;
  return (
    <>
      <p className={`group-label ${kind}`}>{label}</p>
      <ul className={`ingredient-list ${kind}`}>
        {items.map((ing, i) => (
          <li key={i}>{ing.raw}</li>
        ))}
      </ul>
    </>
  );
}

/** One step at a time, large enough to read from across the counter, with
 *  the screen kept awake where the browser allows it (Screen Wake Lock). */
function CookMode({ title, steps, onClose }: { title: string; steps: string[]; onClose: () => void }) {
  const [i, setI] = useState(0);
  const [awake, setAwake] = useState(false);

  useEffect(() => {
    let lock: WakeLockSentinel | null = null;
    let cancelled = false;
    navigator.wakeLock
      ?.request("screen")
      .then((l) => {
        if (cancelled) return void l.release();
        lock = l;
        setAwake(true);
      })
      .catch(() => setAwake(false));
    return () => {
      cancelled = true;
      lock?.release().catch(() => {});
    };
  }, []);

  const last = i === steps.length - 1;
  return (
    <div className="cook-mode" role="dialog" aria-modal="true" aria-label={`Cook mode: ${title}`}>
      <div className="cook-head">
        <p className="kicker">{title}</p>
        <button className="icon-btn" aria-label="Close cook mode" onClick={onClose}>
          <CloseIcon />
        </button>
      </div>
      <div className="cook-progress" aria-hidden="true">
        {steps.map((_, n) => (
          <span key={n} className={n <= i ? "done" : ""} />
        ))}
      </div>
      <div className="cook-step" aria-live="polite">
        <span className="step-number">
          Step {i + 1} of {steps.length}
        </span>
        <p>{steps[i]}</p>
      </div>
      <div className="cook-nav">
        <button className="btn secondary" onClick={() => setI(i - 1)} disabled={i === 0}>
          <BackIcon size={18} /> Back
        </button>
        <button className="btn" onClick={() => (last ? onClose() : setI(i + 1))}>
          {last ? "Done" : "Next"} {!last && <NextIcon size={18} />}
        </button>
      </div>
      {awake && <p className="cook-awake">Screen stays on while you cook.</p>}
    </div>
  );
}
