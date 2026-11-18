/* Price Signal: deterministic, bounded-memory VIRTUAL product generator.
 * There are 1,048,576 unique SKU IDs per family, not millions of stored records.
 * Price, reviews and specifications are fictional. Matching is rule-based,
 * not a trained LLM or statistically calibrated confidence score.
 */
'use strict';
const VIRTUAL_COUNT = 1048576;
const PAGE_SIZE = 24;
const RATES = Object.freeze({USD:1, EUR:0.92, GBP:0.79, INR:84.1, JPY:155});
const DATASETS = [
  {id:'neural', code:'NX', label:'Neural Hardware', short:'Accelerators & compute', count:VIRTUAL_COUNT, tint:'#9d8fff',
    models:[
      ['Aether Nano X6','Mobile inference accelerator','aether',369,6,18,23,32,16,82,94,'edge ai local llm mobile quiet inference compact', 'Low-profile inference module tuned for private, on-device language models.', 'INT8 48 TOPS · PCIe 4.0 · LPDDR6'],
      ['Aether Nano X12','Neural workstation card','aether',629,12,13,28,57,22,92,91,'edge ai local llm accelerator high vram workstation', 'Desktop-class tensor throughput with dual-fan thermal control.', 'INT8 116 TOPS · PCIe 5.0 · GDDR7'],
      ['Vanta Edge S8','Low-power GPU coprocessor','vanta',449,8,14,21,42,18,87,96,'quiet edge ai gpu low latency llm portable', 'Efficient eight-gigabyte coprocessor for battery-sensitive deployment.', 'FP16 34 TFLOPS · 8 GB VRAM · 42 W'],
      ['Kora Tensor M16','High-memory matrix engine','kora',899,16,10,30,78,28,96,86,'ai neural accelerator high memory vram inference', 'Memory-heavy accelerator with coherent compute scheduling.', 'INT8 210 TOPS · 16 GB VRAM · 78 W'],
      ['Helix Compute Air','Fanless neural module','helix',295,6,26,0,18,24,73,97,'quiet silent fanless edge ai mobile inference small', 'Passively cooled embedded compute module for quiet installations.', 'INT8 25 TOPS · 6 GB LPDDR · 18 W'],
      ['Orion NPU Studio','Creator inference accelerator','orion',529,10,16,25,52,24,89,92,'ai editing local llm gpu creator accelerator', 'Creator-focused inference silicon with low-jitter response.', 'INT8 80 TOPS · 10 GB · 52 W'],
      ['Flux Pocket TPU','Portable tensor co-processor','flux',199,4,32,19,11,12,65,94,'portable power efficient quiet edge inference', 'USB powered compute for compact field experiments.', 'INT8 12 TOPS · USB4 · 11 W'],
      ['Nova Stream G8','Real-time neural renderer','nova',479,8,12,27,66,18,91,89,'gpu neural streaming rendering real time gaming ai', 'Low-latency model execution optimized for real-time visual pipelines.', 'FP16 44 TFLOPS · 8 GB · 66 W']
    ]},
  {id:'gaming', code:'GX', label:'Gaming Peripherals', short:'Input & audio precision', count:VIRTUAL_COUNT, tint:'#69dfff',
    models:[
      ['Pulse Zero 8K','Wireless gaming mouse','pulse',129,0,0.35,0,6,24,95,93,'gaming mouse low latency wireless esports lightweight quiet', 'Esports-grade sensor polling with a weight-balanced carbon frame.', '8k Hz polling · 42k DPI · 52 g'],
      ['Obsidian Key 75','Magnetic gaming keyboard','obsidian',219,0,0.65,29,18,36,94,91,'gaming keyboard hall effect low latency silent quiet', 'Rapid-trigger magnetic switches with individually tunable actuation.', '8k Hz · 0.1 mm actuation · 75% layout'],
      ['Echo Rift Pro','Spatial gaming headset','echo',189,0,17,19,9,24,87,96,'gaming headset audio spatial quiet wireless low latency', 'Closed-back spatial audio with tuned voice isolation.', '96 kHz audio · 18 ms wireless · 32 h'],
      ['Spectra Glide L','Ambidextrous gaming mouse','spectra',79,0,0.8,0,3,12,84,90,'budget gaming mouse lightweight low latency value', 'Budget optical tracking with predictable micro-movement.', '4k Hz · 30k DPI · 60 g'],
      ['Vertex Pad X','Programmable macro pad','vertex',115,0,2.2,23,5,24,77,92,'gaming streaming control pad macro quiet', 'Dedicated low-profile controls for streams and creative shortcuts.', '16 keys · optical switches · 1 ms scan'],
      ['Ardent 60 HE','Compact gaming keyboard','ardent',159,0,0.4,27,11,24,91,93,'gaming compact keyboard esports low latency', 'Fast hall-effect switches in a compact travel-ready body.', '8k Hz · 0.1 mm actuation · 60%'],
      ['Riven Link 2','Wireless game controller','riven',99,0,3.5,0,5,24,86,89,'gaming controller wireless ergonomic latency', 'Adaptive trigger controller with stable wireless input telemetry.', '1k Hz · hall sticks · 40 h'],
      ['Arc Quiet TKL','Silent mechanical keyboard','arc',145,0,1.7,18,8,36,82,98,'keyboard quiet silent typing office gaming', 'Acoustically damped switches engineered for shared workspaces.', '2k Hz · gasket mount · TKL']
    ]},
  {id:'robotics', code:'RB', label:'Autonomous Robotics', short:'Drones & navigation systems', count:VIRTUAL_COUNT, tint:'#ffb983',
    models:[
      ['Strato Scout R2','Autonomous scout drone','strato',729,0,28,57,90,24,89,93,'drone autonomous aerial mapping camera robotics', 'Compact mapping platform with onboard obstacle prediction.', '48 MP · 42 min flight · 6 km navigation'],
      ['Terra Rover Mini','Indoor robotics rover','terra',479,0,24,32,52,24,83,95,'robotics autonomous rover quiet indoor mapping', 'Low-noise wheeled navigation for lab and classroom experimentation.', 'LiDAR 360° · 8 h runtime · ROS 2'],
      ['Nimbus Micro FPV','Lightweight smart drone','nimbus',299,0,19,46,38,12,78,89,'drone fpv compact lightweight aerial gaming', 'Low-profile aerial capture in constrained spaces.', '4K · 26 min flight · 2 km'],
      ['Vector Arm S4','Precision robot arm','vector',1099,0,12,42,115,36,97,92,'robotic robot arm automation precise manufacturing', 'Desktop six-axis manipulation with smooth closed-loop control.', '0.03 mm repeatability · 2 kg payload'],
      ['Echo Nav Core','Edge navigation controller','echo',259,6,8,22,14,24,88,94,'autonomous robotics edge ai navigation low latency', 'Navigation brain for local sensor fusion without cloud dependency.', 'ROS 2 · 6 GB RAM · 8 ms fusion'],
      ['Orbit Survey X','Long-range mapping drone','orbit',1399,0,22,61,135,36,94,87,'drone survey long range endurance mapping professional', 'Wide-area mapping concept with terrain-aware path selection.', '56 MP · 58 min flight · 12 km'],
      ['Mica Fleet Bot','Warehouse transport rover','mica',849,0,16,39,85,36,91,90,'robotics logistics warehouse autonomous rover', 'Modular indoor mobility concept for repetitive material transport.', '12 kg payload · 10 h · 3D depth'],
      ['Aero Whisper One','Quiet autonomous drone','aero',599,0,25,34,62,24,86,97,'quiet silent drone autonomous low noise camera', 'Low-noise inspection design with optimized propeller geometry.', '4K HDR · 36 min flight · 34 dBA']
    ]}
];
const familiesById = Object.fromEntries(DATASETS.map(d => [d.id,d]));
const TOKENS = ['carbon', 'graphite', 'arctic', 'cobalt', 'ember', 'onyx', 'silver', 'nebula'];
function hash32(x) { x = Math.imul(x ^ (x >>> 16), 0x7feb352d); x = Math.imul(x ^ (x >>> 15), 0x846ca68b); return (x ^ (x >>> 16)) >>> 0; }
function round(x, n=2){ return Number(x.toFixed(n)); }
function normalize(v){return String(v ?? '').toLowerCase().normalize('NFKD');}
function datasetIds(id){return id==='all' ? DATASETS.map(d=>d.id) : (familiesById[id] ? [id] : DATASETS.map(d=>d.id));}
function makeProduct(datasetId, index){
  const d=familiesById[datasetId];
  if(!d || !Number.isInteger(index) || index<0 || index>=d.count) return null;
  const m=d.models[index % d.models.length];
  const profile=Math.floor(index/d.models.length)%128;
  const variant=hash32(profile + (index % d.models.length)*1327 + (d.code==='GX'?4:0));
  const tier=((variant%17)-8)/150;
  const latency=Math.max(0.08,round(m[5]*(1+((profile%9)-4)/100),2));
  const price=round(m[3]*(1+tier) + (profile%5)*1.5);
  const noise=m[6]===0?0:Math.round(m[6] + (profile%7)-3);
  const power=Math.max(1,Math.round(m[7]*(1+((profile%11)-5)/100)));
  const vram=m[4];
  const sentiment=Math.min(99,Math.max(60,m[10] + (profile%9)-4));
  const rating=round(Math.min(4.9,3.5 + sentiment/95),1);
  const score=Math.max(40,Math.min(99,Math.round(m[9] + ((profile%15)-7)/2)));
  const batch=String(index).padStart(7,'0');
  const warrantyMonths=m[8];
  const warrantyTier=warrantyMonths>=36?'Premium':warrantyMonths>=24?'Extended':'Standard';
  const p95LatencyMs=round(latency*1.18,2);
  const performancePerW=round(score/power,2);
  const technicalDescription=`${m[12]} Modeled p95 latency is ${p95LatencyMs} ms at an illustrative ${power} W design envelope. ${warrantyTier} mock support covers ${warrantyMonths} months; the benchmark, review sample, power class and performance measurements are not real.`;
  const metadata={
    'neural':[['Memory',`${vram} GB`],['Latency',`${latency} ms`],['Compute',m[13].split(' · ')[0]],['Power',`${power} W`]],
    'gaming':[['Input latency',`${latency} ms`],['Noise',noise===0?'Passive':`${noise} dBA`],['Polling / signal',m[13].split(' · ')[0]],['Power',`${power} W`]],
    'robotics':[['Control latency',`${latency} ms`],['Noise',`${noise} dBA`],['Capability',m[13].split(' · ')[0]],['Power',`${power} W`]]
  };
  return {
    id:`${d.code}-${batch}`,dataset:datasetId,category:d.label,group:d.code,index,
    name:m[0],subtitle:m[1],brand:m[2].toUpperCase(),sku:`${d.code}-${m[2].toUpperCase().slice(0,3)}-${batch}`,
    priceUsd:price,latencyMs:latency,vramGb:vram,noiseDba:noise,powerW:power,performanceIndex:score,
    efficiencyIndex:Math.max(45,Math.min(99,Math.round(93 - (power/12) + (profile%9)))),
    warrantyMonths,warrantyTier,p95LatencyMs,performancePerW,technicalDescription,sentiment,rating,reviewCount:Math.floor(760+hash32(index+23)%11600),
    efficiencyTier:power<15?'A+++':power<35?'A++':power<75?'A+':'A',
    tags:m[11].split(' '),description:m[12],benchmark:m[13],specs:metadata[datasetId],
    finish:TOKENS[profile % TOKENS.length],
    note:'Fictional product, benchmark, warranty and customer sentiment. Not for purchase.'
  };
}
// Model tuple: name, subtitle, brand, USD price, VRAM, latency, noise,
// power, warranty months, performance index, sentiment, tags, description, benchmark.
const STOP=new Set(['a','an','the','me','i','my','for','and','or','find','with','at','least','than','under','below','of','a','to','in','is','want','need','show','product','products','some','good','best','please','that','has','which','give']);
function parseQuery(query, currency='USD'){
  const text=normalize(query).replace(/[,]/g,'');
  const budgetMatch=text.match(/(?:under|below|less than|max(?:imum)?|up to|within|<=)\s*(\$|€|£|₹|¥|usd|eur|gbp|inr|jpy)?\s*(\d+(?:\.\d+)?)/i);
  const mapSymbol={'$':'USD','€':'EUR','£':'GBP','₹':'INR','¥':'JPY'};
  const curr=budgetMatch ? (mapSymbol[budgetMatch[1]] || (budgetMatch[1] || currency).toUpperCase()) : currency;
  const amount=budgetMatch ? Number(budgetMatch[2]) : null;
  const budgetUsd=amount!==null && Number.isFinite(amount) && RATES[curr] ? amount / RATES[curr] : null;
  const memory=text.match(/(?:at least|min(?:imum)?|>=)\s*(\d+)\s*g(?:b|ib)\s*(?:vram|memory)?/) || text.match(/(\d+)\s*g(?:b|ib)\s*(?:vram|memory)/);
  const minVram=memory ? Math.min(Number(memory[1]),2048) : null;
  const wantsQuiet=/\b(quiet|silent|low[- ]noise|fanless|noiseless)\b/.test(text);
  const wantsLatency=/\b(low latency|low-latency|responsive|fast input|realtime|real-time|instant)\b/.test(text);
  const wantsEfficiency=/\b(efficient|efficiency|low[- ]power|battery|energy saving)\b/.test(text);
  const wantsPerformance=/\b(powerful|fastest|high performance|performance|throughput|extreme)\b/.test(text);
  const keywords=text.replace(/(?:under|below|less than|max(?:imum)?|up to|within)\s*(?:\$|€|£|₹|¥|usd|eur|gbp|inr|jpy)?\s*\d+(?:\.\d+)?/g,' ')
    .replace(/\b(?:\d+\s*(?:gb|gib|vram|usd|eur|gbp|inr|jpy))\b/g,' ')
    .split(/[^a-z0-9]+/).filter(x=>x.length>2 && !STOP.has(x)).slice(0,16);
  const explicitFamily= /\b(drone|robot|robotics|rover|navigation|aerial|survey)\b/.test(text)?'robotics':
    /\b(gaming|mouse|keyboard|headset|controller|esports|peripheral)\b/.test(text)?'gaming':
    /\b(gpu|accelerator|inference|neural|tensor|npu|llm|vram|compute)\b/.test(text)?'neural':null;
  return {query, currency:curr, budget:amount, budgetUsd, minVram, wantsQuiet,wantsLatency,wantsEfficiency,wantsPerformance,keywords,explicitFamily};
}
function scoreProduct(p,parsed){
  if(parsed.budgetUsd!==null && p.priceUsd>parsed.budgetUsd+0.0001) return null;
  if(parsed.minVram!==null && p.vramGb<parsed.minVram) return null;
  const hay=normalize(`${p.name} ${p.subtitle} ${p.description} ${p.tags.join(' ')} ${p.benchmark}`);
  const overlap=parsed.keywords.filter(t=>hay.includes(t)).length;
  const union=parsed.keywords.length;
  let score=36 + (union?Math.round(29*overlap/union):0);
  if(parsed.explicitFamily) score+=p.dataset===parsed.explicitFamily?17:-18;
  if(parsed.minVram!==null) score+=p.vramGb===parsed.minVram?11:Math.max(2,10-(p.vramGb-parsed.minVram));
  if(parsed.budgetUsd!==null) score+=6 + Math.round(4*Math.min(1,Math.max(0,(parsed.budgetUsd-p.priceUsd)/Math.max(1,parsed.budgetUsd))));
  if(parsed.wantsQuiet) score+=p.noiseDba<=24?14:p.noiseDba<=32?4:-15;
  if(parsed.wantsLatency) score+=p.latencyMs<=3?15:p.latencyMs<=17?11:p.latencyMs<=24?5:-7;
  if(parsed.wantsEfficiency) score+=Math.round((p.efficiencyIndex-70)/3);
  if(parsed.wantsPerformance) score+=Math.round((p.performanceIndex-75)/4);
  const match=Math.max(1,Math.min(99,Math.round(score)));
  return {match,matchedTerms:overlap};
}
function result(page=0, dataset='all', sort='relevance'){
  page=Math.max(0,Math.min(131071,Math.trunc(page)||0));
  const ids=datasetIds(dataset);
  const total=ids.length*VIRTUAL_COUNT;
  const offset=page*PAGE_SIZE;
  const items=[];
  for(let n=offset;n<Math.min(total,offset+PAGE_SIZE);n++){
    // Round-robin interleaving ensures that an ALL browse page displays
    // examples from all three families instead of showing only the first.
    const family=ids[n%ids.length];
    const index=Math.floor(n/ids.length);
    items.push(makeProduct(family,index));
  }
  // In browse mode sorting is page-local because the full SKU universe
  // is intentionally never materialized. Search mode ranks spec profiles.
  if(sort==='price') items.sort((a,b)=>a.priceUsd-b.priceUsd);
  else if(sort==='performance') items.sort((a,b)=>b.performanceIndex-a.performanceIndex);
  else if(sort==='efficiency') items.sort((a,b)=>b.efficiencyIndex-a.efficiencyIndex);
  return {items,total,page,pageSize:PAGE_SIZE,mode:'virtual_browse',profilesScanned:0,sortScope:'visible_page'};
}
function search(query,dataset='all',currency='USD',page=0,sort='relevance'){
  const parsed=parseQuery(query,currency);
  const candidates=[];
  const ids=datasetIds(dataset);
  let inspected=0;
  for(const family of ids){
    const d=familiesById[family];
    // Exhaustively consider all 128 spec profiles for every model family,
    // which is enough because physical SKU IDs repeat those profiles.
    for(let profile=0;profile<128;profile++){
      for(let mi=0;mi<d.models.length;mi++){
        const p=makeProduct(family,profile*d.models.length+mi);
        inspected++;
        const rank=scoreProduct(p,parsed);
        if(rank && (rank.matchedTerms>0 || !parsed.keywords.length || parsed.explicitFamily===family)) candidates.push({...p, match:rank.match, matchedTerms:rank.matchedTerms});
      }
    }
  }
  candidates.sort((a,b)=>sort==='price'?a.priceUsd-b.priceUsd || b.match-a.match:
      sort==='performance'?b.performanceIndex-a.performanceIndex || b.match-a.match:
      sort==='efficiency'?b.efficiencyIndex-a.efficiencyIndex || b.match-a.match:
      b.match-a.match || a.priceUsd-b.priceUsd);
  // Diversity cap prevents one archetype occupying all result slots.
  const counts=new Map(), ranked=[];
  for(const p of candidates){
    const key=p.dataset+':'+p.name;const used=counts.get(key)||0;
    if(used>=4) continue;
    counts.set(key,used+1);
    ranked.push(p);
  }
  page=Math.max(0,Math.min(1000,Math.trunc(page)||0));
  const total=ranked.length,offset=page*PAGE_SIZE;
  return {items:ranked.slice(offset,offset+PAGE_SIZE), total, page,pageSize:PAGE_SIZE,
    mode:'sampled_ranking',parsed,profilesScanned:inspected,virtualCount:ids.length*VIRTUAL_COUNT,
    explanation:'Rule-based scoring over every distinct specification profile; SKUs are virtual variants. Scores are not calibrated probabilities.'};
}
const workerGlobal=typeof self!=='undefined'?self:globalThis;
workerGlobal.onmessage=function(event){
  const m=event.data || {};
  const rid=m.requestId;
  try {
    let data;
    if(m.type==='metadata') data={datasets:DATASETS.map(({id,label,short,count,code,tint})=>({id,label,short,count,code,tint})),total:3*VIRTUAL_COUNT,rates:RATES};
    else if(m.type==='browse') data=result(m.page,m.dataset,m.sort);
    else if(m.type==='search') data=search(String(m.query||'').slice(0,400),m.dataset,m.currency,m.page,m.sort);
    else if(m.type==='product') data={item:makeProduct(m.dataset,Number(m.index))};
    else throw new Error('Unknown worker message');
    workerGlobal.postMessage({requestId:rid,type:m.type,...data});
  } catch (err){ workerGlobal.postMessage({requestId:rid,type:'error',error:String(err.message||err)}); }
};
