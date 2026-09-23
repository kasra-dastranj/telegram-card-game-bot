import { chromium } from 'playwright';
import { mkdir } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { resolve, basename } from 'node:path';

const base = process.env.QA_URL || 'http://127.0.0.1:5173/miniapp-assets/';
const label = process.env.QA_LABEL || 'after';
const output = `test-results/redesign-${label}`;
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ headless: true, executablePath: existsSync('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe') ? 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe' : undefined });
try {
  for (const [width, height] of [[390,844], [375,667], [768,1024]].filter(([width]) => !process.env.QA_WIDTH || width === Number(process.env.QA_WIDTH))) {
    const context = await browser.newContext({ viewport: {width,height}, isMobile:true, hasTouch:true, reducedMotion:'reduce' });
    await context.addInitScript(() => localStorage.setItem('telbattle:onboarding:v1', 'done'));
    const page = await context.newPage();
    const errors=[];
    page.on('pageerror', e=>errors.push(e.message));
    page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
    await page.route('https://telegram.org/js/**', r=>r.fulfill({body:'',contentType:'application/javascript'}));
    // Use real repository artwork; demo gameplay never writes to production.
    if (base.includes('127.0.0.1')) await page.route('**/card-images/**', async r=>{
      const file=resolve('../../assets/card_images', basename(new URL(r.request().url()).pathname));
      await r.fulfill({path:file,contentType:'image/png'});
    });
    await page.goto(`${base}?demo=1&dense=1`, {waitUntil:'networkidle'});
    await page.locator('.hub-nav').waitFor();
    await page.locator('.featured-card__art').first().waitFor();
    await page.evaluate(() => document.fonts.ready);
    if (!await page.evaluate(() => document.fonts.check('14px Vazirmatn'))) throw new Error('Persian font did not load');
    const headerFit = await page.evaluate(() => ({
      header: document.querySelector('.lobby-command-bar').getBoundingClientRect().bottom,
      title: document.querySelector('.table-heading').getBoundingClientRect().top,
      cta: document.querySelector('[data-action="enter-quick"]').getBoundingClientRect().bottom,
      nav: document.querySelector('.hub-nav').getBoundingClientRect().top,
    }));
    if (headerFit.title < headerFit.header || headerFit.cta > headerFit.nav) throw new Error(`Lobby overlap: ${JSON.stringify(headerFit)}`);
    await page.screenshot({path:`${output}/lobby-${width}.png`});
    for (const [action,name,ready] of [
      ['open-collection','collection','.collection-card'],
      ['hub-decks','decks','.decks-screen'],
      ['hub-progress','progress','.progress-screen'],
      ['hub-shop','shop','.shop-screen'],
    ]) {
      await page.locator(`[data-action="${action}"]`).first().click();
      await page.locator(ready).first().waitFor();
      await page.screenshot({path:`${output}/${name}-${width}.png`});
      const fit=await page.evaluate(()=>({overflow:document.documentElement.scrollWidth>innerWidth,nav:document.querySelector('.hub-nav').getBoundingClientRect().toJSON()}));
      if(fit.overflow || fit.nav.bottom>height+1) throw new Error(`${name} layout overflow ${width}`);
    }
    await page.locator('[data-action="hub-game"]').click();
    await page.locator('[data-action="enter-arena"]').click();
    await page.locator('[data-action="select-card"]').first().waitFor();
    await page.screenshot({path:`${output}/selection-${width}.png`});
    await page.locator('[data-action="select-card"]').first().click();
    await page.locator('[data-action="start"]').click();
    await page.locator('.battle-screen').waitFor();
    await page.waitForTimeout(800);
    const boardFit = await page.evaluate(() => {
      const canvas=document.querySelector('#game-root canvas').getBoundingClientRect();
      const hud=document.querySelector('.battle-hud').getBoundingClientRect();
      const controls=document.querySelector('.stat-console').getBoundingClientRect();
      // Solo cards use logical centers 330/760; allow for the tilted frame corners.
      return {opponentTop:canvas.top+canvas.height*(330-125)/1280,playerBottom:canvas.top+canvas.height*(760+150)/1280,hudBottom:hud.bottom,controlsTop:controls.top};
    });
    if(boardFit.opponentTop < boardFit.hudBottom || boardFit.playerBottom > boardFit.controlsTop) throw new Error(`Board covered by controls: ${JSON.stringify(boardFit)}`);
    await page.screenshot({path:`${output}/battle-${width}.png`});
    // The demo wins the first two rounds, so best-of-three ends at 2–0.
    for (let round=0; round<2; round++) {
      await page.locator('[data-action="stat"]:enabled').first().waitFor();
      await page.locator('[data-action="stat"]:enabled').first().click();
      if (round < 1) await page.locator('[data-action="stat"]:enabled').first().waitFor();
    }
    await page.locator('.result-screen').waitFor();
    await page.screenshot({path:`${output}/result-${width}.png`});
    if(errors.length) throw new Error(errors.join('\n'));
    console.log(`PASS ${width}x${height}`);
    await context.close();
  }
  // Real API contract with empty / one-card / two-card inventories, not demo state.
  for (const count of process.env.QA_WIDTH ? [] : [0, 1, 2]) {
    const context = await browser.newContext({viewport:{width:375,height:667},reducedMotion:'reduce'});
    await context.addInitScript(() => localStorage.setItem('telbattle:onboarding:v1','done'));
    const page = await context.newPage();
    const cards = Array.from({length:count}, (_,index)=>({card_id:`qa-${index}`,name:'قهرمان با نام فارسی بلند',rarity:'rare',power:70,speed:75,iq:80,popularity:85,image_url:''}));
    await page.route('https://telegram.org/js/**', r=>r.fulfill({body:'',contentType:'application/javascript'}));
    await page.route('**/api/v1/**', r=>r.fulfill({contentType:'application/json',body:JSON.stringify(r.request().url().includes('/profile') ? {first_name:'بازیکن تازه',level:1,hearts:3,max_hearts:5,coins:0,counts:{cards:count,decks:0}} : {cards,total:count,page:1,page_count:1,limit:3})}));
    await page.goto(base,{waitUntil:'networkidle'});
    await page.locator('.lobby-screen').waitFor();
    if (await page.locator('.featured-card__art').count() !== count) throw new Error(`Invented or missing card with inventory ${count}`);
    const bounds = await page.locator('.featured-card').evaluateAll(items => items.map(item => {const r=item.getBoundingClientRect();return {left:r.left,right:r.right};}));
    if(bounds.some(r=>r.left<0 || r.right>375)) throw new Error(`Preview exceeds viewport with ${count} cards`);
    await page.screenshot({path:`${output}/inventory-${count}.png`});
    await page.locator('[data-action="open-collection"]').first().click();
    if(count===0) await page.locator('.empty-state').waitFor();
    else await page.locator('.collection-card').first().waitFor();
    console.log(`PASS inventory=${count}`);
    await context.close();
  }
} finally { await browser.close(); }
