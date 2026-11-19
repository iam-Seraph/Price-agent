"use strict";

const $ = (id) => document.getElementById(id);
let currentOffer = null;

async function api(path) {
  const response = await fetch(path, { cache: "no-store" });
  let body;
  try { body = await response.json(); } catch { throw new Error("Server returned invalid JSON"); }
  if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Request failed");
  return body;
}

function cell(row, value) {
  const td = document.createElement("td");
  td.textContent = String(value ?? "—");
  row.appendChild(td);
  return td;
}

function money(minor, currency) {
  if (!Number.isSafeInteger(minor) || minor < 0) return "—";
  const value = (minor / 100).toLocaleString("en-IN", {minimumFractionDigits: 2, maximumFractionDigits: 2});
  return (currency === "INR" ? "₹" : currency === "USD" ? "$" : "") + value;
}

function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString();
}

function showMessage(target, message) {
  $(target).textContent = message;
}

function drawHistory(points, currency) {
  const canvas = $("history-chart");
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  const W = canvas.width, H = canvas.height;
  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = "#172334";
  ctx.fillRect(0, 0, W, H);
  const accepted = points.filter(p => Number.isSafeInteger(p.price_minor) && p.price_minor > 0);
  if (accepted.length === 0) {
    ctx.fillStyle = "#9fb0c6";
    ctx.font = "18px system-ui";
    ctx.fillText("No stored observations for this period", 24, H / 2);
    return;
  }
  const costs = accepted.map(x => x.price_minor);
  let lo = Math.min(...costs), hi = Math.max(...costs);
  const padding = Math.max(1, Math.ceil((hi - lo) * 0.1));
  lo -= padding; hi += padding;
  const x = i => 55 + (i / Math.max(1, accepted.length - 1)) * (W - 75);
  const y = v => H - 38 - ((v - lo) / Math.max(1, hi - lo)) * (H - 70);
  ctx.strokeStyle = "#46556a"; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(55, 20); ctx.lineTo(55, H - 38); ctx.lineTo(W - 20, H - 38); ctx.stroke();
  ctx.fillStyle = "#a8bbd0"; ctx.font = "14px system-ui";
  ctx.fillText(money(hi, currency), 6, 19);
  ctx.fillText(money(Math.max(0, lo), currency), 6, H - 15);
  ctx.beginPath();
  accepted.forEach((point, i) => {
    if (i === 0) ctx.moveTo(x(i), y(point.price_minor));
    else ctx.lineTo(x(i), y(point.price_minor));
  });
  ctx.strokeStyle = "#5cd8c2"; ctx.lineWidth = 3; ctx.stroke();
  accepted.forEach((point, i) => {
    ctx.beginPath();
    ctx.arc(x(i), y(point.price_minor), point.stock === "IN_STOCK" ? 4 : 2, 0, Math.PI * 2);
    ctx.fillStyle = point.stock === "IN_STOCK" ? "#5cd8c2" : "#eab65e";
    ctx.fill();
  });
}

async function chooseOffer(offer) {
  currentOffer = offer;
  $("selection").textContent = offer.title + " — " + offer.merchant;
  $("currency").value = offer.currency;
  showMessage("decision", "Select Analyze to evaluate source-backed deal rules.");
  $("checks").replaceChildren();
  await refreshHistory();
}

async function refreshHistory() {
  if (!currentOffer) return;
  try {
    const result = await api("/api/verified/offers/" + encodeURIComponent(currentOffer.offer_id) + "/history?days=30&limit=300");
    drawHistory(result.observations, result.currency);
    $("history-text").textContent = result.observations.length + " recorded provider observations in the past 30 days. Unknown or out-of-stock prices do not qualify as genuine deal evidence.";
  } catch (error) {
    drawHistory([], currentOffer.currency);
    showMessage("history-text", error.message);
  }
}

