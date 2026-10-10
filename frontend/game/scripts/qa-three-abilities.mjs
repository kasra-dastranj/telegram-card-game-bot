// UI acceptance against disposable API responses; never contacts production.
import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { mkdir } from 'node:fs/promises';
import { chromium } from 'playwright';

const base = process.env.QA_URL || 'http://127.0.0.1:5173/miniapp-assets/';
assert(['127.0.0.1', 'localhost'].includes(new URL(base).hostname), 'Local QA server required');
const output = 'test-results/three-abilities';
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ headless: true,
  executablePath: existsSync('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')
    ? 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe' : undefined });
const abilities = [
  ['reveal_opponent', '👁 مشاهده کارت حریف', 'پیش از انتخاب ویژگی، کارت حریف را می‌بینی.'],
  ['reroll_arena', '🔄 تغییر زمین', 'زمین یک‌بار به‌صورت تصادفی عوض می‌شود.'],
  ...['power', 'speed', 'iq', 'popularity'].map((stat, index) =>
    [`weaken_${stat}`, `📉 کاهش ${['قدرت', 'سرعت', 'هوش', 'محبوبیت'][index]}`, '۲ واحد از ویژگی حریف کم می‌کند.']),
].map(([ability_key, title, description]) => ({ ability_key, title, description, quantity: 2 }));
try {
  for (const [width, height, abilityKey] of [[375, 667, 'reveal_opponent'], [390, 844, 'reroll_arena'], [375, 812, 'weaken_speed']]) {
    const context = await browser.newContext({ viewport: { width, height }, isMobile: true,
      hasTouch: true, reducedMotion: 'reduce' });
    await context.addInitScript(() => localStorage.setItem('telbattle:onboarding:v1', 'done'));
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('https://telegram.org/js/**', route => route.fulfill({ body: '', contentType: 'application/javascript' }));
    await page.route('**/card-images/**', route => route.fulfill({ contentType: 'image/svg+xml',
      body: '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="96"><rect width="64" height="96" fill="#294634"/></svg>' }));
    const card = { card_id: 'qa-my-card', name: 'قهرمان تست', rarity: 'normal', power: 80,
      speed: 70, iq: 60, popularity: 50, card_type: 'POWER_TYPE', abilities: [], image_url: '/card-images/qa.png' };
    let match = { request_id: 'qa-three', user_id: 1, opponent_id: 2, status: 'active',
      source: 'random_queue', phase: 'stat_selection', round: 2,
      expires_at: new Date(Date.now()+300000).toISOString(), deadline: new Date(Date.now()+60000).toISOString(),
      arena: { arena_id: 'power_arena', name_fa: 'زمین قدرت', emoji: '⚔️', boost_stat: 'power', boost_amount: 3 },
      my_card: card, opponent_card: null, my_card_locked: true, opponent_card_selected: true,
      my_stat_locked: false, opponent_stat_selected: false, my_ability_used: false,
      abilities_enabled: true, abilities, my_values: { power: 80, speed: 70, iq: 60, popularity: 50 },
      my_boosts: { power: 3, speed: 0, iq: 0, popularity: 0 },
      available_stats: ['speed', 'iq', 'popularity'], rounds_won: { '1': 0, '2': 0 } };
    const requests = [];
    let holdNextRead = false, releaseRead, readStarted;
    const started = new Promise(resolve => { readStarted = resolve; });
    await page.route('**/api/v1/three-round/**', async route => {
      const request = route.request();
      const path = new URL(request.url()).pathname;
      if (path.endsWith('/ability')) {
        const body = request.postDataJSON(); requests.push(body);
        assert.equal(body.round, 2); assert.equal(body.ability_key, abilityKey);
        match = { ...match, my_ability_used: true, abilities: [],
          my_ability: { ability_key: abilityKey, round: 2, title: abilities.find(a => a.ability_key === abilityKey).title } };
        if (abilityKey === 'reveal_opponent') match.opponent_card = { ...card, card_id: 'qa-rival', name: 'حریف تست' };
        if (abilityKey === 'reroll_arena') match.arena = { ...match.arena, arena_id: 'qa-new', name_fa: 'زمین تازه' };
      } else if (path.endsWith('/stat')) {
        assert.equal(request.postDataJSON().stat, 'speed'); match = { ...match, my_stat_locked: true };
      }
      const snapshot = structuredClone(match);
      if (request.method() === 'GET' && holdNextRead) {
        holdNextRead = false; readStarted();
        await new Promise(resolve => { releaseRead = resolve; });
      }
      await route.fulfill({ json: snapshot });
    });
    await page.goto(`${base}?demo=1`, { waitUntil: 'networkidle' });
    await page.locator('[data-action="enter-three"]').first().click();
    await page.locator('[data-action="three-random"]').click();
    await page.locator('.three-ability-menu summary').click();
    await page.locator('.three-ability-menu .ability-list').evaluate(node => { node.scrollTop = 90; });
    const viewportElement = await page.locator('.screen').elementHandle();
    await page.waitForTimeout(2700); // Polling must preserve the expanded menu and its scroll position.
    assert(await viewportElement.evaluate(node => node.isConnected), 'Polling must preserve the live scroll container');
    assert(await page.locator('.three-ability-menu').evaluate(node => node.open));
    assert(await page.locator('.three-ability-menu .ability-list').evaluate(node => node.scrollTop > 0));
    assert.equal(await page.locator('[data-action="three-ability"]').count(), 6);
    assert.equal(await page.locator('.decision-panel').count(), 1); // No overlapping panels in landscape.
    assert(await page.locator('#game-root').isVisible());
    assert(!(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)));
    if (width === 375 && height === 667) {
      const bounds = await page.locator('.three-ability-panel .decision-title').boundingBox();
      const startY = Math.min(bounds.y + 35, height - 20);
      const hit = await page.evaluate(y => {
        const node = document.elementFromPoint(150, y);
        return { pointerEvents: node && getComputedStyle(node).pointerEvents,
          touchAction: getComputedStyle(document.querySelector('.screen')).touchAction };
      }, startY);
      assert.equal(hit.pointerEvents, 'auto'); assert.equal(hit.touchAction, 'pan-y');
      await page.mouse.move(150, startY);
      await page.mouse.wheel(0, 140);
      await page.waitForTimeout(200);
      const scrolled = await page.evaluate(() => ['html', 'body', '#app', '#ui-root', '.screen'].map(selector => {
        const node = document.querySelector(selector);
        return { selector, top: node.scrollTop, height: node.clientHeight, content: node.scrollHeight };
      }));
      assert(scrolled.some(node => node.top > 0), `Scroll must reach below-fold stats: ${JSON.stringify(scrolled)}`);
      await page.waitForTimeout(2700);
      assert(await page.locator('.screen').evaluate(node => node.scrollTop > 0), 'Polling must preserve screen scroll');
      await page.evaluate(() => ['html', 'body', '#app', '#ui-root', '.screen'].forEach(selector => document.querySelector(selector).scrollTop = 0));
    }
    await page.screenshot({ path: `${output}/choices-${width}.png` });
    if (abilityKey === 'reveal_opponent') holdNextRead = true;
    if (holdNextRead) await started;
    await page.locator(`[data-action="three-ability"][data-value="${abilityKey}"]`).click();
    await page.locator('.three-ability-panel').filter({ hasText: 'استفاده شد' }).waitFor();
    if (releaseRead) { releaseRead(); await page.waitForTimeout(600); }
    assert.equal(await page.locator('[data-action="three-ability"]').count(), 0);
    assert.equal(requests.length, 1);
    if (abilityKey === 'reveal_opponent') assert(await page.locator('.reveal-card').isVisible());
    if (abilityKey === 'reroll_arena') assert(await page.locator('.quick-match-hud').innerText().then(text => text.includes('زمین تازه')));
    await page.screenshot({ path: `${output}/used-${width}.png` });
    await page.locator('[data-action="three-stat"][data-value="speed"]').click();
    await page.locator('.choice-locked').waitFor();
    assert.deepEqual(errors, []);
    await context.close();
    console.log(`${width}x${height}: ${abilityKey}, polling and stat selection passed`);
  }
  for (const abilityKey of ['reveal_opponent', 'reroll_arena', 'weaken_iq']) {
    const context = await browser.newContext({ viewport: { width: 390, height: 844 },
      isMobile: true, hasTouch: true, reducedMotion: 'reduce' });
    await context.addInitScript(() => localStorage.setItem('telbattle:onboarding:v1', 'done'));
    const page = await context.newPage();
    const errors = [], requests = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('https://telegram.org/js/**', route => route.fulfill({ body: '' }));
    await page.route('**/card-images/**', route => route.fulfill({ contentType: 'image/svg+xml',
      body: '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="96"><rect width="64" height="96" fill="#294634"/></svg>' }));
    const card = { card_id: 'qa-solo', name: 'قهرمان تمرین', rarity: 'normal', power: 80,
      speed: 70, iq: 60, popularity: 50, card_type: 'POWER_TYPE', abilities: [], image_url: '/card-images/qa.png' };
    let fight = { fight_id: 'qa-aso', player_card: card, ai_card: null, ai_name: 'ASO',
      aso_dialog: 'تمرین محلی', current_round: 1, available_stats: ['power', 'speed', 'iq', 'popularity'],
      arena: { arena_id: 'power_arena', name_fa: 'زمین قدرت', boost_stat: 'power', version: 1 },
      abilities, abilities_enabled: true, my_ability_used: false,
      my_values: { power: 83, speed: 70, iq: 60, popularity: 50 } };
    await page.route('**/api/v1/**', async route => {
      const path = new URL(route.request().url()).pathname;
      let json;
      if (path.endsWith('/profile')) json = { first_name: 'تست', level: 7, current_tier: 'Gold',
        hearts: 5, max_hearts: 5, coins: 500, total_score: 0 };
      else if (path.endsWith('/cards')) json = { cards: [card], total: 1, page: 1, limit: 20, page_count: 1 };
      else if (path.endsWith('/solo/start')) json = fight;
      else if (path.endsWith('/solo/ability')) {
        const data = route.request().postDataJSON(); requests.push(data);
        assert.equal(data.round, 2); assert.equal(data.ability_key, abilityKey);
        fight = { ...fight, abilities: [], my_ability_used: true,
          my_ability: { ability_key: abilityKey, round: 2, title: abilities.find(a => a.ability_key === abilityKey).title } };
        if (abilityKey === 'reveal_opponent') fight.ai_card = { ...card, card_id: 'qa-ai' };
        if (abilityKey === 'reroll_arena') fight.arena = { ...fight.arena, arena_id: 'speed_arena', name_fa: 'زمین تازه', boost_stat: 'speed' };
        json = fight;
      } else if (path.endsWith('/solo/round')) {
        const stat = route.request().postDataJSON().player_stat;
        assert.equal(stat, 'power');
        fight = { ...fight, current_round: 2, available_stats: ['speed', 'iq', 'popularity'] };
        json = { round_number: 1, player_stat: stat, player_value: 80, player_boost: 3, player_total: 83,
          ai_stat: 'power', ai_value: 80, ai_boost: 3, ai_total: 83, round_winner: 'tie', player_rounds_won: 0,
          ai_rounds_won: 0, game_over: false, next_round: 2, available_stats: fight.available_stats,
          aso_dialog: 'راوند بعدی', fight };
      } else throw new Error(`Unexpected QA API ${path}`);
      await route.fulfill({ json });
    });
    await page.goto(base, { waitUntil: 'networkidle' });
    await page.locator('[data-action="enter-three"]').first().click();
    await page.locator('[data-action="enter-arena"]').first().click();
    await page.locator('[data-action="select-card"]').first().click();
    await page.locator('[data-action="start"]').click();
    await page.locator('[data-action="stat"][data-value="power"]').click();
    await page.locator('[data-action="stat"][data-value="speed"]:enabled').waitFor();
    await page.locator('.three-ability-menu summary').click();
    await page.locator(`[data-action="solo-ability"][data-value="${abilityKey}"]`).click();
    await page.locator('.three-ability-panel').filter({ hasText: 'استفاده شد' }).waitFor();
    assert.equal(requests.length, 1);
    assert.equal(await page.locator('[data-action="solo-ability"]').count(), 0);
    assert(await page.locator('[data-action="stat"][data-value="power"]').isDisabled());
    assert(await page.locator('[data-action="stat"][data-value="speed"]').isEnabled());
    if (abilityKey === 'reroll_arena') assert((await page.locator('.arena-name').innerText()).includes('زمین تازه'));
    assert(await page.locator('#game-root').isVisible());
    await page.screenshot({ path: `${output}/aso-${abilityKey}.png` });
    assert.deepEqual(errors, []);
    await page.setViewportSize({ width: 844, height: 390 });
    assert(await page.locator('#orientation-guard').isVisible());
    await context.close();
    console.log(`ASO: ${abilityKey} saved for round two, shared UI passed`);
  }
} finally { await browser.close(); }
