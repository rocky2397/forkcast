// D49: a meal being built from ingredients, and the sums the form shows.
// The server works the logged totals out again from the same USDA values.
import type { Food, FoodForm } from "./api";

/** D49: one ingredient of a meal being built, with how much of it. */
export interface Part {
  food: Food;
  amount: string;
  /** -1: grams; otherwise an index into the current form's portions. */
  unit: number;
  cooked: boolean;
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