async function renderOverview() {
  try {
    const [stats, data] = await Promise.all([api("/api/verified/status"), api("/api/verified/offers?limit=100")]);
    $("offer-count").textContent = stats.offers;
    $("observation-count").textContent = stats.observations;
    $("latest-record").textContent = formatDate(stats.last_observed_at);
    const tbody = $("offers-body");
    tbody.replaceChildren();
    for (const offer of data.offers) {
      const tr = document.createElement("tr");
      const nameCell = cell(tr, "");
      const anchor = document.createElement("a");
      anchor.textContent = offer.title;
      try {
        const link = new URL(offer.product_url);
        if (link.protocol === "https:") {
          anchor.href = link.href; anchor.target = "_blank"; anchor.rel = "noopener noreferrer";
        }
      } catch {}
      nameCell.appendChild(anchor);
      cell(tr, offer.merchant);
      cell(tr, money(offer.latest_price_minor, offer.currency));
      cell(tr, offer.stock);
      const td = document.createElement("td");
      const button = document.createElement("button");
      button.type = "button"; button.textContent = "Inspect";
      button.addEventListener("click", () => chooseOffer(offer));
      td.appendChild(button); tr.appendChild(td); tbody.appendChild(tr);
    }
    if (!data.offers.length) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 5; td.textContent = "No provider offers stored. Use the real_price_agent.py CLI after configuring a private SerpApi key.";
      tr.appendChild(td); tbody.appendChild(tr);
    }
    showMessage("overview-status", "All displayed prices come from timestamped source responses stored in SQLite.");
  } catch (error) {
    showMessage("overview-status", "Unable to load local source records: " + error.message);
  }
}

$("budget-form").addEventListener("submit", async event => {
  event.preventDefault();
  if (!currentOffer) { showMessage("decision", "Select an offer first."); return; }
  const budget = $("budget").value.trim();
  if (!/^[0-9,]+(\.[0-9]{1,2})?$/.test(budget)) {
    showMessage("decision", "Enter a valid numeric budget."); return;
  }
  try {
    const url = "/api/verified/offers/" + encodeURIComponent(currentOffer.offer_id) +
      "/analysis?budget=" + encodeURIComponent(budget) +
      "&currency=" + encodeURIComponent($("currency").value);
    const result = await api(url);
    $("decision").textContent = result.decision + " — Current price " + result.price +
      ". 30-day source samples: " + result.sample_count_30d +
      " across " + result.unique_days_30d + " days.";
    $("decision").className = result.decision === "ALERT" ? "good" : "neutral";
    const checks = $("checks"); checks.replaceChildren();
    for (const [name, ok] of Object.entries(result.checks)) {
      const li = document.createElement("li");
      li.textContent = (ok ? "PASS" : "UNVERIFIED / FAIL") + " — " + name.replaceAll("_", " ");
      li.className = ok ? "good" : "warn";
      checks.appendChild(li);
    }
  } catch (error) {
    showMessage("decision", "Analysis unavailable: " + error.message);
    $("checks").replaceChildren();
  }
});

renderOverview();



async function postAPI(path, data) {
  const response = await fetch(path, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    cache: "no-store",
    credentials: "same-origin",
    body: JSON.stringify(data || {})
  });
  let body;
  try { body = await response.json(); } catch { throw new Error("Server returned invalid JSON"); }
  if (!response.ok) {
    throw new Error(typeof body.detail === "string" ? body.detail : "Request failed");
  }
  return body;
}

function validBudget(value) {
  return /^[0-9,]+(\.[0-9]{1,2})?$/.test(value) && value.length <= 30;
}

$("search-form").addEventListener("submit", async event => {
  event.preventDefault();
  const query = $("search-query").value.trim();
  const budget = $("search-budget").value.trim();
  const currency = $("search-currency").value;
  if (query.length < 2 || query.length > 120 || !validBudget(budget)) {
    showMessage("search-status", "Use a 2–120 character query and valid positive amount.");
    return;
  }
  const submit = $("search-form").querySelector("button[type=submit]");
  submit.disabled = true;
  showMessage("search-status", "Requesting source-attributed offers…");
  try {
    const result = await postAPI("/api/verified/search", {query, budget, currency, limit: 5});
    showMessage("search-status",
      "Retrieved " + result.analyses.length + " matching offers; stored " +
      result.inserted + " new observations. Provider-reported only.");
    await renderOverview();
  } catch (error) {
    showMessage("search-status", "Search unavailable: " + error.message);
  } finally {
    submit.disabled = false;
  }
});

