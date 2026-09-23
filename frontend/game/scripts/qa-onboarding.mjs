import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";
import { resolve, basename } from "node:path";

const baseURL = process.env.QA_URL || "http://127.0.0.1:5173/miniapp-assets/?demo=1";
const outputDir = resolve("tmp/qa-onboarding");
await mkdir(outputDir, { recursive: true });

const browser = await chromium.launch({
  headless: true,
  executablePath: "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
});
const errors = [];

async function fitReport(page, label) {
  const report = await page.evaluate(() => {
    const viewport = { width: innerWidth, height: innerHeight };
    const selectors = [".onboarding-topbar", ".onboarding-visual", ".story-panel", ".story-next"];
    const boxes = Object.fromEntries(selectors.map((selector) => {
      const rect = document.querySelector(selector)?.getBoundingClientRect();
      return [selector, rect ? { top: rect.top, right: rect.right, bottom: rect.bottom, left: rect.left, width: rect.width, height: rect.height } : null];
    }));
    return {
      viewport,
      boxes,
      scrollWidth: document.documentElement.scrollWidth,
      scrollHeight: document.documentElement.scrollHeight,
    };
  });
  for (const [selector, box] of Object.entries(report.boxes)) {
    if (!box) throw new Error(`${label}: missing ${selector}`);
    if (box.left < -1 || box.right > report.viewport.width + 1 || box.top < -1 || box.bottom > report.viewport.height + 1) {
      throw new Error(`${label}: ${selector} is clipped: ${JSON.stringify(box)}`);
    }
  }
  if (report.scrollWidth > report.viewport.width) throw new Error(`${label}: horizontal overflow`);
  return report;
}

async function newMobilePage(viewport) {
  const context = await browser.newContext({ viewport, isMobile: true, hasTouch: true, reducedMotion: "reduce" });
  const page = await context.newPage();
  await page.route('https://telegram.org/js/**', route => route.fulfill({body:'', contentType:'application/javascript'}));
  await page.route('**/card-images/**', route => route.fulfill({path:resolve('../../assets/card_images', basename(new URL(route.request().url()).pathname)), contentType:'image/png'}));
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("requestfailed", (request) => {
    if (request.resourceType() === "image") errors.push(`image failed: ${request.url()}`);
  });
  return { context, page };
}

try {
  const primary = await newMobilePage({ width: 390, height: 844 });
  await primary.page.goto(baseURL, { waitUntil: "domcontentloaded" });
  await primary.page.locator(".splash-screen").waitFor();
  await primary.page.screenshot({ path: resolve(outputDir, "01-splash-390x844.png") });
  await primary.page.locator(".onboarding-screen").waitFor({ timeout: 8000 });
  const firstFit = await fitReport(primary.page, "mentor 390x844");
  await primary.page.screenshot({ path: resolve(outputDir, "02-mentor-390x844.png") });

  await primary.page.getByRole("button", { name: "ادامه" }).click();
  await primary.page.getByRole("heading", { name: "هر کارت، یک قهرمان است" }).waitFor();
  await primary.page.screenshot({ path: resolve(outputDir, "03-stats-390x844.png") });
  await primary.page.getByRole("button", { name: "مرحله قبل" }).click();
  await primary.page.getByRole("heading", { name: "فرمانده، نوبت توست" }).waitFor();
  await primary.page.getByRole("button", { name: "ادامه" }).click();
  await primary.page.getByRole("button", { name: "ادامه" }).click();
  await primary.page.getByRole("heading", { name: "سه انتخاب تا پیروزی" }).waitFor();
  await primary.page.screenshot({ path: resolve(outputDir, "04-guide-390x844.png") });
  await primary.page.getByRole("button", { name: "ادامه" }).click();
  await primary.page.getByRole("heading", { name: "افسانه‌ات را بساز" }).waitFor();
  await primary.page.screenshot({ path: resolve(outputDir, "05-ready-390x844.png") });
  await primary.page.getByRole("button", { name: "ورود به میدان" }).click();
  await primary.page.locator(".lobby-screen").waitFor();

  await primary.page.reload({ waitUntil: "domcontentloaded" });
  await primary.page.locator(".lobby-screen").waitFor({ timeout: 8000 });
  if (await primary.page.locator(".onboarding-screen").count()) throw new Error("returning player saw onboarding again");
  await primary.context.close();

  const compact = await newMobilePage({ width: 360, height: 640 });
  await compact.page.goto(baseURL, { waitUntil: "domcontentloaded" });
  await compact.page.locator(".onboarding-screen").waitFor({ timeout: 8000 });
  const compactFit = await fitReport(compact.page, "mentor 360x640");
  await compact.page.screenshot({ path: resolve(outputDir, "06-mentor-360x640.png") });
  await compact.page.getByRole("button", { name: "رد کردن معرفی" }).click();
  await compact.page.locator(".lobby-screen").waitFor();
  await compact.context.close();

  const standard = await newMobilePage({ width: 375, height: 812 });
  await standard.page.goto(baseURL, { waitUntil: "domcontentloaded" });
  await standard.page.locator(".onboarding-screen").waitFor({ timeout: 8000 });
  const standardFit = await fitReport(standard.page, "mentor 375x812");
  await standard.context.close();

  const landscapeContext = await browser.newContext({ viewport: { width: 844, height: 390 }, isMobile: true, hasTouch: true });
  const landscapePage = await landscapeContext.newPage();
  await landscapePage.goto(baseURL, { waitUntil: "domcontentloaded" });
  await landscapePage.locator("#orientation-guard").waitFor({ state: "visible", timeout: 8000 });
  await landscapePage.getByText("گوشی را عمودی بگیر", { exact: true }).waitFor();
  await landscapeContext.close();

  if (errors.length) throw new Error(errors.join('\n'));
  console.log(JSON.stringify({ ok: true, firstFit, compactFit, standardFit, landscapeGuard: true, pageErrors: errors, screenshots: outputDir }, null, 2));
} finally {
  await browser.close();
}
