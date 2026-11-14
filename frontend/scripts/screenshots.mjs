// README screenshots and an accessibility check, from a fresh demo kitchen.
//
//   node scripts/screenshots.mjs <base-url> <out-dir>
//
// Expects a Forkcast backend at <base-url> with an EMPTY data dir (ops/screenshots.sh
// starts one). Seeds the same demo kitchen every time through the public API,
// drives the real UI in the Chrome already installed on the machine
// (playwright-core, channel "chrome"; no browser download), saves the
// screenshots, and runs axe-core on every screen it visits. Exits non-zero
// on any serious or critical WCAG 2.1 AA violation.
import { readFileSync, mkdirSync } from "node:fs";
import { createRequire } from "node:module";
import { join } from "node:path";
import { chromium } from "playwright-core";

const [base = "http://localhost:8799", outDir = "../docs/screenshots"] = process.argv.slice(2);
const require = createRequire(import.meta.url);
const AXE = readFileSync(require.resolve("axe-core/axe.min.js"), "utf8");

// The demo kitchen. Recipe ids belong to corpus release corpus-20261114-d29.
const KITCHEN = [
  "basil", "bell pepper", "carrots", "chicken breasts", "chickpeas", "cumin", "eggs",
  "feta", "garlic", "ginger", "honey", "lemons", "milk", "oats", "paprika", "parmesan",
  "pasta", "potatoes", "red onion", "rice", "soy sauce", "spinach", "tomatoes",
  "greek yogurt", "zucchini",
];
const PROFILE = { sex: "f", age: 29, height_cm: 168, weight_kg: 63, activity: "moderate", goal: "maintain" };
const COOKED = [49644, 21529]; // Cherry Tomato Pasta, Foil Chicken Casserole for One: both liked
const TYPED_MEAL = { name: "Oats with yogurt and honey", calories: 420, protein_g: 18, carbs_g: 64, fat_g: 9 };

async function api(path, body, method = body ? "POST" : "GET") {
  const res = await fetch(base + path, {
    method,
    headers: { "content-type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`${path}: ${res.status} ${await res.text()}`);
  return res.json();
}

async function seed() {
  const day = await api("/api/day");
  if (day.meals.length || (await api("/api/inventory")).items.length) {
    throw new Error("the data dir is not empty; run this against a fresh one (ops/screenshots.sh)");
  }
  await api("/api/profile", PROFILE, "PUT");
  const inv = await api("/api/inventory", { items: KITCHEN });
  if (inv.unknown.length) throw new Error(`demo kitchen items not recognised: ${inv.unknown}`);
  for (const id of COOKED) {
    const { meal_log_id } = await api(`/api/recipes/${id}/cooked`, { used_up: [] });
    await api(`/api/meals/${meal_log_id}/rate`, { liked: true });
  }
  await api("/api/meals", TYPED_MEAL);
}

const violations = [];
async function audit(page, label) {
  await page.addScriptTag({ content: AXE });
  const result = await page.evaluate(() =>
    window.axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa"] } }),
  );
  for (const v of result.violations) {
    violations.push({ screen: label, id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.length });
  }
}

async function shot(page, name, label) {
  await page.waitForTimeout(400); // fonts and transitions settle
  await page.screenshot({ path: join(outDir, `${name}.jpg`), type: "jpeg", quality: 86 });
  await audit(page, label);
  console.log(`  ${name}.jpg`);
}

async function context(browser, viewport, deviceScaleFactor) {
  const ctx = await browser.newContext({
    viewport,
    deviceScaleFactor,
    colorScheme: "light",
    reducedMotion: "reduce",
    serviceWorkers: "block",
  });
  // Walkthrough and guides already seen: the screenshots show the screens.
  await ctx.addInitScript(() => {
    for (const k of ["intro", "feedguide", "todayguide", "kitchenguide"]) {
      localStorage.setItem(`forkcast.${k}.v1`, "1");
    }
  });
  return ctx;
}

const tab = (page, label) => page.locator(".tabbar button:visible, .topnav button:visible").filter({ hasText: label }).first();

async function main() {
  mkdirSync(outDir, { recursive: true });
  await seed();
  const browser = await chromium.launch({ channel: "chrome", headless: true });
  try {
    // Phone: 390x844 at 2x, like a current iPhone.
    const phone = await (await context(browser, { width: 390, height: 844 }, 2)).newPage();
    await phone.goto(base);

    await tab(phone, "Recipes").click();
    await phone.locator(".recipe-card").first().waitFor();
    await shot(phone, "recipes", "feed (phone)");

    // The shopping suggestions sit below the feed: scroll their heading to the top.
    await phone.locator("#worth-buying").evaluate((h) => window.scrollTo(0, h.getBoundingClientRect().top + window.scrollY - 80));
    await shot(phone, "shopping", "worth buying (phone)");
    await phone.evaluate(() => window.scrollTo(0, 0));

    // A one-away recipe with a swap: the demo's pick if it's listed, else the first.
    await phone.getByRole("button", { name: "One away" }).click();
    await phone.locator(".recipe-card").filter({ hasText: "use your" }).first().waitFor();
    const pick = phone.locator(".recipe-card").filter({ hasText: "Chicken and Chickpea Salad" });
    await ((await pick.count()) ? pick.first() : phone.locator(".recipe-card").filter({ hasText: "use your" }).first()).click();
    await phone.locator(".recipe-detail h1").waitFor();
    await shot(phone, "recipe", "recipe detail (phone)");

    await tab(phone, "Today").click();
    await phone.locator(".ring").waitFor();
    await shot(phone, "today", "today (phone)");

    await tab(phone, "Kitchen").click();
    await phone.locator(".kitchen-group").first().waitFor();
    await shot(phone, "kitchen", "kitchen (phone)");

    // Desktop: the feed with the open recipe beside it.
    const desk = await (await context(browser, { width: 1440, height: 900 }, 1.5)).newPage();
    await desk.goto(base);
    await tab(desk, "Recipes").click();
    await desk.locator(".detail-pane h1").waitFor();
    await shot(desk, "desktop", "feed (desktop)");
  } finally {
    await browser.close();
  }

  const serious = violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  console.log(`\naxe-core, WCAG 2.1 AA: ${violations.length} violation(s), ${serious.length} serious or critical`);
  for (const v of violations) console.log(`  [${v.impact}] ${v.screen}: ${v.id} (${v.nodes}) ${v.help}`);
  if (serious.length) process.exit(1);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
