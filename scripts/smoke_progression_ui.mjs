import { chromium } from '../frontend/game/node_modules/playwright/index.mjs';
import fs from 'node:fs';
import assert from 'node:assert/strict';
fs.mkdirSync('.test-tmp-phase2', { recursive:true });
const browser = await chromium.launch({ executablePath:process.env.TELBATTLE_BROWSER_PATH, headless:true });
const page = await browser.newPage({viewport:{width:430,height:900}});
const errors=[];
page.on('pageerror',error=>errors.push(error.message));
let spent=0, upgrades=0, sales=0;
const card={card_id:'deadpool',name:'Deadpool',rarity:'normal',power:5,speed:5,iq:5,popularity:5,abilities:['hero'],biography:'test',card_type:'POWER_TYPE',image_url:'',inventory:{normal:6,epic:2},upgrade:{ok:false,error_code:'coin_upgrade_removed'}};
const profile={user_id:1,first_name:'Tester',level:5,hearts:8,max_hearts:8,coins:1000,total_score:3,current_xp:25,xp_to_next_level:300,progression_v2_enabled:true,current_tier:null,tier_points:null,counts:{cards:1,decks:0,missions_ready:0,rarities:{normal:1}},economy:{items:{silver_ticket:3,upgrade_card:1},capacity:{slots:7,max_hearts:8},shop:{silver_ticket:{enabled:true},upgrade_card:{enabled:true},refill:{enabled:true}},daily_ticket_percent:20,silver_claim_tickets:3},claim:{can_claim:true,remaining_seconds:0}};
await page.route('**/api/v1/**',async route=>{
  const url=new URL(route.request().url());const path=url.pathname.slice('/api/v1'.length);
  let body={};
  if(path==='/profile'||path==='/player-hub/overview')body=profile;
  else if(path==='/cards')body={cards:[card],total:1,page:1,limit:60,page_count:1};
  else if(path==='/cards/deadpool')body=card;
  else if(path==='/cards/deadpool/fuse-copies/preview')body={ok:true,required:url.searchParams.get('target')==='legend'?2:3,upgrade_cards_required:1,xp:200,config_version:1};
  else if(path==='/economy/quote')body={ok:true,quote_id:'test-quote',price:100,config_version:1};
  else if(path==='/economy/purchase'){spent++;body={ok:true,profile:{...profile,coins:900}};}
  else if(path==='/economy/cards/deadpool/upgrade'){upgrades++;body={ok:true,xp_gained:200,profile};}
  else if(path==='/economy/cards/deadpool/sell/preview')body={ok:true,price:60,config_version:1};
  else if(path==='/economy/cards/deadpool/sell'){sales++;body={ok:true,profile};}
  else if(path==='/claim'&&route.request().method()==='GET')body={can_claim:true,remaining_seconds:0,pool_count:1};
  else if(path==='/claim'){body={ok:true,message:'یک Silver Ticket دریافت شد',data:{card:null,reward_type:'silver_ticket',quantity:1,ability:{key:'reveal_opponent',title:'دیدن حریف'}},profile};}
  else if(path==='/missions')body={missions:[]};
  else if(path==='/decks')body={decks:[]};
  else if(path==='/solo/quota')body={used:0,remaining:10,limit:10};
  await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(body)});
});
await page.goto(process.env.TELBATTLE_SMOKE_URL || 'http://127.0.0.1:5173/miniapp-assets/');
await page.locator('[data-action="onboarding-skip"]').click();
await page.locator('[data-action="hub-shop"]').first().click();
await page.locator('[data-action="v2-quote"][data-value="silver_ticket"]').click();
await page.locator('[data-action="v2-buy"]').click();
assert.equal(spent,1);
assert.equal(await page.locator('[data-action="fusion-target"]').count(),0);
await page.locator('[data-action="open-collection"]').first().click();
await page.locator('[data-action="card-detail"]').first().click();
await page.locator('[data-action="ask-copy-fusion"][data-value="legend"]').click();
await page.locator('[data-action="confirm-copy-fusion"]').click();
assert.equal(upgrades,1);
await page.locator('[data-action="preview-sell"][data-value="epic"]').click();
await page.locator('[data-action="confirm-sell"]').click();
assert.equal(sales,1);
await page.locator('[data-action="hub-progress"]').click();
await page.locator('[data-action="claim-daily"]').click();
await page.getByRole('heading',{name:'🎟 یک Silver Ticket دریافت شد'}).waitFor();
assert.equal(await page.locator('.tier-badge').count(),0);
assert.deepEqual(errors,[]);
await page.screenshot({path:'.test-tmp-phase2/browser-progress.png',fullPage:true});
fs.writeFileSync('.test-tmp-phase2/browser-results.json',JSON.stringify({browser:'Edge headless',api:'local fixtures; no live Telegram',spent,upgrades,sales,errors},null,2));
await browser.close();
process.stdout.write('Phase2 browser smoke passed: quote/purchase, 2-Epic recipe preview/upgrade, sell, Ticket claim, legacy Fusion/Tier hidden.\n');
