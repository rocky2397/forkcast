import { useState } from "react";
import { api, type Food, type FoodLookup, type LinePart } from "../api";
import { CloseIcon } from "../Icons";
import { amountOf, cap, formOf, gramsOf, partTotals, totalsOf, unitLabel, type Part } from "../mealParts";

const fmt = (n: number) => Math.round(n).toLocaleString("en");

const PRODUCT_SOURCE = {
  openfoodfacts: "from Open Food Facts",
  label: "read from the label",
  saved: "saved from your earlier scan",
  logged: "as you logged it", // D56: editing a logged meal
} as const;

/** D54: what you had last time; else the food's usual portion (D60: 1 medium
 *  banana, 1 large egg, 1 slice of toast, 1 tbsp of butter, a glass); else 100 g. */
function newPart(food: Food): Part {
  if (food.last && !(food.start_cooked && !food.last.cooked) && !(food.start_canned && !food.last.canned)) {
    const canned = Boolean(food.last.canned && food.canned);
    const cooked = !canned && food.last.cooked && food.cooked !== null;
    const form = canned && food.canned ? food.canned : cooked && food.cooked ? food.cooked : food;
    return { food, ...amountOf(food.last.grams, form.portions), cooked, canned, fromLast: true };
  }
  // D64: "Kichererbsen aus der Dose" starts canned.
  if (food.start_canned && food.canned) {
    return { food, amount: "150", unit: -1, cooked: false, canned: true };
  }
  // D55: "Reis gekocht" starts as cooked rice.
  if (food.start_cooked && food.cooked) {
    return { food, amount: "150", unit: -1, cooked: true };
  }
  const piece = food.portions.findIndex((p) => p.label === food.default_portion);
  return piece >= 0 ? { food, amount: "1", unit: piece, cooked: false } : { food, amount: "100", unit: -1, cooked: false };
}

/** D61: a row with the amount typed for it ("2 eggs", "150 g Reis"); else as newPart. */
function linePart(lp: LinePart): Part {
  const canned = Boolean(lp.canned && lp.food.canned);
  const cooked = !canned && lp.cooked && lp.food.cooked !== null;
  const form = canned && lp.food.canned ? lp.food.canned : cooked && lp.food.cooked ? lp.food.cooked : lp.food;
  // A dish's parts read in grams ("10 g mayonnaise", not "1 × packet").
  if (lp.grams != null && lp.dish) return { food: lp.food, amount: String(lp.grams), unit: -1, cooked, canned };
  if (lp.grams != null) return { food: lp.food, ...amountOf(lp.grams, form.portions), cooked, canned };
  if (lp.count != null && lp.portion) {
    const unit = form.portions.findIndex((o) => o.label === lp.portion);
    if (unit >= 0) return { food: lp.food, amount: String(lp.count), unit, cooked, canned };
  }
  return newPart(lp.food);
}

