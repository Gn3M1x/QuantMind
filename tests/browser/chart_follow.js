// Run after a real query with playwright-cli run-code --filename. No fabricated bars.
async (page) => {
  const check = (ok, message) => { if (!ok) throw new Error(message); };
  const near = (a, b, message) => check(Math.abs(a - b) < 1e-8, `${message}: ${a} != ${b}`);
  const frame = () => page.frames().find(f => f.url().includes('/component/quantmind.chart_component'));
  const read = () => frame().evaluate(() => {
    const g = document.getElementById('chart'), l = g._fullLayout, t = g._fullData[0];
    const x = [...l.xaxis.range], first = Math.max(0, Math.ceil(x[0] - 1e-9));
    const last = Math.min(t.x.length - 1, Math.floor(x[1] + 1e-9));
    let middle = first;
    for (let i = first; i <= last; i++)
      if (Math.abs(i - (x[0]+x[1])/2) < Math.abs(middle - (x[0]+x[1])/2)) middle = i;
    let low = Infinity, high = -Infinity;
    for (let i = first; i <= last; i++) {
      low = Math.min(low, t.low[i]); high = Math.max(high, t.high[i]);
      for (const ma of g._fullData.filter(t => ['MA5','MA20','MA60'].includes(t.name) && t.visible !== 'legendonly' && t.visible !== false)) {
        if (Number.isFinite(ma.y[i])) { low=Math.min(low,ma.y[i]); high=Math.max(high,ma.y[i]); }
      }
    }
    const center = (t.high[middle] + t.low[middle]) / 2;
    const radius = Math.max(center-low,high-center,Math.abs(center)*.002,1e-6);
    return {x,y:[...l.yaxis.range],expectedY:[center-1.1*radius,center+1.1*radius],first,last,middle,
      centerDate:t.x[middle],phase:g.dataset.phase,auto:g.dataset.autoFollow,
      axes:Object.keys(l).filter(k=>/^xaxis\d*$/.test(k)).map(k=>[...l[k].range]),
      subordinate:Object.keys(l).filter(k=>/^yaxis\d+$/.test(k)).map(k=>[...l[k].range]),
      visibleCloseChange:t.close[last]-t.close[first],
      yLocked:l.yaxis.fixedrange,datesAligned:g._fullData.every(t=>t.x.length===g._fullData[0].x.length && t.x.every((x,i)=>x===g._fullData[0].x[i])),
      listeners:g._ev.listeners('plotly_relayout').filter(f=>f.name==='onRelayout').length};
  });
  function validate(s) {
    check(s.datesAligned,'subplot dates differ'); check(s.listeners===1,'duplicate range listener');
    for(const x of s.axes) { near(x[0],s.x[0],'shared x start'); near(x[1],s.x[1],'shared x end'); }
    if(s.auto==='true') { near(s.y[0],s.expectedY[0],'lower price bound'); near(s.y[1],s.expectedY[1],'upper price bound'); }
  }
  async function point(selector='.draglayer .xy .nsewdrag') {
    const host=await frame().frameElement(); await host.scrollIntoViewIfNeeded();
    const b=await host.boundingBox(), r=await frame().locator(selector).boundingBox();
    // Frame locator boundingBox already returns coordinates in the top-level page.
    return {x:r.x+r.width*.5,y:r.y+r.height*.5,host:b};
  }
  async function dragBy(dx,dy=0,steps=12) {
    const p=await point(), before=await read(), samples=[];
    await page.mouse.move(p.x,p.y); await page.mouse.down();
    try {
      for(let i=1;i<=steps;i++) {
        await page.mouse.move(p.x+dx*i/steps,p.y+dy*i/steps);
        await page.waitForTimeout(45); const s=await read(); validate(s); samples.push(s);
      }
      check(samples.some(s=>s.phase==='dragging' && Math.abs(s.x[0]-before.x[0])>.05),
        `no continuous update before release: ${JSON.stringify({before,first:samples[0],last:samples.at(-1),point:p})}`);
    } finally { await page.mouse.up(); }
    await page.waitForTimeout(180);
    const after=await read(); validate(after);
    near(after.x[1]-after.x[0],before.x[1]-before.x[0],'drag changed density');
    check(JSON.stringify(after.subordinate)===JSON.stringify(before.subordinate),'subordinate scales changed during pan');
    return {before,during:samples,after};
  }

  await page.setViewportSize({width:1440,height:1450});
  const rangeButton=page.getByRole('radio',{name:'3个月',exact:true});
  if(await rangeButton.getAttribute('aria-checked')!=='true') await rangeButton.click();
  await page.waitForTimeout(1000);
  await frame().getByRole('button',{name:'恢复视图',exact:true}).click(); await page.waitForTimeout(200);
  const original=await read(); validate(original);
  const right=await dragBy(180,55);
  const left=await dragBy(-180,-40);
  near(left.after.x[0],original.x[0],'opposite pans did not restore x');

  const p=await point(), beforeWheel=await read();
  const wheelWidth=await frame().evaluate(()=>document.getElementById('chart')._fullLayout.xaxis._length);
  await page.mouse.move(p.x,p.y); await page.mouse.wheel(-220,0); await page.waitForTimeout(300);
  const wheel=await read(); validate(wheel);
  check(wheel.x[0]<beforeWheel.x[0],'horizontal wheel did not move time');
  near(wheel.x[1]-wheel.x[0],beforeWheel.x[1]-beforeWheel.x[0],'wheel changed density');
  // CDP wheel delivery may scale with the host display; calibrate automation input,
  // never compensate real WheelEvent deltas in production code.
  const wheelFactor=(wheel.x[0]-beforeWheel.x[0])/(-220*(beforeWheel.x[1]-beforeWheel.x[0])/wheelWidth);

  await page.keyboard.down('Control'); await page.mouse.wheel(0,-150); await page.keyboard.up('Control');
  await page.waitForTimeout(300);
  const zoom=await read(); validate(zoom);
  check(zoom.x[1]-zoom.x[0]<wheel.x[1]-wheel.x[0],'modified wheel did not zoom');
  const afterZoomDrag=await dragBy(140,40);

  await frame().getByRole('checkbox',{name:'自动跟随',exact:true}).uncheck();
  await page.waitForTimeout(150);
  const manual=await read(); check(!manual.yLocked && manual.auto==='false','manual scale locked');
  const axis=await point('.draglayer .xy .nsdrag');
  await page.mouse.move(axis.x,axis.y); await page.mouse.down();
  await page.mouse.move(axis.x,axis.y+65,{steps:10}); await page.mouse.up(); await page.waitForTimeout(200);
  const manualAxis=await read(); check(Math.abs(manualAxis.y[0]-manual.y[0])>.001,'manual axis drag failed');
  const manualPan=await dragBy(-80,30);
  near(manualPan.after.y[0],manualAxis.y[0],'manual price range was overwritten');

  await frame().getByRole('checkbox',{name:'自动跟随',exact:true}).check(); await page.waitForTimeout(200);
  const followingAgain=await read(); validate(followingAgain); check(followingAgain.yLocked,'follow did not lock y');
  await frame().getByRole('button',{name:'恢复视图',exact:true}).click(); await page.waitForTimeout(200);
  const reset=await read(); validate(reset); near(reset.x[0],original.x[0],'reset start'); near(reset.x[1],original.x[1],'reset end');
  check(reset.auto==='true','reset did not enable auto follow');

  // Native box zoom must commit once, not repeatedly shrink on preview events.
  await frame().getByRole('button',{name:'Zoom',exact:true}).click();
  const zoomHost=await frame().frameElement();await zoomHost.scrollIntoViewIfNeeded();
  const zoomBox=await frame().locator('.draglayer .xy .nsewdrag').boundingBox();
  await page.mouse.move(zoomBox.x+zoomBox.width*.25,zoomBox.y+zoomBox.height*.35);await page.mouse.down();
  await page.mouse.move(zoomBox.x+zoomBox.width*.75,zoomBox.y+zoomBox.height*.65,{steps:12});await page.mouse.up();await page.waitForTimeout(250);
  const boxZoom=await read();validate(boxZoom);
  check(Math.abs((boxZoom.x[1]-boxZoom.x[0])/(reset.x[1]-reset.x[0])-.5)<.01,'box zoom compounded continuous events');
  await frame().getByRole('button',{name:'Pan',exact:true}).click();
  await frame().getByRole('button',{name:'恢复视图',exact:true}).click();await page.waitForTimeout(200);

  // Real loaded candles: locate strong rise and fall windows, then navigate there using wheel input.
  const targets={},trends={};
  for(const name of ['rise','fall']) {
    // Use a native modebar zoom, then wheel-pan to the independently chosen window.
    await frame().getByRole('button',{name:'Zoom in',exact:true}).click(); await page.waitForTimeout(180);
    targets[name]=await frame().evaluate(direction=>{
      const g=document.getElementById('chart'),c=g._fullData[0].close,width=Math.floor(g._fullLayout.xaxis.range[1]-g._fullLayout.xaxis.range[0]);
      let best={change:direction==='rise'?-Infinity:Infinity};
      for(let i=0;i+width<c.length;i++) {const change=c[i+width]-c[i];
        if(direction==='rise'?change>best.change:change<best.change) best={start:i,change};}
      return best;
    },name);
    for(let attempt=0;attempt<4;attempt++) {
      const s=await read(),target=targets[name].start-.2;
      if(Math.abs(s.x[0]-target)<.02) break;
      const width=await frame().evaluate(()=>document.getElementById('chart')._fullLayout.xaxis._length);
      const q=await point(); await page.mouse.move(q.x,q.y);
      await page.mouse.wheel((target-s.x[0])*width/(s.x[1]-s.x[0])/wheelFactor,0); await page.waitForTimeout(300);
    }
    trends[name]=await read(); validate(trends[name]);
    await page.screenshot({path:`output/playwright/chart-follow/${name}.png`});
  }
  check(targets.rise.change>0 && targets.fall.change<0,'no actual rising/falling sample found');
  check(trends.rise.visibleCloseChange>0 && trends.fall.visibleCloseChange<0,'visible trend windows have wrong direction');

  const edgePoint=await point(); await page.mouse.move(edgePoint.x,edgePoint.y);
  await page.mouse.wheel(100000,0); await page.waitForTimeout(250);
  const rightBoundary=await read(); validate(rightBoundary);
  const count=await frame().evaluate(()=>document.getElementById('chart')._fullData[0].x.length);
  near(rightBoundary.x[1],count-.5,'large wheel escaped right boundary');
  await frame().getByRole('button',{name:'恢复视图',exact:true}).click(); await page.waitForTimeout(200);
  validate(await read());

  // A normal vertical wheel outside the chart must scroll the page without touching time.
  await page.evaluate(()=>document.querySelector('[data-testid=stMain]').scrollTop=0);
  const beforeScroll=await read(); await page.mouse.move(1200,190); await page.mouse.wheel(0,300); await page.waitForTimeout(300);
  const pageScroll=await page.evaluate(()=>document.querySelector('[data-testid=stMain]').scrollTop);
  check(pageScroll>0,'outside-page vertical scroll blocked'); near((await read()).x[0],beforeScroll.x[0],'page scroll moved time');

  return {status:'passed',original,right,left,wheel,wheelFactor,zoom,boxZoom,afterZoomDrag,manualAxis,manualPan,followingAgain,reset,targets,trends,pageScroll,
    rightBoundary,physicalMacTrackpad:'NOT VERIFIED: requires human two-finger gesture on a real Mac trackpad'};
}
