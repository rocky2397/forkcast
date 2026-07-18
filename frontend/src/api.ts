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
  recipe: (id: number) => req<RecipeDetail>(`/api/recipes/${id}`),
  logCooked: (id: number) =>
    req<{ logged: boolean; meal_log_id: number }>(`/api/recipes/${id}/cooked`, { method: "POST" }),
};

/** "black_pepper" -> "black pepper" for display */
export const pretty = (canonical: string) => canonical.replaceAll("_", " ");
