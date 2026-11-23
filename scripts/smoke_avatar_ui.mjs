// Real Flask + built Mini App + real admin, synthetic users/media/credentials only.
import { chromium } from '../frontend/game/node_modules/playwright/index.mjs';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';

const root=path.resolve('.test-tmp-avatar-ui',String(Date.now()));fs.mkdirSync(root,{recursive:true});
const env={...process.env,PYTHONUTF8:'1',DB_PATH:path.join(root,'fixture.db'),DATABASE_PATH:path.join(root,'fixture.db'),
  TELBATTLE_CUSTOM_MEDIA_ROOT:path.join(root,'media'),TELBATTLE_AVATAR_UI_ROOT:root,
  ADMIN_API_TOKEN:'synthetic-avatar-ui',BOT_TOKEN:'123456:synthetic-avatar-fixture',FLASK_DEBUG:'1'};
for(const key of ['ARENA_ADMIN_TOKEN','ARENA_ADMIN_PUBLISH_TOKEN','RUN_LIVE_TELEGRAM_TESTS'])delete env[key];
const server=spawn(process.env.TELBATTLE_TEST_PYTHON||'.venv/Scripts/python.exe',['-u','-c',`
import os,json,sqlite3,threading
from pathlib import Path
from PIL import Image,ImageDraw
from io import BytesIO
import web.miniapp_api as mini
from web.web_api import WebAPI
from systems.card_inventory_system import CardInventorySystem as Inventory
from systems import card_avatars
from core.models import Card,CardRarity
from werkzeug.serving import make_server
root=Path(os.environ['TELBATTLE_AVATAR_UI_ROOT']);db=mini.db
db.get_or_create_player(1,first_name='آزمایش آواتار')
for cid,rarity,color in [('hero','normal','yellow'),('rare','rare','lime')]:
    db.add_card(Card(cid,'قهرمان آزمایشی' if cid=='hero' else 'ریر آزمایشی',CardRarity(rarity),10,20,30,40,[]))
    image=Image.new('RGBA',(1024,1024));ImageDraw.Draw(image).ellipse((260,180,764,850),fill=color)
    output=BytesIO();image.save(output,'PNG')
    card_avatars.save_upload(db,cid,'legend' if cid=='hero' else 'rare',output.getvalue(),kind='portrait')
with sqlite3.connect(db.db_path) as conn:
    conn.execute("UPDATE foundation_settings SET value_json='true' WHERE key='progression_v2_enabled'")
    conn.execute('UPDATE players SET coins=2000 WHERE user_id=1')
    Inventory.grant_in(conn,1,'hero','legend');Inventory.grant_in(conn,1,'rare','rare')
frame=Image.new('RGBA',(512,512));d=ImageDraw.Draw(frame)
d.line([(256,25),(487,256),(256,487),(25,256),(256,25)],fill='cyan',width=12)
d.rectangle((248,3,264,22),fill='cyan');frame.save(root/'frame.png')
mask=Image.new('RGBA',(512,512));ImageDraw.Draw(mask).polygon([(256,36),(476,256),(256,476),(36,256)],fill='white');mask.save(root/'mask.png')
admin=make_server('127.0.0.1',0,WebAPI(db).app,threaded=True)
threading.Thread(target=admin.serve_forever,daemon=True).start()
mini.app.debug=True
player=make_server('127.0.0.1',0,mini.app,threaded=True)
print('READY:'+json.dumps(dict(admin=admin.server_port,player=player.server_port)),flush=True)
player.serve_forever()
`],{env,windowsHide:true});
let browser,stderr='';server.stderr.on('data',data=>{stderr+=data.toString();});
try{
  const ports=await new Promise((resolve,reject)=>{let out='';const timer=setTimeout(()=>reject(Error('Flask startup timeout')),30000);server.stdout.on('data',data=>{out+=data.toString();const match=out.match(/READY:(\{[^\n]+\})/);if(match){clearTimeout(timer);resolve(JSON.parse(match[1]));}});server.once('exit',code=>{clearTimeout(timer);reject(Error('Flask '+code+': '+stderr));});server.once('error',reject);});
  browser=await chromium.launch({executablePath:process.env.TELBATTLE_BROWSER_PATH,headless:true});
  const errors=[];const admin=await browser.newPage({viewport:{width:1280,height:1000}});
  admin.on('pageerror',error=>errors.push(error.message));
  await admin.goto(`http://127.0.0.1:${ports.admin}/avatar-items`);
  await admin.locator('#token').fill('synthetic-avatar-ui');await admin.locator('#connect').click();
  await admin.locator('#workspace').waitFor({state:'visible'});
  await admin.locator('#list button').filter({hasText:'قاب طلایی'}).click();
  await admin.locator('#artFile').setInputFiles(path.join(root,'frame.png'));
  await admin.getByText('فایل آماده شد؛ برای ثبت نهایی ذخیرهٔ آیتم را بزن.').waitFor();
  await admin.waitForFunction(()=>!document.querySelector('#save').disabled);
  await admin.locator('#maskFile').setInputFiles(path.join(root,'mask.png'));
  await admin.waitForResponse(r=>r.url().endsWith('/media')&&r.request().method()==='POST'&&r.status()===200);
  await admin.waitForFunction(()=>!document.querySelector('#save').disabled);
  await admin.locator('#geometry').selectOption('custom');
  const saving=admin.waitForResponse(r=>r.url().endsWith('/catalog')&&r.request().method()==='POST');
  await admin.locator('#save').click();assert.equal((await saving).status(),200);
  await admin.getByText('آیتم ذخیره شد.').waitFor();
  await admin.locator('#previewFace').selectOption('0');
  await admin.waitForTimeout(300);
  await admin.screenshot({path:path.join(root,'avatar-admin.png'),fullPage:true});
  assert.equal(await admin.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);

  const page=await browser.newPage({viewport:{width:420,height:900},deviceScaleFactor:1});
  page.on('pageerror',error=>errors.push(error.message));
  const base=`http://127.0.0.1:${ports.player}`;
  await page.goto(base+'/?avatar=1');
  await page.getByRole('heading',{name:'ظاهر آواتار',exact:true}).waitFor();
  const face=page.locator('.avatar-option').filter({has:page.getByRole('heading',{name:'قهرمان آزمایشی',exact:true})});
  await face.getByRole('button',{name:'انتخاب',exact:true}).click();
  await page.locator('[data-action="avatar-tab"][data-value="frame"]').click();
  const gold=page.locator('.avatar-option').filter({has:page.getByRole('heading',{name:'قاب طلایی',exact:true})});
  await gold.getByRole('button',{name:'امتحان روی آواتار من'}).click();
  assert.equal(await page.locator('[data-action="avatar-save"]').isDisabled(),true);
  assert.equal(await page.locator('.avatar-preview .avatar-head').count(),1);
  await gold.getByRole('button',{name:'خرید',exact:true}).click();
  await page.getByRole('alertdialog',{name:'تأیید خرید آیتم آواتار'}).waitFor();
  const bought=page.waitForResponse(r=>r.url().endsWith('/economy/purchase'));
  await page.getByRole('button',{name:'تأیید خرید',exact:true}).click();
  assert.equal((await bought).status(),200);
  await page.waitForFunction(()=>!document.querySelector('[data-action="avatar-save"]').disabled);
  const saved=page.waitForResponse(r=>r.url().endsWith('/avatar')&&r.request().method()==='PUT');
  await page.locator('[data-action="avatar-save"]').click();assert.equal((await saved).status(),200);
  await page.waitForFunction(()=>!document.querySelector('[data-action="avatar-save"]').disabled);
  const catalog=await page.evaluate(async()=> (await fetch('/api/v1/avatar',{headers:{'X-Debug-User-Id':'1'}})).json());
  assert.equal(catalog.selections.profile.frame.item_id,'gold');assert.equal(catalog.selections.profile.face.card_id,'hero');
  const profile=await page.evaluate(async()=> (await fetch('/api/v1/profile',{headers:{'X-Debug-User-Id':'1'}})).json());
  assert.equal(profile.coins,1850);
  await page.waitForTimeout(1200); await page.locator('.hub-scroll').evaluate(el=>el.scrollTop=0);
  await page.screenshot({path:path.join(root,'avatar-mobile.png'),fullPage:true});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.locator('#avatar-slot').selectOption('easy');
  assert.equal(await page.locator('#avatar-inherit').isChecked(),true);
  await page.locator('#avatar-inherit').uncheck();
  await page.locator('[data-action="avatar-tab"][data-value="face"]').click();
  await page.locator('.avatar-option').filter({has:page.getByRole('heading',{name:'ریر آزمایشی',exact:true})}).getByRole('button',{name:'انتخاب',exact:true}).click();
  await page.locator('[data-action="avatar-save"]').click();
  await page.waitForFunction(()=>!document.querySelector('[data-action="avatar-save"]').disabled);
  await page.reload();await page.getByRole('heading',{name:'ظاهر آواتار',exact:true}).waitFor();
  await page.locator('#avatar-slot').selectOption('easy');assert.equal(await page.locator('#avatar-inherit').isChecked(),false);
  assert.deepEqual(errors,[]);
  console.log('Avatar admin + mobile preview/purchase/save/inheritance/reload passed. Screenshots: '+root);
}finally{if(browser)await browser.close();server.kill();}
