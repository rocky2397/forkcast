// README screenshots and an accessibility check, from a fresh demo kitchen.
//
//   node scripts/screenshots.mjs <base-url> <out-dir> [video-dir]
//
// With a video dir it also records the README walkthrough there as frames.
// Expects a Forkcast backend at <base-url> with an EMPTY data dir (ops/screenshots.sh
// starts one). Seeds the same demo kitchen every time through the public API,
// drives the real UI in the Chrome already installed on the machine
// (playwright-core, channel "chrome"; no browser download), saves the
// screenshots, and runs axe-core on every screen it visits. Exits non-zero
// on any serious or critical WCAG 2.1 AA violation.
import { execFileSync } from "node:child_process";
import { readFileSync, mkdirSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { join } from "node:path";
import { chromium } from "playwright-core";

const [base = "http://localhost:8799", outDir = "../docs/screenshots", videoDir] = process.argv.slice(2);
const require = createRequire(import.meta.url);
const AXE = readFileSync(require.resolve("axe-core/axe.min.js"), "utf8");

// The demo kitchen, shared with the public demo (D32). Recipe ids belong to
// corpus release corpus-20261114-d29.
const DEMO = JSON.parse(readFileSync(new URL("../../backend/app/demo_kitchen.json", import.meta.url), "utf8"));
const KITCHEN = DEMO.kitchen;
const PROFILE = DEMO.profile;
const COOKED = DEMO.cooked_and_liked; // Cherry Tomato Pasta, Foil Chicken Casserole for One
const TYPED_MEAL = DEMO.typed_meal;

// D43: the progress screens need six weeks of history, which the API can't
// backdate, so a sample person is written straight into the database.
const SHOT_DB = process.env.FORKCAST_SHOT_DB;
const SHOT_PY = process.env.FORKCAST_SHOT_PY || "python3";
function persona(name) {
  if (!SHOT_DB) throw new Error("FORKCAST_SHOT_DB not set (run ops/screenshots.sh)");
  const script = new URL("../../backend/scripts/sample_history.py", import.meta.url).pathname;
  console.log("  " + execFileSync(SHOT_PY, [script, SHOT_DB, name], { encoding: "utf8" }).trim());
}

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

// A ring where each tap lands: headless video has no cursor to follow.
function showTaps() {
  addEventListener(
    "pointerdown",
    (e) => {
      const dot = document.createElement("div");
      dot.style.cssText = `position:fixed;left:${e.clientX - 22}px;top:${e.clientY - 22}px;width:44px;height:44px;border-radius:50%;background:rgba(194,65,12,.28);border:2px solid rgba(194,65,12,.7);pointer-events:none;z-index:99999;transition:transform .45s ease-out,opacity .45s ease-out`;
      document.body.appendChild(dot);
      requestAnimationFrame(() => {
        dot.style.transform = "scale(1.6)";
        dot.style.opacity = "0";
      });
      setTimeout(() => dot.remove(), 600);
    },
    true,
  );
}

/** Scroll smoothly, so the video reads like a thumb, not a jump cut. */
async function glide(page, y, ms = 900) {
  await page.evaluate(
    ([to, dur]) =>
      new Promise((done) => {
        const from = scrollY;
        const t0 = performance.now();
        const step = (t) => {
          const k = Math.min(1, (t - t0) / dur);
          scrollTo(0, from + (to - from) * (1 - Math.cos(Math.PI * k)) / 2);
          if (k < 1) requestAnimationFrame(step);
          else done();
        };
        requestAnimationFrame(step);
      }),
    [y, ms],
  );
}

const yOf = (locator) => locator.evaluate((el) => el.getBoundingClientRect().top + scrollY - 90);

/** Chrome's screencast: a frame whenever the screen changes. Returns stop(dir). */
async function capture(ctx, page) {
  const frames = [];
  const cdp = await ctx.newCDPSession(page);
  cdp.on("Page.screencastFrame", ({ data, metadata, sessionId }) => {
    frames.push({ data, t: metadata.timestamp });
    cdp.send("Page.screencastFrameAck", { sessionId }).catch(() => {});
  });
  await cdp.send("Page.startScreencast", { format: "jpeg", quality: 90, maxWidth: 780, maxHeight: 1688 });
  return async (dir, label) => {
    await cdp.send("Page.stopScreencast");
    // Each frame stays up until the next one; the last holds for a second.
    mkdirSync(dir, { recursive: true });
    const list = [];
    frames.forEach((f, i) => {
      const name = `f${String(i).padStart(5, "0")}.jpg`;
      writeFileSync(join(dir, name), Buffer.from(f.data, "base64"));
      const hold = i + 1 < frames.length ? frames[i + 1].t - f.t : 1;
      list.push(`file '${name}'`, `duration ${hold.toFixed(3)}`);
    });
    list.push(list.at(-2)); // concat ignores the last duration unless the file repeats
    writeFileSync(join(dir, "frames.txt"), list.join("\n") + "\n");
    console.log(`  ${label}: ${frames.length} frames, ${(frames.at(-1).t - frames[0].t + 1).toFixed(1)} s`);
  };
}

/**
 * The README walkthrough: a first visit on a phone, about 30 seconds.
 * Chrome's own screencast (DevTools protocol) streams a frame whenever the
 * screen changes; the frames and their timings go to videoDir as JPEGs plus
 * an ffmpeg concat list, and ops/screenshots.sh turns them into the GIF.
 * Runs after the screenshots, so the items it adds don't show up in them.
 */
async function recordDemo(browser, videoDir) {
  const ctx = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
    colorScheme: "light",
    serviceWorkers: "block",
  });
  // The walkthrough shows (a first visit); the guides start closed.
  await ctx.addInitScript(() => {
    for (const k of ["feedguide", "todayguide", "kitchenguide"]) localStorage.setItem(`forkcast.${k}.v1`, "1");
  });
  await ctx.addInitScript(showTaps);
  const page = await ctx.newPage();
  const pause = (ms) => page.waitForTimeout(ms);

  await page.goto(base);
  await page.getByRole("button", { name: "Get started" }).waitFor();
  await pause(300); // fonts settle before the first frame

  const stop = await capture(ctx, page);
  await pause(3200);
  await page.getByRole("button", { name: "Get started" }).click();
  await page.locator(".ring").waitFor();
  await pause(1600);

  // Stock the kitchen.
  await tab(page, "Kitchen").click();
  await page.locator(".kitchen-group").first().waitFor();
  await pause(900);
  const field = page.getByPlaceholder("e.g. chicken breasts");
  await field.click();
  await field.pressSequentially("avocado, lime", { delay: 85 });
  await pause(500);
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await pause(1700);

  // What can I cook? Then what the dots mean.
  await tab(page, "Recipes").click();
  await page.locator(".recipe-card").first().waitFor();
  await pause(1500);
  await page.locator(".help-btn").first().click();
  await pause(3000);
  await page.locator(".guide-close").click();
  await pause(700);
  await glide(page, 700, 1400);
  await pause(600);
  await glide(page, 0, 700);

  // One ingredient away, with a swap from what you have.
  await page.getByRole("button", { name: "One away" }).click();
  const card = page.locator(".recipe-card").filter({ hasText: "use your" }).first();
  await card.waitFor();
  await pause(1300);
  await card.click();
  await page.locator(".recipe-detail h1").waitFor();
  await pause(1600);
  await glide(page, await yOf(page.locator(".swap-note").first()) - 200, 1300);
  await pause(2400);

  // Cook mode: one step at a time, screen kept on.
  await glide(page, await yOf(page.getByRole("button", { name: "Start cook mode" })) - 300, 900);
  await pause(500);
  await page.getByRole("button", { name: "Start cook mode" }).click();
  await pause(1800);
  await page.getByRole("button", { name: "Next" }).click();
  await pause(1800);
  await page.getByRole("button", { name: "Close cook mode" }).click();
  await pause(500);

  // Today: what's left of the day's calories and macros.
  await tab(page, "Today").click();
  await page.locator(".ring").waitFor();
  await pause(2600);

  await stop(join(videoDir, "demo"), "demo walkthrough");
  await ctx.close();
}

