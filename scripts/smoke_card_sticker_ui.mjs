// Real admin browser regression, with isolated SQLite and uploaded asset folders.
import { chromium } from '../frontend/game/node_modules/playwright/index.mjs';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';

const root = path.resolve('.test-tmp-sticker-ui', String(Date.now()));
fs.mkdirSync(root, { recursive: true });
const env = { ...process.env, DB_PATH: path.join(root, 'cards.db'), TELBATTLE_UI_ROOT: root, PYTHONUTF8: '1' };
for (const key of ['BOT_TOKEN', 'ADMIN_API_TOKEN', 'ARENA_ADMIN_TOKEN', 'RUN_LIVE_TELEGRAM_TESTS']) delete env[key];
const server = spawn(process.env.TELBATTLE_TEST_PYTHON || '.venv/Scripts/python.exe', ['-u', '-c', `
import os
from pathlib import Path
from PIL import Image
from core.database import DatabaseManager
import web.web_api as web
root=Path(os.environ['TELBATTLE_UI_ROOT'])
web.PROJECT_ROOT=root
api=web.WebAPI(DatabaseManager(os.environ['DB_PATH']))
for color in ('red','blue'):
    Image.new('RGB',(128,128),color).save(root/(color+'.webp'),'WEBP')
forms={r:dict(power=5,speed=6,iq=7,popularity=8,image_path=str(root/'blue.webp'),
    photo_file_id='photo-'+r,sticker_file_id='sticker-'+r) for r in ('normal','epic','legend')}
result=api.app.test_client().post('/api/cards/family',json=dict(name='Heisenberg UI Fixture',variants=forms))
assert result.status_code==201,result.get_json()
from werkzeug.serving import make_server
server=make_server('127.0.0.1',0,api.app)
print('READY:'+str(server.server_port),flush=True)
server.serve_forever()
`], { env, windowsHide: true });
let browser;
let stderr = '';
server.stderr.on('data', data => { stderr += data.toString(); });
try {
  const port = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('Flask startup timeout')), 30000);
    let output = '';
    server.stdout.on('data', data => {
      output += data.toString();
      const match = output.match(/READY:(\d+)/);
      if (match) { clearTimeout(timer); resolve(Number(match[1])); }
    });
    server.once('error', error => { clearTimeout(timer); reject(error); });
    server.once('exit', code => { clearTimeout(timer); reject(new Error(`Flask exit ${code}: ${stderr}`)); });
  });
  browser = await chromium.launch({ executablePath: process.env.TELBATTLE_BROWSER_PATH, headless: true });
  const page = await browser.newPage({ viewport: { width: 1280, height: 1000 } });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const base = `http://127.0.0.1:${port}`;
  await page.goto(base);
  await page.getByRole('button', { name: /Heisenberg UI Fixture/ }).click();
  const selectForm = async rarity => {
    await page.locator('[data-tab="base"]').click();
    await page.locator('#rarity').selectOption(rarity);
    await page.locator('[data-tab="media"]').click();
  };
  await selectForm('normal');
  const upload = async kind => {
    await page.locator(kind === 'image' ? '#imageFile' : '#stickerFile').setInputFiles(path.join(root, 'red.webp'));
    const response = page.waitForResponse(r => r.url().endsWith('/api/upload_' + kind));
    await page.locator(kind === 'image' ? '#uploadImageBtn' : '#uploadStickerBtn').click();
    assert.equal((await response).status(), 200);
    await page.waitForFunction(() => !document.querySelector('#saveBtn').disabled);
    assert.equal(await page.locator('#stickerFileId').inputValue(), '');
  };
  const save = async () => {
    const response = page.waitForResponse(r => r.url().endsWith('/family') && r.request().method() === 'PUT');
    await page.locator('#saveBtn').click();
    assert.equal((await response).status(), 200);
    await page.waitForFunction(() => !document.querySelector('#saveBtn').disabled);
  };
  await upload('image');
  assert.equal(await page.locator('#photoFileId').inputValue(), '');
  const imagePath = await page.locator('#imagePath').inputValue();
  await selectForm('epic');
  assert.equal(await page.locator('#stickerFileId').inputValue(), 'sticker-epic');
  await selectForm('normal');
  assert.equal(await page.locator('#stickerFileId').inputValue(), '');
  await save();
  await selectForm('normal');
  await page.locator('#stickerFileId').fill('cached-before-new-upload');
  await save();
  await selectForm('normal');
  await upload('sticker');
  await save();
  await selectForm('normal');
  await upload('image'); // Same filename must still expire both cached ids.
  assert.equal(await page.locator('#imagePath').inputValue(), imagePath);
  await save();
  const catalog = await (await fetch(base + '/api/cards')).json();
  const forms = Object.fromEntries(catalog.cards[0].variants.map(form => [form.rarity, form]));
  assert.equal(forms.normal.sticker_file_id, '');
  assert.equal(forms.normal.photo_file_id, '');
  assert.equal(forms.epic.sticker_file_id, 'sticker-epic');
  assert.equal(forms.legend.sticker_file_id, 'sticker-legend');
  assert.deepEqual(errors, []);
  await page.locator('[data-tab="media"]').click();
  await page.screenshot({ path: path.join(root, 'admin-sticker-refresh.png'), fullPage: true });
  console.log('Card media upload/save/form-switch browser regression passed. Screenshot: ' + root);
} finally {
  if (browser) await browser.close();
  server.kill();
}
