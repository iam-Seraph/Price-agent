'use strict';
const assert=require('node:assert/strict');
const test=require('node:test');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {performance}=require('node:perf_hooks');
const source=fs.readFileSync(path.resolve(__dirname,'../price_engine/static/intelligence.worker.js'),'utf8');
const responses=[];const self={postMessage:message=>responses.push(message)};
vm.runInNewContext(source,{self});
let seq=0;
function send(query){responses.length=0;const requestId=++seq;self.onmessage({data:{...query,requestId}});
 assert.equal(responses.length,1);const result=responses[0];assert.equal(result.requestId,requestId);assert.notEqual(result.type,'error',result.error);return result;
}
test('three virtual namespaces cover exactly 3,145,728 synthetic SKU IDs',()=>{
 const data=send({type:'metadata'});
 assert.equal(data.datasets.length,3);
 assert.equal(data.total,3145728);
 assert.ok(data.datasets.every(item=>item.count===1048576));
});
test('browsing All interleaves all dataset families and keeps only 24 records',()=>{
 const data=send({type:'browse',dataset:'all',page:0});
 assert.equal(data.items.length,24);
 assert.deepEqual(new Set(data.items.map(x=>x.dataset)),new Set(['neural','gaming','robotics']));
 assert.equal(new Set(data.items.map(x=>x.sku)).size,24);
 assert.ok(data.items.every(x=>x.priceUsd>0 && x.benchmark && x.description && x.warrantyMonths>0));
 assert.deepEqual(data.items,send({type:'browse',dataset:'all',page:0}).items);
});
test('far-page generation does not materialize the full catalog',()=>{
 const first=send({type:'browse',dataset:'neural',page:0}).items;
 const far=send({type:'browse',dataset:'neural',page:24000}).items;
 assert.equal(far.length,24);
 assert.ok(far.every(p=>p.dataset==='neural'));
 assert.ok(far.every(p=>!first.some(f=>f.id===p.id)));
 assert.ok(far.every(p=>/^NX-\d{7}$/.test(p.id)));
});
test('NL query applies hard price/VRAM constraints and returns matched entries',()=>{
 const data=send({type:'search',dataset:'all',currency:'USD',page:0,query:'quiet low-latency mobile GPU accelerator with at least 6GB VRAM under $500 for local LLM inference'});
 assert.equal(data.parsed.minVram,6);
 assert.equal(data.parsed.budgetUsd,500);
 assert.ok(data.items.length>0);
 assert.ok(data.items.every(x=>x.priceUsd<=500 && x.vramGb>=6));
 assert.equal(data.items[0].dataset,'neural');
 assert.ok(data.items.every(x=>x.match>=1 && x.match<=99));
 assert.equal(data.profilesScanned,3072);
});
test('explicit non-USD budget uses illustrative FX rates',()=>{
 const data=send({type:'search',dataset:'neural',currency:'USD',page:0,query:'accelerator below ₹20000'});
 assert.equal(data.parsed.currency,'INR');
 assert.ok(Math.abs(data.parsed.budgetUsd-20000/84.1)<0.001);
 assert.ok(data.items.every(p=>p.priceUsd<=20000/84.1));
});
test('impossible budgets return an empty result rather than made-up matches',()=>{
 const data=send({type:'search',dataset:'all',page:0,currency:'USD',query:'quiet GPU with at least 64GB VRAM under $1'});
 assert.equal(data.items.length,0);
 assert.equal(data.total,0);
});
test('browse price ordering is bounded and page-local',()=>{
 const data=send({type:'browse',dataset:'all',page:0,sort:'price'});
 assert.equal(data.sortScope,'visible_page');
 assert.ok(data.items.every((p,i)=>i===0||p.priceUsd>=data.items[i-1].priceUsd));
});
test('search finishes within a bounded processing budget',()=>{
 const start=performance.now();
 const data=send({type:'search',dataset:'all',page:0,currency:'USD',query:'lightweight gaming mouse low latency under $200'});
 const time=performance.now()-start;
 assert.ok(data.items.length>0);
 assert.ok(time<2000,`worker took ${time.toFixed(1)}ms`);
});