/**
 * D43: the progress walkthrough, about 20 seconds, with the sample person
 * losing weight: the plan under the ring, "Done for today", a weigh-in and
 * the trend, then the streak, the day strip and the weekly recap.
 */
async function recordProgress(browser, videoDir) {
  const ctx = await context(browser, { width: 390, height: 844 }, 2);
  await ctx.addInitScript(showTaps);
  const page = await ctx.newPage();
  const pause = (ms) => page.waitForTimeout(ms);
  await page.goto(base);
  await tab(page, "Today").click();
  await page.locator(".weight-card").waitFor();
  await pause(400);
  const stop = await capture(ctx, page);

  await pause(2600); // the ring and the plan line

  // Log a small dinner that brings the day to its target, then call it done:
  // the streak goes up by one. (Confirming the sample's 1,429 kcal as
  // complete would rightly count as a day under her minimum.)
  const left = (await api("/api/progress")).progress.target - (await api("/api/day")).totals.calories;
  await glide(page, (await yOf(page.getByRole("button", { name: "Log a meal" }))) - 320, 1100);
  await pause(500);
  await page.getByRole("button", { name: "Log a meal" }).click();
  await pause(600);
  await page.getByPlaceholder("e.g. Skyr with berries").pressSequentially("Chickpea salad", { delay: 70 });
  await page.getByRole("spinbutton", { name: "kcal", exact: true }).pressSequentially(String(Math.round(left / 10) * 10), { delay: 110 });
  await page.getByRole("spinbutton", { name: "Protein g" }).pressSequentially("16", { delay: 90 });
  await page.getByRole("spinbutton", { name: "Carbs g" }).pressSequentially("34", { delay: 90 });
  await page.getByRole("spinbutton", { name: "Fat g" }).pressSequentially("9", { delay: 90 });
  await pause(500);
  await page.getByRole("button", { name: "Log meal" }).click();
  await pause(1400);
  await glide(page, (await yOf(page.locator(".day-check"))) - 180, 900);
  await pause(800);
  await page.getByRole("button", { name: "Done for today" }).click();
  await pause(1400);
  await glide(page, (await yOf(page.locator(".weight-card"))) + 10, 1300);
  await pause(1800);
  const field = page.getByPlaceholder("Today's weight, kg");
  // Carry on from the recent weigh-ins (not the trend, which lags a loss).
  const entries = (await api("/api/weight")).entries;
  const kg = (entries.at(-1).weight_kg - 0.2).toFixed(1);
  await field.click();
  await field.pressSequentially(kg, { delay: 120 });
  await pause(400);
  await page.getByRole("button", { name: "Log weight" }).click();
  await pause(2600);
  await glide(page, (await yOf(page.locator(".progress-card"))) + 10, 1300);
  await pause(2400);
  await glide(page, (await yOf(page.locator(".recap"))) - 260, 1000);
  await pause(2800);

  await stop(join(videoDir, "progress"), "progress walkthrough");
  await ctx.close();
}

