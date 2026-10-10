import { chromium } from '../frontend/game/node_modules/playwright/index.mjs';
import fs from 'node:fs';
import assert from 'node:assert/strict';
fs.mkdirSync('.test-tmp-phase3', {recursive:true});
const browser=await chromium.launch({executablePath:process.env.TELBATTLE_BROWSER_PATH,headless:true});
try {
  const page=await browser.newPage({viewport:{width:430,height:900}});
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  let enabled=true,variant=null,images=0;
  const card={card_id:'cc-fixture',name:'Private Fixture',rarity:'legend',origin:'custom',power:5,speed:6,iq:7,popularity:8,abilities:[],biography:'test',card_type:'POWER_TYPE',image_url:'/api/v1/custom/cards/cc-fixture/image',inventory:{},upgrade:{ok:false,error:'not eligible'}};
  const profile={user_id:1,first_name:'Tester',level:5,hearts:8,max_hearts:8,coins:1000,total_score:3,current_xp:25,xp_to_next_level:300,progression_v2_enabled:true,counts:{cards:0,custom_cards:1,decks:0,missions_ready:0,rarities:{normal:0}},claim:{can_claim:true,remaining_seconds:0}};
  const quick={request_id:'fixture-friendly',mode:'quick',variant:'friendly',status:'waiting',source:'invite_link',phase:'lobby',user_id:1,creator_id:1,opponent_id:null,expires_at:new Date(Date.now()+300000).toISOString(),invite_url:'https://t.me/fixture?start=fixture',arena:null};
  await page.route('**/api/v1/**',async route=>{
    const path=new URL(route.request().url()).pathname.slice('/api/v1'.length);let body={};
    if(path==='/custom/cards/cc-fixture/image'){
      assert.equal(route.request().headers()['x-debug-user-id'],'1');images++;
      await route.fulfill({status:200,contentType:'image/png',headers:{'Cache-Control':'private, no-store'},body:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aHqUAAAAASUVORK5CYII=','base64')});return;
    }
    if(path==='/profile'||path==='/player-hub/overview')body=profile;
    else if(path==='/custom/settings')body={quick_friendly_enabled:enabled,order_contact:null};
    else if(path==='/cards')body={cards:[card],total:1,page:1,limit:60,page_count:1};
    else if(path==='/cards/cc-fixture')body=card;
    else if(path==='/quick/invites'){variant=route.request().postDataJSON().variant;body=quick;}
    else if(path.startsWith('/quick/invites/'))body={variant:'friendly'};
    else if(path.startsWith('/quick/matches/'))body=quick;
    else if(path==='/decks')body={decks:[]};
    else if(path==='/missions')body={missions:[]};
    await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(body)});
  });
  const url=process.env.TELBATTLE_SMOKE_URL||'http://127.0.0.1:5173/miniapp-assets/';
  await page.goto(url);await page.locator('[data-action="onboarding-skip"]').click();
  await page.locator('[data-action="enter-quick"]').click();
  await page.locator('[data-action="quick-friendly"]').click();
  await page.getByText('0 XP / 0 Score / 0 Coin؛ باخت: -1 Heart',{exact:true}).waitFor();
  await page.screenshot({path:'.test-tmp-phase3/browser-friendly.png',fullPage:true});
  await page.locator('[data-action="quick-invite"]').click();
  await page.locator('[data-action="share-invite"]').waitFor();assert.equal(variant,'friendly');
  await page.goto(url);
  await page.locator('[data-action="open-collection"]').first().click();
  await page.locator('[data-action="card-detail"]').first().click();
  await page.locator('[role="dialog"]').getByText('Private Fixture',{exact:true}).waitFor();
  assert.match(await page.locator('[role="dialog"] .eyebrow').textContent(),/LEGEND.*سفارشی/);
  assert.equal(await page.locator('[data-action="open-skins"],[data-action="preview-sell"],[data-action="ask-copy-fusion"]').count(),0);
  assert.ok(images>=2);assert.match(await page.locator('.card-sheet__hero').getAttribute('style'),/blob:/);
  await page.screenshot({path:'.test-tmp-phase3/browser-custom.png',fullPage:true});
  enabled=false;await page.goto(url);const settingsReady=page.waitForResponse(response=>response.url().endsWith('/custom/settings'));await page.locator('[data-action="enter-quick"]').click();await settingsReady;
  assert.equal(await page.locator('[data-action="quick-friendly"]').count(),0);
  await page.goto(url+'?invite=fixture');
  await page.getByText('دعوت دوستانه: 0 XP / 0 Score / 0 Coin؛ باخت: -1 Heart',{exact:true}).waitFor();
  assert.equal(await page.locator('[data-action="accept-invite"]').isEnabled(),true);
  const admin=await browser.newPage();const keys=[];let attempts=0;
  await admin.route('**/custom-cards',route=>route.fulfill({contentType:'text/html',body:fs.readFileSync('web/custom_card_management.html','utf8')}));
  await admin.route('**/api/custom/**',async route=>{
    assert.equal(route.request().headers()['x-admin-token'],'synthetic-ui-admin');
    if(route.request().method()==='POST'){keys.push(route.request().postDataJSON().request_key);attempts++;}
    await route.fulfill({status:attempts===1?503:200,contentType:'application/json',body:JSON.stringify(attempts===1?{error:'retry fixture'}:{users:[1,2],active:true})});
  });
  await admin.goto(new URL('/custom-cards',url).href);
  await admin.locator('#token').fill('synthetic-ui-admin');await admin.locator('#action').selectOption('grant');
  await admin.locator('#payload').fill(JSON.stringify({card_id:'cc-fixture',order_id:'fixture',users:[1,2]}));
  await admin.locator('#submit').click();await admin.getByText('retry fixture',{exact:true}).waitFor();
  await admin.locator('#submit').click();await admin.locator('#output').filter({hasText:'active'}).waitFor();
  assert.equal(keys.length,2);assert.equal(keys[0],keys[1]);
  assert.equal(await admin.evaluate(()=>JSON.stringify({...localStorage,...sessionStorage}).includes('synthetic-ui-admin')),false);
  assert.deepEqual(errors,[]);
  fs.writeFileSync('.test-tmp-phase3/browser-results.json',JSON.stringify({browser:'Edge headless',api:'synthetic local fixtures',variant,images,adminRetrySameKey:true,flagsOffHidden:true,errors},null,2));
  process.stdout.write('Phase3 browser passed: Friendly variant, reward/heart text, real rarity/custom badge, authenticated blob image, economy actions hidden, flags off, admin retry key.\n');
} finally {await browser.close();}
