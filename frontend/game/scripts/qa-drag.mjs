import { chromium } from "playwright";
import { existsSync, mkdirSync } from "node:fs";
import path from "node:path";

const root = path.resolve(import.meta.dirname, "../../..");
const artifacts = path.resolve(import.meta.dirname, "../qa-artifacts");
mkdirSync(artifacts, { recursive: true });

const chrome = process.env.PLAYWRIGHT_BROWSER_PATH || (existsSync("C:/Program Files/Google/Chrome/Application/chrome.exe") ? "C:/Program Files/Google/Chrome/Application/chrome.exe" : "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe");
const cardImages = {
  "heisenberg.png": path.join(root, "assets/card_images/heisenberg.png"),
  "batman.png": path.join(root, "assets/card_images/batman.png"),
  "thanos.png": path.join(root, "assets/card_images/thanos.png"),
};

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function openQuick(page, { dense = false } = {}) {
  await page.addInitScript(() => localStorage.setItem("telbattle:onboarding:v1", "done"));
  const bootErrors = [];
  page.on("pageerror", (error) => bootErrors.push(`pageerror: ${error.message}`));
  page.on("console", (message) => {
    if (message.type() === "error") bootErrors.push(`console: ${message.text()}`);
  });
  await page.route("https://telegram.org/js/telegram-web-app.js*", (route) => route.fulfill({
    contentType: "application/javascript",
    body: "window.Telegram={WebApp:{ready(){},expand(){},HapticFeedback:{impactOccurred(){},notificationOccurred(){}}}};",
  }));
  await page.route("**/card-images/*", async (route) => {
    const fileName = decodeURIComponent(new URL(route.request().url()).pathname.split("/").at(-1));
    const imagePath = cardImages[fileName];
    if (imagePath) await route.fulfill({ path: imagePath, contentType: "image/png" });
    else await route.abort();
  });
  const query = dense ? "?demo=1&dense=1" : "?demo=1";
  await page.goto(`${process.env.QA_URL || "http://127.0.0.1:4173/miniapp-assets/"}${query}`, { waitUntil: "domcontentloaded" });
  try {
    await page.locator('[data-action="enter-quick"]').waitFor({ state: "visible", timeout: 12_000 });
  } catch (error) {
    await page.screenshot({ path: path.join(artifacts, "boot-failure.png"), fullPage: true });
    console.error(JSON.stringify({
      stage: "boot",
      url: page.url(),
      title: await page.title(),
      body: (await page.locator("body").innerText()).slice(0, 1_000),
      scripts: await page.locator("script").evaluateAll((items) => items.map((item) => item.src)),
      errors: bootErrors,
    }, null, 2));
    throw error;
  }
  await page.locator('[data-action="enter-quick"]').click();
  await page.locator('[data-action="quick-random"]').click();
  await page.locator(".drag-card-screen").waitFor({ state: "visible", timeout: 12_000 });
  await page.waitForTimeout(900);
}

async function canvasPoint(page, x, y) {
  const canvas = page.locator("#game-root canvas");
  const box = await canvas.boundingBox();
  assert(box, "Canvas was not visible");
  return { x: box.x + box.width * (x / 720), y: box.y + box.height * (y / 1280) };
}

async function rejectDrop(page, screenshotPrefix) {
  const start = await canvasPoint(page, 360, 1060);
  const outside = await canvasPoint(page, 110, 520);
  await page.mouse.move(start.x, start.y);
  await page.mouse.down();
  await page.mouse.move(outside.x, outside.y, { steps: 10 });
  await page.mouse.up();
  await page.waitForTimeout(420);
  assert(await page.locator(".drag-card-screen").isVisible(), "Rejected drop left the card-selection screen");
  assert(!(await page.locator(".quick-match-screen").isVisible()), "Rejected drop submitted a card");
  await page.screenshot({ path: path.join(artifacts, `${screenshotPrefix}-returned.png`) });
}

async function dragCenterCard(page, screenshotPrefix) {
  const start = await canvasPoint(page, 360, 1060);
  const hover = await canvasPoint(page, 360, 790);
  const drop = await canvasPoint(page, 360, 650);
  await page.mouse.move(start.x, start.y);
  await page.mouse.down();
  await page.mouse.move(hover.x, hover.y, { steps: 10 });
  await page.waitForTimeout(140);
  await page.screenshot({ path: path.join(artifacts, `${screenshotPrefix}-dragging.png`) });
  if (screenshotPrefix === "large-phone") {
    await page.locator(".drag-card-header").screenshot({ path: path.join(artifacts, "large-phone-drag-header.png") });
  }
  await page.mouse.move(drop.x, drop.y, { steps: 8 });
  await page.mouse.up();
  await page.locator(".quick-match-screen").waitFor({ state: "visible", timeout: 12_000 });
  await page.waitForTimeout(500);
  assert(await page.getByText("Ability را انتخاب کن").isVisible(), "Drop did not advance Quick to Ability selection");
}

