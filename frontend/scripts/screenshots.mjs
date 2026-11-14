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
import { readFileSync, mkdirSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { join } from "node:path";
import { chromium } from "playwright-core";

const [base = "http://localhost:8799", outDir = "../docs/screenshots", videoDir] = process.argv.slice(2);
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

  const frames = [];
  const cdp = await ctx.newCDPSession(page);
  cdp.on("Page.screencastFrame", ({ data, metadata, sessionId }) => {
    frames.push({ data, t: metadata.timestamp });
    cdp.send("Page.screencastFrameAck", { sessionId }).catch(() => {});
  });
  await cdp.send("Page.startScreencast", { format: "jpeg", quality: 90, maxWidth: 780, maxHeight: 1688 });
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

  await cdp.send("Page.stopScreencast");
  await ctx.close();

  // Each frame stays up until the next one; the last holds for a second.
  mkdirSync(videoDir, { recursive: true });
  const list = [];
  frames.forEach((f, i) => {
    const name = `f${String(i).padStart(5, "0")}.jpg`;
    writeFileSync(join(videoDir, name), Buffer.from(f.data, "base64"));
    const hold = i + 1 < frames.length ? frames[i + 1].t - f.t : 1;
    list.push(`file '${name}'`, `duration ${hold.toFixed(3)}`);
  });
  list.push(list.at(-2)); // concat ignores the last duration unless the file repeats
  writeFileSync(join(videoDir, "frames.txt"), list.join("\n") + "\n");
  const secs = frames.at(-1).t - frames[0].t + 1;
  console.log(`  demo walkthrough: ${frames.length} frames, ${secs.toFixed(1)} s`);
}

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

    if (videoDir) await recordDemo(browser, videoDir);
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
