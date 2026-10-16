// Real UI continuation: assumes an existing 510300 analysis and real-source query.
async (page) => {
  const check=(ok,message)=>{if(!ok)throw new Error(message);};
  const frame=()=>page.frames().find(f=>f.url().includes('/component/quantmind.chart_component'));
  const read=()=>frame().evaluate(()=>{
    const g=document.getElementById('chart'),l=g._fullLayout;
    return {query:l.uirevision,x:[...l.xaxis.range],y:[...l.yaxis.range],auto:g.dataset.autoFollow,
      names:g._fullData.map(t=>t.name),count:g._fullData[0].x.length,
      datesAligned:g._fullData.every(t=>t.x.every((v,i)=>v===g._fullData[0].x[i])),
      listeners:g._ev.listeners('plotly_relayout').filter(f=>f.name==='onRelayout').length};
  });
  const samePosition=(a,b)=>{
    check(a.x.every((v,i)=>Math.abs(v-b.x[i])<1e-8),'ordinary UI interaction lost x range');
    check(a.auto===b.auto,'ordinary UI interaction lost follow state');
    check(a.query===b.query,'ordinary UI interaction changed query');
    check(b.listeners===1 && b.datesAligned,'duplicate handlers or wrong dates after UI rerender');
  };
  const settle=()=>page.waitForTimeout(1000);
  await frame().getByRole('button',{name:'恢复视图',exact:true}).click();
  await frame().getByRole('checkbox',{name:'自动跟随',exact:true}).uncheck();
  await page.waitForTimeout(150);
  const host=await frame().frameElement();await host.scrollIntoViewIfNeeded();
  const box=await frame().locator('.draglayer .xy .nsewdrag').boundingBox();
  await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down();
  await page.mouse.move(box.x+box.width/2+100,box.y+box.height/2,{steps:12});await page.mouse.up();await page.waitForTimeout(200);
  const browsed=await read();
  await page.getByTestId('stCheckbox').getByText('均线',{exact:true}).click();await settle();
  const maOff=await read();samePosition(browsed,maOff);check(!maOff.names.includes('MA5'),'MA toggle failed');
  await page.getByTestId('stCheckbox').getByText('均线',{exact:true}).click();await settle();
  const maOn=await read();samePosition(browsed,maOn);check(maOn.names.includes('MA5'),'MA restore failed');
  await page.getByRole('combobox',{name:'副图指标',exact:true}).click();
  await page.getByRole('option',{name:'RSI',exact:true}).click();await settle();
  const rsi=await read();samePosition(browsed,rsi);
  check(rsi.names.includes('RSI14')&&!rsi.names.includes('DIF'),'RSI-only panel failed');
  await page.getByRole('tab',{name:'研究报告',exact:true}).click();await page.waitForTimeout(200);
  await page.getByRole('tab',{name:'行情图表',exact:true}).click();await settle();
  const afterTabs=await read();samePosition(browsed,afterTabs);

  await page.getByRole('combobox',{name:'ETF',exact:true}).click();
  await page.getByRole('option',{name:'510500 · 中证500ETF',exact:true}).click();await page.waitForTimeout(200);
  const edited=await read();samePosition(browsed,edited);
  check((await page.locator('.qm-heading').textContent()).includes('沪深300ETF'),'unsubmitted form changed current analysis');
  await page.getByTestId('stBaseButton-primaryFormSubmit').click();
  await page.getByRole('heading',{name:'中证500ETF',exact:true}).waitFor({state:'visible',timeout:65000});await settle();
  const changed=await read();
  check(changed.query!==browsed.query,'new ETF kept old query identity');
  check(changed.auto==='true' && changed.x[0]===-.5 && Math.abs(changed.x[1]-(changed.count-.5))<1e-8,'new ETF did not reset view');

  await frame().getByRole('checkbox',{name:'自动跟随',exact:true}).uncheck();await page.waitForTimeout(200);
  await page.getByTestId('stBaseButton-primaryFormSubmit').click();
  await frame().waitForFunction(old=>document.getElementById('chart')?._fullLayout?.uirevision!==old,changed.query,{timeout:65000});await settle();
  const resubmitted=await read();
  check(resubmitted.query!==changed.query,'same-ETF query did not reset identity');
  check(resubmitted.auto==='true' && resubmitted.x[0]===-.5,'same-ETF query did not restore auto follow and initial time');
  check(resubmitted.datesAligned && resubmitted.listeners===1,'bad dates/listeners after requery');
  await page.screenshot({path:'output/playwright/chart-follow/query-reset.png'});
  return {status:'passed',browsed,maOff,maOn,rsi,afterTabs,edited,changed,resubmitted};
}
