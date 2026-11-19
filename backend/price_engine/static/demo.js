"use strict";
const $ = id => document.getElementById(id);
let selected = null;
let lastBudget = "4000";
let learningEnabled = false;

async function read(path) {
  const response = await fetch(path, {cache: "no-store"});
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "Local demo request failed");
  return data;
}
async function write(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    cache: "no-store",
    credentials: "same-origin",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify(payload)
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "Local demo action failed");
  return data;
}
function money(value) {
  return Number.isSafeInteger(value) ? "₹" + (value / 100).toLocaleString("en-IN", {
    minimumFractionDigits: 2, maximumFractionDigits: 2
  }) : "—";
}
function cell(tr, content) {
  const td = document.createElement("td");
  td.textContent = String(content ?? "—");
  tr.appendChild(td);
  return td;
}
function show(id, content) { $(id).textContent = content; }
function displayJSON(id, object) { $(id).textContent = JSON.stringify(object, null, 2); }
function safeBudget(value) {
  return /^[0-9,]+(\.[0-9]{1,2})?$/.test(value) && value.length <= 30;
}

async function refreshStatus() {
  try {
    const status = await read("/api/demo/status");
    show("status-products", status.counts.offers);
    show("status-samples", status.counts.prices);
    show("status-tick", status.simulated_tick);
    show("runtime-message", "OFFLINE · Fictional records only. Network requests: 0. API keys: none.");
  } catch (err) { show("runtime-message", err.message); }
}
async function refreshSearch() {
  const q = $("search-query").value.trim(), budget = $("search-budget").value.trim();
  if (q.length < 2 || q.length > 120 || !safeBudget(budget)) {
    show("search-status", "Enter a valid product name and INR budget."); return;
  }
  lastBudget = budget;
  try {
    const data = await read("/api/demo/search?q=" + encodeURIComponent(q) +
      "&budget=" + encodeURIComponent(budget));
    const tbody = $("offers-body"); tbody.replaceChildren();
    for (const offer of data.offers) {
      const tr = document.createElement("tr");
      cell(tr, offer.title); cell(tr, offer.merchant);
      cell(tr, offer.price_display); cell(tr, offer.stock);
      cell(tr, offer.preference || "Not rated");
      const td = document.createElement("td");
      const btn = document.createElement("button");
      btn.type = "button"; btn.textContent = "Inspect";
      btn.addEventListener("click", () => inspectOffer(offer));
      td.appendChild(btn); tr.appendChild(td); tbody.appendChild(tr);
    }
    if (!data.offers.length) {
      const tr = document.createElement("tr");
      const td = cell(tr, "No matching fictional products.");
      td.colSpan = 6; tbody.appendChild(tr);
    }
    const names = new Map(data.offers.map(x => [x.offer_id, x.title + " at " + x.merchant]));
    const ranked = data.personalized_offer_ids.slice(0, 5).map(id => names.get(id)).filter(Boolean);
    show("personalized-order",
      (data.learning_enabled ? "Personalized ranking: " : "Objective price ranking: ") +
      ranked.join(" • ") + " (budget-eligible first; fictional offers)");
    show("search-status", data.count + " fictional retailer listings. No network request made.");
  } catch (err) { show("search-status", err.message); }
}
function drawHistory(points) {
  const ctx = $("demo-chart").getContext("2d");
  if (!ctx) return;
  const w = ctx.canvas.width, h = ctx.canvas.height;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#172334"; ctx.fillRect(0, 0, w, h);
  if (!points.length) return;
  const vals = points.map(x => x.price_minor);
  let lo = Math.min(...vals), hi = Math.max(...vals);
  if (hi === lo) { hi++; lo--; }
  ctx.fillStyle = "#d2e8f8"; ctx.font = "15px system-ui";
  ctx.fillText("Fictional history — " + money(vals[0]) + " → " + money(vals.at(-1)), 16, 26);
  const x = i => 30 + i * (w - 55) / Math.max(points.length - 1, 1);
  const y = v => h - 24 - ((v-lo)/(hi-lo))*(h-70);
  ctx.strokeStyle = "#56e0d0"; ctx.lineWidth = 3;
  ctx.beginPath();
  points.forEach((p,i)=>{if(i===0)ctx.moveTo(x(i),y(p.price_minor));else ctx.lineTo(x(i),y(p.price_minor));});
  ctx.stroke();
}
async function inspectOffer(offer) {
  selected = offer;
  show("selected-offer", offer.title + " from " + offer.merchant + " · DEMO_FIXTURE");
  try {
    const base = "/api/demo/";
    const [history, analysis, explanation] = await Promise.all([
      read(base + "history/" + offer.offer_id),
      read(base + "analysis/" + offer.offer_id + "?budget=" + encodeURIComponent(lastBudget)),
      read(base + "explain/" + offer.offer_id + "?budget=" + encodeURIComponent(lastBudget))
    ]);
    drawHistory(history.observations);
    displayJSON("analysis-output", {
      mode: "FICTIONAL_DEMO", decision: analysis.decision,
      price: analysis.price_display, samples: analysis.sample_count,
      average_minor: analysis.average_minor, low_minor: analysis.low_minor,
      checks: analysis.checks, explanation: explanation.text, ai_model_called: false
    });
  } catch (err) { show("analysis-output", err.message); }
}
async function refreshWatches() {
  try {
    const data = await read("/api/demo/watches");
    const tbody = $("watches-body"); tbody.replaceChildren();
    for (const row of data.watches) {
      const tr = document.createElement("tr");
      cell(tr, row.query_text); cell(tr, money(row.budget_minor));
      cell(tr, row.channel.replace("SIMULATED_", ""));
      const action = document.createElement("td");
      const button = document.createElement("button");
      button.type="button"; button.textContent = row.enabled ? "Disable" : "Disabled";
      button.disabled=!row.enabled;
      button.addEventListener("click", async () => {
        try { await write("/api/demo/watch/" + row.watch_id + "/disable", {});
              await refreshWatches(); } catch(err){show("watch-status",err.message);}
      });
      action.appendChild(button); tr.appendChild(action); tbody.appendChild(tr);
    }
  } catch(err) { show("watch-status",err.message); }
}
async function refreshAlerts() {
  try {
    const data = await read("/api/demo/alerts");
    const body = $("alerts-body"); body.replaceChildren();
    for (const item of data.alerts) {
      const tr = document.createElement("tr");
      cell(tr,item.title); cell(tr,money(item.price_minor));
      cell(tr,item.channel.replace("SIMULATED_","")); cell(tr,item.status);
      body.appendChild(tr);
    }
  } catch(err) { show("watch-status",err.message); }
}
async function refreshLearning() {
  try {
    const state = await read("/api/demo/learning");
    learningEnabled = state.enabled;
    show("learning-status",
      (state.enabled ? "Enabled" : "Disabled") + " · " +
      state.count + " saved fictional-offer preferences. No model retraining.");
  } catch(err){show("learning-status",err.message);}
}
async function refreshCatalog() {
  try {
    const data = await read("/api/demo/catalog");
    const body = $("catalog-body"); body.replaceChildren();
    for (const row of data.products) {
      const tr = document.createElement("tr");
      cell(tr,row.name); cell(tr,row.retailer);
      cell(tr, "₹" + row.price.toLocaleString("en-IN"));
      cell(tr, Object.entries(row.specs || {}).slice(0,2).map(([k,v])=>k+": "+v).join(" • "));
      body.appendChild(tr);
    }
  } catch(err){show("runtime-message",err.message);}
}
$("search-form").addEventListener("submit",event=>{event.preventDefault();refreshSearch();});
$("watch-form").addEventListener("submit",async event=>{
  event.preventDefault();
  const q=$("watch-query").value.trim(), budget=$("watch-budget").value.trim();
  if(q.length<2||!safeBudget(budget)){show("watch-status","Enter a valid watch and budget.");return;}
  if(!window.confirm("Save a watch for fictional prices? No real notifications will be sent."))return;
  try {
    const result=await write("/api/demo/watch",{
      query:q,budget,channel:$("watch-channel").value,confirmed:true
    });
    show("watch-status","Saved fictional watch "+result.watch_id+".");
    await refreshWatches(); await refreshStatus();
  } catch(err){show("watch-status",err.message);}
});
$("poll-run").addEventListener("click",async()=>{
  try {
    const result=await write("/api/demo/poll",{confirmed:true});
    show("watch-status","Updated "+result.offers_updated+" simulated offers, queued "+
      result.queued_simulated_alerts+" fake alerts. Zero network requests.");
    await Promise.all([refreshStatus(),refreshAlerts(),refreshSearch()]);
  } catch(err){show("watch-status",err.message);}
});
$("dispatch-run").addEventListener("click",async()=>{
  try {
    const result=await write("/api/demo/dispatch",{confirmed:true});
    show("watch-status",result.simulated_sent+" simulated delivery receipts. ZERO real messages.");
    await refreshAlerts();
  } catch(err){show("watch-status",err.message);}
});
$("learning-on").addEventListener("click",async()=>{
  if(!window.confirm("Enable local demo offer preferences?"))return;
  try{await write("/api/demo/learning",{enabled:true,confirmed:true});
    await refreshLearning(); await refreshSearch();}catch(err){show("feedback-status",err.message);}
});
$("learning-off").addEventListener("click",async()=>{
  try{await write("/api/demo/learning",{enabled:false,confirmed:true});
    await refreshLearning(); await refreshSearch();}catch(err){show("feedback-status",err.message);}
});
$("learning-clear").addEventListener("click",async()=>{
  if(!window.confirm("Erase all fictional-offer feedback and disable local learning?"))return;
  try{await write("/api/demo/clear",{confirmed:true});
    await refreshLearning(); await refreshSearch();}catch(err){show("feedback-status",err.message);}
});
for (const [id,preference] of [["prefer-selected","PREFER"],["avoid-selected","AVOID"]]){
  $(id).addEventListener("click",async()=>{
    if(!selected){show("feedback-status","Select a product first.");return;}
    try{
      await write("/api/demo/feedback",{offer_id:selected.offer_id,preference});
      show("feedback-status","Saved "+preference+" for "+selected.title+" (demo only).");
      await refreshLearning();await refreshSearch();
    }catch(err){show("feedback-status",err.message);}
  });
}
$("forget-selected").addEventListener("click",async()=>{
  if(!selected){show("feedback-status","Select a product first.");return;}
  try{await write("/api/demo/forget",{offer_id:selected.offer_id});
    show("feedback-status","Local vote removed.");await refreshLearning();await refreshSearch();
  }catch(err){show("feedback-status",err.message);}
});
$("assistant-form").addEventListener("submit",async event=>{
  event.preventDefault();
  const command=$("assistant-command").value.trim();
  try {
    let result=await write("/api/demo/assistant",{command,confirmed:false});
    if(result.status==="CONFIRMATION_REQUIRED"&&window.confirm(
      "Create this watch only in the fictional demo database?")){
      result=await write("/api/demo/assistant",{command,confirmed:true});
    }
    displayJSON("assistant-output",result);
    await refreshWatches();
  }catch(err){show("assistant-output",err.message);}
});
$("audit-run").addEventListener("click",async()=>{
  try{displayJSON("runtime-details",await read("/api/demo/diagnostics"));}
  catch(err){show("runtime-details",err.message);}
});
$("config-run").addEventListener("click",async()=>{
  try{displayJSON("runtime-details",await read("/api/demo/config"));}
  catch(err){show("runtime-details",err.message);}
});
Promise.all([refreshStatus(),refreshSearch(),refreshWatches(),
             refreshAlerts(),refreshLearning(),refreshCatalog()]);
