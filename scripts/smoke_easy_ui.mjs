import { chromium } from '../frontend/game/node_modules/playwright/index.mjs';
import fs from 'node:fs';
import assert from 'node:assert/strict';

// Offline browser integration: synthetic catalog/cards, every HTTP request intercepted.
const directory='.test-tmp-easy-authoring';fs.mkdirSync(directory,{recursive:true});
let catalog={revision:0,stats:{power:'قدرت',speed:'سرعت',iq:'هوش',popularity:'محبوبیت',scary:'ترسناکی',funny:'بامزگی',survival:'بقا',management:'مدیریت'},questions:[
  {id:'scary',text:'وحشتناک‌ترین کیه؟',formula:'scary',enabled:true,filter:'none',filter_value:''},
  {id:'hero',text:'ترسناک‌ترین {trait} کیه؟',formula:'scary',enabled:true,filter:'trait',filter_value:''}]};
let lastPayload=null, saved=0;
let card={id:'fixture',name:'Offline Hero',rarity:'normal',traits:['hero'],series:'Fixture',hidden_stats:{funny:32,survival:88,older_dimension:27},
  variants:['normal','epic','legend'].map((rarity,i)=>({rarity,card_type:'POWER_TYPE',power:30,speed:40,iq:50,popularity:60,traits:i===0?['hero']:['hero','ninja'],abilities:[],card_effects:[],passive:{}}))};
const browser=await chromium.launch({headless:true,executablePath:process.env.TELBATTLE_BROWSER_PATH});
try {
  const page=await browser.newPage({viewport:{width:430,height:900}}), errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  page.on('dialog',dialog=>dialog.accept());
  await page.route('**/*',async route=>{
    const path=new URL(route.request().url()).pathname;
    if(path==='/card-admin/easy-questions')return route.fulfill({contentType:'text/html',body:fs.readFileSync('web/easy_questions.html','utf8')});
    if(path==='/card-admin/')return route.fulfill({contentType:'text/html',body:fs.readFileSync('web/card_management.html','utf8')});
    let body={success:true};
    if(path==='/card-admin/api/easy/catalog'){
      assert.equal(route.request().headers()['x-admin-token'],'synthetic-ui-only');
      if(route.request().method()==='PUT'){catalog={...route.request().postDataJSON(),revision:catalog.revision+1};saved++;}
      body.catalog=catalog;
    }else if(path==='/card-admin/api/card-editor/options')body={success:true,traits:['hero','ninja'],series:['Fixture'],arenas:['city'],names:['Offline Hero'],images:[],easy_stats:catalog.stats};
    else if(path==='/card-admin/api/cards')body.cards=[card];
    else if(path==='/card-admin/api/cards/fixture/family'){
      lastPayload=route.request().postDataJSON();card={...card,...lastPayload,variants:Object.entries(lastPayload.variants).map(([rarity,v])=>({rarity,...v}))};body.card=card;body.message='ذخیره شد';
    }else return route.fulfill({status:404,body:''});
    return route.fulfill({contentType:'application/json',body:JSON.stringify(body)});
  });
  await page.goto('http://127.0.0.1:8099/card-admin/easy-questions');
  await page.locator('#token').fill('synthetic-ui-only');await page.locator('#load').click();await page.locator('#workspace').waitFor({state:'visible'});
  await page.locator('#example').click();assert.equal(await page.locator('#formula').inputValue(),'survival + management');
  await page.locator('#stat').selectOption('scary');await page.locator('#minus').click();
  await page.locator('#text').fill('کدوم کرکتر تو دنیای زامبی‌ها به قدرت می‌رسه؟');
  await page.locator('#save').click();await page.getByText('ذخیره شد؛ بازی‌های جدید از این فهرست استفاده می‌کنند.').waitFor();
  assert.equal(saved,1);assert.equal(catalog.questions.at(-1).formula,'survival + management - scary');
  await page.locator('#questions button').nth(1).click();await page.locator('#formula').fill('scary + survival');
  await page.locator('#enabled').uncheck();await page.locator('#save').click();await page.waitForFunction(()=>document.getElementById('count').textContent.includes('نسخه 2'));
  assert.equal(catalog.questions[1].enabled,false);assert.equal(catalog.questions[1].formula,'scary + survival');
  await page.locator('#statKey').fill('strategy');await page.locator('#statLabel').fill('استراتژی');await page.locator('#addStat').click();await page.locator('#save').click();
  await page.waitForFunction(()=>document.getElementById('count').textContent.includes('نسخه 3'));
  assert.equal(catalog.stats.strategy,'استراتژی');
  await page.screenshot({path:directory+'/question-editor-mobile.png',fullPage:true});
  assert.ok(await page.evaluate(()=>document.body.scrollWidth<=innerWidth));
  await page.goto('http://127.0.0.1:8099/card-admin/');await page.locator('[data-card-id="fixture"]').click();
  await page.locator('[data-tab="modes"]').click();assert.equal(await page.locator('#easy_survival').inputValue(),'88');
  assert.equal(await page.locator('#easy_older_dimension').inputValue(),'27');
  await page.locator('#easy_strategy').fill('61');await page.locator('#saveBtn').click();
  await page.waitForFunction(()=>document.getElementById('toast').textContent==='ذخیره شد');
  assert.deepEqual(lastPayload.hidden_stats,{funny:32,survival:88,older_dimension:27,strategy:61});
  assert.deepEqual(lastPayload.variants.normal.traits,['hero']);assert.deepEqual(lastPayload.variants.epic.traits,['hero','ninja']);
  await page.screenshot({path:directory+'/card-easy-stats-mobile.png',fullPage:true});
  assert.ok(await page.evaluate(()=>document.body.scrollWidth<=innerWidth));
  await page.setViewportSize({width:1280,height:900});await page.goto('http://127.0.0.1:8099/card-admin/easy-questions');
  await page.locator('#token').fill('synthetic-ui-only');await page.locator('#load').click();await page.locator('#workspace').waitFor({state:'visible'});
  await page.screenshot({path:directory+'/question-editor-desktop.png',fullPage:true});
  assert.equal(await page.evaluate(()=>localStorage.length+sessionStorage.length),0);
  assert.deepEqual(errors,[]);console.log('Easy editor and card values: mobile/desktop, safe round trip, variant traits preserved, no browser errors.');
} finally {await browser.close();}
