// Browser QA against local demo and disposable responses. Never uses a player account.
import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { mkdir } from 'node:fs/promises';
import { chromium } from 'playwright';

const base = process.env.QA_URL || 'http://127.0.0.1:4173/miniapp-assets/';
assert(['127.0.0.1', 'localhost'].includes(new URL(base).hostname), 'Local preview required');
await mkdir('test-results/citadel', { recursive: true });
const browser = await chromium.launch({ headless: true,
  executablePath: existsSync('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')
    ? 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe' : undefined });

async function pageFor(viewport, demo = true, reducedMotion = 'reduce') {
  const context = await browser.newContext({ viewport, isMobile: true, hasTouch: true, reducedMotion });
  await context.addInitScript(() => localStorage.setItem('telbattle:onboarding:v1', 'done'));
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('https://telegram.org/js/**', route => route.fulfill({ body: '', contentType: 'application/javascript' }));
  await page.route('**/card-images/**', route => route.fulfill({ contentType: 'image/svg+xml',
    body: '<svg xmlns="http://www.w3.org/2000/svg" width="300" height="450"><rect width="300" height="450" fill="#152b47"/><path d="M20 20h260v410H20z" fill="none" stroke="#c99c56" stroke-width="5"/><text x="150" y="225" text-anchor="middle" fill="#e8c785" font-size="55">♜</text></svg>' }));
  return { context, page, errors, url: `${base}${demo ? '?demo=1&dense=1' : ''}` };
}

async function noHorizontalOverflow(page) {
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
}

try {
  for (const [width, height] of [[375, 667], [390, 844]]) {
    const { context, page, errors, url } = await pageFor({ width, height });
    await page.goto(url, { waitUntil: 'networkidle' });
    await page.locator('[data-action="enter-quick"]').first().click();
    await page.locator('[data-action="quick-random"]').click();
    await page.locator('.cards-screen .card-grid').waitFor();
    const grid = page.locator('.card-grid');
    assert(await page.locator('[data-action="select-card"]').count() > 8);
    await grid.evaluate(node => { node.scrollTop = node.scrollHeight; });
    assert(await grid.evaluate(node => node.scrollTop > 0), 'Quick card list must scroll');
    await page.waitForTimeout(2500); // A status poll must preserve the scrolled card list.
    assert(await grid.evaluate(node => node.scrollTop > 0), 'Quick poll reset card scroll');
    await page.locator('[data-action="select-card"]').last().click();
    assert.equal(await page.locator('[data-action="select-card"].is-selected').count(), 1);
    await page.screenshot({ path: `test-results/citadel/quick-selection-${width}.png` });
    await page.locator('[data-action="start"]').click();
    await page.locator('.quick-match-screen .citadel-duel').waitFor();
    assert(await page.locator('.duel-side--rival .combat-card--hidden').isVisible(), 'Opponent card revealed before server authorization');
    await page.screenshot({ path: `test-results/citadel/quick-hidden-${width}.png` });
    await page.locator('[data-action="quick-ability"][data-value="skip"]').click();
    await page.locator('[data-action="quick-stat"]:enabled').first().click();
    await page.locator('.victory-crest--win').waitFor();
    assert.equal(await page.locator('.citadel-rewards').count(), 0, 'Demo result must not invent rewards');
    await noHorizontalOverflow(page);
    assert.deepEqual(errors, []);
    await context.close();
    console.log(`Quick selection, privacy and result passed at ${width}x${height}`);
  }

  {
    const { context, page, errors, url } = await pageFor({ width: 375, height: 667 });
    const myCard = { card_id: 'qa-last', name: 'آخرین کارت', rarity: 'epic', power: 70, speed: 75,
      iq: 80, popularity: 85, image_url: '/card-images/qa.png', card_type: 'IQ_TYPE', abilities: [], biography: '' };
    let match = { request_id: 'qa-three', user_id: 1, opponent_id: 2, status: 'active', source: 'random_queue',
      phase: 'card_selection', round: 1, expires_at: new Date(Date.now() + 300000).toISOString(),
      arena: { arena_id: 'city', name_fa: 'میدان شهر', emoji: '⚔', boost_stat: 'power' },
      my_card: null, opponent_card: null, my_card_locked: false, opponent_card_selected: true,
      rounds_won: { '1': 0, '2': 0 }, abilities_enabled: false };
    await page.route('**/api/v1/three-round/**', async route => {
      const path = new URL(route.request().url()).pathname;
      if (path.endsWith('/card')) {
        assert.equal(route.request().postDataJSON().card_id, 'demo-normal-3');
        match = { ...match, phase: 'stat_selection', my_card_locked: true, my_card: myCard,
          my_values: { power: 70, speed: 75, iq: 80, popularity: 85 },
          my_boosts: { power: 0, speed: 0, iq: 0, popularity: 0 },
          available_stats: ['power', 'speed', 'iq', 'popularity'] };
      }
      await route.fulfill({ json: structuredClone(match) });
    });
    await page.goto(url, { waitUntil: 'networkidle' });
    await page.locator('[data-action="enter-three"]').first().click();
    await page.locator('[data-action="three-random"]').click();
    await page.locator('.cards-screen .card-grid').waitFor();
    const grid = page.locator('.card-grid');
    await grid.evaluate(node => { node.scrollTop = node.scrollHeight; });
    await page.waitForTimeout(2700);
    assert(await grid.evaluate(node => node.scrollTop > 0), 'Three-round poll reset card scroll');
    await page.locator('[data-action="select-card"]').last().click();
    await page.locator('[data-action="start"]').click();
    await page.locator('.three-ability-panel').waitFor();
    assert(await page.locator('.duel-side--rival .combat-card--hidden').isVisible());
    await noHorizontalOverflow(page);
    await page.screenshot({ path: 'test-results/citadel/three-hidden-375.png' });
    assert.deepEqual(errors, []);
    await context.close();
    console.log('Three-round bottom card, polling scroll and hidden rival passed');
  }

  {
    const { context, page, errors, url } = await pageFor({ width: 375, height: 667 }, false, 'no-preference');
    const profile = { first_name: 'فرمانده', level: 4, hearts: 2, max_hearts: 5, coins: 500,
      current_xp: 40, xp_to_next_level: 100, counts: { cards: 0, decks: 0, missions_ready: 0 },
      progression_v2_enabled: true, economy: { items: { silver_ticket: 0, upgrade_card: 0, free_silver_claim: 0 },
        capacity: { slots: 3, max_hearts: 5 }, shop: { refill: { enabled: true } }, silver_claim_tickets: 3 } };
    let purchased = false;
    await page.route('**/api/v1/**', async route => {
      const path = new URL(route.request().url()).pathname;
      if (path.endsWith('/profile')) return route.fulfill({ json: { ...profile, hearts: purchased ? 5 : 2 } });
      if (path.endsWith('/cards')) return route.fulfill({ json: { cards: [], total: 0, page: 1, page_count: 1, limit: 60 } });
      if (path.endsWith('/economy/quote')) {
        assert.equal(route.request().postDataJSON().item, 'refill');
        return route.fulfill({ json: { quote_id: 'local-quote', price: 80, config_version: 1 } });
      }
      if (path.endsWith('/economy/purchase')) {
        assert.equal(route.request().postDataJSON().quote_id, 'local-quote'); purchased = true;
        return route.fulfill({ json: { profile: { ...profile, hearts: 5, coins: 420 } } });
      }
      throw new Error(`Unexpected fixture API: ${path}`);
    });
    await page.goto(url, { waitUntil: 'networkidle' });
    await page.locator('[data-action="hub-shop"]').first().click();
    await page.locator('[data-action="v2-quote"][data-value="refill"]').click();
    await page.locator('[data-action="v2-buy"]').click();
    await page.locator('#toast[data-kind="success"]').waitFor();
    assert(await page.locator('.event-effect--heart').isVisible(), 'Confirmed heart purchase needs heart feedback');
    assert(await page.locator('.hub-resources').innerText().then(text => text.includes('5/5')));
    assert.equal(await page.getByText('Battle Pass').count(), 0);
    await noHorizontalOverflow(page);
    await page.screenshot({ path: 'test-results/citadel/heart-purchase-375.png' });
    assert.deepEqual(errors, []);
    await context.close();
    console.log('Real-price quote, confirmed refill and success effect passed');
  }
} finally {
  await browser.close();
}
