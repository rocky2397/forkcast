export interface InventoryItem {
  canonical: string;
  added_at: string;
}

export interface CookableRecipe {
  id: number;
  name: string;
  minutes: number;
  calories: number | null;
  protein_g: number | null;
  carbs_g: number | null;
  fat_g: number | null;
  ingredients_needed: number;
  ingredients_missing: number;
  missing: string[];
  taste_sim?: number;
}

export interface TasteProfile {
  meals_logged: number;
  profile: { ingredient: string; similarity: number }[];
}

export interface ScanProposal {
  seen: string;
  quantity: string | null;
  confidence: number;
  canonical: string | null;
}

export interface Profile {
  sex: "m" | "f";
  age: number;
  height_cm: number;
  weight_kg: number;
  activity: "sedentary" | "light" | "moderate" | "active" | "very_active";
  goal: "cut" | "maintain" | "bulk";
}

export interface Targets {
  calories: number;
  protein_g: number;
  fat_g: number;
  carbs_g: number;
}

export interface DayMeal {
  id: number;
  recipe_id: number | null;
  logged_at: string;
  name: string | null;
  calories: number | null;
  protein_g: number | null;
  carbs_g: number | null;
  fat_g: number | null;
}

export interface DaySummary {
  date: string;
  meals: DayMeal[];
  totals: { calories: number; protein_g: number; carbs_g: number; fat_g: number };
  targets: Targets | null;
}

export interface Product {
  barcode: string | null;
  name: string | null;
  brand: string | null;
  calories_100g: number | null;
  protein_g_100g: number | null;
  carbs_g_100g: number | null;
  fat_g_100g: number | null;
  source: "openfoodfacts" | "label";
}

export interface RecipeDetail {
  id: number;
  name: string;
  minutes: number;
  description: string | null;
  steps: string[];
  calories: number | null;
  protein_g: number | null;
  carbs_g: number | null;
  fat_g: number | null;
  ingredients: { raw: string; canonical: string | null; in_inventory: boolean }[];
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `${res.status} ${res.statusText}`);
  }
  return res.json();
}

export const api = {
  inventory: () => req<{ items: InventoryItem[] }>("/api/inventory"),
  addInventory: (items: string[]) =>
    req<{ added: string[]; unknown: string[] }>("/api/inventory", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ items }),
    }),
  removeInventory: (name: string) =>
    req<{ removed: string }>(`/api/inventory/${encodeURIComponent(name)}`, { method: "DELETE" }),
  normalize: (q: string) =>
    req<{ query: string; canonical: string | null }>(`/api/normalize?q=${encodeURIComponent(q)}`),
  cookable: (maxMissing: number) =>
    req<{ count: number; personalized: boolean; recipes: CookableRecipe[] }>(
      `/api/recipes/cookable?max_missing=${maxMissing}&limit=30`,
    ),
  taste: () => req<TasteProfile>("/api/taste"),
  scanPhoto: (file: File) => {
    const form = new FormData();
    form.append("photo", file);
    return req<{ proposals: ScanProposal[] }>("/api/vision/scan", { method: "POST", body: form });
  },
  profile: () => req<{ profile: Profile | null; targets: Targets | null }>("/api/profile"),
  saveProfile: (p: Profile) =>
    req<{ profile: Profile; targets: Targets }>("/api/profile", {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(p),
    }),
  day: (date?: string) => req<DaySummary>(date ? `/api/day?date=${date}` : "/api/day"),
  addMeal: (meal: { name: string; calories: number; protein_g: number; carbs_g: number; fat_g: number }) =>
    req<{ logged: boolean; meal_log_id: number }>("/api/meals", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(meal),
    }),
  deleteMeal: (id: number) => req<{ deleted: number }>(`/api/meals/${id}`, { method: "DELETE" }),
  barcodeLookup: (code: string) =>
    req<{ product: Product }>(`/api/nutrition/barcode/${encodeURIComponent(code)}`),
  scanProduct: (file: File) => {
    const form = new FormData();
    form.append("photo", file);
    return req<{ product: Product }>("/api/nutrition/scan", { method: "POST", body: form });
  },
  recipe: (id: number) => req<RecipeDetail>(`/api/recipes/${id}`),
  logCooked: (id: number) =>
    req<{ logged: boolean; meal_log_id: number }>(`/api/recipes/${id}/cooked`, { method: "POST" }),
};

/** "black_pepper" -> "black pepper" for display */
export const pretty = (canonical: string) => canonical.replaceAll("_", " ");
