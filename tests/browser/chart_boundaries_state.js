// Run with a full-year 510300 or 510500 Analysis loaded from a real data source.
async (page) => {
  const check=(ok,message)=>{if(!ok)throw new Error(message);};
  const frame=()=>page.frames().find(f=>f.url().includes('/component/quantmind.chart_component'));
  const read=()=>frame().evaluate(()=>{
    const g=document.getElementById('chart'),l=g._fullLayout,t=g._fullData[0];
    return {query:l.uirevision,x:[...l.xaxis.range],count:t.x.length,firstDate:t.x[0],lastDate:t.x.at(-1),
      follow:g.dataset.autoFollow,y:[...l.yaxis.range],center:(t.high[0]+t.low[0])/2,
      axes:Object.keys(l).filter(k=>/^xaxis\d*$/.test(k)).map(k=>({range:[...l[k].range],min:l[k].minallowed,max:l[k].maxallowed})),
      datesAligned:g._fullData.every(d=>d.x.length===t.x.length&&d.x.every((v,i)=>v===t.x[i]))};
  });
  const initial=await read();
  async function startDate(year,month,day) {
    await page.keyboard.press('Escape');
    // Date segments are visible React Aria spinbuttons; set day first so every
    // intermediate date stays within the existing analysis end.
    for(const [segment,value] of [['day',day],['month',month],['year',year]]) {
      const field=page.getByRole('spinbutton',{name:`${segment}, 开始日期`,exact:true});
      await field.fill(value);await field.press('Tab');
    }
    await page.keyboard.press('Escape'); // leave the date-picker popover before submitting
  }
  async function submit(previous) {
    await page.getByTestId('stBaseButton-primaryFormSubmit').click();
    await page.waitForFunction(old=>{
      const f=[...document.querySelectorAll('iframe')].find(f=>f.src.includes('/component/quantmind.chart_component'));
      try {const g=f?.contentDocument?.getElementById('chart');return g?._fullLayout?.uirevision!==old&&g?._fullData?.length>0;}
      catch(_){return false;}
    },previous.query,{timeout:65000});
    await page.waitForTimeout(1000);
    const s=await read();
    check(s.query!==previous.query&&s.follow==='true','date query did not reset state');
    check(s.x[0]===-.5&&Math.abs(s.x[1]-(s.count-.5))<1e-8,'new date bounds incorrect');
    check(s.datesAligned,'subplot dates diverged');
    check(s.axes.every(a=>a.min===-.5&&a.max===s.count-.5&&a.range.every((v,i)=>Math.abs(v-s.x[i])<1e-8)),'stale limits after date query');
    return s;
  }
  await startDate('2026','08','03');
  check((await read()).query===initial.query,'unsubmitted date edit changed analysis');
  const short=await submit(initial);
  check(short.count<initial.count&&short.count>1,'shorter query did not crop data');
  check(short.firstDate==='2026-08-03'&&short.lastDate==='2026-10-15','selected dates not respected');
  await startDate('2026','10','15');
  const single=await submit(short);
  check(single.count===1&&single.x[0]===-.5&&single.x[1]===.5,'one candle must occupy one slot');
  check(Math.abs((single.y[0]+single.y[1])/2-single.center)<1e-8,'one-candle price center incorrect');
  await (await frame().frameElement()).scrollIntoViewIfNeeded();
  const box=await frame().locator('.draglayer .xy .nsewdrag').boundingBox();
  const p={x:box.x+box.width/2,y:box.y+box.height/2};
  await page.mouse.move(p.x,p.y);await page.mouse.down();
  await page.mouse.move(p.x+250,p.y,{steps:8});await page.mouse.up();
  for(const dx of [-100000,100000]) {await page.mouse.move(p.x,p.y);await page.mouse.wheel(dx,0);}
  await frame().getByRole('button',{name:'Zoom out',exact:true}).click();
  await frame().getByRole('button',{name:'Zoom in',exact:true}).click();await page.waitForTimeout(300);
  const singleAfter=await read();
  check(singleAfter.x[0]===-.5&&singleAfter.x[1]===.5&&singleAfter.datesAligned,'one-candle interaction escaped boundary');
  await page.screenshot({path:'output/playwright/chart-boundaries/single-candle.png'});
  return {status:'passed',initial,short,single,singleAfter};
}
