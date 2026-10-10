// Browser acceptance against the real Flask API and a fresh synthetic SQLite DB.
// Local tooling: npm install --no-save --package-lock=false playwright (frontend/game).
import { chromium } from '../frontend/game/node_modules/playwright/index.mjs';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';

const root = path.resolve('.test-tmp-form-traits');
fs.mkdirSync(root, { recursive: true });
const database = path.join(root, `browser-${Date.now()}.db`);
const env = { ...process.env, DATABASE_PATH: database, DB_PATH: database, PYTHONUTF8: '1' };
for (const key of ['BOT_TOKEN', 'ADMIN_API_TOKEN', 'ARENA_ADMIN_TOKEN', 'RUN_LIVE_TELEGRAM_TESTS']) delete env[key];
const server = spawn(process.env.TELBATTLE_TEST_PYTHON || '.venv/Scripts/python.exe', ['-u', '-c', `
import os
from core.database import DatabaseManager
from web.web_api import WebAPI
from werkzeug.serving import make_server
api = WebAPI(DatabaseManager(os.environ['DB_PATH']))
forms = {r: dict(power=p, speed=p, iq=p, popularity=p, traits=[], passive={}, abilities=[], card_effects=[])
         for r, p in [('normal', 30), ('epic', 60), ('legend', 90)]}
response = api.app.test_client().post('/api/cards/family', json=dict(name='Subzero UI Fixture', variants=forms))
assert response.status_code == 201, response.get_json()
server = make_server('127.0.0.1', 0, api.app)
print('READY:' + str(server.server_port), flush=True)
server.serve_forever()
`], { env, windowsHide: true });
let browser;
const stderr = [];
server.stderr.on('data', data => stderr.push(data.toString()));
try {
  const port = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('Flask startup timed out')), 30000);
    let stdout = '';
    server.stdout.on('data', data => {
      stdout += data.toString();
      const ready = stdout.match(/READY:(\d+)/);
      if (ready) { clearTimeout(timer); resolve(Number(ready[1])); }
    });
    server.once('error', error => { clearTimeout(timer); reject(error); });
    server.once('exit', code => { clearTimeout(timer); reject(new Error(`Flask exited ${code}: ${stderr.join('')}`)); });
  });
  browser = await chromium.launch({ executablePath: process.env.TELBATTLE_BROWSER_PATH, headless: true });
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const base = `http://127.0.0.1:${port}`;
  const selected = () => page.locator('#traits').evaluate(node => [...node.selectedOptions].map(option => option.value));
  const form = async rarity => {
    await page.locator('[data-tab="base"]').click();
    await page.locator('#rarity').selectOption(rarity);
    await page.locator('[data-tab="modes"]').click();
  };
  const add = async name => {
    await page.locator('#newTrait').fill(name);
    const registered = page.waitForResponse(response => response.url().endsWith('/api/card-editor/traits') && response.request().method() === 'POST');
    await page.locator('#addTraitBtn').click();
    assert.equal((await registered).status(), 200);
    await page.waitForFunction(value => [...document.querySelector('#traits').selectedOptions].some(option => option.value === value), name);
  };
  const save = async (method = 'PUT') => {
    const saved = page.waitForResponse(response => response.url().endsWith('/family') && response.request().method() === method);
    await page.locator('button[type="submit"]').click();
    assert.equal((await saved).status(), method === 'POST' ? 201 : 200);
    await page.waitForFunction(() => document.querySelector('#saveBtn')?.disabled === false);
  };
  const open = async () => {
    await page.goto(base);
    await page.getByRole('button', { name: /Subzero UI Fixture/ }).click();
    await form('normal');
  };
  await open();
  await add('یخ');
  await form('epic');
  assert.deepEqual(await selected(), []);
  await page.locator('#traits').selectOption(['یخ']);
  await add('نینجا');
  await form('legend');
  assert.deepEqual(await selected(), []);
  await page.locator('#traits').selectOption(['یخ', 'نینجا']);
  await add('رهبر');
  await form('normal');
  assert.deepEqual(await selected(), ['یخ']);
  await save();
  // Reload the whole page: values must come from SQLite, not browser drafts.
  await open();
  assert.deepEqual(await selected(), ['یخ']);
  await form('epic');
  assert.deepEqual((await selected()).sort(), ['یخ', 'نینجا'].sort());
  await form('legend');
  assert.deepEqual((await selected()).sort(), ['یخ', 'نینجا', 'رهبر'].sort());
  await page.locator('#traits').selectOption([]);
  await save();
  await open();
  assert.deepEqual(await selected(), ['یخ']);
  await form('legend');
  assert.deepEqual(await selected(), []);
  assert.ok((await page.locator('#traits option').allTextContents()).includes('رهبر'));
  // The new-card path must also preserve three different drafts before first save.
  await page.locator('#newBtn').click();
  await page.locator('#name').fill('New Independent UI Fixture');
  const traitForms = { normal: ['یخ'], epic: ['یخ', 'نینجا'], legend: ['یخ', 'نینجا', 'رهبر'] };
  for (const [rarity, traits] of Object.entries(traitForms)) {
    await form(rarity);
    await page.locator('#traits').selectOption(traits);
    await page.locator('[data-tab="base"]').click();
    for (const stat of ['power', 'speed', 'iq', 'popularity']) await page.locator(`#${stat}`).fill('50');
  }
  await save('POST');
  await page.reload();
  await page.getByRole('button', { name: /New Independent UI Fixture/ }).click();
  for (const [rarity, traits] of Object.entries(traitForms)) {
    await form(rarity);
    assert.deepEqual((await selected()).sort(), [...traits].sort());
  }
  assert.deepEqual(errors, []);
  await page.screenshot({ path: path.join(root, 'independent-form-traits.png'), fullPage: true });
  console.log('PASS: real API/SQLite; creating and editing Normal 1, Epic 2, Legend 3; switching, save, reload, empty form and permanent vocabulary.');
} finally {
  if (browser) await browser.close();
  if (server.exitCode === null) { const exited = once(server, 'exit'); server.kill(); await exited; }
}
