// Display helpers: turn the corpus's flattened text back into something a
// person would write, and give each food family a colour for the ingredient
// dots that stand in for recipe photos (the corpus has none).

const SMALL_WORDS = new Set(["a", "an", "and", "as", "at", "for", "in", "of", "on", "or", "the", "to", "with"]);

/** "angel hair pasta with basil   tomatoes" -> "Angel Hair Pasta with Basil & Tomatoes".
 *  The source dataset stripped punctuation to spaces, so three spaces were an
 *  ampersand, two were a comma, and a lone "s" was an apostrophe-s. */
export function displayName(raw: string): string {
  const text = raw
    .trim()
    .replace(/\s{3,}/g, " & ")
    .replace(/\s{2}/g, ", ")
    .replace(/(\w) s\b/g, "$1's");
  return text
    .split(" ")
    .map((w, i) => {
      if (i > 0 && SMALL_WORDS.has(w)) return w;
      return w.charAt(0).toUpperCase() + w.slice(1);
    })
    .join(" ");
}

/** "heat oven to 450f" -> "Heat oven to 450f". Recipe text is all lower case. */
export function sentence(raw: string): string {
  const t = raw
    .trim()
    .replace(/\s+([,.;:!?])/g, "$1")
    .replace(/\s{2,}/g, " ")
    .replace(/(\d)\s?-\s?(\d)/g, "$1–$2"); // "6-7 minutes" -> "6–7 minutes"
  // Capitalise each sentence, not just the first: "... paper. caramelizing" .
  const s = t.replace(/(^|[.!?]\s+)([a-z])/g, (_, lead: string, c: string) => lead + c.toUpperCase());
  return /[.!?)]$/.test(s) ? s : `${s}.`;
}

/** Breakfast, lunch or dinner, from the local clock. */
export function mealOfDay(d = new Date()): string {
  const h = d.getHours();
  return h < 11 ? "breakfast" : h < 16 ? "lunch" : "dinner";
}

// Colours per food class (backend/app/food_classes.py, D28). A few common
// foods outside any class get their own, so a tomato is never grey.
const FAMILY: Record<string, string> = {
  meat: "#D9A27A", cured_meat: "#C26D5B", seafood: "#7FA7B8", egg: "#F2D16B",
  bean: "#A0785A", dairy: "#F1E9DA", melting_cheese: "#F2C14E", hard_cheese: "#EBD9A0",
  crumbly_cheese: "#F4EEE3", soft_cheese: "#F7F3EA", allium: "#EFE7D6",
  green_veg: "#8DAA5B", aromatic_root: "#E2894B", starchy_root: "#C9A26B",
  cooking_green: "#4F7A3A", salad_green: "#9BC27A", cabbage: "#B7CF9A",
  mushroom: "#A8927A", fresh_chili: "#6E9A3E", dried_chili: "#B8402A",
  olive_caper: "#6B7240", herb: "#5B7F3F", warm_spice: "#A65E2E",
  spice_blend: "#C68A3C", ginger: "#D9B26B", citrus: "#F2D04B", berry: "#6E4A8C",
  stone_fruit: "#F0A36B", pome_fruit: "#C8D96B", tropical_fruit: "#F5B83D",
  dried_fruit: "#7A4E3A", nut: "#B08455", seed: "#D8C9A8", grain: "#E8D9B5",
  noodle: "#E3B55B", flatbread: "#E7CFA0", bread: "#D6A967", flour: "#F3EDE0",
  sweetener: "#D9A441", chocolate: "#5A3A2A", vinegar: "#B8865A", broth: "#D9B98A",
  cooking_wine: "#C9B26B", umami_sauce: "#4A3326", thick_sauce: "#6B3A2A",
  solid_fat: "#F2E3B3", oil: "#D6C060",
};
const FOOD: Record<string, string> = {
  tomato: "#D2553B", sun_dried_tomato: "#A8402C", bell_pepper: "#D8613C",
  cucumber: "#9BC27A", avocado: "#7E9A4A", corn: "#F2C94C", eggplant: "#5E3B5E",
  banana: "#F2D96B", pumpkin: "#E8873A", pea: "#7FA650",
};

export function foodColor(canonical: string, family: string | null): string {
  return FOOD[canonical] ?? (family ? FAMILY[family] : undefined) ?? "#CFC4B4";
}
