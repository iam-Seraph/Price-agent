/* Price Signal Intelligence Studio — no third-party JS, no network calls.
 * Every offer, statistic, launch date and sentiment value is simulated.
 * Matching runs in a Web Worker and never generates all virtual SKUs.
 */
'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const stat = {dataset:'all',currency:'USD',query:'',sort:'relevance',page:0,items:[],total:0,
    parsed:null, profiles:3072,selected:new Map(),advisorProduct:null,lastAdvisor:'',loading:false};
  const currencyRates={USD:1,EUR:.92,GBP:.79,INR:84.1,JPY:155};
  const datasetOrder=['all','neural','gaming','robotics'];
  const safePrefs=(key,fallback)=>{try{return localStorage.getItem(key)||fallback;}catch(_){return fallback;}};
  const savePref=(key,value)=>{try{localStorage.setItem(key,String(value));}catch(_){/* private browsing */}};
  const workerSupported=typeof Worker!=='undefined';
  const worker=workerSupported?new Worker('/static/intelligence.worker.js'):null;
  const pending=new Map();let nextRequestId=0,renderVersion=0,debounceTimer=null,toastTimer=null,telemetryTimer=null;
  const reducedMotion=window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  if(worker){
    worker.addEventListener('message',event=>{
      const msg=event.data||{};const promise=pending.get(msg.requestId);
      if(!promise) return;
      pending.delete(msg.requestId);
      if(msg.type==='error')promise.reject(new Error(msg.error||'Worker error'));
      else promise.resolve(msg);
    });
    worker.addEventListener('error',()=>{
      for(const p of pending.values())p.reject(new Error('Background engine unavailable'));
      pending.clear();
      $('result-count').textContent='Background engine unavailable. Try refreshing the page.';
    });
  }
  function askWorker(message){
    if(!worker)return Promise.reject(new Error('This browser does not support Web Workers'));
    const requestId=++nextRequestId;
    return new Promise((resolve,reject)=>{
      pending.set(requestId,{resolve,reject});
      worker.postMessage({...message,requestId});
    });
  }
  function number(x){return Number(x).toLocaleString('en-US');}
  function formatMoney(value){const c=stat.currency;return new Intl.NumberFormat('en-US',{
    style:'currency',currency:c,maximumFractionDigits:c==='JPY'?0:2,
    minimumFractionDigits:c==='JPY'?0:2
  }).format(value*(currencyRates[c]||1));}
  function svgIcon(id){const s=document.createElementNS('http://www.w3.org/2000/svg','svg');const use=document.createElementNS('http://www.w3.org/2000/svg','use');use.setAttribute('href',`#i-${id}`);s.append(use);return s;}
  function text(tag,value,cls){const e=document.createElement(tag);if(value!==undefined)e.textContent=String(value);if(cls)e.className=cls;return e;}
  function toast(message){const el=$('toast');el.textContent=message;el.classList.add('visible');clearTimeout(toastTimer);toastTimer=setTimeout(()=>el.classList.remove('visible'),3000);}
  function addLog(value){const log=$('event-log');const div=text('div');const dot=text('i');div.append(dot,document.createTextNode(value));log.prepend(div);while(log.children.length>3)log.lastElementChild.remove();}
  function setDataset(value){if(!datasetOrder.includes(value))return;stat.dataset=value;stat.page=0;
    document.querySelectorAll('[data-dataset]').forEach(el=>{
      const selected=el.dataset.dataset===value;el.classList.toggle('is-active',selected);el.setAttribute('aria-pressed',String(selected));
    });
    savePref('ps:intelligence:dataset',value);
    addLog(`Dataset switched to ${value==='all'?'unified index':value}`);
    loadProducts();
  }
  function showSearch(query){$('search-input').value=query;stat.query=query.trim();stat.page=0;loadProducts();}
  function selectCurrency(value){if(!currencyRates[value])return;stat.currency=value;$('currency').value=value;savePref('ps:intelligence:currency',value);
    stat.items.forEach((p,i)=>{const card=$('product-grid').children[i];if(card?.querySelector('.product-price'))card.querySelector('.product-price').textContent=formatMoney(p.priceUsd);});
    if(stat.query)loadProducts();
    if($('comparison-dialog').open)renderComparison();
    addLog(`Display currency changed to ${value} (mock FX)`);
  }
  // Decorative product silhouettes are authored locally: they are NOT images of real merchandise.
  const artwork={
    neural:`<svg viewBox="0 0 250 150" aria-hidden="true"><defs><linearGradient id="a" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#d4caff"/><stop offset="1" stop-color="#6d68ac"/></linearGradient></defs><g transform="translate(125 75) rotate(-14) translate(-125 -75)"><rect x="48" y="12" width="154" height="126" rx="15" fill="#191b34" stroke="#a59bed" stroke-width="2"/><rect x="75" y="35" width="100" height="82" rx="12" fill="url(#a)"/><rect x="98" y="52" width="54" height="47" rx="7" fill="#24213d"/><path d="M109 72h32M125 57v30" stroke="#d4cefb" stroke-width="5" stroke-linecap="round"/><g stroke="#857dc7" stroke-width="5"><path d="M62 5v7M90 5v7M120 5v7M150 5v7M180 5v7M62 138v7M90 138v7M120 138v7M150 138v7M180 138v7"/></g></g></svg>`,
    gaming:`<svg viewBox="0 0 250 150" aria-hidden="true"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#b1f2f5"/><stop offset="1" stop-color="#36899e"/></linearGradient></defs><g transform="translate(83 10) rotate(12 42 65)"><rect x="0" y="0" width="84" height="134" rx="42" fill="#132e3c" stroke="#77dbe8" stroke-width="2.5"/><path d="M42 1v55M3 62h78" stroke="#5bafc5" stroke-width="2"/><rect x="38" y="22" width="8" height="20" rx="4" fill="url(#g)"/><path d="M24 89h36" stroke="#79dbe5" stroke-width="4" stroke-linecap="round"/></g><ellipse cx="125" cy="137" rx="86" ry="7" fill="#4aaac7" opacity=".2"/></svg>`,
    robotics:`<svg viewBox="0 0 250 150" aria-hidden="true"><defs><linearGradient id="r" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#ffdfb6"/><stop offset="1" stop-color="#d18b5c"/></linearGradient></defs><g transform="translate(0 6)"><path d="M125 58 57 30M125 58l68-28M125 58l-68 58m68-58 68 58" stroke="#d4a378" stroke-width="9" stroke-linecap="round"/><g fill="#22212b" stroke="#f0bd8a" stroke-width="3"><circle cx="57" cy="30" r="22"/><circle cx="193" cy="30" r="22"/><circle cx="57" cy="116" r="22"/><circle cx="193" cy="116" r="22"/></g><g stroke="#ac7455" stroke-width="3"><path d="M35 30h44m-22-22v44M171 30h44m-22-22v44M35 116h44m-22-22v44M171 116h44m-22-22v44"/></g><path d="m105 45 40 0 16 28-36 20-36-20z" fill="url(#r)" stroke="#edc398" stroke-width="2"/><rect x="116" y="67" width="18" height="9" rx="4" fill="#3a3843"/></g></svg>`
  };
  function cardFor(p){
    const article=$('product-card-template').content.firstElementChild.cloneNode(true);
    article.dataset.id=p.id;
    article.classList.add(p.dataset);
    article.querySelector('.visual-category').textContent=p.group+' / '+p.category.toUpperCase();
    article.querySelector('.sku-label').textContent=p.sku;
    // Only one of three local, hard-coded SVG strings. Never render remote or user HTML here.
    article.querySelector('.product-illustration').innerHTML=artwork[p.dataset]||artwork.neural;
    article.querySelector('.product-brand').textContent=p.brand+' · '+p.finish.toUpperCase();
    const score=article.querySelector('.match-pill');
    if(Number.isFinite(p.match)){score.textContent=`${p.match}% MATCH`;score.title='Heuristic, uncalibrated match score';}
    else{score.textContent='SIMULATED';score.classList.add('no-query');}
    article.querySelector('.product-name').textContent=p.name;
    article.querySelector('.product-subtitle').textContent=p.subtitle;
    article.querySelector('.spec-one').textContent=p.specs[0]?.join(' · ');
    article.querySelector('.spec-two').textContent=p.specs[1]?.join(' · ');
    article.querySelector('.spec-three').textContent=p.specs[2]?.join(' · ');
    article.querySelector('.product-price').textContent=formatMoney(p.priceUsd);
    article.querySelector('.product-sentiment').textContent=`${p.sentiment}/100`;
    const selected=stat.selected.has(p.id);
    article.querySelector('.card-compare').classList.toggle('selected',selected);
    article.querySelector('.card-compare span').textContent=selected?'Selected':'Compare';
    return article;
  }
  function setResults(data){
    stat.items=data.items||[];stat.total=data.total||0;stat.parsed=data.parsed||null;stat.profiles=data.profilesScanned||3072;
    $('stat-profiles').textContent=number(stat.profiles);
    $('telemetry-profiles').textContent=number(stat.profiles);
    const grid=$('product-grid');const fragment=document.createDocumentFragment();
    for(const p of stat.items) fragment.append(cardFor(p));
    grid.replaceChildren(fragment);
    const isSearch=Boolean(stat.query);
    $('result-count').textContent=isSearch?
      `${number(stat.total)} ranked candidate profiles · ${number(data.profilesScanned||0)} profiles assessed`:
      `${number(stat.total)} virtual SKUs · generated ${stat.items.length} visible records`;
    $('result-description').textContent=isSearch?
      'Ranked virtual designs based on your constraints. Scores are heuristic and fictional.':
      'Browse fictional virtual SKUs. Sorting applies to the visible page only.';
    $('empty-state').hidden=stat.items.length>0;
    $('page-prev').disabled=stat.page===0;
    $('page-next').disabled=(stat.page+1)*24>=stat.total;
    $('page-label').textContent=`Page ${number(stat.page+1)}${isSearch?'':` of ${number(Math.ceil(stat.total/24))}`}`;
    if(isSearch)addLog(`Analyzed ${number(data.profilesScanned||0)} specification profiles`);
  }
  async function loadProducts(){
    const version=++renderVersion;
    stat.loading=true;
    $('result-count').textContent='Ranking specification profiles…';
    $('page-next').disabled=true;$('page-prev').disabled=true;
    try{
      const params=stat.query?{type:'search',query:stat.query,dataset:stat.dataset,currency:stat.currency,page:stat.page,sort:stat.sort}
        :{type:'browse',dataset:stat.dataset,page:stat.page,sort:stat.sort};
      const data=await askWorker(params);
      if(version!==renderVersion)return;
      setResults(data);
    }catch(err){if(version===renderVersion){$('result-count').textContent=`Could not load results: ${err.message}`;toast(err.message);}}
    finally{if(version===renderVersion)stat.loading=false;}
  }
  function toggleCompare(p){
    if(stat.selected.has(p.id)){stat.selected.delete(p.id);toast('Product removed from comparison');}
    else if(stat.selected.size>=4){toast('Up to 4 products can be compared');return;}
    else{stat.selected.set(p.id,p);toast('Added to comparison');}
    const count=stat.selected.size;
    $('compare-count').textContent=String(count);$('nav-compare-count').textContent=String(count);
    document.querySelectorAll('.product-card').forEach(card=>{
      const btn=card.querySelector('.card-compare');const yes=stat.selected.has(card.dataset.id);
      btn.classList.toggle('selected',yes);btn.querySelector('span').textContent=yes?'Selected':'Compare';
    });
    savePref('ps:intelligence:selected',[...stat.selected.keys()].join(','));
    if($('comparison-dialog').open)renderComparison();
  }
  async function restoreSelection(){
    const ids=safePrefs('ps:intelligence:selected','').split(',').filter(Boolean).slice(0,4);
    for(const id of ids){
      const match=id.match(/^(NX|GX|RB)-(\d{7})$/);
      if(!match)continue;
      const family={NX:'neural',GX:'gaming',RB:'robotics'}[match[1]];
      const data=await askWorker({type:'product',dataset:family,index:Number(match[2])});
      if(data.item)stat.selected.set(data.item.id,data.item);
    }
    const count=stat.selected.size;$('compare-count').textContent=count;$('nav-compare-count').textContent=count;
    document.querySelectorAll('.product-card').forEach(card=>{const yes=stat.selected.has(card.dataset.id);const button=card.querySelector('.card-compare');button.classList.toggle('selected',yes);button.querySelector('span').textContent=yes?'Selected':'Compare';});
  }
  function priorityScores(products,priority){
    const values=products.map(p=>p.performanceIndex/p.priceUsd);
    const maxRatio=Math.max(1e-6,...values);
    return products.map((p,i)=>{
      const value=100*values[i]/maxRatio;
      const base=priority==='performance'?p.performanceIndex:priority==='value'?value:priority==='efficiency'?p.efficiencyIndex:
        .36*p.performanceIndex+.27*p.efficiencyIndex+.17*p.sentiment+.2*value;
      return Number(base.toFixed(1));
    });
  }
  function compareAnalysis(){
    const products=[...stat.selected.values()];const priority=$('priority').value;
    const scores=priorityScores(products,priority);
    const top=scores.length?scores.indexOf(Math.max(...scores)):-1;
    return {products,priority,scores,winnerIndex:top};
  }
  function renderComparison(){
    const {products,priority,scores,winnerIndex}=compareAnalysis();
    $('comparison-empty').style.display=products.length?'none':'block';
    $('comparison-table-wrap').style.display=products.length?'block':'none';
    const body=$('comparison-body');body.replaceChildren();
    if(!products.length){$('comparison-summary').textContent='Add products from any of the three collections to generate a comparison.';return;}
    const metrics=[
      {label:'Product',get:p=>p.name,product:true},
      {label:'Illustrative price',get:p=>formatMoney(p.priceUsd),rank:p=>-p.priceUsd},
      {label:'Performance index',get:p=>`${p.performanceIndex}/100`,rank:p=>p.performanceIndex},
      {label:'Control latency',get:p=>`${p.latencyMs} ms`,rank:p=>-p.latencyMs},
      {label:'Video memory',get:p=>p.vramGb?`${p.vramGb} GB`:'Not applicable'},
      {label:'Power draw',get:p=>`${p.powerW} W`,rank:p=>-p.powerW},
      {label:'Energy tier',get:p=>p.efficiencyTier},
      {label:'Efficiency index',get:p=>`${p.efficiencyIndex}/100`,rank:p=>p.efficiencyIndex},
      {label:'Warranty tier',get:p=>`${p.warrantyTier} · ${p.warrantyMonths} months`,rank:p=>p.warrantyMonths},
      {label:'Sentiment',get:p=>`${p.sentiment}/100`,rank:p=>p.sentiment},
      {label:'Ratings (synthetic)',get:p=>`${p.rating}/5 · ${number(p.reviewCount)} reviews`},
      {label:'Value score (relative)',get:p=>`${Math.round(100*(p.performanceIndex/p.priceUsd)/Math.max(...products.map(x=>x.performanceIndex/x.priceUsd)))}/100`},
      {label:'Priority score',get:(p,i)=>`${scores[i]}/100`,rank:(p,i)=>scores[i]}
    ];
    for(const metric of metrics){
      const tr=document.createElement('tr');const th=text('th',metric.label);th.scope='row';tr.append(th);
      const ranks=metric.rank?products.map((p,i)=>metric.rank(p,i)):[];
      const best=ranks.length?Math.max(...ranks):-Infinity;
      for(let i=0;i<products.length;i++){
        const td=text('td');if(metric.product){const label=text('strong',products[i].name,'table-product-name');
          const sku=text('span',products[i].sku,'table-product-sku');
          const remove=text('button','Remove','remove-item');remove.type='button';remove.addEventListener('click',()=>toggleCompare(products[i]));
          td.append(label,sku,remove);td.classList.add('product-column');
        }else td.textContent=metric.get(products[i],i);
        if(metric.rank&&ranks[i]===best)td.classList.add('winning-cell');
        tr.append(td);
      }
      body.append(tr);
    }
    const winner=products[winnerIndex];const label=priority==='balanced'?'balanced factors':priority==='value'?'relative price-to-performance':priority==='performance'?'the invented performance index':'the invented efficiency index';
    const summary=products.length<2?`Selected ${winner.name}. Add another product to produce a relative winner.`:
      `Simulated recommendation: ${winner.name} leads on ${label} (${scores[winnerIndex]}/100). This is a fictional, rule-based ranking; cross-category benchmarks are not directly comparable. No purchase recommendation is implied.`;
    $('comparison-summary').replaceChildren(text('strong',products.length>1?'SIMULATED WINNER · ':'SINGLE SELECTION · '),document.createTextNode(summary));
  }
  function buildAdvisorProduct(product){
    const parsed=stat.parsed||{};
    const intro=text('div',undefined,'advisor-product');intro.append(text('span','LOCAL MATCH ANALYSIS','section-kicker'));
    intro.append(text('h3',product.name));intro.append(text('p',product.technicalDescription||product.description));
    intro.append(text('span',Number.isFinite(product.match)?`${product.match}% heuristic match`:'General product analysis','match-pill'));
    const section=text('section',undefined,'advisor-section');section.append(text('h4','Why this design fits'));
    const ul=text('ul');const reasons=[];
    if(parsed.minVram!=null)reasons.push(`${product.vramGb} GB memory meets the minimum ${parsed.minVram} GB constraint.`);
    if(parsed.budgetUsd!=null)reasons.push(`Illustrative USD price ${product.priceUsd.toFixed(2)} is ${product.priceUsd<=parsed.budgetUsd?'within':'outside'} the requested USD-equivalent budget of ${parsed.budgetUsd.toFixed(2)}.`);
    if(parsed.wantsQuiet)reasons.push(`Declared noise ${product.noiseDba===0?'fanless/passive':product.noiseDba+' dBA'}; this is a fictional specification, not a measurement.`);
    if(parsed.wantsLatency)reasons.push(`Simulated input/control latency: ${product.latencyMs} milliseconds.`);
    if(parsed.wantsEfficiency)reasons.push(`Simulated energy efficiency: ${product.efficiencyTier}, with a ${product.powerW} W design envelope.`);
    if(!reasons.length)reasons.push(`${product.benchmark} is the stated fictional benchmark for this prototype.`, `Illustrative performance index ${product.performanceIndex}/100 and ${product.warrantyMonths}-month sample warranty.`);
    for(const reason of reasons)ul.append(text('li',reason));section.append(ul);
    const limits=text('section',undefined,'advisor-section');limits.append(text('h4','Confidence and limitations'));
    limits.append(text('p','This is a deterministic rules engine, not an LLM. Match percentages are uncalibrated relevance scores. Customer sentiment, performance figures, pricing and inventory are synthetic. Compare only within meaningful product categories.'));
    const specs=text('section',undefined,'advisor-section');specs.append(text('h4','Technical summary'));
    specs.append(text('p',`${product.benchmark}. Power ${product.powerW} W. p95 latency ${product.p95LatencyMs} ms. Synthetic efficiency ratio ${product.performancePerW} performance-index units/W. SKU ${product.sku}. Rating ${product.rating}/5 from ${number(product.reviewCount)} generated reviews. ${product.warrantyTier} mock warranty ${product.warrantyMonths} months.`));
    return {nodes:[intro,section,specs,limits],reasons};
  }
  function openAdvisor(product){
    const p=product||stat.items[0];if(!p){toast('No product available to analyze');return;}
    stat.advisorProduct=p;const container=$('advisor-content');container.replaceChildren(...buildAdvisorProduct(p).nodes);
    stat.lastAdvisor=`# Price Signal fictional recommendation\n\nProduct: ${p.name}\nSKU: ${p.sku}\nDataset: ${p.dataset}\nIllustrative price: ${formatMoney(p.priceUsd)}\nMatch score: ${p.match??'not searched'}\n\n${buildAdvisorProduct(p).reasons.map(x=>'- '+x).join('\n')}\n\nThis report contains only synthetic products and rule-based scores.`;
    $('advisor-dialog').showModal();
  }
  function exportReport(type){
    const {products,priority,scores,winnerIndex}=compareAnalysis();
    if(!products.length){toast('Select products before exporting');return;}
    const output={title:'Price Signal Comparison (SIMULATED)',generatedAt:new Date().toISOString(),
      displayCurrency:stat.currency, exchangeRates:'Illustrative fixed demonstration rates', priority,
      products:products.map((p,i)=>({sku:p.sku,name:p.name,category:p.category,illustrativePriceUsd:p.priceUsd,performanceIndex:p.performanceIndex,efficiencyIndex:p.efficiencyIndex,latencyMs:p.latencyMs,powerW:p.powerW,warrantyMonths:p.warrantyMonths,sentiment:p.sentiment,score:scores[i]})),
      winnerSku:products.length>1?products[winnerIndex].sku:null,
      limitations:'Every product, performance metric, price, rating, warranty and sentiment value is fictional. Scores are not calibrated confidence; categories may not be comparable.'};
    const content=type==='json'?JSON.stringify(output,null,2):
      `# Price Signal — simulated product comparison\n\nGenerated: ${output.generatedAt}\nPriority: ${priority}\nCurrency: ${stat.currency} (fixed mock rates)\n\n| Product | SKU | Price | Performance | Efficiency | Score |\n|---|---|---:|---:|---:|---:|\n${products.map((p,i)=>`| ${p.name} | ${p.sku} | ${formatMoney(p.priceUsd)} | ${p.performanceIndex} | ${p.efficiencyIndex} | ${scores[i]} |`).join('\n')}\n\n${products.length>1?`Simulated winner: **${products[winnerIndex].name}**.`:'One product selected.'}\n\n**Limitation:** ${output.limitations}\n`;
    download(type==='json'?'price-signal-comparison.json':'price-signal-comparison.md',content,type==='json'?'application/json':'text/markdown');
  }
  function download(name,content,mime){
    const blob=new Blob([content],{type:mime+';charset=utf-8'});const url=URL.createObjectURL(blob);
    const link=document.createElement('a');link.href=url;link.download=name;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1500);toast('Report exported locally');
  }
  function countdown(){
    let end=Number(safePrefs('ps:intelligence:preview-date','0'));
    if(!Number.isFinite(end)||end<Date.now()-1000){end=Date.now()+28*86400000;savePref('ps:intelligence:preview-date',end);}
    function update(){const remaining=Math.max(0,Math.floor((end-Date.now())/1000));
      const d=Math.floor(remaining/86400);const h=Math.floor(remaining%86400/3600),m=Math.floor(remaining%3600/60),s=remaining%60;
      $('count-days').textContent=String(d).padStart(2,'0');$('count-hours').textContent=String(h).padStart(2,'0');$('count-minutes').textContent=String(m).padStart(2,'0');$('count-seconds').textContent=String(s).padStart(2,'0');
    }update();setInterval(()=>{if(!document.hidden)update();},1000);
  }
  function telemetry(){
    const chart=$('telemetry-chart');for(let i=0;i<30;i++)chart.append(text('span'));
    let t=0;function update(){if(document.hidden)return;
      t++;const bars=[...chart.children];bars.forEach((b,i)=>{const val=15+Math.round(62*Math.abs(Math.sin(i*.43+t*.28)+Math.cos(i*.27+t*.41)*.16));b.style.height=Math.min(100,val)+'%';});
      $('telemetry-throughput').textContent=(2.2+Math.sin(t*.27)*.45).toFixed(1)+'k';
      $('telemetry-users').textContent=number(Math.round(840+Math.sin(t*.19)*90));
    }update();telemetryTimer=setInterval(update,reducedMotion?10000:3500);
  }
  function webglParticles(){
    if(reducedMotion)return;
    const canvas=$('ambient-canvas');const hero=canvas.closest('.hero');
    let gl;try{gl=canvas.getContext('webgl2',{alpha:true,antialias:false,preserveDrawingBuffer:false,powerPreference:'low-power'});}catch(_){return;}
    if(!gl)return;
    const vs=`#version 300 es\nprecision mediump float; in vec2 aPosition;in float aSize;uniform float uTime;void main(){vec2 p=aPosition;p.y+=sin(uTime*.5+aPosition.x*8.)*.015;gl_Position=vec4(p,0.,1.);gl_PointSize=aSize;}`;
    const fs=`#version 300 es\nprecision mediump float;out vec4 outColor;void main(){float r=length(gl_PointCoord-.5);float fade=smoothstep(.5,.12,r);outColor=vec4(.78,.72,1.,fade*.42);}`;
    function shader(type,source){const s=gl.createShader(type);gl.shaderSource(s,source);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw new Error('Shader compilation failed');return s;}
    let program;try{program=gl.createProgram();const vertex=shader(gl.VERTEX_SHADER,vs),fragment=shader(gl.FRAGMENT_SHADER,fs);gl.attachShader(program,vertex);gl.attachShader(program,fragment);gl.linkProgram(program);gl.deleteShader(vertex);gl.deleteShader(fragment);if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw new Error('Shader link failed');}catch(_){return;}
    const coords=[];let seed=729372;function rnd(){seed=(Math.imul(1664525,seed)+1013904223)>>>0;return seed/4294967296;}
    for(let i=0;i<125;i++){coords.push(rnd()*2-1,rnd()*2-1,1.5+rnd()*3.3);}
    const buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(coords),gl.STATIC_DRAW);
    const position=gl.getAttribLocation(program,'aPosition'),size=gl.getAttribLocation(program,'aSize'),timeLoc=gl.getUniformLocation(program,'uTime');
    gl.enableVertexAttribArray(position);gl.vertexAttribPointer(position,2,gl.FLOAT,false,12,0);
    gl.enableVertexAttribArray(size);gl.vertexAttribPointer(size,1,gl.FLOAT,false,12,8);
    gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);
    let visible=true,frame=0,last=0,lost=false;
    const intersection=new IntersectionObserver(entries=>{visible=entries[0]?.isIntersecting??false;},{threshold:.01});intersection.observe(hero);
    function resize(){const rect=canvas.getBoundingClientRect();const dpr=Math.min(window.devicePixelRatio||1,1.5);const w=Math.max(1,Math.floor(rect.width*dpr)),h=Math.max(1,Math.floor(rect.height*dpr));if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;gl.viewport(0,0,w,h);}}
    function paint(ts){frame=requestAnimationFrame(paint);if(!visible||document.hidden||lost||ts-last<33)return;last=ts;resize();gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT);gl.useProgram(program);gl.uniform1f(timeLoc,ts/1000);gl.drawArrays(gl.POINTS,0,125);}
    canvas.addEventListener('webglcontextlost',e=>{e.preventDefault();lost=true;cancelAnimationFrame(frame);});
    canvas.addEventListener('webglcontextrestored',()=>{lost=true;/* CSS gradient remains intact. Avoid reusing stale GPU handles. */});
    frame=requestAnimationFrame(paint);
    window.addEventListener('pagehide',()=>{cancelAnimationFrame(frame);intersection.disconnect();}, {once:true});
  }
  // Accessibility and event handlers
  $('search-form').addEventListener('submit',event=>{event.preventDefault();clearTimeout(debounceTimer);showSearch($('search-input').value);});
  $('search-input').addEventListener('input',()=>{clearTimeout(debounceTimer);debounceTimer=setTimeout(()=>showSearch($('search-input').value),300);});
  document.querySelectorAll('.prompt-chip').forEach(b=>b.addEventListener('click',()=>{showSearch(b.dataset.query);$('search-input').focus();}));
  document.querySelectorAll('[data-dataset]').forEach(b=>b.addEventListener('click',()=>setDataset(b.dataset.dataset)));
  $('sort').addEventListener('change',()=>{stat.sort=$('sort').value;stat.page=0;loadProducts();});
  $('currency').addEventListener('change',()=>selectCurrency($('currency').value));
  $('page-next').addEventListener('click',()=>{if(stat.loading||stat.page*24+24>=stat.total)return;stat.page++;loadProducts();$('products-heading').scrollIntoView({behavior:reducedMotion?'instant':'smooth',block:'start'});});
  $('page-prev').addEventListener('click',()=>{if(stat.loading||stat.page===0)return;stat.page--;loadProducts();$('products-heading').scrollIntoView({behavior:reducedMotion?'instant':'smooth',block:'start'});});
  $('clear-search').addEventListener('click',()=>showSearch(''));
  $('product-grid').addEventListener('click',event=>{const btn=event.target.closest('button[data-action]');if(!btn)return;const card=btn.closest('.product-card');const p=stat.items.find(x=>x.id===card?.dataset.id);if(!p)return;
    if(btn.dataset.action==='compare')toggleCompare(p);else if(btn.dataset.action==='analyze')openAdvisor(p);
  });
  const compareDialog=$('comparison-dialog'),advisorDialog=$('advisor-dialog');
  function openComparison(){renderComparison();if(!compareDialog.open)compareDialog.showModal();}
  $('compare-trigger').addEventListener('click',openComparison);
  $('open-compare-sidebar').addEventListener('click',openComparison);
  $('ask-advisor').addEventListener('click',()=>openAdvisor());
  document.querySelectorAll('[data-close-dialog]').forEach(button=>button.addEventListener('click',()=>button.closest('dialog').close()));
  for(const dialog of [compareDialog,advisorDialog]) dialog.addEventListener('click',event=>{if(event.target===dialog)dialog.close();});
  $('priority').addEventListener('change',()=>{savePref('ps:intelligence:priority',$('priority').value);renderComparison();});
  $('clear-comparison').addEventListener('click',()=>{stat.selected.clear();savePref('ps:intelligence:selected','');$('compare-count').textContent='0';$('nav-compare-count').textContent='0';renderComparison();document.querySelectorAll('.card-compare').forEach(b=>{b.classList.remove('selected');b.querySelector('span').textContent='Compare';});toast('Comparison cleared');});
  $('export-json').addEventListener('click',()=>exportReport('json'));
  $('export-md').addEventListener('click',()=>exportReport('md'));
  $('advisor-export').addEventListener('click',()=>stat.advisorProduct?download('price-signal-advice.md',stat.lastAdvisor,'text/markdown'):toast('No recommendation to export'));
  $('waitlist-form').addEventListener('submit',event=>{event.preventDefault();const input=$('waitlist-email');if(!input.checkValidity()){input.reportValidity();return;}
    // Privacy preserving demo: do NOT store or transmit the entered email.
    savePref('ps:intelligence:preview-joined','yes');input.value='';$('waitlist-message').textContent='Local preview complete. Your email was not transmitted or saved.';toast('Preview form accepted locally — no registration sent');
  });
  document.addEventListener('keydown',event=>{
    if(event.altKey||event.ctrlKey||event.metaKey)return;
    const target=event.target;const editing=target?.matches?.('input,textarea,select,[contenteditable="true"]');
    if(event.key==='/'&&!editing&&!compareDialog.open&&!advisorDialog.open){event.preventDefault();$('search-input').focus();}
    if(editing||compareDialog.open||advisorDialog.open)return;
    if(event.key.toLowerCase()==='c'){event.preventDefault();openComparison();}
    if(event.key.toLowerCase()==='d'){event.preventDefault();setDataset(datasetOrder[(datasetOrder.indexOf(stat.dataset)+1)%datasetOrder.length]);}
  });
  async function start(){
    const oldCurr=safePrefs('ps:intelligence:currency','USD');if(currencyRates[oldCurr]){stat.currency=oldCurr;$('currency').value=oldCurr;}
    const oldDataset=safePrefs('ps:intelligence:dataset','all');if(datasetOrder.includes(oldDataset))stat.dataset=oldDataset;
    const priority=safePrefs('ps:intelligence:priority','balanced');if(['balanced','value','performance','efficiency'].includes(priority))$('priority').value=priority;
    if(safePrefs('ps:intelligence:preview-joined','')==='yes')$('waitlist-message').textContent='Local preview form was previously completed; no email was retained.';
    document.querySelectorAll('[data-dataset]').forEach(el=>{el.classList.toggle('is-active',el.dataset.dataset===stat.dataset);el.setAttribute('aria-pressed',String(el.dataset.dataset===stat.dataset));});
    countdown();telemetry();webglParticles();
    await Promise.all([loadProducts(),restoreSelection()]);
  }
  start().catch(err=>{toast('Initialization failed: '+err.message);$('result-count').textContent='Initialization failed. Refresh or use the existing data workspace.';});
})();
