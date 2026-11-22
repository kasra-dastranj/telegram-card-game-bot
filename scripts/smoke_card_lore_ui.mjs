// Imported source -> real Admin + real built Mini App; no live credentials/data.
import {chromium} from '../frontend/game/node_modules/playwright/index.mjs';
import {spawn} from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';

const root=path.resolve('.test-tmp-lore-ui',String(Date.now()));fs.mkdirSync(root,{recursive:true});
const source=JSON.parse(fs.readFileSync('content/card_lore_20261122/telbattle_lore.json','utf8')).characters[0];
const env={...process.env,PYTHONUTF8:'1',DATABASE_PATH:path.join(root,'hidden.db'),DB_PATH:path.join(root,'hidden.db'),TELBATTLE_LORE_UI_ROOT:root,
  TELBATTLE_CUSTOM_MEDIA_ROOT:path.join(root,'media'),BOT_TOKEN:'123456:synthetic-lore-ui',FLASK_DEBUG:'1'};
for(const key of ['ADMIN_API_TOKEN','ARENA_ADMIN_TOKEN','RUN_LIVE_TELEGRAM_TESTS'])delete env[key];
const server=spawn(process.env.TELBATTLE_TEST_PYTHON||'.venv/Scripts/python.exe',['-u','-c',`
import os,json,sqlite3,threading
from pathlib import Path
from tests.test_hidden_stat_profiles import game
from systems.card_lore_import import load_bundle,preview,apply
from systems.card_inventory_system import CardInventorySystem
from werkzeug.serving import make_server
root=Path(os.environ['TELBATTLE_LORE_UI_ROOT'])
db=game.__wrapped__(root)
with sqlite3.connect(db.db_path) as conn:
    conn.execute("UPDATE cards SET biography='',dialogs=?",(json.dumps(['من بردم'],ensure_ascii=False),))
    CardInventorySystem.grant_in(conn,1,'live-001','legend')
bundle=load_bundle();plan=preview(db.db_path,bundle)
(root/'preview.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')
result=apply(db.db_path,bundle,plan['plan_hash'],root/'before.db','synthetic-browser-owner')
(root/'applied.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
from web.web_api import WebAPI
admin=make_server('127.0.0.1',0,WebAPI(db).app,threaded=True)
threading.Thread(target=admin.serve_forever,daemon=True).start()
import web.miniapp_api as mini
mini.db=db;mini.app.debug=True
player=make_server('127.0.0.1',0,mini.app,threaded=True)
print('READY:'+json.dumps(dict(admin=admin.server_port,player=player.server_port)),flush=True)
player.serve_forever()
`],{env,windowsHide:true});
let browser,stderr='';server.stderr.on('data',data=>stderr+=data.toString());
try{
  const ports=await new Promise((resolve,reject)=>{let output='';const timer=setTimeout(()=>reject(Error('Flask timeout: '+stderr)),30000);server.stdout.on('data',data=>{output+=data.toString();const match=output.match(/READY:(\{[^\n]+\})/);if(match){clearTimeout(timer);resolve(JSON.parse(match[1]));}});server.once('error',reject);server.once('exit',code=>{clearTimeout(timer);reject(Error('Flask '+code+': '+stderr));});});
  browser=await chromium.launch({headless:true,executablePath:process.env.TELBATTLE_BROWSER_PATH});
  const errors=[];const admin=await browser.newPage({viewport:{width:1280,height:1000}});admin.on('pageerror',e=>errors.push(e.message));
  await admin.goto(`http://127.0.0.1:${ports.admin}/`);
  await admin.getByRole('button',{name:new RegExp(source.name_fa)}).click();
  for(const rarity of ['normal','epic','legend']){
    await admin.locator('[data-tab="base"]').click();await admin.locator('#rarity').selectOption(rarity);
    assert.equal(await admin.locator('#biography').inputValue(),source.bio_text);
    assert.equal(await admin.locator('#dialogs').inputValue(),source.victory_lines.map(l=>l.text).join('\n'));
  }
  await admin.screenshot({path:path.join(root,'lore-admin.png'),fullPage:true});
  const page=await browser.newPage({viewport:{width:420,height:900}});page.on('pageerror',e=>errors.push(e.message));
  await page.goto(`http://127.0.0.1:${ports.player}/?avatar=1`);
  await page.getByRole('heading',{name:'ظاهر آواتار',exact:true}).waitFor();
  await page.locator('[data-action="open-collection"]').click();
  await page.locator('[data-action="card-detail"][data-id="live-001"]').click();
  const bio=page.locator('.card-biography');await bio.waitFor();
  assert.equal(await bio.innerText(),source.bio_text);
  await page.waitForFunction(()=>{const el=document.querySelector('.card-biography');return el&&getComputedStyle(el).whiteSpace==='pre-line';});
  await page.screenshot({path:path.join(root,'lore-mobile.png'),fullPage:true});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  assert.deepEqual(errors,[]);
  const report=JSON.parse(fs.readFileSync(path.join(root,'applied.json'),'utf8'));
  assert.equal(report.active_incoming_lines,314);assert.equal(report.changed_biographies,60);
  console.log('60-character lore import, all admin forms, 3-line mobile biography passed. Reports/screenshots: '+root);
}finally{if(browser)await browser.close();server.kill();}
