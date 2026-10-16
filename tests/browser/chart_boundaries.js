// Run with Playwright CLI against a real queried Analysis, not TEST market bars.
async (page) => {
  const check=(ok,message)=>{if(!ok)throw new Error(message);};
  const near=(a,b,message)=>check(Math.abs(a-b)<1e-8,`${message}: ${a} != ${b}`);
  const frame=()=>page.frames().find(f=>f.url().includes('/component/quantmind.chart_component'));
  const settle=()=>page.waitForTimeout(180);
  const read=()=>frame().evaluate(()=>{
    const g=document.getElementById('chart'),l=g._fullLayout,t=g._fullData[0],x=[...l.xaxis.range];
    const first=Math.max(0,Math.ceil(x[0]-1e-9)),last=Math.min(t.x.length-1,Math.floor(x[1]+1e-9));
    let centerIndex=first;
    for(let i=first;i<=last;i++)
      if(Math.abs(i-(x[0]+x[1])/2)<Math.abs(centerIndex-(x[0]+x[1])/2)) centerIndex=i;
    let low=Infinity,high=-Infinity;
    for(let i=first;i<=last;i++) {
      low=Math.min(low,t.low[i]);high=Math.max(high,t.high[i]);
      for(const ma of g._fullData.filter(t=>['MA5','MA20','MA60'].includes(t.name)&&t.visible!==false&&t.visible!=='legendonly'))
        if(Number.isFinite(ma.y[i])) {low=Math.min(low,ma.y[i]);high=Math.max(high,ma.y[i]);}
    }
    const center=(t.low[centerIndex]+t.high[centerIndex])/2;
    const radius=Math.max(center-low,high-center,Math.abs(center)*.002,1e-6);
    return {x,count:t.x.length,width:x[1]-x[0],pixelWidth:l.xaxis._length,y:[...l.yaxis.range],
      expectedY:[center-1.1*radius,center+1.1*radius],first,last,centerDate:t.x[centerIndex],phase:g.dataset.phase,
      axes:Object.keys(l).filter(k=>/^xaxis\d*$/.test(k)).map(k=>[...l[k].range]),
      subY:Object.keys(l).filter(k=>/^yaxis\d+$/.test(k)).map(k=>[...l[k].range]),
      datesAligned:g._fullData.every(d=>d.x.length===t.x.length&&d.x.every((v,i)=>v===t.x[i])),
      listeners:g._ev.listeners('plotly_relayout').filter(f=>f.name==='onRelayout').length};
  });
  function validate(s,width=null) {
    check(s.x[0]>=-.5-1e-9&&s.x[1]<=s.count-.5+1e-9,'horizontal boundary escaped');
    check(s.width<=s.count+1e-9 && s.first<=s.last,'oversized or empty viewport');
    if(width!==null) near(s.width,width,'pan changed width/density');
    check(s.datesAligned&&s.listeners===1,'dates or listeners incorrect');
    for(const x of s.axes) {near(x[0],s.x[0],'subplot left');near(x[1],s.x[1],'subplot right');}
    near(s.y[0],s.expectedY[0],'center-follow low');near(s.y[1],s.expectedY[1],'center-follow high');
  }
  async function point(selector='.draglayer .xy .nsewdrag') {
    await (await frame().frameElement()).scrollIntoViewIfNeeded();
    const b=await frame().locator(selector).boundingBox();return {x:b.x+b.width/2,y:b.y+b.height/2};
  }
  let sampledDragFrames=0;
  async function pan(dx,selector) {
    const p=await point(selector),before=await read();
    await page.mouse.move(p.x,p.y);await page.mouse.down();
    try {
      for(let i=1;i<=6;i++) {
        await page.mouse.move(p.x+dx*i/6,p.y+12*i/6);await page.waitForTimeout(40);
        const s=await read();validate(s,before.width);sampledDragFrames++;
        check(s.phase==='dragging','drag ended before release');
        check(JSON.stringify(s.subY)===JSON.stringify(before.subY),'subplot scale changed');
      }
    } finally {await page.mouse.up();}
    await settle();return read();
  }
  async function reach(side) {
    let s=await read(); const width=s.width;
    for(let i=0;i<30;i++) {
      if(Math.abs((side==='left'?s.x[0]+.5:s.x[1]-(s.count-.5)))<1e-8) break;
      s=await pan(side==='left'?420:-420);
    }
    near(side==='left'?s.x[0]:s.x[1],side==='left'?-.5:s.count-.5,`mouse ${side} edge`);
    validate(s,width);return s;
  }
  async function reverseHeld(side) {
    const p=await point(),before=await read(),sign=side==='left'?1:-1;
    await page.mouse.move(p.x,p.y);await page.mouse.down();
    try {
      await page.mouse.move(p.x+sign*220,p.y,{steps:8});await settle();
      const overshoot=await read();validate(overshoot,before.width);
      near(overshoot.x[0],before.x[0],'continued edge input moved viewport');
      // Still 214px past pointerdown: a 6px reverse must move immediately.
      await page.mouse.move(p.x+sign*214,p.y);await settle();
      const reversed=await read();validate(reversed,before.width);
      near(reversed.x[0]-before.x[0],sign*6*before.width/before.pixelWidth,'held reverse has dead travel');
      return {overshoot,reversed};
    } finally {await page.mouse.up();await settle();}
  }
  async function wheel(dx,dy=0) {
    const p=await point();await page.mouse.move(p.x,p.y);await page.mouse.wheel(dx,dy);await settle();
    const s=await read();validate(s);return s;
  }
  await page.setViewportSize({width:1440,height:1450});
  const shortcut=page.getByRole('radio',{name:'3个月',exact:true});
  if(await shortcut.getAttribute('aria-checked')!=='true') await shortcut.click();
  await page.waitForTimeout(1000);
  await frame().getByRole('button',{name:'Pan',exact:true}).click();
  await frame().getByRole('button',{name:'恢复视图',exact:true}).click();await settle();
  const initial=await read();validate(initial);
  await frame().evaluate(()=>{
    const g=document.getElementById('chart');
    window.boundaryAudit={samples:0,violations:[],events:0,rangeEvents:0,active:true};
    g.on('plotly_relayout',e=>{
      const a=window.boundaryAudit;a.events++;
      if(Object.keys(e).some(k=>k.includes('.range'))) a.rangeEvents++;
    });
    const tick=()=>{
      const a=window.boundaryAudit,l=g._fullLayout,n=g._fullData[0].x.length;a.samples++;
      for(const k of Object.keys(l).filter(k=>/^xaxis\d*$/.test(k))) {
        const r=l[k].range;
        if(r[0]<-.5-1e-8||r[1]>n-.5+1e-8||r[1]-r[0]>n+1e-8) a.violations.push({k,range:[...r]});
      }
      if(a.active) requestAnimationFrame(tick);
    };requestAnimationFrame(tick);
  });
  const left=await reach('left'),leftReverse=await reverseHeld('left');
  const right=await reach('right'),rightReverse=await reverseHeld('right');
  const axisPan=await pan(90,'.draglayer .x4y4 .ewdrag');
  near(axisPan.width,initial.width,'time scale pan density');

  const momentum=[];
  for(const sign of [-1,1]) {
    const p=await point();await page.mouse.move(p.x,p.y);
    for(let i=0;i<35;i++) await page.mouse.wheel(sign*1200*Math.pow(.91,i),0);
    await settle();const edge=await read();validate(edge,initial.width);
    near(sign<0?edge.x[0]:edge.x[1],sign<0?-.5:edge.count-.5,'momentum did not stop at edge');
    const reversed=await wheel(-sign*5);validate(reversed,initial.width);
    check(sign<0?reversed.x[0]>edge.x[0]:reversed.x[0]<edge.x[0],'wheel reverse delayed');
    momentum.push({sign,edge,reversed});
  }
  await frame().getByRole('button',{name:'Zoom in',exact:true}).click();await settle();
  const zoomed=await read();validate(zoomed);near(zoomed.width,initial.width/2,'zoom in width');
  const zoomLeft=await wheel(-100000),zoomRight=await wheel(100000);
  validate(zoomLeft,zoomed.width);validate(zoomRight,zoomed.width);
  near(zoomLeft.x[0],-.5,'zoomed left edge');near(zoomRight.x[1],zoomRight.count-.5,'zoomed right edge');
  for(let i=0;i<6;i++) {await frame().getByRole('button',{name:'Zoom out',exact:true}).click();await settle();}
  const all=await read();validate(all);near(all.x[0],-.5,'maximum zoom left');near(all.x[1],all.count-.5,'maximum zoom right');
  const fullPan=await pan(300);validate(fullPan,all.count);near(fullPan.x[0],-.5,'full view pan should stay still');
  const p=await point();await page.mouse.move(p.x,p.y);await page.keyboard.down('Control');
  try {for(let i=0;i<8;i++) await page.mouse.wheel(0,300);} finally {await page.keyboard.up('Control');}
  await settle();const maxPinch=await read();validate(maxPinch);near(maxPinch.width,maxPinch.count,'pinch maximum');
  await page.setViewportSize({width:820,height:1250});await page.waitForTimeout(350);
  const resized=await read();validate(resized,all.count);
  await page.setViewportSize({width:1440,height:1450});await page.waitForTimeout(1000);
  const beforeIdle=await frame().evaluate(()=>window.boundaryAudit.rangeEvents);await page.waitForTimeout(450);
  const audit=await frame().evaluate(()=>{window.boundaryAudit.active=false;return window.boundaryAudit;});
  check(audit.violations.length===0,'a live frame crossed a boundary');
  check(audit.rangeEvents===beforeIdle,'range events loop while idle');
  await page.screenshot({path:'output/playwright/chart-boundaries/all-data.png'});
  return {status:'passed',initial,left,leftReverse,right,rightReverse,axisPan,momentum,zoomed,zoomLeft,zoomRight,all,maxPinch,resized,
    sampledDragFrames,audit,physicalMacTrackpad:'NOT VERIFIED: actual two-finger gesture, physical inertia and pinch require human acceptance'};
}