export function MealBuilder({
  parts,
  onChange,
  onDish,
}: {
  parts: Part[];
  onChange: (parts: Part[]) => void;
  /** D62: a line that was only a dish ("Cappuccino") names the meal. */
  onDish?: (name: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [miss, setMiss] = useState<FoodLookup | null>(null);
  const [note, setNote] = useState<string | null>(null);

  async function add(q: string) {
    const text = q.trim();
    if (!text || busy) return;
    setBusy(true);
    setMiss(null); // the last word's "Couldn't find" isn't about this one (D58)
    setNote(null);
    try {
      // D61: one line can hold several foods and their amounts: "2 Eier, Toast, 150 g Reis".
      const res = await api.foodLine(text);
      if (res.parts.length > 0) onChange([...parts, ...res.parts.map(linePart)]);
      for (const dish of res.dishes) {
        const names = res.parts.filter((p) => p.dish === dish).map((p) => p.food.name);
        setNote(`A typical ${dish.toLowerCase()}: ${names.join(", ")}. Change any amount that's different.`);
      }
      if (res.dishes.length === 1 && parts.length === 0 && res.parts.every((p) => p.dish)) onDish?.(res.dishes[0]);
      if (res.missing.length > 0) {
        setMiss(res.missing[0]);
        setQuery(res.missing.map((m) => m.query).join(", "));
      } else {
        setQuery("");
      }
    } catch (e) {
      setMiss({ query: text, canonical: null, food: null, suggestions: [] });
      console.warn(e);
    } finally {
      setBusy(false);
    }
  }

  /** D63: the same amount of another fat level ("low-fat milk" for "milk"). */
  async function switchFood(i: number, key: string) {
    const p = parts[i];
    const { food } = await api.foodByKey(key);
    const grams = gramsOf(p);
    onChange(parts.map((q, j) => (j === i ? { food, ...amountOf(grams, food.portions), cooked: false } : q)));
  }

  function update(i: number, change: Partial<Part>) {
    // Any change makes it your amount now, not last time's (D54).
    onChange(parts.map((p, j) => (j === i ? { ...p, ...change, fromLast: false } : p)));
  }

  const total = totalsOf(parts);

  return (
    <div className="builder">
      <label className="field" htmlFor="builder-query">
        Add an ingredient
      </label>
      <div className="add-row builder-add">
        <input
          id="builder-query"
          placeholder="e.g. 2 eggs, 50 g oats"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            // Enter adds the ingredient; it mustn't log the meal around it.
            if (e.key === "Enter") {
              e.preventDefault();
              add(query);
            }
          }}
        />
        <button type="button" onClick={() => add(query)} disabled={busy || !query.trim()}>
          {busy ? "…" : "Add"}
        </button>
      </div>
      {miss && (
        <p className="feedback warning" role="status">
          {miss.canonical
            ? `No nutrition values for ${miss.canonical.replace(/_/g, " ")} yet. ` +
              (parts.length > 0
                ? "Log it as a meal of its own: scan its barcode or type its numbers."
                : "Scan its barcode or type the meal's numbers below instead.")
            : `Couldn't find "${miss.query}". Try another word, in English or German.`}
          {miss.suggestions.length > 0 && (
            <>
              {" "}Did you mean{" "}
              {miss.suggestions.map((s, i) => (
                <span key={s.canonical}>
                  {i > 0 && (i === miss.suggestions.length - 1 ? " or " : ", ")}
                  <button type="button" className="link-button" onClick={() => add(s.name)}>
                    {s.name}
                  </button>
                </span>
              ))}
              ?
            </>
          )}
        </p>
      )}

      {note && <p className="field-hint builder-note">{note}</p>}
      {parts.length > 0 && (
        <ul className="builder-list">
          {parts.map((p, i) => {
            const form = formOf(p);
            const t = partTotals(p);
            return (
              <li key={i} className="builder-item">
                <div className="builder-head">
                  <strong>{p.product ? p.food.name : cap(p.food.name)}</strong>
                  <span className="builder-kcal">{fmt(t.calories)} kcal</span>
                  <button
                    type="button"
                    className="remove"
                    onClick={() => onChange(parts.filter((_, j) => j !== i))}
                    aria-label={`Remove ${p.food.name}`}
                  >
                    <CloseIcon size={16} />
                  </button>
                </div>
                <div className="builder-amount">
                  <input
                    type="number"
                    inputMode="decimal"
                    min="0"
                    step="any"
                    aria-label={`How much ${p.food.name}`}
                    value={p.amount}
                    onChange={(e) => update(i, { amount: e.target.value })}
                  />
                  <select
                    aria-label={`Unit for ${p.food.name}`}
                    value={p.unit}
                    onChange={(e) => update(i, { unit: Number(e.target.value) })}
                  >
                    <option value={-1}>g</option>
                    {form.portions.map((o, k) => (
                      <option key={o.label} value={k}>
                        {unitLabel(o.label, o.grams)}
                      </option>
                    ))}
                  </select>
                  {!p.product && p.food.variants && (
                    <select
                      className="form-select"
                      aria-label={`Fat level: ${p.food.name}`}
                      value={p.food.canonical}
                      onChange={(e) => switchFood(i, e.target.value)}
                    >
                      {p.food.variants.map((v) => (
                        <option key={v.canonical} value={v.canonical}>
                          {cap(v.name)}, {v.fat_g.toLocaleString("en")}% fat
                        </option>
                      ))}
                    </select>
                  )}
                  {(p.food.cooked || p.food.canned) && (
                    <select
                      className="form-select"
                      aria-label={`Weighed raw or cooked: ${p.food.name}`}
                      value={p.canned ? "canned" : p.cooked ? "cooked" : "raw"}
                      onChange={(e) =>
                        update(i, { cooked: e.target.value === "cooked", canned: e.target.value === "canned", unit: -1 })
                      }
                    >
                      <option value="raw">weighed dry or raw</option>
                      {p.food.cooked && <option value="cooked">weighed cooked</option>}
                      {/* D64: canned beans hold more water than ones boiled from dry. */}
                      {p.food.canned && <option value="canned">from a can, drained</option>}
                    </select>
                  )}
                </div>
                {p.fromLast && <span className="builder-last">Same as last time. Change it to what you had.</span>}
                {/* D60: "10" next to "× tbsp" is often 10 g meant; say what it is and offer grams. */}
                {p.unit >= 0 && Number(p.amount.replace(",", ".")) >= 10 && (
                  <span className="builder-last">
                    That's {fmt(gramsOf(p))} g.{" "}
                    <button type="button" className="link-button" onClick={() => update(i, { unit: -1 })}>
                      Meant {p.amount} g?
                    </button>
                  </span>
                )}
                <span className="builder-source">
                  {p.product ? (
                    `Per 100 g ${PRODUCT_SOURCE[p.product.source]}`
                  ) : (
                    <>
                      {form.source === "openfoodfacts" ? "Open Food Facts" : "USDA"}: {form.usda}
                      {!p.food.checked && " · matched by name only, check it's the right food"}
                    </>
                  )}
                </span>
              </li>
            );
          })}
        </ul>
      )}
      {parts.length > 0 && (
        <p className="builder-total">
          Together: {fmt(total.calories)} kcal · {fmt(total.protein_g)} g protein · {fmt(total.carbs_g)} g carbs ·{" "}
          {fmt(total.fat_g)} g fat
        </p>
      )}
    </div>
  );
}
