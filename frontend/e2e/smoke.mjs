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
      await field.fill("chicken breast, rice, onion, garlic, skyr");
      await page.getByRole("button", { name: "Add", exact: true }).click();
      await expectText(page.locator(".kitchen-group").filter({ hasText: /onion/i }), /onion/i, "kitchen list");
      // D46: skyr is yogurt, and a misspelling gets "Did you mean…?".
      await expectText(page.locator(".kitchen-group").filter({ hasText: /yogurt/i }), /yogurt/i, "skyr as yogurt");
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
        /only recipes you cook teach the feed/, "why a typed meal has no rating");
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
  page.on("console", (m) => m.type() === "error" && problems.push(`console error: ${m.text()}`));
  page.on("response", (r) => {
    if (r.url().includes("/api/") && r.status() >= 400) problems.push(`API ${r.status()}: ${r.request().method()} ${r.url()}`);
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
