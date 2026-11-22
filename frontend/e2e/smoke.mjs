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
      // D68: what you get first, then how, with no way to skip the profile.
      await page.getByRole("heading", { name: "Meals that fit your fridge and your goal." }).waitFor();
      if (await page.getByRole("button", { name: /Skip/ }).count()) throw new Error("the welcome can be skipped");
      await audit(page, "welcome");
      await page.getByRole("button", { name: "Get started" }).click();
      await expectText(page.locator(".intro"), /Your kitchen[\s\S]*Pick a meal[\s\S]*Say you ate it/, "welcome steps");
      await audit(page, "how it works");
      await page.getByRole("button", { name: "Set my targets" }).click();
    }],
    ["a new profile with a goal weight", async () => {
      await page.getByRole("heading", { name: "Your daily targets" }).waitFor();
      await audit(page, "profile form");
      // D60: a new profile starts empty, so nobody saves sample numbers as theirs,
      // and saving an empty one stays on the form.
      for (const field of ["Age", "Height (cm)", "Weight (kg)"]) {
        if ((await page.getByLabel(field).inputValue()) !== "") throw new Error(`${field} starts filled in`);
      }
      await page.getByRole("button", { name: "Save and work out my targets" }).click();
      await expectText(page.locator(".profile-form .error"), /Choose your sex/, "the app's own words for what's missing");
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
      // D58: short enough for a phone; the share of body weight is in the hint below.
      await expectText(page.getByLabel("Pace").locator("option:checked"), /Steady: about 0\.54 kg a week/, "pace option", "attached");
      await expectText(page.locator(".profile-form"), /gentle is 0\.5% a week, steady 0\.75%/, "pace hint");
      await page.getByRole("button", { name: "Save and work out my targets" }).click();
    }],
    ["the welcome ends on your day", async () => {
      // D68: the payoff before any tab: your numbers and the plan, said to be an estimate.
      await page.getByRole("heading", { name: "Here's your day" }).waitFor();
      await expectText(page.locator(".day-targets"), /[\d,]+ kcal a day[\s\S]*\d+ g protein/, "targets");
      await expectText(page.locator(".intro .plan-line"), /To reach 66 kg/, "plan on the payoff");
      await expectText(page.locator(".intro"), /formula's estimate/, "said to be an estimate");
      if (await page.getByRole("button", { name: "Use a sample person" }).count()) throw new Error("sample person outside the demo");
      await audit(page, "your day");
      await page.getByRole("button", { name: "Go to today" }).click();
    }],
    ["Today shows the targets and the plan", async () => {
      await page.locator(".ring").waitFor();
      // With a profile, the welcome never comes back.
      await page.reload();
      await page.locator(".ring").waitFor();
      if (await page.locator(".intro").count()) throw new Error("welcome shown again with a profile");
      await expectText(page.locator(".plan-line"), /To reach 66 kg: about [\d,]+ kcal a day/, "plan line");
      await expectText(page.locator(".macros"), /Protein[\s\S]*Carbs[\s\S]*Fat/, "macro bars");
      await audit(page, "today");
    }],
    ["stock the kitchen by name", async () => {
      await tab(page, "Kitchen").click();
      const field = page.getByPlaceholder("e.g. chicken, rice");
      await field.fill("chicken breast, rice, onion, garlic, skyr, Zitrone");
      await page.getByRole("button", { name: "Add", exact: true }).click();
      await expectText(page.locator(".kitchen-group").filter({ hasText: /onion/i }), /onion/i, "kitchen list");
      // D46: skyr is yogurt, and a misspelling gets "Did you mean…?".
      await expectText(page.locator(".kitchen-group").filter({ hasText: /yogurt/i }), /yogurt/i, "skyr as yogurt");
      // D47: German names work too.
      await expectText(page.locator(".kitchen-group").filter({ hasText: /lemon/i }), /lemon/i, "Zitrone as lemon");
      // D66: adding what's there says so, once.
      await field.fill("Zwiebeln, onions");
      await page.getByRole("button", { name: "Add", exact: true }).click();
      await expectText(page.locator("main"), /Already in your kitchen: onion\./, "already there");
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
      await page.getByRole("button", { name: "I ate it" }).click();
      // "What ran out?": D70 may start some ticked; tick just the first, which should leave the kitchen.
      await page.getByRole("heading", { name: "What ran out?" }).waitFor();
      for (const box of await page.locator(".cook-confirm .scan-list input[type=checkbox]").all()) await box.uncheck();
      const first = page.locator(".scan-list li").first();
      usedUp = (await first.locator(".scan-name").innerText()).split("(")[0].trim();
      await first.getByRole("checkbox").check();
      // D66: a double tap logs the recipe once (counted on Today below).
      await page.getByRole("button", { name: "Log it and remove 1 from your kitchen" }).evaluate((b) => { b.click(); b.click(); });
      await expectText(page.locator(".cook-done"), /Logged\. Enjoy!/, "logged");
      // D71: what ran out can go on the shopping list.
      await page.getByRole("button", { name: "Put what ran out on the shopping list" }).click();
      await expectText(page.locator(".cook-done"), /On your shopping list\./, "ran out, on the list");
      // D60: the recipe now reads against what's left: what ran out is missing.
      await expectText(page.locator(".recipe-detail"), /1 ingredient away/i, "recipe after cooking");
    }],
    ["what ran out left the kitchen", async () => {
      await tab(page, "Kitchen").click();
      await page.locator(".kitchen-group").first().waitFor();
      const list = (await page.locator(".kitchen-group").allTextContents()).join(" ").toLowerCase();
      if (list.includes(usedUp.toLowerCase())) throw new Error(`"${usedUp}" was ticked as used up but is still in the kitchen`);
    }],
    ["the shopping list (D71)", async () => {
      // A Worth buying pick goes on the list in one tap.
      await tab(page, "Recipes").click();
      const pick = page.getByRole("button", { name: /^Put .+ on the shopping list$/ }).first();
      await pick.waitFor({ timeout: 30_000 });
      const picked = (await pick.getAttribute("aria-label")).replace(/^Put | on the shopping list$/g, "");
      await pick.click();
      await page.getByRole("button", { name: `${picked} is on your list` }).waitFor();
      // The Kitchen shows the list: what ran out (from the cooked recipe) and the pick, each with its reason.
      await tab(page, "Kitchen").click();
      const list = page.locator(".buy-list");
      await expectText(list, new RegExp(`${usedUp}[\\s\\S]*Ran out`, "i"), "ran out on the list");
      await expectText(list, /Worth buying/, "pick on the list");
      // Typed in, then taken off again.
      await list.getByRole("textbox", { name: "Add to the shopping list" }).fill("milk");
      await list.getByRole("button", { name: "Add to list" }).click();
      await list.getByRole("button", { name: "Take milk off the list" }).click();
      await expectText(list, /^(?![\s\S]*\bmilk\b)/i, "milk taken off");
      await audit(page, "kitchen, shopping list");
      // Bought: ticked goes into the kitchen and off the list.
      await list.getByRole("checkbox", { name: new RegExp(usedUp, "i") }).check();
      await list.getByRole("button", { name: "Put 1 in your kitchen" }).click();
      await expectText(list, new RegExp(`In your kitchen now: ${usedUp}`, "i"), "bought");
      await expectText(page.locator(".kitchen-groups"), new RegExp(usedUp, "i"), "back in the kitchen");
    }],
    ["fix the kitchen on a recipe, cook it, eat it, undo (D70)", async () => {
      await tab(page, "Recipes").click();
      await page.locator(".recipe-card").first().click();
      await page.locator(".recipe-detail h1").waitFor();
      const title = (await page.locator(".recipe-detail h1").innerText()).trim();
      // "Don't have it" moves a food to Missing; "Have it" brings it back.
      const dont = page.getByRole("button", { name: /^Don't have it: / }).first();
      const food = (await dont.getAttribute("aria-label")).replace("Don't have it: ", "");
      await dont.click();
      // exact: "Have it: x" is also a substring of "Don't have it: x".
      await page.getByRole("button", { name: `Have it: ${food}`, exact: true }).click();
      await page.getByRole("button", { name: `Don't have it: ${food}`, exact: true }).waitFor();
      // "I'm cooking this" pins it; Today shows it and leads back.
      await page.getByRole("button", { name: "I'm cooking this" }).click();
      const close = page.getByRole("button", { name: "Close cook mode" });
      if (await close.isVisible()) await close.click();
      await expectText(page.locator(".cooking-note"), /Pinned while you cook/, "pinned note");
      await tab(page, "Today").click();
      await expectText(page.locator(".cooking-card"), new RegExp(title.slice(0, 12).replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "i"), "cooking now card");
      await audit(page, "today, cooking now");
      await page.getByRole("button", { name: "Back to the recipe" }).click();
      await page.getByRole("button", { name: "I ate it" }).click();
      // Each row says what its tick means.
      for (const row of await page.locator(".cook-confirm .scan-list li").all()) {
        const ticked = await row.getByRole("checkbox").isChecked();
        await expectText(row.locator(".scan-qty"), ticked ? /Ran out/ : /Some left/, "ran out or some left");
      }
      await audit(page, "recipe, what ran out");
      await page.getByRole("button", { name: /^Log it/ }).click();
      await expectText(page.locator(".cook-done"), /Logged\. Enjoy!/, "logged");
      // Undo takes the meal off the log and puts back what ran out (the meal counts below stay right).
      await page.locator(".cook-done").getByRole("button", { name: "Undo" }).click();
      await page.getByRole("button", { name: "I ate it" }).waitFor();
      await tab(page, "Today").click();
      if (await page.locator(".cooking-card").count()) throw new Error("the pin should go once you ate it");
    }],
    ["a fridge scan: confident, not sure, looks gone (D69)", async () => {
      // Only the model's reply is faked: what Haiku 5.5 returns, as the scan route shapes it.
      await page.route("**/api/vision/scan", (route) => route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ proposals: [
          { seen: "eggs", quantity: "6", confidence: 0.9, canonical: "egg", sure: true },
          { seen: "leek", quantity: null, confidence: 0.55, canonical: "leek", sure: false },
          { seen: "onions", quantity: "2", confidence: 0.9, canonical: "onion", sure: true },
          { seen: "leftovers", quantity: null, confidence: 0.5, canonical: null, sure: false },
        ] }),
      }));
      await tab(page, "Kitchen").click();
      await page.locator(".kitchen-actions input[type=file]").setInputFiles({ name: "fridge.png", mimeType: "image/png", buffer: PHOTO });
      await page.getByRole("heading", { name: "Found in your photo" }).waitFor();
      const section = (name) => page.locator(".scan-section").filter({ has: page.getByRole("heading", { name, exact: true }) });
      // Sure: ticked. Not sure: offered, not ticked. Already there: named, not offered again.
      if (!(await section("Confident").getByRole("checkbox", { name: /egg/i }).isChecked())) throw new Error("a sure item should start ticked");
      if (await section("Not sure").getByRole("checkbox", { name: /leek/i }).isChecked()) throw new Error("an unsure item should start unticked");
      await expectText(page.locator(".scan-still"), /Already in your kitchen: onion\./, "already in the kitchen");
      // Looks gone: kitchen food the photo didn't show is offered, never removed on its own.
      const gone = section("Looks gone").getByRole("checkbox").first();
      if (await gone.isChecked()) throw new Error("nothing should be removed without a tick");
      const goneName = (await section("Looks gone").locator(".scan-name").first().innerText()).trim();
      await audit(page, "fridge scan confirm");
      await section("Not sure").getByRole("checkbox", { name: /leek/i }).check();
      await gone.check();
      await page.getByRole("button", { name: "+ Pasta" }).click();
      await page.getByRole("button", { name: "Update kitchen: add 3, remove 1" }).click();
      await expectText(page.locator(".notice"), new RegExp(`Removed ${goneName}`, "i"), "used up removed");
      const list = (await page.locator(".kitchen-group").allTextContents()).join(" ").toLowerCase();
      for (const want of ["egg", "leek", "pasta"]) if (!list.includes(want)) throw new Error(`${want} should be in the kitchen after the scan`);
      if (list.includes(goneName.toLowerCase())) throw new Error(`${goneName} was ticked as used up but is still there`);
      await page.unroute("**/api/vision/scan");
    }],
    ["log a meal by hand", async () => {
      await tab(page, "Today").click();
      await page.locator(".ring").waitFor();
      await expectText(page.locator(".meal-list"), new RegExp(cooked.slice(0, 12).replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "i"), "cooked recipe on Today");
      const cookedCount = await page.locator(".meal-list li").count();
      if (cookedCount !== 1) throw new Error(`a double tap on Log it logged the recipe ${cookedCount} times`);
      await page.getByRole("button", { name: "Log a meal" }).click();
      await page.getByRole("button", { name: "Or type the calories yourself" }).click();
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
      await page.getByPlaceholder("e.g. 2 eggs, 50 g oats").fill("banana");
      await page.getByPlaceholder("e.g. 2 eggs, 50 g oats").press("Enter");
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
        await page.getByPlaceholder("e.g. 2 eggs, 50 g oats").fill(name);
        await page.getByPlaceholder("e.g. 2 eggs, 50 g oats").press("Enter");
      };
      await add("Haferflocken"); // German, found as oats
      await page.getByLabel("How much oats").waitFor();
      await add("Milch");
      await page.getByLabel("How much milk").waitFor();
      await add("banana"); // a whole piece by default: 1 medium, 118 g
      // D60: short enough for a phone's unit menu.
      await expectText(page.getByLabel("Unit for banana").locator("option:checked"), /^× medium \(118 g\)$/, "short unit", "attached");
      await page.getByLabel("How much banana").waitFor();
      await page.getByLabel("How much oats").fill("50");
      await page.getByLabel("How much milk").fill("200");
      // D60: a big number next to a portion is checked: 20 bananas is 2,360 g.
      await page.getByLabel("How much banana").fill("20");
      await expectText(page.locator(".builder-item").filter({ hasText: "Banana" }), /That's 2,360 g\. Meant 20 g\?/, "grams guard");
      await page.getByLabel("How much banana").fill("1");
      // 50 g oats 181 + 200 g milk 122 + 1 medium banana 110 (EU values, D53)
      await expectText(page.locator(".builder-total"), /Together: 413 kcal/, "built meal total");
      await expectText(page.locator(".builder-source").first(), /USDA: Cereals, oats/, "which USDA food");
      await add("Garam Masala"); // a known ingredient with no good USDA food
      await expectText(page.locator(".builder .feedback"), /No nutrition values for garam masala yet/, "garam masala");
      await audit(page, "today, meal built from ingredients");
      await page.getByLabel("Name it (optional)").fill("Smoke test porridge");
      await page.getByRole("button", { name: "Log meal" }).click();
      const meal = page.locator(".meal-list li").filter({ hasText: "Smoke test porridge" });
      await expectText(meal.locator(".meal-macros"), /413 kcal/, "server total");
      await expectText(meal.locator(".meal-ingredients"), /oats 50 g · milk 200 g · banana 118 g/, "what it was made of");
      await meal.getByRole("button", { name: "Liked" }).click(); // two or more ingredients: it can teach the feed
      await expectText(meal.locator(".rate"), /Liked/, "built meal rated");
    }],
    ["the amount from last time (D54)", async () => {
      // The porridge above had 50 g oats and one medium banana.
      await page.getByRole("button", { name: "Log a meal" }).click();
      const add = async (name) => {
        await page.getByPlaceholder("e.g. 2 eggs, 50 g oats").fill(name);
        await page.getByPlaceholder("e.g. 2 eggs, 50 g oats").press("Enter");
      };
      await add("Haferflocken");
      await page.getByLabel("How much oats").waitFor();
      if ((await page.getByLabel("How much oats").inputValue()) !== "50") throw new Error("oats didn't start at last time's 50 g");
      await expectText(page.locator(".builder-last").first(), /Same as last time\. Change it to what you had\./, "last-time note");
      await page.getByLabel("How much oats").fill("60");
      if (await page.locator(".builder-last").count()) throw new Error("the note stayed after the amount changed");
      await audit(page, "today, amount from last time");
      await page.getByRole("button", { name: "Cancel" }).click();
    }],
    ["everyday words find the food people mean (D55)", async () => {
      await page.getByRole("button", { name: "Log a meal" }).click();
      const add = async (name) => {
        await page.getByPlaceholder("e.g. 2 eggs, 50 g oats").fill(name);
        await page.getByPlaceholder("e.g. 2 eggs, 50 g oats").press("Enter");
      };
      await add("Paprika"); // the vegetable in a meal, not the spice
      await page.getByLabel("How much bell pepper").waitFor();
      await expectText(page.locator(".builder-item").filter({ hasText: "Bell pepper" }).locator(".builder-source"), /USDA: Peppers, sweet, red, raw/, "paprika is the vegetable");
      await add("Reis gekocht");
      await page.getByLabel("How much rice").waitFor();
      if ((await page.getByLabel("Weighed raw or cooked: rice").inputValue()) !== "cooked") throw new Error("Reis gekocht didn't start cooked");
      await add("Haferdrink");
      await page.getByLabel("How much oat drink").waitFor();
      await expectText(page.locator(".builder-item").filter({ hasText: "Oat drink" }).locator(".builder-source"), /Open Food Facts: median of 12 products sold in Germany/, "German-pack values");
      await expectText(page.getByLabel("Unit for oat drink"), /× glass \(250 g\)/, "a glass for a drink");
      await audit(page, "today, everyday words");
      await page.getByRole("button", { name: "Cancel" }).click();
    }],
    ["amounts, several foods and dishes in one line (D61, D62)", async () => {
      await page.getByRole("button", { name: "Log a meal" }).click();
      const box = page.getByPlaceholder("e.g. 2 eggs, 50 g oats");
      await box.fill("2 Eier, Haferflocken, 50 g, Blubberkraut");
      await box.press("Enter");
      await page.getByLabel("How much egg").waitFor();
      if ((await page.getByLabel("How much egg").inputValue()) !== "2") throw new Error("the 2 in 2 Eier was lost");
      await expectText(page.getByLabel("Unit for egg").locator("option:checked"), /^× large \(50 g\)$/, "eggs as pieces", "attached");
      if ((await page.getByLabel("How much oats").inputValue()) !== "50") throw new Error("Haferflocken, 50 g isn't 50 g");
      await expectText(page.locator(".builder .feedback"), /Couldn't find "Blubberkraut"/, "what wasn't found");
      if ((await box.inputValue()) !== "Blubberkraut") throw new Error("the word not found should stay in the box");
      await page.getByRole("button", { name: "Cancel" }).click();
      // A dish is its typical parts, and names the meal.
      await page.getByRole("button", { name: "Log a meal" }).click();
      await box.fill("Cappuccino");
      await box.press("Enter");
      await page.getByLabel("How much espresso").waitFor();
      await expectText(page.locator(".builder-dish"), /A typical cappuccino\. Change any amount that's different\./, "dish note");
      // D65: the note heads the dish's own rows: the next row is the espresso.
      await expectText(page.locator(".builder-dish + .builder-item strong"), /Espresso/, "note above its rows");
      if ((await page.getByLabel("Name it (optional)").inputValue()) !== "Cappuccino") throw new Error("the dish didn't name the meal");
      await audit(page, "today, a dish");
      await page.getByRole("button", { name: "Cancel" }).click();
      // D63: fat levels: "fettarme Milch" is 1.5% milk, and the row can switch.
      await page.getByRole("button", { name: "Log a meal" }).click();
      await box.fill("200 ml fettarme Milch");
      await box.press("Enter");
      const fat = page.getByLabel("Fat level: low-fat milk");
      await fat.waitFor();
      await expectText(fat.locator("option:checked"), /Low-fat milk, 1\.5% fat/, "1.5% milk", "attached");
      const kcal = async () => Number((await page.locator(".builder-kcal").first().innerText()).replace(/\D/g, ""));
      const low = await kcal();
      await fat.selectOption("milk");
      await expectText(page.getByLabel("Fat level: milk").locator("option:checked"), /Whole milk, 3\.2% fat/, "whole milk", "attached");
      await page.getByLabel("Fat level: milk").waitFor();
      if ((await page.getByLabel("How much milk").inputValue()) !== "200") throw new Error("switching fat level lost the amount");
      if (!((await kcal()) > low)) throw new Error("whole milk should have more calories than 1.5%");
      await page.getByRole("button", { name: "Cancel" }).click();
      // D64: chickpeas from a can, drained: a form of their own.
      await page.getByRole("button", { name: "Log a meal" }).click();
      await box.fill("200 g Kichererbsen aus der Dose");
      await box.press("Enter");
      const form = page.getByLabel("Weighed raw or cooked: chickpeas");
      await form.waitFor();
      if ((await form.inputValue()) !== "canned") throw new Error("Kichererbsen aus der Dose didn't start canned");
      await expectText(page.locator(".builder-source").first(), /Open Food Facts: median of 12 products sold in Germany/, "values from German cans");
      await page.getByRole("button", { name: "Cancel" }).click();
    }],
    ["German words, spoons and typos (D67)", async () => {
      await page.getByRole("button", { name: "Log a meal" }).click();
      const box = page.getByPlaceholder("e.g. 2 eggs, 50 g oats");
      await box.fill("1 TL Zucker, Käsebrot, Knöblauch");
      await box.press("Enter");
      await page.getByLabel("How much sugar").waitFor();
      await expectText(page.getByLabel("Unit for sugar").locator("option:checked"), /^× tsp/, "a teaspoon", "attached");
      await expectText(page.locator(".builder-dish"), /A typical Käsebrot\. /, "Käsebrot is a dish, its name as it reads");
      // A typo is offered the right food, not turned into leek.
      await expectText(page.locator(".builder .feedback"), /Couldn't find "Knöblauch"[\s\S]*garlic/, "typo offered garlic");
      await page.getByRole("button", { name: "Cancel" }).click();
    }],
    ["log again, and a favourite (D50)", async () => {
      const again = page.locator(".again");
      await expectText(again, /Smoke test porridge[\s\S]*Smoke test salad/, "recent meals, latest first");
      await page.getByRole("button", { name: "Star Smoke test salad: keep it at the top" }).click();
      await expectText(again.locator(".again-item").first(), /Smoke test salad/, "the starred meal moved to the top");
      await audit(page, "today, log again");
      // D66: a double tap logs it once.
      await page.getByRole("button", { name: "Log Smoke test porridge again" }).evaluate((b) => { b.click(); b.click(); });
      await expectText(page.locator(".meal-list"), /Smoke test porridge[\s\S]*Smoke test porridge/, "logged a second time");
      await page.waitForTimeout(800);
      const porridges = await page.locator(".meal-list li").filter({ hasText: "Smoke test porridge" }).count();
      if (porridges !== 2) throw new Error(`a double tap on Log again logged ${porridges - 1} copies`);
      const copy = page.locator(".meal-list li").filter({ hasText: "Smoke test porridge" }).last();
      await expectText(copy.locator(".meal-ingredients"), /oats 50 g · milk 200 g · banana 118 g/, "with its ingredients");
    }],
    ["edit, undo, servings and an earlier day (D56)", async () => {
      // Edit: back into the form, filled in, and saved over.
      await page.getByRole("button", { name: "Edit Smoke test porridge" }).first().click();
      await page.getByLabel("How much oats").waitFor();
      await page.getByLabel("How much oats").fill("60");
      await page.getByRole("button", { name: "Save changes" }).click();
      await expectText(page.locator(".meal-list"), /oats 60 g · milk 200 g/, "edited meal");
      // Remove, then Undo.
      await page.getByRole("button", { name: "Remove Smoke test salad" }).click();
      await expectText(page.locator(".undo-bar"), /Removed Smoke test salad\./, "undo bar");
      // D66: a second removal joins the first; Undo puts both back.
      await page.locator(".meal-list li").filter({ hasText: "Smoke test salad" }).waitFor({ state: "detached" });
      const before = await page.locator(".meal-list li").count();
      await page.getByRole("button", { name: "Remove Smoke test porridge" }).first().click();
      await expectText(page.locator(".undo-bar"), /Removed 2 meals\./, "undo bar for two");
      await page.locator(".undo-bar").getByRole("button", { name: "Undo" }).click();
      await expectText(page.locator(".meal-list"), /Smoke test salad/, "salad back");
      await page.waitForFunction((n) => document.querySelectorAll(".meal-list li").length === n, before + 1);
      // Servings of the cooked recipe.
      const cookedMeal = page.locator(".meal-list li").filter({ has: page.locator(".servings select") }).first();
      const kcal = async () => Number((await cookedMeal.locator(".meal-macros").innerText()).match(/([\d,]+) kcal/)[1].replace(",", ""));
      const one = await kcal();
      await cookedMeal.locator(".servings select").selectOption("2");
      await expectText(cookedMeal.locator(".meal-macros"), /^2 servings · /, "2 servings");
      if (Math.abs((await kcal()) - 2 * one) > 1) throw new Error("two servings didn't double the calories");
      // An earlier day, filled in afterwards.
      await page.getByRole("button", { name: "‹ Earlier" }).click();
      await expectText(page.locator(".empty-note"), /Nothing logged on /, "an empty earlier day");
      await page.getByRole("button", { name: "Log a meal" }).click();
      await expectText(page.locator(".form-title"), /Log a meal for /, "logging for that day");
      await page.getByRole("button", { name: "Or type the calories yourself" }).click();
      await page.getByPlaceholder("e.g. Skyr with berries").fill("Smoke test yesterday");
      await page.getByRole("spinbutton", { name: "kcal", exact: true }).fill("300");
      await page.getByRole("button", { name: "Log meal" }).click();
      await expectText(page.locator(".meal-list"), /Smoke test yesterday/, "logged on the earlier day");
      await audit(page, "today, an earlier day");
      await page.getByRole("button", { name: "Later ›" }).click();
      await page.getByRole("heading", { name: "Today", exact: true }).waitFor();
      if ((await page.locator(".meal-list").innerText()).includes("Smoke test yesterday")) throw new Error("yesterday's meal shows today");
      // A meal logged for yesterday brings the question about yesterday first.
      await page.getByRole("button", { name: "No, I missed some" }).click();
    }],
    ["calmer screens (D58)", async () => {
      // "Log a meal" sits above the meals, not below them.
      const above = await page.evaluate(() => {
        const btn = [...document.querySelectorAll("button")].find((b) => b.textContent.trim() === "Log a meal");
        const list = document.querySelector(".meal-list");
        return Boolean(btn && list && btn.compareDocumentPosition(list) & Node.DOCUMENT_POSITION_FOLLOWING);
      });
      if (!above) throw new Error("Log a meal isn't above the meal list");
      // D60: on a phone it's on the first screen, under the ring, and it's the only one.
      await page.evaluate(() => window.scrollTo(0, 0));
      const logBtn = page.getByRole("button", { name: "Log a meal" });
      if ((await logBtn.count()) !== 1) throw new Error("more than one Log a meal button shows");
      const box = await logBtn.boundingBox();
      if (!box || box.y + box.height > 844) throw new Error(`Log a meal is below the first screen (at ${box?.y})`);
      // The form opens on one box; the numbers are behind a link, and a greyed
      // Log meal says why.
      await page.getByRole("button", { name: "Log a meal" }).click();
      if (await page.getByRole("spinbutton", { name: "kcal", exact: true }).count()) throw new Error("the number fields show before asked for");
      await page.getByRole("button", { name: "Or type the calories yourself" }).click();
      await expectText(page.locator(".meal-form"), /Give the meal a name and its calories\./, "why Log meal is greyed");
      await page.getByRole("button", { name: "Cancel" }).click();
      // An impossible weight gets the app's own words.
      await page.getByPlaceholder("Today's weight, kg").fill("500");
      await page.getByRole("button", { name: "Log weight" }).click();
      await expectText(page.locator(".weight-card .feedback.error"), /Enter a weight between 35 and 250 kg\./, "weight message");
      await page.getByPlaceholder("Today's weight, kg").fill("");
      // A first visit gets a one-line pointer, not the whole guide.
      // (the test marks guides seen on every load, so clear it and restart the tab)
      await page.evaluate(() => localStorage.removeItem("forkcast.todayguide.v1"));
      await tab(page, "Today").click();
      await page.locator(".guide-hint").waitFor();
      if (await page.locator("#today-guide").count()) throw new Error("the guide opened by itself");
      await page.getByRole("button", { name: "See how this page works" }).click();
      await page.locator("#today-guide").waitFor();
      await page.getByRole("button", { name: "Got it" }).click();
      // Tapping the Recipes tab inside a recipe goes back to the list.
      await tab(page, "Recipes").click();
      await page.locator(".recipe-card").first().click();
      await page.locator(".recipe-detail h1").waitFor();
      await tab(page, "Recipes").click();
      await page.locator(".recipe-card").first().waitFor();
      await audit(page, "recipes, back to the list");
      await tab(page, "Today").click();
    }],
    ["recipe honesty (D59)", async () => {
      await tab(page, "Recipes").click();
      await page.locator(".recipe-card").first().click();
      await expectText(page.locator(".amounts-note"), /without amounts/, "no amounts, said");
      await page.getByRole("button", { name: "I ate it" }).click();
      await expectText(page.locator(".cook-confirm"), /How much did you eat\?/, "servings asked");
      await page.getByRole("button", { name: "Cancel" }).click();
      await tab(page, "Recipes").click();
      // Losing weight (the profile's goal weight): desserts don't count towards what to buy.
      await expectText(page.locator("section.shopping"), /Desserts aren't counted, since you're losing weight\./, "dessert note");
      // D65: the jump link lands the section's heading at the top, below the header.
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.getByRole("button", { name: "What's worth buying? ↓" }).click();
      await page.waitForFunction(() => {
        const top = document.getElementById("worth-buying")?.getBoundingClientRect().top ?? -1;
        return top > 40 && top < 160;
      }, null, { timeout: 5000 }).catch(async () => {
        const top = await page.evaluate(() => document.getElementById("worth-buying")?.getBoundingClientRect().top);
        throw new Error(`Worth buying should land near the top, but its heading is at ${top}px`);
      });
      await tab(page, "Today").click();
    }],
    ["Done for today", async () => {
      await page.getByRole("button", { name: "Done for today" }).click();
      await expectText(page.locator(".day-check-done"), /Today is marked complete/, "day check");
    }],
    ["a weigh-in, and what you burn", async () => {
      await page.getByPlaceholder("Today's weight, kg").fill("71.8");
      // D66: a double tap is one weigh-in (checked below: "1 weigh-in so far").
      await page.getByRole("button", { name: "Log weight" }).evaluate((b) => { b.click(); b.click(); });
      await expectText(page.locator(".weight-card h2"), /trend 71\.8 kg/, "weight trend");
      // D45: a new kitchen uses the formula and says how far learning has got.
      await expectText(page.locator(".burn-line"), /What you burn: about [\d,]+ kcal a day.*0 of 10 complete days/, "burn line");
      // D65: one weigh-in reads as one, not as "spread over 0 days".
      await expectText(page.locator(".burn-line"), /1 weigh-in so far; the next ones should spread over 12 days/, "one weigh-in");
      await audit(page, "today, after logging");
    }],
    ["the back button stays in the app (D66)", async () => {
      await tab(page, "Recipes").click();
      await page.locator(".recipe-card").first().click();
      await page.locator(".recipe-detail h1").waitFor();
      await page.goBack();
      await page.locator(".recipe-card").first().waitFor();
      if (await page.locator(".recipe-detail").count()) throw new Error("Back didn't close the recipe");
      await page.goBack();
      await page.locator(".ring").waitFor(); // the tab before: Today
      if (!page.url().startsWith("http://127.0.0.1") && !page.url().startsWith("http://localhost")) throw new Error(`Back left the app: ${page.url()}`);
      // Tapping Recipes while a recipe is open still goes back to the list (D58).
      await tab(page, "Recipes").click();
      await page.locator(".recipe-card").first().click();
      await page.locator(".recipe-detail h1").waitFor();
      await tab(page, "Recipes").click();
      await page.locator(".recipe-card").first().waitFor();
      if (await page.locator(".recipe-detail").count()) throw new Error("the Recipes tab didn't go back to the list");
      await tab(page, "Today").click();
    }],
    ["a failed request says so (D66)", async () => {
      // No connection used to look like an empty kitchen and "nothing cookable".
      const blocked = ["/api/inventory", "/api/recipes/cookable", "/api/foods/line"];
      for (const path of blocked) expectedErrors.add(path);
      const offline = (url) => blocked.includes(url.pathname);
      const abort = (route) => route.abort();
      await page.route(offline, abort);
      await tab(page, "Recipes").click();
      await expectText(page.locator(".load-error"), /Couldn't reach Forkcast/, "recipes say they couldn't load");
      await tab(page, "Today").click();
      await page.getByRole("button", { name: "Log a meal" }).click();
      const box = page.getByPlaceholder("e.g. 2 eggs, 50 g oats");
      await box.fill("Banane");
      await box.press("Enter");
      await expectText(page.locator(".builder .feedback"), /Couldn't reach Forkcast/, "not \"couldn't find\"");
      await page.getByRole("button", { name: "Cancel" }).click();
      await tab(page, "Kitchen").click();
      await expectText(page.locator(".load-error"), /Couldn't reach Forkcast/, "kitchen says it couldn't load");
      await page.unroute(offline, abort);
      await page.locator(".load-error").getByRole("button", { name: "Try again" }).click();
      await page.locator(".kitchen-group").first().waitFor();
      for (const path of blocked) expectedErrors.delete(path);
      await tab(page, "Today").click();
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
