/* Artificial TEST observations only. Exercises the exact module used in the browser. */
const test = require('node:test');
const assert = require('node:assert/strict');
const { constrainRange, visibleWindow, priceRange, panByPixels, zoomAt } = require('../quantmind/assets/chart/viewport.js');
const near = (a, b) => assert.ok(Math.abs(a - b) < 1e-10, `${a} != ${b}`);

test('boundaries shift the entire window without squeezing its width', () => {
  assert.deepEqual(constrainRange(10,[-4,0]),[-.5,3.5]);
  assert.deepEqual(constrainRange(10,[9,13]),[5.5,9.5]);
  assert.deepEqual(constrainRange(10,[2.25,6.25]),[2.25,6.25]);
  assert.deepEqual(constrainRange(10,[-.5,9.5]),[-.5,9.5]);
});
test('oversized zoom and shorter replacement data show only all browsable records', () => {
  assert.deepEqual(constrainRange(3,[-20,40]),[-.5,2.5]);
  assert.deepEqual(constrainRange(3,[100.25,104.25]),[-.5,2.5]);
  assert.deepEqual(constrainRange(3,zoomAt([-.5,2.5],.8,2)),[-.5,2.5]);
});
test('empty, single, invalid and deep-zoom ranges have finite deterministic handling', () => {
  for (const count of [0,-1,NaN,1.5,Infinity]) assert.equal(constrainRange(count,[0,5]),null);
  for (const range of [null,[],[NaN,2],[Infinity,3],[3,2],[2,2]])
    assert.deepEqual(constrainRange(4,range),[-.5,3.5]);
  for (const range of [[-10,10],[20,21],[-.02,.02]])
    assert.deepEqual(constrainRange(1,range),[-.5,.5]);
  assert.deepEqual(constrainRange(4,[1.2,1.4]),[1.2,2.2]);
  assert.deepEqual(zoomAt([-.5,.5],.5,.01),[-.5,.5]);
  assert.deepEqual(constrainRange(4,[-Number.MAX_VALUE,Number.MAX_VALUE]),[-.5,3.5]);
});
test('consumed overshoot reverses immediately with the next pixel delta', () => {
  let r=[-.5,3.5];
  for(let i=0;i<20;i++) r=constrainRange(10,panByPixels(r,1000,400));
  assert.deepEqual(r,[-.5,3.5]);
  r=constrainRange(10,panByPixels(r,-1,400));
  near(r[0],-.49); near(r[1],3.51);
  r=constrainRange(10,panByPixels(r,-100000,400));
  assert.deepEqual(r,[5.5,9.5]);
  r=constrainRange(10,panByPixels(r,1,400));
  near(r[0],5.49); near(r[1],9.49);
});
test('fast momentum, reversals and resized plot retain span, bounds and visible candles', () => {
  let r=[7.25,17.5]; const span=10.25;
  for(let i=0;i<3000;i++) {
    const delta=(i%80<40?1:-1)*Math.pow(2,i%14);
    r=constrainRange(37,panByPixels(r,delta,i%2?537:290));
    near(r[1]-r[0],span);
    assert.ok(r[0]>=-.5 && r[1]<=36.5);
    assert.ok(visibleWindow(37,r));
    assert.deepEqual(constrainRange(37,r),r); // idempotent: no correction loop
  }
});
test('price following uses the legal window and retains the same center rule', () => {
  const range=constrainRange(3,[20,22]);
  assert.deepEqual(range,[.5,2.5]);
  const p=priceRange({low:[1000,10,15],high:[1001,12,20]},range);
  assert.equal(p.centerIndex,1); assert.equal(p.center,11);
  near(p.range[0],1.1); near(p.range[1],20.9);
});

