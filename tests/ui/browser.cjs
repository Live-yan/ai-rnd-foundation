const {chromium}=require('playwright');const fs=require('fs');const assert=require('assert/strict');
(async()=>{
  fs.mkdirSync('ui-reports',{recursive:true});const browser=await chromium.launch({headless:true});
  const pages=['/factory','/factory-providers','/factory-toolchain'];const receipts=[];
  const diagnostics=[]; let currentPage; let currentRoute='startup';
  async function newPage(viewport) {
    const page=await browser.newPage({viewport,deviceScaleFactor:1}); currentPage=page;
    page.on('pageerror',error=>diagnostics.push({route:currentRoute,type:'pageerror',message:String(error)}));
    page.on('console',message=>{if(message.type()==='error') diagnostics.push({route:currentRoute,type:'console',message:message.text()});});
    page.on('requestfailed',request=>diagnostics.push({route:currentRoute,type:'requestfailed',url:request.url(),error:request.failure()}));
    page.on('response',response=>{if(response.status()>=400) diagnostics.push({route:currentRoute,type:'http',url:response.url(),status:response.status()});});
    return page;
  }
  try{
    for(const [width,height] of [[1366,768],[1280,720],[820,760],[390,780]]){
      const page=await newPage({width,height});
      for(const route of pages){
        currentRoute=route; await page.goto('http://127.0.0.1:4173/#'+route);await page.locator('.rnd-embedded').waitFor();
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
    const page=await newPage({width:1280,height:720}); currentRoute='configuration-actions';
    await page.goto('http://127.0.0.1:4173/#/factory-providers');await page.getByRole('button',{name:'添加模型',exact:true}).click();
    await page.locator('input[data-testid="api-key"], [data-testid="api-key"] input').fill('fixture-private-key');
    await page.locator('[data-testid="provider-select"]').click();await page.getByRole('option',{name:'Anthropic',exact:true}).click();
    assert.equal(await page.locator('input[data-testid="api-key"], [data-testid="api-key"] input').inputValue(),'');
    await page.getByRole('button',{name:'取消',exact:true}).click();
    // Stub only the external site; exercise real window.open under a user click.
    await page.context().route('https://auth.openai.com/**', route => route.fulfill({contentType:'text/html',body:'<h1>Official authorization fixture (no account)</h1>'}));
    async function clickLogin() {
      const opened=page.context().waitForEvent('page');
      await page.locator('.provider-row').nth(1).getByRole('button',{name:'网页登录'}).click();
      const popup=await opened; await popup.waitForLoadState();
      assert.equal(popup.url(),'https://auth.openai.com/codex/device');
      assert.equal(await popup.evaluate(()=>window.opener),null,'Official site must not access the workbench');
      await popup.close();
    }
    await clickLogin();
    await page.locator('.el-dialog__headerbtn').last().click();await page.waitForTimeout(1500);
    assert.deepEqual(await page.evaluate(()=>window.__calls),[], 'Closing login must prevent delayed authorization creation');
    await clickLogin();
    await page.getByText('TEST-ONLY',{exact:true}).waitFor();
    assert.deepEqual(await page.evaluate(()=>window.__calls),['oauth:begin']);
    await page.getByRole('button',{name:'复制设备码',exact:true}).waitFor();
    await page.locator('.el-dialog__headerbtn').last().click();
    await page.evaluate(()=>{window.__authFail=true;});
    await clickLogin();
    await page.getByRole('button',{name:'重试授权检查',exact:true}).waitFor();
    await page.evaluate(()=>{window.__authFail=false;});
    await page.getByRole('button',{name:'重试授权检查',exact:true}).click();
    await page.getByText('TEST-ONLY',{exact:true}).waitFor();
    await page.locator('.el-dialog__headerbtn').last().click();
    await page.goto('http://127.0.0.1:4173/#/factory-toolchain');
    for(let i=0;i<11;i++){await page.locator('.tool-card').nth(i).getByRole('button').click();await page.getByRole('button',{name:'保存配置',exact:true}).waitFor();await page.locator('.el-drawer__close-btn').last().click();}
    const cube=page.locator('.tool-card').filter({has:page.locator('strong',{hasText:/^cube$/})});
    await cube.getByRole('button').click();
    await page.getByLabel('测试字段',{exact:true}).fill('fixture-override');
    await page.getByRole('button',{name:'保存配置',exact:true}).click();
    await page.waitForFunction(()=>window.__configCalls.length===1);
    await page.getByRole('button',{name:'恢复默认',exact:true}).click();
    await page.getByRole('button',{name:'取消',exact:true}).click();
    assert.equal(await page.getByLabel('测试字段',{exact:true}).inputValue(),'fixture-override');
    assert.equal(await page.evaluate(()=>window.__configCalls.length),1,'Cancelled reset must not reach API');
    await page.getByRole('button',{name:'恢复默认',exact:true}).click();
    await page.getByRole('button',{name:'确认恢复',exact:true}).click();
    await page.waitForFunction(()=>window.__configCalls.length===2);
    await page.waitForFunction(()=>document.querySelector('.el-drawer input').value==='');
    await page.getByLabel('测试字段',{exact:true}).fill('fixture-after-reset');
    await page.getByRole('button',{name:'保存配置',exact:true}).click();
    await page.waitForFunction(()=>window.__configCalls.length===3);
    assert.deepEqual(await page.evaluate(()=>window.__configCalls),[
      {id:'cube',action:'save',revision:0},{id:'cube',action:'reset',revision:1},{id:'cube',action:'save',revision:2}
    ]);
    await page.getByRole('button',{name:'检查已保存配置',exact:true}).click();
    await page.locator('.el-drawer__close-btn').last().click();
    await page.locator('.tool-card').filter({has:page.locator('strong',{hasText:/^coder$/})}).getByRole('button').click();
    await page.waitForTimeout(1200);
    assert.equal(await page.getByText('迟到探针:cube',{exact:true}).count(),0,'Late probe must not overwrite another integration');
    fs.writeFileSync('ui-reports/layout.json' ,JSON.stringify({scope:'actual_components_with_API_fixtures',receipts,credential_switch:'passed',closed_authorization:'passed',official_login_popup:'passed',authorization_retry:'passed',configuration_drawers:11,reset_confirmation_and_revision:'passed',stale_probe:'passed'},null,2));
  }catch(error){
    if(currentPage && !currentPage.isClosed()) {
      await currentPage.screenshot({path:'ui-reports/failure.png',fullPage:true}).catch(()=>{});
      fs.writeFileSync('ui-reports/failure.html',await currentPage.content().catch(()=>''));
      diagnostics.push({route:currentRoute,type:'vue-errors',errors:await currentPage.evaluate(()=>window.__errors||[]).catch(()=>[])});
    }
    console.error(JSON.stringify(diagnostics,null,2)); throw error;
  }finally{
    fs.writeFileSync('ui-reports/diagnostics.json',JSON.stringify(diagnostics,null,2));
    await browser.close();
  }
})().catch(e=>{console.error(e);process.exit(1)});
