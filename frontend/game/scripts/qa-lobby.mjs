import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";
import { resolve, basename } from "node:path";

const baseURL = process.env.QA_URL || "http://127.0.0.1:5173/miniapp-assets/?demo";
const outputDir = resolve("tmp/qa-lobby");
await mkdir(outputDir, { recursive: true });

const browser = await chromium.launch({
  headless: true,
  executablePath: "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
});

const pageErrors = [];
const reports = [];

async function inspectLobby(page, label) {
  const report = await page.evaluate(() => {
    const selectors = [".lobby-command-bar", ".lobby-table", ".battle-console", ".hub-nav"];
    const boxes = Object.fromEntries(selectors.map((selector) => {
      const rect = document.querySelector(selector)?.getBoundingClientRect();
      return [selector, rect ? {
        top: Math.round(rect.top), right: Math.round(rect.right), bottom: Math.round(rect.bottom),
        left: Math.round(rect.left), width: Math.round(rect.width), height: Math.round(rect.height),
      } : null];
    }));
    const targets = [...document.querySelectorAll(".lobby-screen button")].map((button) => {
      const rect = button.getBoundingClientRect();
      return { label: button.getAttribute("aria-label") || button.textContent?.trim(), width: rect.width, height: rect.height };
    });
    return {
      viewport: { width: innerWidth, height: innerHeight },
      boxes,
      targets,
      scrollWidth: document.documentElement.scrollWidth,
      font: getComputedStyle(document.querySelector(".table-copy h1")).fontFamily,
      headline: document.querySelector(".table-copy h1")?.textContent?.replace(/\s+/g, " ").trim(),
    };
  });

  for (const [selector, box] of Object.entries(report.boxes)) {
    if (!box) throw new Error(`${label}: missing ${selector}`);
    if (box.left < -1 || box.right > report.viewport.width + 1 || box.top < -1 || box.bottom > report.viewport.height + 1) {
      throw new Error(`${label}: ${selector} clipped: ${JSON.stringify(box)}`);
    }
  }
  if (report.scrollWidth > report.viewport.width) throw new Error(`${label}: horizontal overflow`);
  const tooSmall = report.targets.filter((target) => target.width < 44 || target.height < 44);
  if (tooSmall.length) throw new Error(`${label}: touch targets below 44px: ${JSON.stringify(tooSmall)}`);
  if (!report.font.includes("Vazirmatn")) throw new Error(`${label}: Persian font did not load (${report.font})`);
  reports.push({ label, ...report });
}

async function capture(viewport, label, reducedMotion = "no-preference") {
  const context = await browser.newContext({ viewport, isMobile: true, hasTouch: true, reducedMotion });
  const page = await context.newPage();
  page.on("pageerror", (error) => pageErrors.push(`${label}: ${error.message}`));
  await page.addInitScript(() => localStorage.setItem("telbattle:onboarding:v1", "done"));
  await page.route('https://telegram.org/js/**', route => route.fulfill({body:'',contentType:'application/javascript'}));
  await page.route('**/card-images/**', route => route.fulfill({path:resolve('../../assets/card_images',basename(new URL(route.request().url()).pathname)),contentType:'image/png'}));
  await page.goto(baseURL, { waitUntil: "networkidle" });
  await page.locator(".lobby-screen").waitFor();
  await page.locator(".battle-mode--quick").waitFor();
  await inspectLobby(page, label);
  await page.screenshot({ path: resolve(outputDir, `${label}.png`) });

  if (label === "390x844") {
    await page.locator(".lobby-identity").focus();
    const outline = await page.locator(".lobby-identity").evaluate((node) => getComputedStyle(node).outlineStyle);
    if (outline === "none") throw new Error("keyboard focus ring is missing");
    await page.locator(".lobby-identity").click();
    await page.locator(".profile-hub-screen").waitFor();
    await page.screenshot({ path: resolve(outputDir, "profile-hub-390x844.png") });
    await page.getByRole("button", { name: "بازی", exact: true }).click();
    await page.locator(".lobby-screen").waitFor();
    await page.getByRole("button", { name: "کارت‌ها", exact: true }).click();
    await page.locator(".collection-screen").waitFor();
    await page.screenshot({ path: resolve(outputDir, "collection-390x844.png") });
    await page.getByRole("button", { name: "بازی", exact: true }).click();
    await page.locator(".lobby-screen").waitFor();
    await page.locator('[data-action="enter-quick"]').click();
    await page.locator(".quick-menu-screen").waitFor();
  }
  await context.close();
}

try {
  await capture({ width: 390, height: 844 }, "390x844");
  await capture({ width: 375, height: 812 }, "375x812");
  await capture({ width: 360, height: 640 }, "360x640");
  await capture({ width: 390, height: 844 }, "390x844-reduced", "reduce");
  if(pageErrors.length) throw new Error(pageErrors.join('\n'));
  console.log(JSON.stringify({ ok: true, reports, pageErrors, screenshots: outputDir }, null, 2));
} finally {
  await browser.close();
}