test('fractional category coordinates map to original rows, with earlier tie', () => {
  assert.deepEqual(visibleWindow(7, [1.2, 5.7]), {first:2,last:5,centerIndex:3});
  assert.deepEqual(visibleWindow(7, [1.5, 5.5]), {first:2,last:5,centerIndex:3});
  assert.deepEqual(visibleWindow(7, [-3.5, 1.1]), {first:0,last:1,centerIndex:0});
  assert.deepEqual(visibleWindow(7, [5.8, 9]), {first:6,last:6,centerIndex:6});
  assert.deepEqual(visibleWindow(7, [2, 2.2]), {first:2,last:2,centerIndex:2});
});
test('empty, non-finite, reversed, and fractional gaps produce no fake candle', () => {
  for (const range of [[7,9],[-3,-1],[1.1,1.9],[Infinity,3],[NaN,3],[2,1],[1,1]])
    assert.equal(visibleWindow(7,range),null);
  assert.equal(visibleWindow(0,[-.5,.5]),null);
});
test('independent hand calculation: middle wick center 11, visible extrema 8/20', () => {
  const p=priceRange({low:[8,10,15],high:[10,12,20]},[-.5,2.5]);
  assert.equal(p.centerIndex,1); assert.equal(p.center,11);
  // R=max(11-8,20-11)=9; buffer is 9.9, hence 1.1 to 20.9.
  near(p.range[0],1.1); near(p.range[1],20.9);
});
test('off-screen extremes never stretch a visible window', () => {
  const p=priceRange({low:[.001,8,10,15,1],high:[10000,10,12,20,50000]},[.5,3.5]);
  assert.equal(p.centerIndex,2); assert.equal(p.center,11);
  near(p.range[0],1.1); near(p.range[1],20.9);
});
test('visible MA expands symmetric radius while preserving the candle center', () => {
  const p=priceRange({low:[8,10,15],high:[10,12,20]},[-.5,2.5],[[5,null,30]]);
  assert.equal(p.center,11);
  // MA high=30 -> R=19, not a new center; 1.1R=20.9.
  near(p.range[0],-9.9); near(p.range[1],31.9);
});
test('single and flat candles get finite minimum span and stay centered', () => {
  const p=priceRange({low:[10],high:[10]},[-.5,.5]);
  assert.equal(p.center,10); near(p.range[0],9.978); near(p.range[1],10.022);
  assert.deepEqual(priceRange({low:[],high:[]},[-1,1]),{status:'empty'});
});
test('invalid visible OHLC blocks following instead of dropping records', () => {
  for (const [low,high] of [[null,11],[10,Infinity],[12,11],[0,1],[NaN,11]])
    assert.equal(priceRange({low:[low],high:[high]},[-.5,.5]).status,'invalid');
  assert.equal(priceRange({low:[10],high:[11]},[-.5,.5],[[Infinity]]).status,'invalid');
  assert.equal(priceRange({low:[10],high:[11]},[-.5,.5],[[null]]).status,'ok');
});
test('horizontal drag preserves width and density, independent of Y motion', () => {
  const p=panByPixels([10.25,30.25],100,500);
  assert.deepEqual(p,[6.25,26.25]);
  let r=[10.25,30.25];
  for(let i=0;i<1000;i++) r=panByPixels(r,1.2,537);
  near(r[1]-r[0],20);
  assert.equal(panByPixels(r,10,0),null);
});
test('zoom keeps the pointer anchor; subsequent pan preserves new width', () => {
  const z=zoomAt([0,20],.25,.5);
  assert.deepEqual(z,[2.5,12.5]);
  const p=panByPixels(z,-100,500);
  assert.deepEqual(p,[4.5,14.5]);
});
test('moving across rising and falling sequences follows exact wick centers', () => {
  const o={low:[8,10,12,14,12,10,8],high:[10,12,14,16,14,12,10]};
  const centers=[];
  for(let i=1;i<=5;i++) {
    const p=priceRange(o,[i-1.4,i+1.4]);
    centers.push((p.range[0]+p.range[1])/2);
    assert.equal(p.centerIndex,i);
    for(let j=p.first;j<=p.last;j++) {
      assert.ok(p.range[0]<=o.low[j]); assert.ok(p.range[1]>=o.high[j]);
    }
  }
  assert.deepEqual(centers,[11,13,15,13,11]);
});
