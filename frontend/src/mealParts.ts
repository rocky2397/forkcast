// D49: a meal being built from ingredients, and the sums the form shows.
// The server works the logged totals out again from the same USDA values.
import type { Food, FoodForm, MealProduct, Product } from "./api";

/** D49: one ingredient of a meal being built, with how much of it. */
export interface Part {
  food: Food;
  amount: string;
  /** -1: grams; otherwise an index into the current form's portions. */
  unit: number;
  cooked: boolean;
  /** D64: from a can, drained (beans, peas); wins over cooked. */
  canned?: boolean;
  /** D51: a scanned product, with where its values came from. */
  product?: { barcode: string | null; source: Product["source"] | "logged" };
  /** D62: the dish this row is a typical share of ("Döner"), for the note above its rows. */
  dish?: string;
  /** D54: the amount is the one from last time, untouched so far. */
  fromLast?: boolean;
}

/** D54: an amount in grams as a row's amount, in a portion when one weighs exactly that. */
export function amountOf(grams: number, portions: { grams: number }[]): { amount: string; unit: number } {
  const k = portions.findIndex((o) => Math.abs(o.grams - grams) < 0.05);
  return k >= 0 ? { amount: "1", unit: k } : { amount: String(Math.round(grams * 10) / 10), unit: -1 };
}

/** Whether a scanned product has all four values, so it can join a meal (D51). */
export function complete(p: Product): boolean {
  return [p.calories_100g, p.protein_g_100g, p.carbs_g_100g, p.fat_g_100g].every((v) => v != null);
}

/** D52: a scanned product's serving and pack, as portions like a banana's "1 medium". */
function productPortions(p: Product): { label: string; grams: number }[] {
  const out = [];
  if (p.serving_g) out.push({ label: "1 serving", grams: p.serving_g });
  if (p.pack_g && p.pack_g !== p.serving_g) out.push({ label: "1 pack", grams: p.pack_g });
  return out;
}

/** A complete scanned product as a row of the meal being built. One serving
 *  when that's the amount chosen on its card, else grams. */
export function productPart(p: Product, grams: string): Part {
  const food: Food = {
    canonical: "",
    name: p.name ?? "Unnamed product",
    checked: true,
    usda: "",
    fdc_id: 0,
    per_100g: {
      calories: p.calories_100g ?? 0,
      protein_g: p.protein_g_100g ?? 0,
      carbs_g: p.carbs_g_100g ?? 0,
      fat_g: p.fat_g_100g ?? 0,
    },
    portions: productPortions(p),
    cooked: null,
  };
  const product = { barcode: p.barcode, source: p.source };
  const fromLast = p.last_grams != null && Number(grams) === p.last_grams;
  const serving = food.portions.findIndex((o) => o.label === "1 serving");
  if (serving >= 0 && Number(grams) === food.portions[serving].grams) {
    return { food, amount: "1", unit: serving, cooked: false, product, fromLast };
  }
  return { food, amount: grams, unit: -1, cooked: false, product, fromLast };
}

/** What the server is sent for a product row. */
export function asMealProduct(p: Part): MealProduct {
  const v = p.food.per_100g;
  return {
    name: p.food.name,
    barcode: p.product?.barcode ?? null,
    grams: gramsOf(p),
    calories_100g: v.calories,
    protein_g_100g: v.protein_g,
    carbs_g_100g: v.carbs_g,
    fat_g_100g: v.fat_g,
  };
}

const MACROS = ["calories", "protein_g", "carbs_g", "fat_g"] as const;
type Totals = Record<(typeof MACROS)[number], number>;

export const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

/** D60: a portion as the unit menu shows it, short enough for a phone:
 *  "× medium (118 g)" after an amount of 1, not "× 1 medium (118 g)"; the
 *  USDA's longer descriptions up to their first "or". */
export function unitLabel(label: string, grams: number): string {
  const short = label.replace(/^1 /, "").split(/ or |, /)[0];
  return `× ${short} (${Math.round(grams).toLocaleString("en")} g)`;
}

export function formOf(p: Part): FoodForm {
  if (p.canned && p.food.canned) return p.food.canned;
  return p.cooked && p.food.cooked ? p.food.cooked : p.food;
}

export function gramsOf(p: Part): number {
  // D58: a negative amount counts as none (the form says amounts must be above 0).
  const n = Math.max(Number(p.amount.replace(",", ".")) || 0, 0);
  return p.unit < 0 ? n : n * (formOf(p).portions[p.unit]?.grams ?? 0);
}

export function partTotals(p: Part): Totals {
  const f = gramsOf(p) / 100;
  const per = formOf(p).per_100g;
  return { calories: per.calories * f, protein_g: per.protein_g * f, carbs_g: per.carbs_g * f, fat_g: per.fat_g * f };
}

export function totalsOf(parts: Part[]): Totals {
  const out: Totals = { calories: 0, protein_g: 0, carbs_g: 0, fat_g: 0 };
  for (const p of parts) {
    const t = partTotals(p);
    for (const k of MACROS) out[k] += t[k];
  }
  return out;
}

/** The name a built meal gets when none is typed: "Banana, milk". */
export function defaultName(parts: Part[]): string {
  return cap(parts.map((p) => p.food.name).join(", "));
}