async function refreshWatches() {
  const tbody = $("watches-body");
  try {
    const response = await api("/api/verified/watches?limit=100");
    tbody.replaceChildren();
    for (const watch of response.watches) {
      const row = document.createElement("tr");
      cell(row, watch.query_text);
      cell(row, money(watch.budget_minor, watch.currency));
      cell(row, watch.enabled ? "Enabled (worker required)" : "Disabled");
      const actions = document.createElement("td");
      if (watch.enabled) {
        const disable = document.createElement("button");
        disable.type = "button"; disable.textContent = "Disable";
        disable.addEventListener("click", async () => {
          if (!window.confirm("Disable this price watch?")) return;
          try {
            await postAPI("/api/verified/watches/" + encodeURIComponent(watch.watch_id) + "/disable", {});
            showMessage("watch-status", "Watch disabled.");
            await refreshWatches();
          } catch (error) { showMessage("watch-status", error.message); }
        });
        actions.appendChild(disable);
        for (const channel of ["EMAIL", "TELEGRAM"]) {
          const button = document.createElement("button");
          button.type = "button"; button.textContent = "Enable " + channel;
          button.addEventListener("click", async () => {
            const description = "Enable " + channel + " alerts for " +
              watch.query_text + "? This requires private server credentials and an explicitly running delivery worker.";
            if (!window.confirm(description)) return;
            try {
              await postAPI("/api/verified/alerts/channel", {
                watch_id: watch.watch_id, channel, enabled: true, confirmed: true
              });
              showMessage("watch-status", channel + " alerts enabled. Delivery worker is not automatically started.");
            } catch (error) { showMessage("watch-status", error.message); }
          });
          actions.appendChild(button);
        }
      }
      row.appendChild(actions);
      tbody.appendChild(row);
    }
    if (response.watches.length === 0) {
      const row = document.createElement("tr"), td = document.createElement("td");
      td.colSpan = 4; td.textContent = "No saved watch queries.";
      row.appendChild(td); tbody.appendChild(row);
    }
  } catch (error) {
    showMessage("watch-status", "Watchlist unavailable: " + error.message);
  }
}

$("watch-form").addEventListener("submit", async event => {
  event.preventDefault();
  const query = $("watch-query").value.trim();
  const budget = $("watch-budget").value.trim();
  const currency = $("watch-currency").value;
  const interval_minutes = Number($("watch-interval").value);
  if (query.length < 2 || query.length > 120 || !validBudget(budget)) {
    showMessage("watch-status", "Use a valid query and numeric price threshold.");
    return;
  }
  try {
    const result = await postAPI("/api/verified/watches", {
      query, budget, currency, interval_minutes
    });
    showMessage("watch-status",
      "Watch saved: " + result.watch_id + ". Monitoring has not been started automatically.");
    await refreshWatches();
  } catch (error) {
    showMessage("watch-status", "Unable to save watch: " + error.message);
  }
});

refreshWatches();


$("compare-form").addEventListener("submit", async event => {
  event.preventDefault();
  const query = $("compare-query").value.trim();
  const budget = $("compare-budget").value.trim();
  const currency = $("compare-currency").value;
  if (query.length < 2 || query.length > 120 || !validBudget(budget)) {
    showMessage("compare-status", "Enter a valid search term and price threshold.");
    return;
  }
  const url = "/api/verified/research?q=" + encodeURIComponent(query) +
      "&budget=" + encodeURIComponent(budget) +
      "&currency=" + encodeURIComponent(currency) + "&limit=30";
  try {
    const result = await api(url);
    const rows = result.comparison.rows, tbody = $("comparison-body");
    tbody.replaceChildren();
    const byId = new Map(result.explanations.results.map(x => [x.offer_id, x]));
    for (const offer of rows) {
      const tr = document.createElement("tr");
      cell(tr, offer.title);
      cell(tr, offer.merchant);
      cell(tr, offer.price_display);
      cell(tr, offer.freshness);
      const details = byId.get(offer.offer_id);
      cell(tr, details ? details.research_class.replaceAll("_", " ") : "Unknown");
      tbody.appendChild(tr);
    }
    if (rows.length === 0) {
      const tr = document.createElement("tr"), td = document.createElement("td");
      td.colSpan = 5;
      td.textContent = "No matching source-attributed offers are stored yet.";
      tr.appendChild(td); tbody.appendChild(tr);
    }
    showMessage("compare-status", "Found " + rows.length + " source-attributed listings from " +
      result.comparison.merchant_count + " merchants. Prices are NOT guaranteed for equivalent variants.");
  } catch (error) {
    $("comparison-body").replaceChildren();
    showMessage("compare-status", "Comparison unavailable: " + error.message);
  }
});
