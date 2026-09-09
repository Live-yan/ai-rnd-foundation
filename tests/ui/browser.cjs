const {chromium}=require('playwright');const fs=require('fs');const assert=require('assert/strict');
(async()=>{
  fs.mkdirSync('ui-reports',{recursive:true});const browser=await chromium.launch({headless:true});
  const pages=['/factory','/factory-providers','/factory-toolchain'];const receipts=[];
  try{
    for(const [width,height] of [[1366,768],[1280,720],[820,760],[390,780]]){
      const page=await browser.newPage({viewport:{width,height},deviceScaleFactor:1});
      for(const route of pages){
        await page.goto('http://127.0.0.1:4173/#'+route);await page.locator('.rnd-embedded').waitFor();
        await page.waitForTimeout(900);
        const metrics=await page.evaluate(()=>{const p=document.querySelector('.rnd-embedded'),r=p.getBoundingClientRect();return {bottom:r.bottom,width:document.documentElement.scrollWidth,viewport:innerWidth,height:innerHeight,errors:window.__errors||[]};});
        assert(metrics.bottom<=height+2,`${route} bottom overflow ${JSON.stringify(metrics)}`);
        assert(metrics.width<=width+2,`${route} horizontal overflow`);assert.deepEqual(metrics.errors,[]);
        if(route==='/factory') {const box=await page.locator('.composer').boundingBox();assert(box&&box.y+box.height<=height);}
        if(route==='/factory-providers') assert(await page.locator('.provider-row').count()===9);
        if(route==='/factory-toolchain') assert(await page.locator('.tool-card').count()===11);
        await page.screenshot({path:`ui-reports/${route.slice(1)}-${width}x${height}.png`});receipts.push({route,width,height,...metrics});
      }
      await page.close();
    }
    const page=await browser.newPage({viewport:{width:1280,height:720}});
    await page.goto('http://127.0.0.1:4173/#/factory-providers');await page.getByRole('button',{name:'添加模型',exact:true}).click();
    await page.locator('[data-testid="api-key"] input').fill('fixture-private-key');
    await page.locator('[data-testid="provider-select"]').click();await page.getByRole('option',{name:'Anthropic',exact:true}).click();
    assert.equal(await page.locator('[data-testid="api-key"] input').inputValue(),'');
    await page.getByRole('button',{name:'取消',exact:true}).click();
    await page.locator('.provider-row').nth(1).getByRole('button',{name:'网页登录'}).click();
    await page.locator('.el-dialog__headerbtn').last().click();await page.waitForTimeout(1500);
    assert.deepEqual(await page.evaluate(()=>window.__calls),[], 'Closing login must prevent delayed authorization creation');
    await page.goto('http://127.0.0.1:4173/#/factory-toolchain');
    for(let i=0;i<11;i++){await page.locator('.tool-card').nth(i).getByRole('button').click();await page.getByRole('button',{name:'保存配置'}).waitFor();await page.locator('.el-drawer__close-btn').last().click();}
    fs.writeFileSync('ui-reports/layout.json',JSON.stringify({scope:'actual_components_with_API_fixtures',receipts,credential_switch:'passed',closed_authorization:'passed',configuration_drawers:11},null,2));
  }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
