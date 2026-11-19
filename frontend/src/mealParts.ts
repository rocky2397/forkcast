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
  /** D51: a scanned product, with where its values came from. */
  product?: { barcode: string | null; source: Product["source"] };
}

/** Whether a scanned product has all four values, so it can join a meal (D51). */
export function complete(p: Product): boolean {
  return [p.calories_100g, p.protein_g_100g, p.carbs_g_100g, p.fat_g_100g].every((v) => v != null);
}

/** A complete scanned product as a row of the meal being built, in grams. */
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
    portions: [],
    cooked: null,
  };
  return { food, amount: grams, unit: -1, cooked: false, product: { barcode: p.barcode, source: p.source } };
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

export function formOf(p: Part): FoodForm {
  return p.cooked && p.food.cooked ? p.food.cooked : p.food;
}

export function gramsOf(p: Part): number {
  const n = Number(p.amount.replace(",", ".")) || 0;
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

