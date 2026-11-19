// A first visit, end to end, in a real browser: the check that the screens and
// the API still fit together. Unit tests on either side can't see that: a
// renamed field, a missing query parameter or an error rendered as
// "[object Object]" passes both and breaks the app.
//
//   node e2e/smoke.mjs <base-url> [failure-dir]
//
// Expects a Forkcast backend at <base-url> with an EMPTY data dir and the
// built frontend (ops/e2e.sh starts one). Drives the Chrome installed on the
// machine (playwright-core, channel "chrome"). Fails on any of:
//   - a step that doesn't show what it should,
//   - a JavaScript error or console error on the page,
//   - an API response of 400 or more,
//   - a serious or critical accessibility problem (axe-core, WCAG 2.1 AA)
//     on any screen it visits.
// On failure it saves a screenshot and the page's text to failure-dir.
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { join } from "node:path";
import { chromium } from "playwright-core";

const [base = "http://localhost:8798", failDir = "e2e-failure"] = process.argv.slice(2);
const require = createRequire(import.meta.url);
const AXE = readFileSync(require.resolve("axe-core/axe.min.js"), "utf8");

const problems = [];
// API errors a step provokes on purpose (a route it fakes), not counted as problems.
const expectedErrors = new Set();
// A 1×1 PNG: the "photo" for the faked label reader. It has no barcode in it.
const PHOTO = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=",
  "base64",
);

async function audit(page, screen) {
  await page.addScriptTag({ content: AXE });
  const result = await page.evaluate(() =>
    window.axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa"] } }),
  );
  for (const v of result.violations) {
    if (v.impact === "serious" || v.impact === "critical") {
      problems.push(`${screen}: accessibility, ${v.id} (${v.impact}): ${v.help}`);
    }
  }
}

const tab = (page, label) =>
  page.locator(".tabbar button:visible, .topnav button:visible").filter({ hasText: label }).first();

/** Wait until the element shows text matching pattern (the UI updates after the API answers). */
async function expectText(locator, pattern, what, state = "visible") {
  await locator.first().waitFor({ state, timeout: 10_000 });
  const until = Date.now() + 10_000;
  let text = "";
  while (Date.now() < until) {
    text = ((await locator.first().textContent()) ?? "").replace(/\s+/g, " ");
    if (pattern.test(text)) return text;
    await new Promise((r) => setTimeout(r, 200));
  }
  throw new Error(`${what}: expected ${pattern}, got "${text.slice(0, 200)}"`);
}

