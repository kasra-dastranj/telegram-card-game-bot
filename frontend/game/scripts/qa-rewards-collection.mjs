// Runs against a local build with disposable API responses and no real inventory.
import assert from 'node:assert/strict';
import { existsSync, mkdirSync } from 'node:fs';
import { chromium } from 'playwright';

const base = process.env.QA_URL || 'http://127.0.0.1:4181/miniapp-assets/';
assert(['localhost', '127.0.0.1'].includes(new URL(base).hostname));
const output = 'test-results/rewards-collection';
mkdirSync(output, { recursive: true });
const browser = await chromium.launch({ headless: true, executablePath: process.env.PLAYWRIGHT_BROWSER_PATH
  || (existsSync('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')
    ? 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe' : undefined) });
const art = '<svg xmlns="http://www.w3.org/2000/svg" width="300" height="400"><rect width="300" height="400" fill="#193552"/><text x="70" y="210" fill="white" font-size="30">EPIC CARD</text></svg>';
const viewports = [{ width: 375, height: 667 }, { width: 390, height: 844 }, { width: 844, height: 390 }]
  .filter(viewport => !process.env.QA_VIEWPORT || process.env.QA_VIEWPORT === `${viewport.width}x${viewport.height}`);
try {
  for (const viewport of viewports) {
    const context = await browser.newContext({ viewport, isMobile: true, hasTouch: true, reducedMotion: 'reduce' });
    await context.addInitScript(() => localStorage.setItem('telbattle:onboarding:v1', 'done'));
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('https://telegram.org/**', route => route.fulfill({ body: '' }));
    await page.route('**/card-images/**', route => route.fulfill({ contentType: 'image/svg+xml', body: art }));
    let active = 'legend';
    let inventory = { normal: 3, epic: 2, legend: 1 };
    let mutations = 0;
    let outcome = 'win';
    const card = rarity => ({ card_id: 'qa-card', name: 'QA Character', origin: 'official', rarity,
      power: 7, speed: 8, iq: 9, popularity: 6, card_type: 'IQ_TYPE', abilities: [],
      biography: 'A character biography.', image_url: `/card-images/${rarity}.svg`, inventory: { ...inventory } });
    const profile = () => ({ user_id: 1, first_name: 'QA', level: 3, hearts: 5, max_hearts: 5, coins: 1000,
      current_tier: 'bronze', current_xp: 55, xp_to_next_level: 100, total_score: 150,
      progression_v2_enabled: true, counts: { cards: 6, decks: 0, missions_ready: 0, rarities: {} },
      economy: { items: { silver_ticket: 3, upgrade_card: 1 }, capacity: { slots: 3, max_hearts: 5 },
        shop: {}, daily_ticket_percent: 20, silver_claim_tickets: 3 } });
    const rewards = () => ({ xp: outcome === 'win' ? 50 : 10, score: outcome === 'loss' ? -12 : 20,
      coins: 125, hearts_lost: outcome === 'loss' ? 1 : 0, tp_delta: 15 });
    const arena = { arena_id: 'qa', name: 'QA Arena', name_fa: 'QA Arena', emoji: '', effects: [] };
    const winner = () => outcome === 'tie' ? null : outcome === 'win' ? 1 : 2;
    const match = () => ({ request_id: 'qa-match', status: 'completed', phase: 'completed',
      user_id: 1, opponent_id: 2, variant: 'normal', my_card: card(active), opponent_card: card('epic'),
      arena, my_final_values: { power: 7, speed: 8, iq: 9, popularity: 6 },
      report: { winner_id: winner(), is_tie: outcome === 'tie', forfeit: false, rewards: { 1: rewards() },
        rounds_won: { 1: 2, 2: 1 }, rounds: [1, 2, 3].map(round => ({ round, winner_id: winner(), arena,
          values: { 1: { stat: 'power', base: 7, boost: -2, total: 5 }, 2: { stat: 'speed', base: 8, boost: 3, total: 11 } } })),
        breakdown: { 1: { selected_stat: 'power', scored_stats: ['power', 'speed'], final_components: [5, 8], final_value: 13 },
          2: { selected_stat: 'speed', scored_stats: ['power', 'speed'], final_components: [7, 11], final_value: 18 } } } });
    await page.route('**/api/v1/**', async route => {
      const req = route.request();
      const url = new URL(req.url());
      const path = url.pathname.replace('/api/v1', '');
      let result;
      if (path === '/profile') result = profile();
      else if (path === '/cards') result = { cards: [card(active)], total: 1, page: 1, page_count: 1, limit: 20 };
      else if (path === '/cards/qa-card') result = card(active);
      else if (path.endsWith('/active-form')) { mutations++; active = req.postDataJSON().rarity; result = { card: card(active) }; }
      else if (path.endsWith('/fuse-copies/preview')) result = { ok: true, required: 3, upgrade_cards_required: 0, xp: 50, config_version: 1 };
      else if (path.endsWith('/upgrade')) {
        mutations++; inventory.normal -= 3; inventory.epic++;
        result = { ok: true, xp_gained: 50, profile: profile() };
      }
      else if (path === '/economy/claim/silver') {
        mutations++; inventory.epic++;
        result = { ok: true, card_id: 'qa-card', rarity: 'epic', card: card('epic'), profile: profile() };
      }
      else if (path === '/claim' && req.method() === 'GET') result = { can_claim: true, remaining_seconds: 0, pool_count: 1 };
      else if (path === '/claim') result = { ok: true, message: 'Claimed', data: { card: card('normal') }, profile: profile() };
      else if (path === '/missions') result = { missions: [] };
      else if (path.startsWith('/quick/') || path.startsWith('/three-round/')) result = match();
      else if (path === '/solo/start') result = { fight_id: 'qa-solo', player_card: card(active), ai_card: card('epic'),
        ai_name: 'ASO', aso_dialog: 'QA', arena, current_round: 1, available_stats: ['power', 'speed', 'iq', 'popularity'] };
      else if (path === '/solo/round') result = { round_number: 1, player_stat: 'power', player_value: 7, player_boost: 0,
        player_total: 7, ai_stat: 'speed', ai_value: 8, ai_boost: 0, ai_total: 8, round_winner: 'player',
        player_rounds_won: 2, ai_rounds_won: 1, game_over: true, next_round: 2, available_stats: [], aso_dialog: 'QA',
        final_result: { winner: outcome === 'tie' ? 'tie' : outcome === 'win' ? 'player' : 'ai',
          aso_dialog: 'A longer battle result message that must wrap cleanly on a small phone.', rewards: rewards() } };
      else if (path === '/custom/settings') result = { quick_friendly_enabled: false };
      else throw new Error(`Unmocked API: ${path}`);
      await route.fulfill({ json: result });
    });
    await page.goto(base, { waitUntil: 'networkidle' });
    const click = action => page.locator(`[data-action="${action}"]`).first().click();
    await click('open-collection');
    await click('card-detail');
    await page.locator('.card-stat-list').waitFor();
    assert.equal(await page.locator('[data-action="activate-card-form"]').count(), 0);
    await page.locator('[data-action="card-detail-section"][data-value="forms"]').click();
    assert.equal(await page.locator('.card-form-option').count(), 3);
    assert.equal(await page.locator('[data-action="ask-copy-fusion"]').count(), 0);
    await page.locator('[data-action="activate-card-form"][data-value="normal"]').click();
    await page.waitForFunction(() => document.querySelector('[data-action="activate-card-form"][data-value="normal"]')?.getAttribute('aria-pressed') === 'true');
    assert.equal(mutations, 1);
    assert.deepEqual(inventory, { normal: 3, epic: 2, legend: 1 });
    await page.waitForTimeout(300); // Sheet entry animation after re-render.
    await page.screenshot({ path: `${output}/forms-${viewport.width}.png` });
    await page.locator('[data-action="card-detail-section"][data-value="upgrade"]').click();
    assert.equal(await page.locator('[data-action="activate-card-form"]').count(), 0);
    await page.locator('[data-action="ask-copy-fusion"][data-value="epic"]').click();
    await page.locator('[data-action="confirm-copy-fusion"]').waitFor();
    assert.equal(mutations, 1, 'Preview must not consume cards');
    await page.locator('[data-action="confirm-copy-fusion"]').scrollIntoViewIfNeeded();
    await page.waitForTimeout(300);
    await page.screenshot({ path: `${output}/upgrade-${viewport.width}.png` });
    await page.locator('[data-action="card-detail-section"][data-value="forms"]').click();
    await page.locator('[data-action="card-detail-section"][data-value="upgrade"]').click();
    assert.equal(await page.locator('[data-action="confirm-copy-fusion"]').count(), 0, 'Tab changes dismiss old confirmation');
    await page.locator('[data-action="ask-copy-fusion"][data-value="epic"]').click();
    await click('confirm-copy-fusion');
    await page.waitForFunction(() => !document.querySelector('[data-action="confirm-copy-fusion"]'));
    assert.equal(mutations, 2);
    assert.deepEqual(inventory, { normal: 0, epic: 3, legend: 1 });
    await page.locator('[data-action="close-card-detail"]').last().click();
    await click('hub-shop');
    await click('v2-silver');
    await page.locator('.reward-reveal').waitFor();
    assert((await page.locator('.reward-reveal').innerText()).includes('QA Character'));
    assert((await page.locator('.reward-reveal').innerText()).includes('EPIC'));
    assert((await page.locator('.reward-reveal > span').getAttribute('style')).includes('epic.svg'));
    assert.equal(mutations, 3);
    await page.waitForTimeout(300);
    await page.screenshot({ path: `${output}/silver-${viewport.width}.png` });
    await click('hub-progress');
    await click('claim-daily');
    await page.locator('.reward-reveal').waitFor();
    assert((await page.locator('.reward-reveal').innerText()).includes('NORMAL'));
    await click('hub-game');
    for (outcome of ['win', 'loss', 'tie']) {
      for (const mode of ['quick', 'three', 'solo']) {
        // Enter through the portrait menus, then rotate the result screen.
        if (viewport.height < 520) await page.setViewportSize({ width: 390, height: 844 });
        await click(mode === 'quick' ? 'enter-quick' : 'enter-three');
        if (mode === 'solo') {
          await click('enter-arena'); await click('select-card'); await click('start'); await click('stat');
        } else await click(mode === 'quick' ? 'quick-random' : 'three-random');
        await page.locator('.result-screen').waitFor();
        await page.locator('.result-screen .citadel-level').waitFor();
        await page.setViewportSize(viewport);
        if (mode === 'quick') await page.locator('.result-breakdown summary').click();
        const bounds = await page.locator('.result-screen').evaluate(screen => {
          const children = [...screen.children].filter(node => getComputedStyle(node).position !== 'absolute');
          const boxes = children.map(node => ({ name: node.className || node.tagName,
            top: node.getBoundingClientRect().top, bottom: node.getBoundingClientRect().bottom }));
          return { boxes, width: screen.scrollWidth, client: screen.clientWidth };
        });
        for (let i = 1; i < bounds.boxes.length; i++) {
          assert(bounds.boxes[i].top >= bounds.boxes[i - 1].bottom - 1,
            `Overlapping ${mode}/${outcome}: ${JSON.stringify(bounds.boxes)}`);
        }
        assert(bounds.width <= bounds.client + 1, 'Result must not overflow horizontally');
        await page.locator('.result-screen').evaluate(node => { node.scrollTop = node.scrollHeight; });
        await page.screenshot({ path: `${output}/${mode}-${outcome}-${viewport.width}.png` });
        await click('home');
      }
    }
    assert.deepEqual(errors, []);
    console.log(`Rewards, form selection, upgrade confirmation and 9 result screens passed: ${viewport.width}x${viewport.height}`);
    await context.close();
  }
} finally { await browser.close(); }
