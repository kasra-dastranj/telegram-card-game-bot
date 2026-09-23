import { existsSync, mkdirSync } from "node:fs";
import { chromium } from "playwright";

const baseUrl = process.env.QA_URL || "http://127.0.0.1:4173/miniapp-assets/?demo=1&dense=1";
const allViewports = [
  { name: "390x844", width: 390, height: 844 },
  { name: "375x667", width: 375, height: 667 },
  { name: "768x1024", width: 768, height: 1024 },
  { name: "844x390-landscape", width: 844, height: 390 },
];
const viewports = process.env.QA_VIEWPORT ? allViewports.filter((item) => item.name === process.env.QA_VIEWPORT) : allViewports;

mkdirSync("test-results", { recursive: true });
const systemBrowser = process.env.PLAYWRIGHT_BROWSER_PATH
  || (existsSync("C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe")
    ? "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
    : "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe");
const browser = await chromium.launch({ headless: true, executablePath: systemBrowser });

try {
  for (const viewport of viewports) {
    const context = await browser.newContext({
      viewport: { width: viewport.width, height: viewport.height },
      isMobile: true,
      hasTouch: true,
      reducedMotion: viewport.name === "375x667" ? "reduce" : "no-preference",
    });
    await context.addInitScript(() => localStorage.setItem("telbattle:onboarding:v1", "done"));
    const page = await context.newPage();
    const failures = [];
    const placeholderCard = `<svg xmlns="http://www.w3.org/2000/svg" width="360" height="540"><rect width="100%" height="100%" rx="28" fill="#102a25"/><rect x="18" y="18" width="324" height="504" rx="22" fill="none" stroke="#d5aa52" stroke-width="6"/><text x="180" y="280" text-anchor="middle" fill="#f8f2df" font-size="30" font-family="sans-serif">TelBattle</text></svg>`;
    await page.route("**/card-images/**", (route) => route.fulfill({
      status: 200,
      contentType: "image/svg+xml",
      body: placeholderCard,
    }));
    await page.route("https://telegram.org/js/**", (route) => route.fulfill({
      status: 200,
      contentType: "application/javascript",
      body: "",
    }));
    page.on("pageerror", (error) => failures.push(`pageerror: ${error.message}`));
    page.on("console", (message) => {
      if (message.type() === "error") failures.push(`console: ${message.text()}`);
    });

    await page.goto(baseUrl, { waitUntil: "networkidle" });
    await page.locator(".hub-nav").waitFor();
    if (await page.locator(".hub-nav button").count() !== 5) throw new Error("Bottom navigation must have five destinations");

    await page.locator('[data-action="open-profile"]').first().click();
    await page.getByRole("heading", { name: "مرکز فرمانده" }).waitFor();
    if (await page.locator(".hub-resources .hub-resource").count() !== 4) throw new Error("HUD must show hearts, coins, cards, and decks");
    const resourceLabels = await page.locator(".hub-resources .hub-resource small").allTextContents();
    if (resourceLabels.join("|") !== "جان|سکه|کارت|دک") throw new Error(`Unexpected HUD labels: ${resourceLabels.join("|")}`);
    await page.screenshot({ path: `test-results/player-hub-profile-${viewport.name}.png`, fullPage: false });

    await page.locator('[data-action="open-collection"]').first().click();
    await page.locator(".collection-card").first().waitFor();
    const initialCards = await page.locator(".collection-card").count();
    if (initialCards < 3) throw new Error("Dense demo collection did not load");

    await page.locator("#collection-query").fill("Batman");
    await page.waitForTimeout(500);
    const searchedNames = await page.locator(".collection-card__body strong").allTextContents();
    if (!searchedNames.length || searchedNames.some((name) => !name.includes("Batman"))) throw new Error("Collection search did not filter cards");

    await page.locator("#collection-query").fill("");
    await page.waitForTimeout(500);
    await page.locator("#collection-rarity").selectOption("epic");
    await page.locator(".collection-card").first().waitFor();
    const rarityLabels = await page.locator(".collection-card__body > small").allTextContents();
    if (rarityLabels.some((label) => !label.includes("EPIC"))) throw new Error("Rarity filter returned a non-Epic card");

    await page.locator(".collection-card").first().click();
    await page.getByRole("dialog", { name: "جزئیات کارت" }).waitFor();
    if (await page.locator(".card-stat-list span").count() !== 4) throw new Error("Card details must show four stats");
    await page.locator('[data-action="preview-upgrade"]').click();
    await page.getByRole("alertdialog", { name: "تأیید ارتقای کارت" }).waitFor();
    await page.locator('[data-action="confirm-upgrade"]').click();
    await page.getByText("LEGEND", { exact: true }).waitFor();
    await page.screenshot({ path: `test-results/player-hub-card-${viewport.name}.png`, fullPage: false });
    await page.locator('[data-action="close-card-detail"]').last().click();

    await page.locator('[data-action="hub-decks"]').first().click();
    await page.getByRole("heading", { name: "دک‌های من" }).waitFor();
    await page.locator('[data-action="new-deck"]').click();
    await page.locator("#deck-name").fill("تیم QA");
    const picks = page.locator('[data-action="toggle-deck-card"]');
    await picks.nth(0).click();
    await picks.nth(1).click();
    await picks.nth(2).click();
    await page.locator('[data-action="save-deck"]').click();
    await page.getByRole("heading", { name: "تیم QA" }).waitFor();
    await page.locator('[data-action="ask-delete-deck"]').click();
    await page.getByRole("alertdialog", { name: "تأیید حذف دک" }).waitFor();
    await page.locator('[data-action="confirm-delete-deck"]').click();
    await page.getByText("هنوز دکی نساختی.").waitFor();

    await page.locator('[data-action="hub-progress"]').first().click();
    await page.getByRole("heading", { name: "پیشرفت و پاداش" }).waitFor();
    await page.locator('[data-action="claim-daily"]').click();
    await page.getByText("پاداش تازه").waitFor();
    await page.locator('[data-action="claim-mission"]').click();
    await page.getByText("LEGEND", { exact: true }).waitFor();

    await page.locator('[data-action="open-collection"]').first().click();
    await page.locator("#collection-rarity").selectOption("all");
    await page.locator(".collection-card").first().click();
    await page.locator('[data-action="open-skins"]').click();
    await page.getByRole("dialog", { name: "پوسته‌های کارت" }).waitFor();
    await page.locator('[data-action="activate-skin"]').click();
    await page.getByText("فعال", { exact: true }).waitFor();
    await page.locator('[data-action="close-skins"]').last().click();

    await page.locator('[data-action="hub-shop"]').first().click();
    await page.getByRole("heading", { name: "آزمایشگاه Fusion" }).waitFor();
    const fusionCards = page.locator('[data-action="toggle-fusion-card"]');
    await fusionCards.nth(0).click();
    await fusionCards.nth(1).click();
    await fusionCards.nth(2).click();
    await page.locator('[data-action="retain-fusion-card"]').first().click();
    await page.locator('[data-action="preview-fusion"]').click();
    await page.getByRole("alertdialog", { name: "تأیید نهایی Fusion" }).waitFor();
    await page.locator('[data-action="execute-fusion"]').click();
    await page.getByText("کارت کافی برای این Fusion نداری.").waitFor();

    const fit = await page.evaluate(() => ({
      documentOverflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth,
      nav: document.querySelector(".hub-nav")?.getBoundingClientRect().toJSON(),
      hud: document.querySelector(".hub-hud")?.getBoundingClientRect().toJSON(),
    }));
    if (fit.documentOverflowX) throw new Error("Horizontal overflow detected");
    if (!fit.nav || fit.nav.bottom > viewport.height + 1 || fit.nav.top < 0) throw new Error("Bottom navigation is clipped");
    if (!fit.hud || fit.hud.top < 0 || fit.hud.bottom > viewport.height) throw new Error(`Player HUD is clipped: ${JSON.stringify(fit.hud)}`);
    if (failures.length) throw new Error(failures.join("\n"));

    if (viewport.name === "390x844") {
      const authPage = await context.newPage();
      let authAttempts = 0;
      await authPage.route("https://telegram.org/js/**", (route) => route.fulfill({ status: 200, contentType: "application/javascript", body: "" }));
      await authPage.route("**/api/v1/profile", (route) => {
        authAttempts += 1;
        if (authAttempts === 1) {
          return route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ error: "ورود لازم است", error_code: "auth_required" }) });
        }
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ first_name: "QA", level: 2, current_tier: "Bronze", hearts: 3, max_hearts: 5, coins: 999, total_score: 20, counts: { cards: 7, decks: 2, missions_ready: 0, rarities: {} } }),
        });
      });
      await authPage.route("**/api/v1/cards?**", route => route.fulfill({ contentType: "application/json", body: JSON.stringify({cards: [], total: 0, page: 1, page_count: 1, limit: 3}) }));
      const authUrl = new URL(baseUrl);
      authUrl.search = "";
      await authPage.goto(authUrl.toString(), { waitUntil: "networkidle" });
      await authPage.locator(".profile-auth-error").waitFor();
      await authPage.getByRole("button", { name: "تلاش دوباره" }).click();
      await authPage.locator(".profile-auth-error").waitFor({ state: "detached" });
      const recovered = await authPage.locator(".lobby-resource b").allTextContents();
      if (recovered.join("|") !== "3/5|۹۹۹|۷|۲") throw new Error(`Retry did not restore resources: ${recovered.join("|")}`);
      await authPage.close();
    }

    await context.close();
    process.stdout.write(`PASS ${viewport.name} cards=${initialCards}\n`);
  }
} finally {
  await browser.close();
}
