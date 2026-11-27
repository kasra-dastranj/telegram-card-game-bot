// Two private uploads, editor reload, replacement and removal using synthetic local APIs.
import assert from 'node:assert/strict';
import { readFileSync, mkdirSync, existsSync } from 'node:fs';
import { chromium } from '../frontend/game/node_modules/playwright/index.mjs';

const browser = await chromium.launch({ headless: true, executablePath: process.env.TELBATTLE_BROWSER_PATH
  || (existsSync('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')
    ? 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe' : undefined) });
const image = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a4V8AAAAASUVORK5CYII=', 'base64');
mkdirSync('.test-tmp-catalog', { recursive: true });
try {
  for (const width of [390, 1100]) {
    const page = await browser.newPage({ viewport: { width, height: 900 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('dialog', dialog => dialog.accept());
    let saved;
    let version = 0;
    const uploads = [];
    const mutations = [];
    await page.route('http://127.0.0.1:4181/**', async route => {
      const req = route.request();
      const path = new URL(req.url()).pathname;
      if (path === '/custom-cards') return route.fulfill({ contentType: 'text/html', body: readFileSync('web/custom_card_management.html', 'utf8') });
      assert.equal(req.headers()['x-admin-token'], 'synthetic-ui-admin');
      let body;
      if (path === '/api/custom/records') body = { cards: saved ? [saved] : [], grants: [], orders: [],
        settings: { custom_cards_enabled: true, quick_friendly_enabled: true, easy_custom_cards_enabled: false },
        official_references: [], options: { stats: {}, traits: [], arenas: [] } };
      else if (path.startsWith('/api/custom/players')) body = { players: [{ user_id: 1, first_name: 'QA Player' }] };
      else if (path === '/api/custom/media') {
        const payload = req.postDataBuffer().toString();
        const kind = payload.includes('name="kind"') ? 'sticker' : 'photo';
        uploads.push(kind);
        body = { media_id: kind + '-' + uploads.length };
      } else if (path.startsWith('/api/custom/media/')) return route.fulfill({ contentType: 'image/png', body: image });
      else if (path === '/api/custom/fulfill' || path === '/api/custom/revise') {
        const request = req.postDataJSON();
        mutations.push(request.data);
        version++;
        saved = { card_id: 'cc-ui-fixture', payload_json: JSON.stringify(request.data.card), status: 'active',
          media_id: request.data.media_id, sticker_media_id: request.data.sticker_media_id, updated_at: String(version) };
        body = { card_id: saved.card_id, updated_at: saved.updated_at };
      } else throw new Error('Unexpected mock endpoint ' + path);
      return route.fulfill({ json: body });
    });
    await page.goto('http://127.0.0.1:4181/custom-cards');
    await page.locator('#token').fill('synthetic-ui-admin');
    await page.locator('#connect').click();
    await page.locator('#workspace').waitFor();
    await page.locator('#name').fill('Two private artworks');
    await page.locator('#image').setInputFiles({ name: 'portrait.png', mimeType: 'image/png', buffer: image });
    await page.locator('#sticker').setInputFiles({ name: 'sticker.png', mimeType: 'image/png', buffer: image });
    assert(await page.locator('#previewImage').isVisible());
    assert(await page.locator('#stickerPreview').isVisible());
    await page.screenshot({ path: `.test-tmp-catalog/custom-media-inputs-${width}.png`, fullPage: true });
    await page.locator('#playerQuery').fill('QA'); await page.locator('#findPlayer').click();
    await page.locator('#playerResults button').click();
    await page.locator('#submit').click();
    await page.waitForFunction(() => document.querySelector('#cardList button') && !document.querySelector('#submit').disabled);
    assert.deepEqual(uploads, ['photo', 'sticker']);
    assert.equal(mutations[0].media_id, 'photo-1'); assert.equal(mutations[0].sticker_media_id, 'sticker-2');
    await page.locator('#cardList button').click();
    await page.waitForFunction(() => !document.querySelector('#submit').disabled && document.querySelector('#stickerPreview').src.startsWith('blob:'));
    assert(await page.locator('#previewImage').isVisible());
    assert(await page.locator('#stickerPreview').isVisible());
    await page.locator('#sticker').setInputFiles({ name: 'replacement.png', mimeType: 'image/png', buffer: image });
    await page.locator('#submit').click();
    await page.waitForFunction(() => !document.querySelector('#submit').disabled);
    assert.equal(mutations.length, 2);
    assert.equal(mutations[1].media_id, 'photo-1'); assert.equal(mutations[1].sticker_media_id, 'sticker-3');
    await page.locator('#clearSticker').click();
    assert(await page.locator('#stickerPreview').isHidden());
    assert(await page.locator('#previewImage').isVisible());
    await page.locator('#submit').click();
    await page.waitForFunction(() => !document.querySelector('#submit').disabled);
    assert.equal(mutations[2].media_id, 'photo-1'); assert.equal(mutations[2].sticker_media_id, null);
    assert.deepEqual(uploads, ['photo', 'sticker', 'sticker']);
    assert.deepEqual(errors, []);
    console.log(`Custom dual-media editor passed at ${width}px`);
    await page.close();
  }
} finally { await browser.close(); }