async function finishQuick(page) {
  await page.getByRole("button", { name: /بدون Ability/ }).click();
  await page.getByText("با کدام ویژگی حمله می‌کنی؟").waitFor({ state: "visible" });
  await page.screenshot({ path: path.join(artifacts, "large-phone-stat.png") });
  await page.locator('[data-action="quick-stat"][data-value="iq"]').click();
  await page.locator(".quick-result-screen").waitFor({ state: "visible" });
  assert(await page.getByText("تصمیم تو برنده شد").isVisible(), "Quick result did not render after the final stat choice");
  await page.screenshot({ path: path.join(artifacts, "large-phone-result.png") });
}

async function inspectPage(page, label) {
  const data = await page.evaluate(() => {
    const canvas = document.querySelector("#game-root canvas")?.getBoundingClientRect();
    const header = document.querySelector(".drag-card-header")?.getBoundingClientRect();
    const guide = document.querySelector(".drag-guide")?.getBoundingClientRect();
    const orientationGuard = document.querySelector("#orientation-guard")?.getBoundingClientRect();
    return {
      viewport: [innerWidth, innerHeight],
      scroll: [document.documentElement.scrollWidth, document.documentElement.scrollHeight],
      overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth,
      overflowY: document.documentElement.scrollHeight > document.documentElement.clientHeight,
      canvas: canvas && [canvas.x, canvas.y, canvas.width, canvas.height],
      header: header && [header.x, header.y, header.right, header.bottom],
      guide: guide && [guide.x, guide.y, guide.right, guide.bottom],
      orientationGuard: orientationGuard && [orientationGuard.x, orientationGuard.y, orientationGuard.right, orientationGuard.bottom],
    };
  });
  assert(!data.overflowX, `${label}: horizontal overflow`);
  assert(!data.overflowY, `${label}: vertical overflow`);
  assert(data.canvas && data.canvas[2] >= data.viewport[0] - 1 && data.canvas[3] >= data.viewport[1] - 1, `${label}: canvas does not fill viewport`);
  return data;
}

const browser = await chromium.launch({ headless: true, executablePath: chrome });
const results = [];
try {
  for (const config of [
    { label: "large-phone", viewport: { width: 390, height: 844 }, reducedMotion: "no-preference" },
    { label: "small-phone", viewport: { width: 375, height: 667 }, reducedMotion: "no-preference" },
    { label: "landscape", viewport: { width: 844, height: 390 }, reducedMotion: "no-preference" },
    { label: "reduced-motion", viewport: { width: 390, height: 844 }, reducedMotion: "reduce" },
  ]) {
    const initialViewport = config.label === "landscape" ? { width: 390, height: 844 } : config.viewport;
    const context = await browser.newContext({ viewport: initialViewport, isMobile: true, hasTouch: true, reducedMotion: config.reducedMotion });
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", (error) => errors.push(`pageerror: ${error.message}`));
    page.on("console", (message) => { if (message.type() === "error") errors.push(`console: ${message.text()}`); });
    await openQuick(page);
    if (config.label === "landscape") {
      await page.setViewportSize(config.viewport);
      await page.locator("#orientation-guard").waitFor({ state: "visible" });
      const before = await inspectPage(page, config.label);
      assert(await page.getByText("گوشی را عمودی بگیر").isVisible(), "Landscape orientation guidance is missing");
      await page.screenshot({ path: path.join(artifacts, "landscape-guard.png") });
      assert(errors.length === 0, `${config.label}: ${errors.join(" | ")}`);
      results.push({ label: config.label, before, errors });
      await context.close();
      continue;
    }
    const before = await inspectPage(page, config.label);
    if (config.label === "large-phone") await page.screenshot({ path: path.join(artifacts, "large-phone-hand.png") });
    if (config.label === "large-phone") await rejectDrop(page, config.label);
    await dragCenterCard(page, config.label);
    if (config.label === "large-phone") {
      await page.screenshot({ path: path.join(artifacts, "large-phone-ability.png") });
      await finishQuick(page);
    }
    assert(errors.length === 0, `${config.label}: ${errors.join(" | ")}`);
    results.push({ label: config.label, before, errors });
    await context.close();
  }

  const denseContext = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, reducedMotion: "reduce" });
  const densePage = await denseContext.newPage();
  const denseErrors = [];
  densePage.on("pageerror", (error) => denseErrors.push(`pageerror: ${error.message}`));
  densePage.on("console", (message) => { if (message.type() === "error") denseErrors.push(`console: ${message.text()}`); });
  await openQuick(densePage, { dense: true });
  const firstPage = await densePage.screenshot({ path: path.join(artifacts, "dense-page-1.png") });
  const next = await canvasPoint(densePage, 600, 1140);
  await densePage.mouse.click(next.x, next.y);
  await densePage.locator('#ui-root[data-hand-page="2"]').waitFor({ state: "attached", timeout: 4_000 });
  await densePage.waitForTimeout(500);
  const secondPage = await densePage.screenshot({ path: path.join(artifacts, "dense-page-2.png") });
  assert(!firstPage.equals(secondPage), "Pagination control did not change the visible hand");
  assert(await densePage.locator(".drag-card-screen").isVisible(), "Pagination left the card-selection screen");
  assert(denseErrors.length === 0, `dense-pagination: ${denseErrors.join(" | ")}`);
  results.push({ label: "dense-pagination", errors: denseErrors });
  await denseContext.close();
  console.log(JSON.stringify({ ok: true, results }, null, 2));
} finally {
  await browser.close();
}