/** D43: the Weight card and the day strip, from the card's top to the legend. */
async function progressShot(page, name, label) {
  await page.reload();
  await tab(page, "Today").click();
  await page.locator(".weight-card .weight-chart").waitFor();
  await page.waitForTimeout(500);
  const box = await page.evaluate(() => {
    const top = document.querySelector(".weight-card").getBoundingClientRect().top + scrollY;
    const bottom = document.querySelector(".day-legend").getBoundingClientRect().bottom + scrollY;
    return { top, bottom };
  });
  await page.screenshot({
    path: join(outDir, `${name}.jpg`),
    type: "jpeg",
    quality: 86,
    fullPage: true,
    clip: { x: 0, y: box.top - 12, width: 390, height: box.bottom - box.top + 28 },
  });
  await audit(page, label);
  console.log(`  ${name}.jpg`);
}

async function main() {
  mkdirSync(outDir, { recursive: true });
  await seed();
  persona("lose");
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

    // D43: the progress card for both sample people, side by side in the README.
    const prog = await (await context(browser, { width: 390, height: 844 }, 2)).newPage();
    await prog.goto(base);
    await progressShot(prog, "progress-lose", "progress, losing (phone)");
    persona("gain");
    await progressShot(prog, "progress-gain", "progress, gaining (phone)");
    persona("lose");

    if (videoDir) {
      await recordDemo(browser, videoDir);
      await recordProgress(browser, videoDir);
    }
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