async function run(page) {
  let cooked = "";
  let usedUp = "";
  const steps = [
    ["the welcome screen", async () => {
      await page.goto(base);
      await page.getByRole("button", { name: "Get started" }).waitFor();
      await audit(page, "welcome");
      await page.getByRole("button", { name: "Get started" }).click();
    }],
    ["a new profile with a goal weight", async () => {
      await page.getByRole("heading", { name: "Your daily targets" }).waitFor();
      await audit(page, "profile form");
      await page.getByLabel("Sex").selectOption("f");
      await page.getByLabel("Age").fill("31");
      await page.getByLabel("Height (cm)").fill("170");
      await page.getByLabel("Weight (kg)").fill("72");
      await page.getByLabel("Activity").selectOption("moderate");
      await page.getByLabel("Goal weight in kg (optional)").fill("66");
      // Plain words, with the formula's study one click away for the curious.
      const study = page.getByRole("link", { name: "the study behind it" });
      if ((await study.getAttribute("href")) !== "https://doi.org/10.1093/ajcn/51.2.241") throw new Error("study link missing");
      // D44: the pace is a share of body weight, shown with its kilos.
      await expectText(page.getByLabel("Pace").locator("option:checked"), /0\.75% of your weight a week \(about 0\.54 kg\)/, "pace option", "attached");
      await page.getByRole("button", { name: "Save and work out my targets" }).click();
    }],
    ["Today shows the targets and the plan", async () => {
      await page.locator(".ring").waitFor();
      await expectText(page.locator(".plan-line"), /To reach 66 kg: about [\d,]+ kcal a day/, "plan line");
      await expectText(page.locator(".macros"), /Protein[\s\S]*Carbs[\s\S]*Fat/, "macro bars");
      await audit(page, "today");
    }],
    ["stock the kitchen by name", async () => {
      await tab(page, "Kitchen").click();
      const field = page.getByPlaceholder("e.g. chicken breasts");
      await field.fill("chicken breast, rice, onion, garlic, skyr, Zitrone");
      await page.getByRole("button", { name: "Add", exact: true }).click();
      await expectText(page.locator(".kitchen-group").filter({ hasText: /onion/i }), /onion/i, "kitchen list");
      // D46: skyr is yogurt, and a misspelling gets "Did you mean…?".
      await expectText(page.locator(".kitchen-group").filter({ hasText: /yogurt/i }), /yogurt/i, "skyr as yogurt");
      // D47: German names work too.
      await expectText(page.locator(".kitchen-group").filter({ hasText: /lemon/i }), /lemon/i, "Zitrone as lemon");
      await field.fill("tomatoe");
      await page.getByRole("button", { name: "Add", exact: true }).click();
      await expectText(page.locator(".did-you-mean"), /Couldn't match “tomatoe”\. Add instead/, "did you mean");
      await audit(page, "kitchen, did you mean");
      await page.locator(".did-you-mean").getByRole("button", { name: "+ tomato", exact: true }).click();
      await expectText(page.locator(".kitchen-group").filter({ hasText: /tomato/i }), /tomato/i, "suggestion added");
      await audit(page, "kitchen");
    }],
    ["the recipe feed and a recipe", async () => {
      await tab(page, "Recipes").click();
      const card = page.locator(".recipe-card").first();
      await card.waitFor({ timeout: 15_000 });
      await audit(page, "recipes");
      // Worth buying: three, then two more on request, the first three unchanged.
      const picks = page.locator(".shopping-item .shopping-name");
      await picks.nth(2).waitFor({ timeout: 30_000 });
      const firstThree = await picks.allTextContents();
      await page.getByRole("button", { name: "Show 2 more" }).click();
      await picks.nth(4).waitFor({ timeout: 30_000 });
      const five = await picks.allTextContents();
      if (five.slice(0, 3).join() !== firstThree.join()) throw new Error(`worth buying changed: ${firstThree} -> ${five}`);
      const name = (await card.locator(".recipe-title").innerText()).trim();
      cooked = name;
      await card.click();
      await expectText(page.locator(".recipe-detail h1"), new RegExp(name.slice(0, 12).replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "i"), "recipe title");
      await audit(page, "recipe");
      await page.getByRole("button", { name: "I cooked this" }).click();
      // "Did anything run out?": tick the first item; it should leave the kitchen.
      await page.getByRole("heading", { name: "Did anything run out?" }).waitFor();
      const first = page.locator(".scan-list li").first();
      usedUp = (await first.locator(".scan-name").innerText()).split("(")[0].trim();
      await first.getByRole("checkbox").check();
      await page.getByRole("button", { name: "Log cook, remove 1" }).click();
      await page.getByRole("button", { name: "Logged. Enjoy!" }).waitFor();
    }],
    ["what ran out left the kitchen", async () => {
      await tab(page, "Kitchen").click();
      await page.locator(".kitchen-group").first().waitFor();
      const list = (await page.locator(".kitchen-group").allTextContents()).join(" ").toLowerCase();
      if (list.includes(usedUp.toLowerCase())) throw new Error(`"${usedUp}" was ticked as used up but is still in the kitchen`);
    }],
    ["log a meal by hand", async () => {
      await tab(page, "Today").click();
      await page.locator(".ring").waitFor();
      await expectText(page.locator(".meal-list"), new RegExp(cooked.slice(0, 12).replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "i"), "cooked recipe on Today");
      await page.getByRole("button", { name: "Log a meal" }).click();
      await page.getByPlaceholder("e.g. Skyr with berries").fill("Smoke test salad");
      await page.getByRole("spinbutton", { name: "kcal", exact: true }).fill("420");
      await page.getByRole("spinbutton", { name: "Protein g" }).fill("18");
      await page.getByRole("button", { name: "Log meal" }).click();
      await expectText(page.locator(".meal-list"), /Smoke test salad/, "meal list");
      await expectText(page.locator(".meal-list li").filter({ hasText: "Smoke test salad" }).locator(".rate-note"),
        /Add it by ingredients to rate it/, "why a typed meal has no rating");
    }],
    ["a product that isn't on Open Food Facts (D48)", async () => {
      // Only the label reader (Claude) is faked; saving and the barcode lookup are real.
      const code = "4306188068372";
      const replies = [
        // 1. a label read with protein and fat missing: shown as "?", never 0
        { status: 200, body: { product: { barcode: null, name: null, brand: null, calories_100g: 50, protein_g_100g: null,
          carbs_g_100g: 69, fat_g_100g: null, source: "label", check: "Protein and fat couldn't be read from the photo, and the rest don't add up." } } },
        // 2. a photo of the barcode alone: found, but not listed
        { status: 404, body: { detail: { message: `Found barcode ${code}, but this product isn't on Open Food Facts yet.`, barcode: code } } },
        // 3. the nutrition table from the back of the pack
        { status: 200, body: { product: { barcode: code, name: "Smoke test chips", brand: null, calories_100g: 490,
          protein_g_100g: 6.5, carbs_g_100g: 61, fat_g_100g: 24, source: "label", check: null } } },
      ];
      const sent = [];
      await page.route("**/api/nutrition/scan", async (route) => {
        sent.push(route.request().postDataBuffer()?.toString("latin1") ?? "");
        const reply = replies[sent.length - 1];
        if (reply.status >= 400) expectedErrors.add("/api/nutrition/scan");
        await route.fulfill({ status: reply.status, contentType: "application/json", body: JSON.stringify(reply.body) });
      });
      const photo = () => page.locator('form input[type="file"]').setInputFiles({ name: "p.png", mimeType: "image/png", buffer: PHOTO });
      await page.getByRole("button", { name: "Log a meal" }).click();

      await photo();
      await expectText(page.locator(".product-macros"), /50 kcal · \? g protein · 69 g carbs · \? g fat/, "unread values as ?");
      if (await page.locator(".product-note").count()) throw new Error("an incomplete reading offered to be remembered");

      await photo();
      await expectText(page.locator(".feedback.error"), new RegExp(`Found barcode ${code}, but this product isn't on Open Food Facts`), "barcode not listed");
      await page.getByRole("button", { name: "Photograph the nutrition table" }).waitFor();
      await expectText(page.locator(".field-hint").filter({ hasText: "next photo" }), new RegExp(`nutrition table for barcode ${code}`), "carried barcode");

      await photo();
      await expectText(page.locator(".product-note"), /isn't on Open Food Facts yet\. When you add it, Forkcast remembers/, "remember note");
      if (!sent[2].includes(code)) throw new Error("the label photo was sent without the barcode from the photo before");
      const add = page.getByRole("link", { name: "Add it to Open Food Facts" });
      if ((await add.getAttribute("href")) !== `https://world.openfoodfacts.org/product/${code}`) throw new Error("Open Food Facts link wrong");
      await audit(page, "today, product read from a label");
      await page.getByRole("button", { name: "Add to meal" }).click();
      // D51: the product is a row of the meal, next to a USDA ingredient.
      await expectText(page.locator(".builder-source").first(), /Per 100 g read from the label/, "product row");
      await page.getByPlaceholder("e.g. banana, Haferflocken, rice").fill("banana");
      await page.getByPlaceholder("e.g. banana, Haferflocken, rice").press("Enter");
      await page.getByLabel("How much banana").waitFor();
      await expectText(page.locator(".builder-total"), /Together: 600 kcal/, "chips and a banana"); // 490 + 110
      await page.getByRole("button", { name: "Log meal" }).click();
      const chips = page.locator(".meal-list li").filter({ hasText: "Smoke test chips, banana" });
      await expectText(chips.locator(".meal-ingredients"), /banana 118 g · Smoke test chips 100 g/, "scanned meal logged");
      await page.unroute("**/api/nutrition/scan");

      // Next time the barcode alone fills it in, from the saved reading.
      const saved = await page.evaluate(async (c) => (await fetch(`/api/nutrition/barcode/${c}`)).json(), code);
      if (saved.product?.source !== "saved" || saved.product.calories_100g !== 490) throw new Error(`not remembered: ${JSON.stringify(saved)}`);
    }],
    ["a scanned product starts at one serving (D52)", async () => {
      // Only the scan reply is faked: an Open Food Facts product with a 30 g serving.
      await page.route("**/api/nutrition/scan", (route) => route.fulfill({
        status: 200, contentType: "application/json",
        body: JSON.stringify({ product: { barcode: "4012345678901", name: "Smoke test whey", brand: null,
          calories_100g: 380, protein_g_100g: 78, carbs_g_100g: 6, fat_g_100g: 5, source: "openfoodfacts",
          check: null, serving_g: 30, pack_g: 1000 } }),
      }));
      await page.getByRole("button", { name: "Log a meal" }).click();
      await page.locator('form input[type="file"]').setInputFiles({ name: "p.png", mimeType: "image/png", buffer: PHOTO });
      await expectText(page.locator(".product-card"), /Starts at one serving, 30 g according to Open Food Facts \(the pack is 1,000 g\)\. Change it to what you had\./, "serving hint");
      if ((await page.locator(".product-use input").inputValue()) !== "30") throw new Error("the card didn't start at one serving");
      await page.getByRole("button", { name: "Add to meal" }).click();
      await expectText(page.locator(".builder-total"), /Together: 114 kcal/, "one 30 g serving"); // 380 x 0.3
      if ((await page.getByLabel("Unit for Smoke test whey").inputValue()) !== "0") throw new Error("the row isn't in servings");
      await page.unroute("**/api/nutrition/scan");
      await page.getByRole("button", { name: "Cancel" }).click();
    }],
    ["a meal built from ingredients (D49)", async () => {
      await page.getByRole("button", { name: "Log a meal" }).click();
      const add = async (name) => {
        await page.getByPlaceholder("e.g. banana, Haferflocken, rice").fill(name);
        await page.getByPlaceholder("e.g. banana, Haferflocken, rice").press("Enter");
      };
      await add("Haferflocken"); // German, found as oats
      await page.getByLabel("How much oat").waitFor();
      await add("Milch");
      await page.getByLabel("How much milk").waitFor();
      await add("banana"); // a whole piece by default: 1 medium, 118 g
      await page.getByLabel("How much banana").waitFor();
      await page.getByLabel("How much oat").fill("50");
      await page.getByLabel("How much milk").fill("200");
      // 50 g oats 181 + 200 g milk 122 + 1 medium banana 110 (EU values, D53)
      await expectText(page.locator(".builder-total"), /Together: 413 kcal/, "built meal total");
      await expectText(page.locator(".builder-source").first(), /USDA: Cereals, oats/, "which USDA food");
      await add("Magerquark"); // a known ingredient the USDA table doesn't have
      await expectText(page.locator(".builder .feedback"), /No nutrition values for quark yet/, "quark");
      await audit(page, "today, meal built from ingredients");
      await page.getByLabel("Name it (optional)").fill("Smoke test porridge");
      await page.getByRole("button", { name: "Log meal" }).click();
      const meal = page.locator(".meal-list li").filter({ hasText: "Smoke test porridge" });
      await expectText(meal.locator(".meal-macros"), /413 kcal/, "server total");
      await expectText(meal.locator(".meal-ingredients"), /oat 50 g · milk 200 g · banana 118 g/, "what it was made of");
      await meal.getByRole("button", { name: "Liked" }).click(); // two or more ingredients: it can teach the feed
      await expectText(meal.locator(".rate"), /Liked/, "built meal rated");
    }],
    ["the amount from last time (D54)", async () => {
      // The porridge above had 50 g oats and one medium banana.
      await page.getByRole("button", { name: "Log a meal" }).click();
      const add = async (name) => {
        await page.getByPlaceholder("e.g. banana, Haferflocken, rice").fill(name);
        await page.getByPlaceholder("e.g. banana, Haferflocken, rice").press("Enter");
      };
      await add("Haferflocken");
      await page.getByLabel("How much oat").waitFor();
      if ((await page.getByLabel("How much oat").inputValue()) !== "50") throw new Error("oats didn't start at last time's 50 g");
      await expectText(page.locator(".builder-last").first(), /Same as last time\. Change it to what you had\./, "last-time note");
      await page.getByLabel("How much oat").fill("60");
      if (await page.locator(".builder-last").count()) throw new Error("the note stayed after the amount changed");
      await audit(page, "today, amount from last time");
      await page.getByRole("button", { name: "Cancel" }).click();
    }],
    ["log again, and a favourite (D50)", async () => {
      const again = page.locator(".again");
      await expectText(again, /Smoke test porridge[\s\S]*Smoke test salad/, "recent meals, latest first");
      await page.getByRole("button", { name: "Star Smoke test salad: keep it at the top" }).click();
      await expectText(again.locator(".again-item").first(), /Smoke test salad/, "the starred meal moved to the top");
      await audit(page, "today, log again");
      await page.getByRole("button", { name: "Log Smoke test porridge again" }).click();
      await expectText(page.locator(".meal-list"), /Smoke test porridge[\s\S]*Smoke test porridge/, "logged a second time");
      const copy = page.locator(".meal-list li").filter({ hasText: "Smoke test porridge" }).last();
      await expectText(copy.locator(".meal-ingredients"), /oat 50 g · milk 200 g · banana 118 g/, "with its ingredients");
    }],
    ["Done for today", async () => {
      await page.getByRole("button", { name: "Done for today" }).click();
      await expectText(page.locator(".day-check-done"), /Today is marked complete/, "day check");
    }],
    ["a weigh-in, and what you burn", async () => {
      await page.getByPlaceholder("Today's weight, kg").fill("71.8");
      await page.getByRole("button", { name: "Log weight" }).click();
      await expectText(page.locator(".weight-card h2"), /trend 71\.8 kg/, "weight trend");
      // D45: a new kitchen uses the formula and says how far learning has got.
      await expectText(page.locator(".burn-line"), /What you burn: about [\d,]+ kcal a day.*0 of 10 complete days/, "burn line");
      await audit(page, "today, after logging");
    }],
    ["everything is still there after a reload", async () => {
      await page.reload();
      await tab(page, "Today").click();
      await expectText(page.locator(".meal-list"), /Smoke test salad/, "meal list after reload");
      await expectText(page.locator(".weight-card h2"), /trend 71\.8 kg/, "weight after reload");
    }],
  ];
  for (const [name, fn] of steps) {
    await fn();
    console.log(`  ok  ${name}`);
  }
}

async function main() {
  const browser = await chromium.launch({ channel: "chrome", headless: true });
  const ctx = await browser.newContext({
    viewport: { width: 390, height: 844 },
    colorScheme: "light",
    reducedMotion: "reduce",
    serviceWorkers: "block",
  });
  // The screens' own guides start closed, as for someone who has seen them.
  await ctx.addInitScript(() => {
    for (const k of ["feedguide", "todayguide", "kitchenguide"]) localStorage.setItem(`forkcast.${k}.v1`, "1");
  });
  const page = await ctx.newPage();
  page.on("pageerror", (e) => problems.push(`JavaScript error: ${e.message}`));
  const expected = (url) => [...expectedErrors].some((path) => url.includes(path));
  page.on("console", (m) => {
    if (m.type() === "error" && !expected(m.location().url ?? "")) problems.push(`console error: ${m.text()}`);
  });
  page.on("response", (r) => {
    if (r.url().includes("/api/") && r.status() >= 400 && !expected(r.url())) {
      problems.push(`API ${r.status()}: ${r.request().method()} ${r.url()}`);
    }
  });

  let failed = null;
  try {
    await run(page);
  } catch (e) {
    failed = e;
  }
  if (failed || problems.length) {
    mkdirSync(failDir, { recursive: true });
    await page.screenshot({ path: join(failDir, "screen.png"), fullPage: true }).catch(() => {});
    writeFileSync(join(failDir, "page.txt"), await page.locator("body").innerText().catch(() => ""));
  }
  await browser.close();
  if (failed) console.error(`\nFAILED: ${failed.message}`);
  for (const p of problems) console.error(`  problem: ${p}`);
  if (failed || problems.length) process.exit(1);
  console.log("\nSmoke test passed: no errors, no failed API calls, no serious accessibility problems.");
}

main();
